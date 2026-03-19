#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Team Task Queue System - Task Queue Manager

This module implements the TaskQueue class for managing tasks with dependency support.
Uses file-based storage with atomic file locking for task claiming.
"""

import os
import json
import time
import uuid
from typing import List, Optional, Set, Dict, Any

try:
    from .models import Task, LoopGroup
except ImportError:
    from models import Task, LoopGroup


class TaskQueue:
    """
    任务队列管理器
    - 文件存储，无数据库依赖
    - 支持 blockedBy 依赖声明
    - 动态计算可用任务
    - Windows兼容：使用 msvcrt 进行文件锁定
    """

    def __init__(self, team_id: str, base_dir: str):
        """初始化任务队列
        
        Args:
            team_id: 团队/会话唯一标识
            base_dir: 基础存储目录
        """
        self.team_id = team_id
        self.tasks_dir = os.path.join(base_dir, "tasks", team_id)
        self.locks_dir = os.path.join(self.tasks_dir, "locks")
        self.lock_file = os.path.join(self.tasks_dir, ".lock")

        # 确保目录存在
        os.makedirs(self.tasks_dir, exist_ok=True)
        os.makedirs(self.locks_dir, exist_ok=True)

    def _get_task_path(self, task_id: str) -> str:
        """获取任务文件的完整路径"""
        return os.path.join(self.tasks_dir, f"{task_id}.json")

    def _get_lock_path(self, task_id: str) -> str:
        """获取任务锁文件的完整路径"""
        return os.path.join(self.locks_dir, f"{task_id}.lock")

    def _acquire_file_lock(self, lock_file) -> bool:
        """获取文件锁（非阻塞）
        
        Windows使用msvcrt，Unix使用fcntl
        
        Args:
            lock_file: 已打开的文件对象
            
        Returns:
            True 如果成功获取锁，False 如果被占用
        """
        import sys
        if sys.platform == 'win32':
            import msvcrt
            try:
                # Windows: 使用非阻塞锁定
                # LK_NBLCK = 非阻塞独占锁
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                # 文件被其他进程锁定
                return False
        else:
            import fcntl
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except BlockingIOError:
                return False

    def _release_file_lock(self, lock_file):
        """释放文件锁
        
        Args:
            lock_file: 已打开的文件对象
        """
        import sys
        if sys.platform == 'win32':
            import msvcrt
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except IOError:
                pass

    # === 任务 CRUD ===

    def create_task(
        self,
        name: str,
        description: str = "",
        blocked_by: List[str] = None,
        expected_artifacts: List[str] = None,
        writable_files: List[str] = None,
        read_only_files: List[str] = None,
        verification_commands: List[str] = None
    ) -> Task:
        """创建新任务
        
        Args:
            name: 任务名称
            description: 任务详细描述
            blocked_by: 依赖的任务ID列表
            expected_artifacts: 期望产出的文件路径列表
            writable_files: 可写文件路径列表
            read_only_files: 只读文件路径列表
            verification_commands: 验收命令列表
            
        Returns:
            新创建的任务对象
        """
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        task = Task(
            id=task_id,
            name=name,
            description=description,
            blocked_by=blocked_by or [],
            expected_artifacts=expected_artifacts or [],
            writable_files=writable_files or [],
            read_only_files=read_only_files or [],
            verification_commands=verification_commands or []
        )

        # 更新阻塞关系：将当前任务添加到被依赖任务的 blocks 列表
        if task.blocked_by:
            for blocked_id in task.blocked_by:
                blocked_task = self.get_task(blocked_id)
                if blocked_task:
                    if task_id not in blocked_task.blocks:
                        blocked_task.blocks.append(task_id)
                        self._save_task(blocked_task)

        self._save_task(task)
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务对象，如果不存在则返回 None
        """
        path = self._get_task_path(task_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return Task.from_json(json.load(f))
        except (json.JSONDecodeError, IOError):
            return None

    def list_tasks(self, status: str = None) -> List[Task]:
        """列出所有任务
        
        Args:
            status: 可选的状态过滤 (pending/in_progress/completed)
            
        Returns:
            任务列表，按创建时间排序
        """
        tasks = []
        if not os.path.exists(self.tasks_dir):
            return tasks

        for filename in os.listdir(self.tasks_dir):
            if filename.endswith('.json') and filename != '.lock':
                path = os.path.join(self.tasks_dir, filename)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        task = Task.from_json(json.load(f))
                        if status is None or task.status == status:
                            tasks.append(task)
                except (json.JSONDecodeError, IOError):
                    continue

        return sorted(tasks, key=lambda t: t.created_at)

    # === 可用性计算 ===

    def _get_completed_ids(self) -> Set[str]:
        """获取所有已完成的任务ID"""
        return {t.id for t in self.list_tasks(status="completed")}

    def get_available_tasks(self, agent_id: str = None) -> List[Task]:
        """
        获取当前可认领的任务（去中心化自协调核心方法）

        规则：
        1. status == "pending"
        2. blocked_by 为空 或 所有依赖已完成
        3. owner == None (未被认领)

        Args:
            agent_id: 可选，过滤当前 agent 已认领的任务

        Returns:
            按 created_at 排序的可认领任务列表
        """
        completed = self._get_completed_ids()
        available = []

        for task in self.list_tasks(status="pending"):
            # 跳过已被认领的任务
            if task.owner is not None:
                continue
            # 检查依赖是否都满足
            if not task.blocked_by:
                available.append(task)
            elif all(dep_id in completed for dep_id in task.blocked_by):
                available.append(task)

        # 按创建时间排序（先创建的任务优先）
        return sorted(available, key=lambda t: t.created_at)

    # === 原子性任务认领 ===

    def claim_task(self, task_id: str, agent_id: str) -> bool:
        """
        原子性认领任务（文件锁）
        
        Args:
            task_id: 要认领的任务ID
            agent_id: 认领者agent_id
            
        Returns:
            True = 成功认领
            False = 已被抢走或不可认领
        """
        lock_path = self._get_lock_path(task_id)
        task_path = self._get_task_path(task_id)

        # 确保锁文件存在
        open(lock_path, 'a').close()

        try:
            with open(lock_path, 'r+') as lock_file:
                # 尝试获取文件锁
                if not self._acquire_file_lock(lock_file):
                    return False

                try:
                    # 重新读取任务状态（防止其他进程已修改）
                    if not os.path.exists(task_path):
                        return False

                    with open(task_path, 'r', encoding='utf-8') as tf:
                        task = Task.from_json(json.load(tf))

                    # 检查是否可认领
                    if task.status != "pending":
                        return False

                    completed = self._get_completed_ids()
                    if task.blocked_by and not all(d in completed for d in task.blocked_by):
                        return False

                    # 原子性更新
                    task.status = "in_progress"
                    task.owner = agent_id

                    with open(task_path, 'w', encoding='utf-8') as tf:
                        json.dump(task.to_json(), tf, ensure_ascii=False, indent=2)

                    return True

                finally:
                    self._release_file_lock(lock_file)

        except (IOError, OSError):
            return False

    def complete_task(self, task_id: str) -> bool:
        """标记任务完成
        
        Args:
            task_id: 要完成的任务ID
            
        Returns:
            True 如果成功，False 如果任务不存在
        """
        task = self.get_task(task_id)
        if not task:
            return False

        task.status = "completed"
        task.completed_at = time.time()
        self._save_task(task)

        # 清理锁文件
        lock_path = self._get_lock_path(task_id)
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except OSError:
                pass

        return True

    def _save_task(self, task: Task):
        """保存任务到文件
        
        Args:
            task: 要保存的任务对象
        """
        path = self._get_task_path(task.id)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(task.to_json(), f, ensure_ascii=False, indent=2)

    def delete_task(self, task_id: str) -> bool:
        """删除任务
        
        Args:
            task_id: 要删除的任务ID
            
        Returns:
            True 如果成功删除，False 如果不存在
        """
        path = self._get_task_path(task_id)
        if not os.path.exists(path):
            return False

        try:
            os.remove(path)
            # 清理锁文件
            lock_path = self._get_lock_path(task_id)
            if os.path.exists(lock_path):
                os.remove(lock_path)
            return True
        except OSError:
            return False

    def get_task_stats(self) -> dict:
        """获取任务统计信息
        
        Returns:
            包含各状态任务数量的字典
        """
        all_tasks = self.list_tasks()
        return {
            "total": len(all_tasks),
            "pending": len([t for t in all_tasks if t.status == "pending"]),
            "in_progress": len([t for t in all_tasks if t.status == "in_progress"]),
            "completed": len([t for t in all_tasks if t.status == "completed"])
        }

    # ========== 循环组管理 (新增) ==========

    def _get_loop_groups_dir(self) -> str:
        """获取循环组存储目录"""
        return os.path.join(self.tasks_dir, "..", "loop_groups")

    def _get_loop_group_path(self, loop_id: str) -> str:
        """获取循环组文件路径"""
        loop_dir = self._get_loop_groups_dir()
        return os.path.join(loop_dir, f"{loop_id}.json")

    def create_loop_group(
        self,
        name: str,
        max_iterations: int = 5,
        exit_condition: str = "true"
    ) -> "LoopGroup":
        """创建循环组
        
        Args:
            name: 循环组名称
            max_iterations: 最大迭代次数
            exit_condition: 退出条件表达式
            
        Returns:
            新创建的循环组对象
        """
        try:
            from .models import LoopGroup
        except ImportError:
            from models import LoopGroup

        loop_id = f"loop-{uuid.uuid4().hex[:8]}"
        loop_group = LoopGroup(
            id=loop_id,
            name=name,
            max_iterations=max_iterations,
            exit_condition=exit_condition
        )
        
        # 确保目录存在
        loop_dir = self._get_loop_groups_dir()
        os.makedirs(loop_dir, exist_ok=True)
        
        self._save_loop_group(loop_group)
        return loop_group

    def get_loop_group(self, loop_id: str) -> Optional["LoopGroup"]:
        """获取循环组
        
        Args:
            loop_id: 循环组 ID
            
        Returns:
            循环组对象，如果不存在则返回 None
        """
        try:
            from .models import LoopGroup
        except ImportError:
            from models import LoopGroup

        path = self._get_loop_group_path(loop_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return LoopGroup.from_json(json.load(f))
        except (json.JSONDecodeError, IOError):
            return None

    def list_loop_groups(self, status: str = None) -> List["LoopGroup"]:
        """列出所有循环组
        
        Args:
            status: 可选的状态过滤
            
        Returns:
            循环组列表
        """
        try:
            from .models import LoopGroup
        except ImportError:
            from models import LoopGroup

        loop_dir = self._get_loop_groups_dir()
        if not os.path.exists(loop_dir):
            return []

        loop_groups = []
        for filename in os.listdir(loop_dir):
            if filename.endswith('.json'):
                path = os.path.join(loop_dir, filename)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        lg = LoopGroup.from_json(json.load(f))
                        if status is None or lg.status == status:
                            loop_groups.append(lg)
                except (json.JSONDecodeError, IOError):
                    continue
        
        return loop_groups

    def _save_loop_group(self, loop_group: "LoopGroup"):
        """保存循环组到文件"""
        path = self._get_loop_group_path(loop_group.id)
        loop_dir = os.path.dirname(path)
        os.makedirs(loop_dir, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(loop_group.to_json(), f, ensure_ascii=False, indent=2)

    def add_task_to_loop(
        self,
        loop_group_id: str,
        task_id: str,
        is_gate: bool = False
    ) -> bool:
        """将任务添加到循环组
        
        Args:
            loop_group_id: 循环组 ID
            task_id: 任务 ID
            is_gate: 是否为 gate 任务
            
        Returns:
            True 如果成功
        """
        loop_group = self.get_loop_group(loop_group_id)
        if not loop_group:
            return False

        task = self.get_task(task_id)
        if not task:
            return False

        # 更新任务
        task.task_type = "gate" if is_gate else "loop"
        task.loop_group_id = loop_group_id
        self._save_task(task)

        # 更新循环组
        if task_id not in loop_group.task_ids:
            loop_group.task_ids.append(task_id)
        if is_gate:
            loop_group.gate_task_id = task_id
        self._save_loop_group(loop_group)

        return True

    def get_loop_group_tasks(self, loop_group_id: str) -> List[Task]:
        """获取循环组内的所有任务
        
        Args:
            loop_group_id: 循环组 ID
            
        Returns:
            任务列表
        """
        loop_group = self.get_loop_group(loop_group_id)
        if not loop_group:
            return []
        
        tasks = []
        for task_id in loop_group.task_ids:
            task = self.get_task(task_id)
            if task:
                tasks.append(task)
        return tasks

    def update_loop_group_status(
        self,
        loop_group_id: str,
        status: str,
        exit_result: dict = None
    ):
        """更新循环组状态
        
        Args:
            loop_group_id: 循环组 ID
            status: 新状态
            exit_result: 退出结果
        """
        loop_group = self.get_loop_group(loop_group_id)
        if loop_group:
            loop_group.status = status
            if exit_result:
                loop_group.exit_result = exit_result
            if status == "completed":
                loop_group.completed_at = time.time()
            self._save_loop_group(loop_group)

    def is_loop_group_ready(self, loop_group_id: str) -> bool:
        """检查循环组是否就绪（所有依赖都已满足）
        
        Args:
            loop_group_id: 循环组 ID
            
        Returns:
            True 如果循环组就绪
        """
        loop_group = self.get_loop_group(loop_group_id)
        if not loop_group:
            return False
        
        if loop_group.status not in ("pending", "running"):
            return False

        completed = self._get_completed_ids()
        for task_id in loop_group.task_ids:
            task = self.get_task(task_id)
            if not task:
                continue
            # 检查任务的外部依赖是否都满足
            for dep_id in task.blocked_by:
                if dep_id not in completed:
                    return False
        
        return True

    def get_ready_loop_groups(self) -> List["LoopGroup"]:
        """获取所有就绪的循环组
        
        Returns:
            循环组列表
        """
        return [
            lg for lg in self.list_loop_groups()
            if self.is_loop_group_ready(lg.id) and lg.status != "completed"
        ]

    def complete_loop_iteration(self, loop_group_id: str):
        """完成一次循环迭代
        
        Args:
            loop_group_id: 循环组 ID
        """
        loop_group = self.get_loop_group(loop_group_id)
        if not loop_group:
            return

        loop_group.current_iteration += 1
        
        # 重置组内任务的迭代状态（为下一次迭代做准备）
        for task_id in loop_group.task_ids:
            task = self.get_task(task_id)
            if task:
                task.iteration_status = "pending"
                task.status = "pending"
                self._save_task(task)
        
        self._save_loop_group(loop_group)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Agent Team Loop Executor - 循环执行引擎

支持：
- 循环组 (Loop Group) 的迭代执行
- 混合 DAG (普通任务 + 循环组)
- 条件退出 (exit_condition)
- 多并行循环组

【使用方式】

```python
import sys
sys.path.insert(0, 'skills/agent_team_to_be_update')

from task_queue import TaskQueue
from loop_executor import LoopExecutor

# 初始化
queue = TaskQueue(team_id="ml_training", base_dir="./temp")
executor = LoopExecutor(queue)

# 创建循环组
loop = executor.create_loop_group(
    name="ML Training",
    max_iterations=10,
    exit_condition="accuracy >= 0.95"
)

# 添加任务到循环组
task_train = queue.create_task(name="训练模型", blocked_by=[])
task_eval = queue.create_task(name="评估模型", blocked_by=[])
task_gate = queue.create_task(name="检查准确率", blocked_by=[])

executor.add_task_to_loop(loop.id, task_train.id)
executor.add_task_to_loop(loop.id, task_eval.id)
executor.add_task_to_loop(loop.id, task_gate.id, is_gate=True)

# 执行混合 DAG
executor.execute_mixed_dag()
```
"""

import re
import time
import random
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass, field

try:
    from .models import Task, LoopGroup, LoopState
    from .task_queue import TaskQueue
except ImportError:
    from models import Task, LoopGroup, LoopState
    from task_queue import TaskQueue


class LoopExecutor:
    """循环执行引擎
    
    负责执行混合 DAG，包括普通任务和循环组。
    """

    def __init__(self, queue: TaskQueue):
        """初始化执行器
        
        Args:
            queue: TaskQueue 实例
        """
        self.queue = queue
        
        # 任务执行回调 (可选)
        self.task_executor: Optional[Callable[[Task], Dict[str, Any]]] = None
        
        # 执行统计
        self.stats = {
            "total_iterations": 0,
            "completed_loops": 0,
            "failed_loops": 0,
            "regular_tasks_completed": 0
        }

    def set_task_executor(self, executor: Callable[[Task], Dict[str, Any]]):
        """设置任务执行回调
        
        Args:
            executor: 接收 Task，返回执行结果 dict
        """
        self.task_executor = executor

    def create_loop_group(
        self,
        name: str,
        max_iterations: int = 5,
        exit_condition: str = "true"
    ) -> LoopGroup:
        """创建循环组
        
        Args:
            name: 循环组名称
            max_iterations: 最大迭代次数
            exit_condition: 退出条件表达式
            
        Returns:
            新创建的循环组
        """
        return self.queue.create_loop_group(
            name=name,
            max_iterations=max_iterations,
            exit_condition=exit_condition
        )

    def add_task_to_loop(
        self,
        loop_group_id: str,
        task_id: str,
        is_gate: bool = False
    ):
        """将任务添加到循环组
        
        Args:
            loop_group_id: 循环组 ID
            task_id: 任务 ID
            is_gate: 是否为 gate 任务
        """
        self.queue.add_task_to_loop(loop_group_id, task_id, is_gate)

    def create_and_add_loop_group(
        self,
        name: str,
        task_defs: List[Dict[str, Any]],
        max_iterations: int = 5,
        exit_condition: str = "true"
    ) -> LoopGroup:
        """创建循环组并添加任务 (便捷方法)
        
        Args:
            name: 循环组名称
            task_defs: 任务定义列表 [{"name": "...", "blocked_by": [...], ...}]
            max_iterations: 最大迭代次数
            exit_condition: 退出条件
            
        Returns:
            新创建的循环组
        """
        # 创建循环组
        loop_group = self.create_loop_group(name, max_iterations, exit_condition)
        
        # 跟踪任务 ID
        name_to_id = {}
        created_tasks = []
        
        # 创建所有任务
        for task_def in task_defs:
            blocked_by_ids = []
            for dep_name in task_def.get("blocked_by", []):
                if dep_name in name_to_id:
                    blocked_by_ids.append(name_to_id[dep_name])
            
            task = self.queue.create_task(
                name=task_def["name"],
                description=task_def.get("description", ""),
                blocked_by=blocked_by_ids,
                expected_artifacts=task_def.get("expected_artifacts", []),
                writable_files=task_def.get("writable_files", []),
                read_only_files=task_def.get("read_only_files", [])
            )
            name_to_id[task_def["name"]] = task.id
            created_tasks.append(task)
        
        # 添加到循环组
        for task in created_tasks:
            is_gate = task_defs[len(created_tasks) - 1].get("is_gate", False)
            self.add_task_to_loop(loop_group.id, task.id, is_gate)
        
        return loop_group

    def _execute_task(self, task: Task, iteration: int = 0) -> Dict[str, Any]:
        """执行单个任务
        
        Args:
            task: 任务对象
            iteration: 当前迭代次数
            
        Returns:
            执行结果
        """
        if self.task_executor:
            return self.task_executor(task)
        
        # 默认模拟执行
        time.sleep(0.1)
        
        result = {"success": True}
        
        # Gate 任务生成模拟评估结果
        if task.task_type == "gate":
            accuracy = random.uniform(0.5, 0.99)
            result = {
                "accuracy": accuracy,
                "passed": accuracy >= 0.95
            }
        
        return result

    def _check_exit_condition(
        self,
        result: Dict[str, Any],
        condition: str
    ) -> bool:
        """检查退出条件
        
        支持的格式:
        - "accuracy >= 0.95"
        - "loss < 0.01"
        - "true" (无条件退出)
        
        Args:
            result: 任务执行结果
            condition: 退出条件表达式
            
        Returns:
            True 如果满足退出条件
        """
        condition = condition.strip()
        
        if condition.lower() == "true":
            return True
        
        # 解析简单表达式
        pattern = r'(\w+)\s*(>=|<=|>|<|==|!=)\s*([\d.]+)'
        match = re.match(pattern, condition)
        
        if match:
            metric, op, threshold_str = match.groups()
            value = result.get(metric, 0)
            threshold = float(threshold_str)
            
            ops = {
                '>=': lambda a, b: a >= b,
                '<=': lambda a, b: a <= b,
                '>': lambda a, b: a > b,
                '<': lambda a, b: a < b,
                '==': lambda a, b: a == b,
                '!=': lambda a, b: a != b,
            }
            return ops[op](value, threshold)
        
        return False

    def execute_loop_iteration(
        self,
        loop_group_id: str,
        iteration: int,
        worker_id: str = "loop-executor"
    ) -> LoopState:
        """执行一次循环迭代
        
        Args:
            loop_group_id: 循环组 ID
            iteration: 迭代次数 (1-based)
            worker_id: 执行者 ID
            
        Returns:
            循环状态
        """
        loop_group = self.queue.get_loop_group(loop_group_id)
        if not loop_group:
            raise ValueError(f"Loop group not found: {loop_group_id}")

        state = LoopState(
            iteration=iteration,
            max_iterations=loop_group.max_iterations,
            loop_group_id=loop_group_id
        )

        print(f"\n    {'='*50}")
        print(f"    Loop '{loop_group.name}' - Iteration {iteration}/{loop_group.max_iterations}")
        print(f"    {'='*50}")

        # 执行组内所有任务
        tasks = self.queue.get_loop_group_tasks(loop_group_id)
        
        for task in tasks:
            # 更新任务迭代信息
            task.iteration = iteration
            task.iteration_status = "in_progress"
            task.status = "in_progress"
            self.queue._save_task(task)
            
            print(f"    [{worker_id}] {task.name} (iter {iteration})")
            
            # 执行任务
            result = self._execute_task(task, iteration)
            task.loop_exit_result = result
            self.queue._save_task(task)
            
            # 如果是 gate 任务，检查退出条件
            if task.task_type == "gate":
                print(f"    [Gate] Result: {result}")
                
                if self._check_exit_condition(result, loop_group.exit_condition):
                    state.exit_condition_met = True
                    state.exit_message = f"条件满足: {result}"
                    state.exit_result = result
                    print(f"    [Gate] Exit condition MET! Stopping loop.")
                else:
                    print(f"    [Gate] Exit condition NOT met. Will continue...")
            
            # 标记任务完成
            task.iteration_status = "completed"
            task.status = "completed"
            self.queue._save_task(task)
            
            state.completed_task_ids.append(task.id)

        # 检查是否达到最大迭代
        if not state.exit_condition_met:
            if iteration >= loop_group.max_iterations:
                state.exit_condition_met = True
                state.exit_message = f"达到最大迭代: {loop_group.max_iterations}"
                print(f"    [Loop] Max iterations reached ({loop_group.max_iterations})")

        # 更新循环组状态
        loop_group.current_iteration = iteration
        if state.exit_condition_met:
            loop_group.status = "completed"
            loop_group.exit_result = state.exit_result
            loop_group.completed_at = time.time()
            self.queue._save_loop_group(loop_group)
            print(f"    [Loop] Completed: {state.exit_message}")
        else:
            loop_group.status = "running"
            self.queue._save_loop_group(loop_group)
            # 重置任务状态，准备下一次迭代
            self.queue.complete_loop_iteration(loop_group_id)

        self.stats["total_iterations"] += 1
        
        return state

    def execute_mixed_dag(
        self,
        max_waves: int = 100,
        worker_prefix: str = "worker"
    ) -> Dict[str, Any]:
        """执行混合 DAG (普通任务 + 循环组)
        
        执行流程:
        1. 获取就绪的普通任务
        2. 获取就绪的循环组
        3. 执行普通任务 (可并行)
        4. 执行循环组迭代
        5. 重复直到全部完成
        
        Args:
            max_waves: 最大波次限制
            worker_prefix: Worker 前缀
            
        Returns:
            执行统计信息
        """
        print("\n" + "=" * 60)
        print("开始执行混合 DAG")
        print("=" * 60)

        wave = 0
        worker_count = 0

        while wave < max_waves:
            wave += 1
            print(f"\n{'='*60}")
            print(f"Wave {wave}")
            print(f"{'='*60}")

            # 1. 获取就绪的普通任务
            ready_tasks = self.queue.get_available_tasks()
            
            # 2. 获取就绪的循环组
            ready_loops = self.queue.get_ready_loop_groups()
            
            if not ready_tasks and not ready_loops:
                # 检查是否全部完成
                all_tasks = self.queue.list_tasks()
                all_loops = self.queue.list_loop_groups()
                
                pending_tasks = [t for t in all_tasks if t.status == "pending"]
                running_tasks = [t for t in all_tasks if t.status == "in_progress"]
                pending_loops = [lg for lg in all_loops if lg.status in ("pending", "running")]
                
                if not pending_tasks and not running_tasks and not pending_loops:
                    print("\n所有任务已完成!")
                    break
                
                # 有任务在进行中或有循环组在运行，等待
                time.sleep(0.1)
                continue

            # 3. 执行就绪的普通任务
            for i, task in enumerate(ready_tasks):
                worker_id = f"{worker_prefix}-{i}"
                if self.queue.claim_task(task.id, worker_id):
                    print(f"\n  [{worker_id}] 执行: {task.name}")
                    try:
                        result = self._execute_task(task)
                        self.queue.complete_task(task.id)
                    except Exception as e:
                        print(f"  [{worker_id}] 任务 {task.id} 执行异常: {e}")
                        self.queue.fail_task(task.id)
                    self.stats["regular_tasks_completed"] += 1

            # 4. 执行就绪的循环组
            for loop_group in ready_loops:
                # 如果循环组还没开始，启动它
                if loop_group.status == "pending":
                    loop_group.status = "running"
                    self.queue._save_loop_group(loop_group)
                
                # 计算下一次迭代
                next_iteration = loop_group.current_iteration + 1
                
                # 执行一次迭代
                state = self.execute_loop_iteration(
                    loop_group.id,
                    next_iteration,
                    f"loop-{loop_group.name}"
                )
                
                if state.exit_condition_met:
                    self.stats["completed_loops"] += 1
                    print(f"\n  Loop '{loop_group.name}' finished: {state.exit_message}")

        # 最终统计
        stats = self.queue.get_task_stats()
        loop_stats = {
            "total": len(self.queue.list_loop_groups()),
            "completed": len([lg for lg in self.queue.list_loop_groups() if lg.status == "completed"]),
            "running": len([lg for lg in self.queue.list_loop_groups() if lg.status == "running"]),
        }
        
        final_stats = {
            "waves": wave,
            "tasks": stats,
            "loops": loop_stats,
            "executor": self.stats
        }
        
        print("\n" + "=" * 60)
        print("执行完成!")
        print("=" * 60)
        print(f"  总波次: {wave}")
        print(f"  任务: {stats['completed']}/{stats['total']} 完成")
        print(f"  循环组: {loop_stats['completed']}/{loop_stats['total']} 完成")
        print(f"  总迭代次数: {self.stats['total_iterations']}")
        
        return final_stats

    def get_execution_summary(self) -> Dict[str, Any]:
        """获取执行摘要
        
        Returns:
            包含任务和循环组状态的摘要
        """
        tasks = self.queue.list_tasks()
        loops = self.queue.list_loop_groups()
        
        return {
            "tasks": {
                "total": len(tasks),
                "by_status": {
                    status: len([t for t in tasks if t.status == status])
                    for status in ["pending", "in_progress", "completed"]
                },
                "loops": {
                    status: len([t for t in tasks if t.task_type == status])
                    for status in ["regular", "loop", "gate"]
                }
            },
            "loops": {
                "total": len(loops),
                "by_status": {
                    status: len([lg for lg in loops if lg.status == status])
                    for status in ["pending", "running", "completed", "failed"]
                }
            }
        }


def demo_task_executor(task: Task) -> Dict[str, Any]:
    """演示用的任务执行器
    
    Args:
        task: 任务对象
        
    Returns:
        执行结果
    """
    import time
    import random
    
    # 模拟执行时间
    time.sleep(random.uniform(0.1, 0.3))
    
    # Gate 任务返回评估结果
    if task.task_type == "gate":
        accuracy = random.uniform(0.6, 0.99)
        return {
            "accuracy": accuracy,
            "passed": accuracy >= 0.95,
            "threshold": 0.95
        }
    
    return {"success": True, "output": f"Result of {task.name}"}

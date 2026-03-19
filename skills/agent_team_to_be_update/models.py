#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Team Task Queue System - Data Models

This module defines the data models for the task queue system,
including the Task dataclass with all required fields for dependency management
and loop/iteration support.
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Task:
    """任务数据模型
    
    用于表示一个可分配、可执行的任务单元，支持依赖关系声明和循环迭代。
    """
    id: str  # 任务唯一ID
    name: str  # 任务名称
    description: str  # 详细描述
    status: str = "pending"  # pending / in_progress / completed
    owner: Optional[str] = None  # 当前认领者 (agent_id)
    blocked_by: List[str] = field(default_factory=list)  # 依赖的任务ID列表
    blocks: List[str] = field(default_factory=list)  # 被这个任务阻塞的任务
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    # 产物信息
    expected_artifacts: List[str] = field(default_factory=list)  # 期望产出文件
    verification_commands: List[str] = field(default_factory=list)  # 验收命令

    # 文件边界（防止冲突）
    writable_files: List[str] = field(default_factory=list)  # 可写文件
    read_only_files: List[str] = field(default_factory=list)  # 只读文件

    # ========== 循环/迭代相关字段 (新增) ==========
    task_type: str = "regular"  # "regular" | "loop" | "gate"
    loop_group_id: Optional[str] = None  # 所属循环组 ID
    iteration: int = 0  # 当前迭代次数 (0 = 未开始)
    iteration_status: str = "pending"  # "pending" | "in_progress" | "completed" | "skipped"
    max_iterations: int = 5  # 最大迭代次数
    exit_condition: Optional[str] = None  # 退出条件 (e.g., "accuracy >= 0.95")
    loop_exit_result: Optional[Dict[str, Any]] = None  # 循环退出时的结果

    def to_json(self) -> dict:
        """将任务转换为JSON字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "owner": self.owner,
            "blockedBy": self.blocked_by,
            "blocks": self.blocks,
            "createdAt": self.created_at,
            "completedAt": self.completed_at,
            "expectedArtifacts": self.expected_artifacts,
            "verificationCommands": self.verification_commands,
            "writableFiles": self.writable_files,
            "readOnlyFiles": self.read_only_files,
            # Loop fields
            "taskType": self.task_type,
            "loopGroupId": self.loop_group_id,
            "iteration": self.iteration,
            "iterationStatus": self.iteration_status,
            "maxIterations": self.max_iterations,
            "exitCondition": self.exit_condition,
            "loopExitResult": self.loop_exit_result
        }

    @classmethod
    def from_json(cls, data: dict) -> "Task":
        """从JSON字典创建任务实例 (增加蛇形和驼峰双向兼容)"""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            status=data.get("status", "pending"),
            owner=data.get("owner"),
            blocked_by=data.get("blockedBy", []) or data.get("blocked_by", []),
            blocks=data.get("blocks", []) or data.get("blocks", []),
            created_at=data.get("createdAt", time.time()) or data.get("created_at", time.time()),
            completed_at=data.get("completedAt") or data.get("completed_at"),
            expected_artifacts=data.get("expectedArtifacts", []) or data.get("expected_artifacts", []),
            verification_commands=data.get("verificationCommands", []) or data.get("verification_commands", []),
            writable_files=data.get("writableFiles", []) or data.get("writable_files", []),
            read_only_files=data.get("readOnlyFiles", []) or data.get("read_only_files", []),
            # Loop fields
            task_type=data.get("taskType", "regular") or data.get("task_type", "regular"),
            loop_group_id=data.get("loopGroupId") or data.get("loop_group_id"),
            iteration=data.get("iteration", 0) if "iteration" in data else data.get("iteration", 0),
            iteration_status=data.get("iterationStatus", "pending") or data.get("iteration_status", "pending"),
            max_iterations=data.get("maxIterations", 5) if "maxIterations" in data else data.get("max_iterations", 5),
            exit_condition=data.get("exitCondition") or data.get("exit_condition"),
            loop_exit_result=data.get("loopExitResult") or data.get("loop_exit_result")
        )

    def is_available(self, completed_ids: set) -> bool:
        """检查任务是否可用（所有依赖都已完成）
        
        Args:
            completed_ids: 已完成任务的ID集合
            
        Returns:
            True 如果任务可以被认领
        """
        if not self.blocked_by:
            return True
        return all(dep_id in completed_ids for dep_id in self.blocked_by)

    def can_be_claimed(self) -> bool:
        """检查任务是否可以被认领
        
        Returns:
            True 如果任务状态为 pending
        """
        return self.status == "pending"

    def mark_in_progress(self, agent_id: str):
        """标记任务为进行中"""
        self.status = "in_progress"
        self.owner = agent_id

    def mark_completed(self):
        """标记任务为已完成"""
        self.status = "completed"
        self.completed_at = time.time()


@dataclass
class LoopGroup:
    """循环组数据模型
    
    用于表示一组需要迭代执行的任务。
    """
    id: str  # 唯一标识
    name: str  # 名称
    max_iterations: int = 5  # 最大迭代次数
    exit_condition: str = "true"  # 退出条件表达式
    current_iteration: int = 0  # 当前迭代次数
    status: str = "pending"  # pending/running/completed/failed
    task_ids: List[str] = field(default_factory=list)  # 组内任务 ID
    gate_task_id: Optional[str] = None  # Gate 任务 ID (用于判断退出)
    exit_result: Optional[Dict[str, Any]] = None  # 退出时的结果
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def to_json(self) -> dict:
        """转换为 JSON"""
        return {
            "id": self.id,
            "name": self.name,
            "maxIterations": self.max_iterations,
            "exitCondition": self.exit_condition,
            "currentIteration": self.current_iteration,
            "status": self.status,
            "taskIds": self.task_ids,
            "gateTaskId": self.gate_task_id,
            "exitResult": self.exit_result,
            "createdAt": self.created_at,
            "completedAt": self.completed_at
        }

    @classmethod
    def from_json(cls, data: dict) -> "LoopGroup":
        """从 JSON 创建"""
        return cls(
            id=data["id"],
            name=data["name"],
            max_iterations=data.get("maxIterations", 5),
            exit_condition=data.get("exitCondition", "true"),
            current_iteration=data.get("currentIteration", 0),
            status=data.get("status", "pending"),
            task_ids=data.get("taskIds", []),
            gate_task_id=data.get("gateTaskId"),
            exit_result=data.get("exitResult"),
            created_at=data.get("createdAt", time.time()),
            completed_at=data.get("completedAt")
        )

    def is_completed(self) -> bool:
        """检查循环组是否已完成"""
        return self.status in ("completed", "failed")

    def is_running(self) -> bool:
        """检查循环组是否正在运行"""
        return self.status == "running"

    def should_continue(self) -> bool:
        """检查是否应该继续迭代"""
        if self.status == "completed":
            return False
        if self.current_iteration >= self.max_iterations:
            return False
        return True


@dataclass
class LoopState:
    """循环执行状态
    
    跟踪循环组在一次执行中的状态。
    """
    iteration: int  # 当前迭代 (1-based)
    max_iterations: int  # 最大迭代
    loop_group_id: str  # 循环组 ID
    completed_task_ids: List[str] = field(default_factory=list)  # 已完成的任务
    exit_condition_met: bool = False  # 是否满足退出条件
    exit_message: str = ""  # 退出原因
    exit_result: Optional[Dict[str, Any]] = None  # 退出结果

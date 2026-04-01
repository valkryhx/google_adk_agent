#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Team Config Management for Agent Team.

Manages the team config.json file (team membership registry).
Provides agent registration, discovery, and lifecycle management.
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class TeamMember:
    """团队成员数据模型

    Attributes:
        name: 成员名称（唯一标识）
        agent_id: Agent 完整ID（如 worker_8001@my-project）
        agent_type: Agent 类型（leader/general-purpose）
        port: Agent 运行的端口号
        role: 角色描述
        status: 当前状态（active/idle/busy/shutdown_requested/shutdown/error）
        joined_at: 加入时间戳
        metadata: 额外元数据
    """
    name: str
    agent_id: str
    agent_type: str
    port: int
    role: str = ""
    status: str = "active"
    joined_at: float = field(default_factory=time.time)
    metadata: Optional[Dict] = None

    def to_json(self) -> dict:
        """将成员转换为JSON字典"""
        result = {
            "name": self.name,
            "agentId": self.agent_id,
            "agentType": self.agent_type,
            "port": self.port,
            "role": self.role,
            "status": self.status,
            "joinedAt": self.joined_at
        }
        if self.metadata is not None:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_json(cls, data: dict) -> "TeamMember":
        """从JSON字典创建成员实例"""
        return cls(
            name=data["name"],
            agent_id=data["agentId"],
            agent_type=data["agentType"],
            port=data.get("port", 0),
            role=data.get("role", ""),
            status=data.get("status", "active"),
            joined_at=data.get("joinedAt", time.time()),
            metadata=data.get("metadata")
        )


class TeamConfig:
    """
    团队配置管理器

    负责：
    - 创建/加载团队配置
    - 注册/注销团队成员
    - 查询团队成员列表
    - 管理成员状态

    使用文件系统存储，config.json 格式：
    {
        "teamName": "my-project",
        "teamId": "team-xyz",
        "createdAt": 1710815900.0,
        "members": [
            {"name": "leader", "agentId": "...", "agentType": "leader", ...},
            {"name": "worker_8001", "agentId": "...", "agentType": "general-purpose", ...}
        ]
    }
    """

    def __init__(self, team_id: str, base_dir: str, team_name: str = None):
        """
        初始化团队配置管理器

        Args:
            team_id: 团队唯一标识
            base_dir: 基础目录路径
            team_name: 团队显示名称（默认为 team_id）
        """
        self.team_id = team_id
        self.team_name = team_name or team_id
        self.config_dir = os.path.join(base_dir, "coordination")
        self.config_file = os.path.join(self.config_dir, "config.json")

        # 确保目录存在
        os.makedirs(self.config_dir, exist_ok=True)

        # 如果配置文件不存在，初始化
        if not os.path.exists(self.config_file):
            self._init_config()

    def _init_config(self):
        """初始化新的配置文件"""
        data = {
            "teamName": self.team_name,
            "teamId": self.team_id,
            "createdAt": time.time(),
            "members": []
        }
        self._write_config(data)

    def _read_config(self) -> dict:
        """读取配置文件

        Returns:
            配置字典，如果文件不存在返回空配置
        """
        if not os.path.exists(self.config_file):
            return {
                "teamName": self.team_name,
                "teamId": self.team_id,
                "createdAt": time.time(),
                "members": []
            }
        with open(self.config_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _write_config(self, data: dict):
        """写入配置文件

        Args:
            data: 要写入的配置字典
        """
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def register_member(self, member: TeamMember) -> bool:
        """注册新成员

        Args:
            member: 要注册的团队成员

        Returns:
            True 如果注册成功，False 如果成员已存在
        """
        config = self._read_config()

        # 检查是否已存在同名成员
        for existing in config.get("members", []):
            if existing["name"] == member.name:
                return False

        # 添加新成员
        config["members"].append(member.to_json())
        self._write_config(config)
        return True

    def unregister_member(self, name: str) -> bool:
        """注销成员

        Args:
            name: 要注销的成员名称

        Returns:
            True 如果成功注销，False 如果成员不存在
        """
        config = self._read_config()
        original_len = len(config.get("members", []))

        # 过滤掉指定成员
        config["members"] = [
            m for m in config.get("members", [])
            if m["name"] != name
        ]

        if len(config["members"]) < original_len:
            self._write_config(config)
            return True
        return False

    def update_member_status(self, name: str, status: str) -> bool:
        """更新成员状态

        Args:
            name: 成员名称
            status: 新状态（active/idle/busy/shutdown_requested/shutdown/error）

        Returns:
            True 如果更新成功，False 如果成员不存在
        """
        config = self._read_config()

        for member in config.get("members", []):
            if member["name"] == name:
                member["status"] = status
                self._write_config(config)
                return True

        return False

    def get_member(self, name: str) -> Optional[TeamMember]:
        """获取指定成员

        Args:
            name: 成员名称

        Returns:
            TeamMember 实例，如果不存在返回 None
        """
        config = self._read_config()

        for member_data in config.get("members", []):
            if member_data["name"] == name:
                return TeamMember.from_json(member_data)

        return None

    def get_all_members(self) -> List[TeamMember]:
        """获取所有成员

        Returns:
            所有团队成员的列表
        """
        config = self._read_config()
        return [
            TeamMember.from_json(m)
            for m in config.get("members", [])
        ]

    def get_active_members(self) -> List[TeamMember]:
        """获取活跃成员

        Returns:
            状态为 "active" 的成员列表
        """
        return [m for m in self.get_all_members() if m.status == "active"]

    def get_worker_members(self) -> List[TeamMember]:
        """获取所有 Worker 成员（非 Leader）

        Returns:
            agent_type 不为 "leader" 的成员列表
        """
        return [m for m in self.get_all_members() if m.agent_type != "leader"]

    def get_leader(self) -> Optional[TeamMember]:
        """获取 Leader 成员

        Returns:
            agent_type 为 "leader" 的成员，如果没有返回 None
        """
        for member in self.get_all_members():
            if member.agent_type == "leader":
                return member
        return None

"""
SkillManager - 技能懒加载管理器

负责解析 SKILL.md 文件，实现两阶段懒加载：
1. 发现阶段：仅提取 name 和 description
2. 执行阶段：按需加载完整 Instructions 内容
"""

import os
import yaml
from typing import Tuple, Optional, List, Dict, Any


class SkillManager:
    """技能管理器：实现 SKILL.md 的懒解析"""

    def __init__(self, base_path: str = "./.claude/skills"):
        """
        初始化技能管理器
        
        Args:
            base_path: 技能目录的基础路径
        """
        self.base_path = base_path

    def _parse_file(self, skill_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        内部逻辑：将 SKILL.md 文件拆分为 Meta (Frontmatter) 和 Body
        
        Args:
            skill_id: 技能标识符（目录名）
            
        Returns:
            (meta_dict, body_string) 元组，解析失败时返回 (None, None)
        """
        path = os.path.join(self.base_path, skill_id, "SKILL.md")
        if not os.path.exists(path):
            return None, None

        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 按 '---' 分割，期望格式：
            # ---
            # frontmatter
            # ---
            # body
            parts = content.split('---', 2)
            if len(parts) < 3:
                return None, None

            meta = yaml.safe_load(parts[1])
            body = parts[2].strip()
            return meta, body
        except Exception as e:
            print(f"[SkillManager] 解析技能 {skill_id} 时出错: {e}")
            return None, None

    def get_discovery_manifests(self) -> str:
        """
        【懒加载 - 阶段 1】仅提取 name 和 description 用于路由发现
        
        这个方法在 Agent 初始化时调用，只返回最少的信息，
        让 Agent 知道有哪些技能可用，而不加载完整的执行指令。
        
        Returns:
            YAML 格式的技能清单字符串
        """
        manifests: List[Dict[str, Any]] = []
        
        if not os.path.exists(self.base_path):
            return "[]"
            
        for skill_id in os.listdir(self.base_path):
            skill_path = os.path.join(self.base_path, skill_id)
            if not os.path.isdir(skill_path):
                continue
                
            meta, _ = self._parse_file(skill_id)
            if meta:
                # 严格只保留这两个字段，节省初始化 Token
                manifests.append({
                    "id": skill_id,
                    "name": meta.get("name"),
                    "description": meta.get("description")
                })
                
        return yaml.dump(manifests, allow_unicode=True, default_flow_style=False)

    def load_full_sop(self, skill_id: str) -> str:
        """
        【懒加载 - 阶段 2】根据 skill_id 读取完整的正文内容
        
        只有当 Agent 决定使用某个技能时才调用此方法，
        此时才会加载完整的 Instructions（标准操作流程）。
        
        Args:
            skill_id: 技能标识符
            
        Returns:
            技能的完整 Instructions 内容
        """
        _, body = self._parse_file(skill_id)
        return body if body else "无法加载技能详情。"

    def list_skills(self) -> List[str]:
        """
        列出所有可用的技能 ID
        
        Returns:
            技能 ID 列表
        """
        if not os.path.exists(self.base_path):
            return []
            
        return [
            skill_id for skill_id in os.listdir(self.base_path)
            if os.path.isdir(os.path.join(self.base_path, skill_id))
        ]

    def skill_exists(self, skill_id: str) -> bool:
        """
        检查技能是否存在
        
        Args:
            skill_id: 技能标识符
            
        Returns:
            技能是否存在
        """
        path = os.path.join(self.base_path, skill_id, "SKILL.md")
        return os.path.exists(path)

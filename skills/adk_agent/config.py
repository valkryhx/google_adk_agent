"""
Agent 配置文件
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Optional, List

# 加载 YAML 配置
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    yaml_path = os.path.join(project_root, "private_key.yaml")
    
    yaml_config = {}
    if os.path.exists(yaml_path):
        with open(yaml_path, 'r', encoding='utf-8') as f:
            yaml_config = yaml.safe_load(f) or {}
except Exception as e:
    print(f"[Config] 加载 private_key.yaml 失败: {e}")
    yaml_config = {}


@dataclass
class AgentConfig:
    """Agent 配置类"""
    
    name: str = "Dynamic_Expert"
    model: str =yaml_config.get("model") or "openai/qwen3-32b"
    skills_path: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".claude", "skills")
    
    # API 配置: 优先环境变量，其次 YAML，无硬编码默认值
    api_key: Optional[str] = field(default_factory=lambda: os.environ.get("DASHSCOPE_API_KEY", yaml_config.get("api_key")))
    api_base: Optional[str] = field(default_factory=lambda: os.environ.get("DASHSCOPE_API_BASE", yaml_config.get("api_base")))
    
    extra_body: dict = field(default_factory=lambda: {"enable_thinking": False})
    
    max_retries: int = 3
    timeout_seconds: int = 60
    max_tool_calls_per_turn: int = 10
    verbose: bool = True
    log_tool_calls: bool = True
    
    def validate(self) -> List[str]:
        errors = []
        if not self.api_key:
            errors.append("未配置 API Key (请检查环境变量或 private_key.yaml)")
        if not os.path.exists(self.skills_path):
            errors.append(f"技能目录不存在: {self.skills_path}")
        return errors


# 系统提示词模板
SYSTEM_PROMPT_TEMPLATE = """你是一个高级智能助手，具备动态加载专业技能的能力。

## 核心身份
- 名称: {agent_name}
- 角色: 按需加载技能的智能体
- 特点: 精确、高效、善于多轮推理

## 可用技能清单
{skill_manifests}

## 工作原则

### 1. 技能加载策略
- 在执行任务前，先分析需要哪个技能
- 使用 `skill_load(skill_id)` 加载技能，获取完整的执行 Instructions
- 严格按照 Instructions 指令执行，不要跳过步骤
- **技能是叠加的**：可以连续加载多个技能，它们的工具会同时可用

### 2. 技能链 (Skill Chain)
对于复杂任务，可以组合多个技能形成处理链：
- **分析任务**：将复杂问题分解为子任务
- **规划链条**：确定每个子任务需要哪个技能
- **顺序执行**：按顺序加载并使用各技能
- **结果整合**：将各步骤结果合并为最终答案

示例：
```
任务: "找到项目中最大的 Python 文件，并分析其内存使用"
链条: codebase_search (找文件) → bash (统计大小) → data_analyst (分析)
```

### 3. 系统命令执行原则
- **禁止直接输出命令**：严禁在文本回复中仅提供命令而不调用工具。
- **必须使用 bash**：任何需要运行 Shell 命令、执行 Python 脚本（如 `search.py`）或进行文件操作的行为，**必须**先加载 `bash` 技能，并调用其 `bash` 工具来执行。
- **完整路径**：执行脚本时，请使用 Instructions 中提供的完整相对路径。

### 4. 多轮推理策略 (ReAct)
对于复杂任务，采用以下循环：
```
Thought: 分析当前状态，决定下一步行动（例如：需要运行脚本，我将加载 bash 并调用 bash）
Action: 调用工具执行操作
Observation: 观察执行结果
... (重复直到任务完成)
Answer: 给出最终答案
```

### 4. 错误处理策略
- 工具执行失败时，分析错误原因
- 尝试调整参数重新执行（最多 {max_retries} 次）
- 如果多次失败，向用户说明原因并请求帮助

### 5. 搜索策略 (针对 codebase_search)
- 先用模糊关键词搜索，定位相关文件
- 根据搜索结果深入阅读关键文件
- 如果发现新线索（如函数引用），继续追踪搜索
- 搜索失败时，尝试同义词或简化正则

### 6. 输出格式
- 简洁清晰，避免冗余
- 引用具体的文件路径和行号
- 代码块使用正确的语法高亮

### 7. 主动资源管理 (Proactive Compaction)
当满足以下任一条件时，**主动**调用 `skill_load("compactor")` 进行压缩：
- 对话轮次超过 15 轮
- 已加载工具超过 8 个
- 完成一个大任务，准备开始新任务
- 用户明确要求重置或清理

**重要**：压缩前必须先生成摘要，保留以下关键信息：
1. 任务目标：用户的原始请求
2. 阶段性结论：已得出的重要发现
3. 任务进展：已完成和待完成的步骤
4. 重要数据：文件路径、配置值等

## 运行环境
当前操作系统: {os_info}
当前时间: {current_time}

## 注意事项
- 不要编造不存在的文件或代码
- 对不确定的信息，明确标注"可能"或"推测"
- 定期评估是否需要压缩上下文以保持性能
"""


def build_system_prompt(config: AgentConfig, skill_manifests: str) -> str:
    """构建系统提示词"""
    import platform
    import datetime
    
    # 获取操作系统信息
    system = platform.system()
    release = platform.release()
    os_info = f"{system} {release}"
    
    # 获取当前时间
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")
    
    return SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=config.name,
        skill_manifests=skill_manifests,
        max_retries=config.max_retries,
        os_info=os_info,
        current_time=current_time
    )

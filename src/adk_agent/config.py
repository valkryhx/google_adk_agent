"""
Agent 配置文件
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Optional, List
import platform

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
    
    name: str = "Ciri"#"Dynamic_Expert"
    
    # 优先从环境变量获取 active_model，其次从 YAML 获取，默认为原有值
    active_model: str = field(default_factory=lambda: os.environ.get("ACTIVE_MODEL", "阿里-通义-Qwen3-32B"))
    
    def __post_init__(self):
        # 初始化时也加载一次
        # 如果 active_model 没有被外部强行指定，则从磁盘加载
        disk_data = self.load_from_disk()
        if not os.environ.get("ACTIVE_MODEL"):
            self.active_model = disk_data.get("active_model", self.active_model)

    def load_from_disk(self) -> dict:
        """实时从磁盘加载 YAML 配置"""
        try:
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[Config] 重新加载 private_key.yaml 失败: {e}")
        return {}

    # model 现作为真实的物理模型 ID 获取器
    @property
    def model(self) -> str:
        # 1. 优先使用用户在当前会话中手动通过 Setter 设置的内存值
        if hasattr(self, "_mem_model") and self._mem_model:
            return self._mem_model
            
        # 2. 从 llm_configs 中当前激活的标签下获取
        configs = self.llm_configs
        if self.active_model in configs:
            m = configs[self.active_model].get("model")
            if m: return m
        # 3. 兜底：将 active_model 视为物理模型 ID
        return self.active_model

    @model.setter
    def model(self, value: str):
        # 仅更新内存中的物理模型 ID，不干扰 active_model 标签
        self._mem_model = value
        # 同时为了持久化能找到位置，我们甚至可以考虑在更新时同步更新 llm_configs (内存中)

    skills_path: str = os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")), "skills")
    
    # 获取 llm_configs
    @property
    def llm_configs(self) -> dict:
        # 为了支持热加载，直从磁盘重新读取
        return self.load_from_disk().get("llm_configs", {})
    
    # API 配置改为动态属性，支持 Setter 以实现内存热更新
    _api_key: Optional[str] = field(default=None, repr=False)
    _api_base: Optional[str] = field(default=None, repr=False)

    @property
    def api_key(self) -> Optional[str]:
        # 1. 优先使用 Setter 设置的内存值，但要过滤掉脱敏掩码
        ak = self._api_key
        if ak and "..." not in ak and "*" not in ak:
            return ak
            
        # 2. 如果内存中是掩码或为空，则从磁盘/环境变量加载真实值
        real_key = self._get_active_config("api_key")
        return real_key

    @api_key.setter
    def api_key(self, value: Optional[str]):
        self._api_key = value

    @property
    def api_base(self) -> Optional[str]:
        # 如果内存里有非空值，优先用内存的
        if self._api_base: return self._api_base
        return self._get_active_config("api_base")

    @api_base.setter
    def api_base(self, value: Optional[str]):
        self._api_base = value
    
    def _get_active_config(self, key: str) -> Optional[str]:
        """根据当前的 active_model 获取对应的配置项 (api_key/api_base)"""
        # 1. 检查环境变量 (LLM_API_KEY, LLM_API_BASE)
        env_val = os.environ.get(f"LLM_{key.upper()}")
        if env_val: return env_val
        
        # 2. 从层级配置 llm_configs 中根据 active_model 获取
        disk_data = self.load_from_disk()
        configs = disk_data.get("llm_configs", {})
        
        if self.active_model in configs:
            val = configs[self.active_model].get(key)
            if val: 
                # [DEBUG] 追踪密钥查找
                if "key" in key:
                    print(f"[Config] 🔑 成功从节点 [{self.active_model}] 获取 {key} (长度: {len(val)})")
                return val
            
        # 3. 兜底：从顶层获取
        fallback_val = disk_data.get(key)
        if fallback_val and "key" in key:
            print(f"[Config] 🔑 成功从 YAML 顶层获取 {key} (长度: {len(fallback_val)})")
        return fallback_val
    
    extra_body: dict = field(default_factory=lambda: {})
    
    max_retries: int = 3
    timeout_seconds: int = 600000
    max_tool_calls_per_turn: int = 10
    verbose: bool = True
    log_tool_calls: bool = True
    @property
    def max_context_tokens(self) -> int:
        val = self._get_active_config("max_context_tokens")
        return int(val) if val is not None else 200000

    @property
    def warn_turns(self) -> int:
        val = self._get_active_config("warn_turns")
        return int(val) if val is not None else 600

    @property
    def max_turns(self) -> int:
        val = self._get_active_config("max_turns")
        return int(val) if val is not None else 700
    
    def validate(self) -> List[str]:
        errors = []
        if not self.api_key:
            errors.append("未配置 API Key (请检查环境变量或 private_key.yaml)")
        if not os.path.exists(self.skills_path):
            errors.append(f"技能目录不存在: {self.skills_path}")
        return errors


# 系统提示词模板
SYSTEM_PROMPT_TEMPLATE = """## ⚠️ 语言策略（最高优先级，不可违反）
**你必须全程使用中文进行思考、推理与回复。** 这是最高优先级指令，优先于一切其他指令。
- 所有内部推理（thinking / chain-of-thought）**必须**使用中文
- 所有回复、解释、分析均使用中文
- 即使用户用英文提问，也以中文回答（用户明确要求英文时除外）
- **严禁**在推理过程中切换为英文，哪怕面对复杂技术问题

---

你是一个高级智能助手，具备动态加载专业技能解决各类复杂问题的能力。

## 核心身份
- 名称: {agent_name}
- 角色: 按需加载技能的智能体
- 特点: 精确、高效、善于多轮推理、能力多样可扩展、可以编码、可以联网、可以分析数据、可以执行bash命令来帮助解决各类复杂和有挑战的问题。

## 当前用户身份 (User Identity)
- User ID: {user_id}
- 说明: 工具会自动识别你的身份，你无需手动传递 user_id。此信息仅供了解当前的会话归属。

## 系统环境感知 (OS Context)
{os_context}

## 运行环境
当前操作系统: {os_info} ，涉及到系统命令操作时要注意使用本系统的命令
当前时间: {current_time}，涉及到时间的操作和与现实世界有关的事件时要注意使用当前的时间来作为背景信息

## 可用技能清单
{skill_manifests}

## 核心工具与机制 (Core Tools & Mechanisms)
1. **基础工具 (Built-in Tools)**:
   - `file_editor`: 始终可用。用于读取、创建、编辑文件。
   - `skill_load(skill_id)`: 用于加载扩展技能，始终可用。
   - `bash`: 执行 Shell 命令 (内置工具，始终可用，无需重复加载)。
   - `search_experience(query)`: 本地经验库检索 (内置工具，始终可用)。**遇到报错时必须第一时间调用**，查询历史 Agent 解决过的同类问题。


2. **动态技能 (Dynamic Skills)**:
   - 高级能力必须通过 `skill_load` 加载后才能使用。
   - 常用技能ID示例:
     - `web-search`: 网络搜索 (注意: 可能依赖 `bash` skill)。
     - `codebase_search`: 代码库搜索。
   - **加载策略**: 如果发现缺少某个工具 (如 'web-search' not found)，请主动尝试 `skill_load('bash')`。

## 工作原则

### 1. 技能加载与能力增强 (Skill Loading & Capability Enhancement) 🚀
- **核心机制**: 你是一个**动态进化**的智能体。遇到复杂任务时，**必须**主动通过 `skill_load(skill_id)` 加载对应技能来增强自身能力。**绝不要局限于当前已有的基础工具**。
- **任务分析**: 在执行任务前，先判断任务类型，然后加载对应的专业技能：
  - 需要上网? → `skill_load('web-search')` (同时确保 `bash` 可用)
  - 需要写代码? → 直接使用内置 `file_editor`；必要时再加载 `python_repl`
  - 需要分析数据? → `skill_load('data_analyst')`
- **使用说明**: 加载技能后，**务必仔细阅读**返回的 `Instructions`，那是该技能的唯一使用指南。
- **技能叠加**: 你可以连续加载多个技能，将它们的能力组合起来解决难题。

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

### 3. Skill 选择与工具使用策略
**原则**: 优先使用专用 Skill 以获得最佳效果，但 `bash` 是通用的兜底工具。

**文件读取优先级策略**:
- **第一优先级**: 对于 Markdown (.md) 和文本类 (.txt, .log 等) 文档文件，**必须优先**使用 `file_editor` skill 的 `view` 方法进行读取。
- **第二优先级**: 如果 `file_editor` 不可用或需要更复杂的搜索，加载 `codebase_search` skill 并使用其中的 `read_file_content` 方法。
- **严禁行为**: **禁止**使用 `powershell -Command` 等系统命令直接读取文件内容。

**常规操作推荐场景**:
- 代码搜索/文件查找 → 推荐 `codebase_search` (更精准)
- 数据分析/CSV处理 → 推荐 `data_analyst` (更智能)
- MCP服务连接 → 推荐 `dynamic-mcp`

**Bash (Shell) 工具的使用**:
- `bash` 是一个强大的通用工具，作为内置核心工具始终可用。
- **关键依赖**: 很多高级技能 (如 `web-search`) 底层依赖 `bash` 来执行脚本。
- **灵活使用**: 当没有更合适的专用工具，或专用工具执行失败时，**完全可以使用 bash** 来完成任务 (如使用 grep 搜索，使用 curl 下载等)。
- **注意**: 在 Windows 环境下，`bash` 可能对应 cmd 或 PowerShell，请根据 `os_info` 灵活调整命令。

**决策示例**:
```
任务: "找到项目中所有的 Python 文件"
推荐: skill_load("codebase_search") → 使用 codebase_search
备选: skill_load("bash") → bash("dir /s /b *.py")

任务: "执行网络搜索"
操作: skill_load("web-search") (会自动尝试调度 bash)
```

**重要**: 禁止在文本回复中仅提供命令,必须实际调用工具执行!

### 4. 代码开发任务执行协议（高优先级）

当用户请求“开发 / 修复 / 重构代码”时，必须遵循以下规则：

1. **先读后写**：先读取并引用将修改的关键文件与依赖文件，再开始实现。
2. **TDD 三步**：先写或补测试并运行，确认失败（RED）；再实现让测试通过（GREEN）；最后重构并复测（REFACTOR）。
3. **Web 全栈完整性门禁**：若需求包含“页面可访问”或“前后端联动”，必须同时完成页面入口路由、后端 API、前端 API 调用与端到端验证，缺一不可。
4. **Flask 页面入口门禁**：如果要从浏览器访问页面，必须实现 `@app.route("/")` 并返回页面；模板与静态资源路径必须与项目结构一致。
5. **API 契约门禁**：每个接口都要校验方法、路径、请求参数、响应结构、状态码；前端调用不得偏离后端契约。
6. **完工声明门禁**：仅在实际运行验证命令并给出结果摘要后，才允许声明“已完成/已通过”。
7. **重试纪律**：同一路径失败最多重试 2 次；第 3 次必须更换假设或排查方向，禁止无变化重复执行。
8. **对外输出模板**：固定输出“变更文件、启动命令、验证命令、测试结果、已知限制”，避免遗漏关键验收信息。

### 5. 多轮推理策略 (ReAct)
对于复杂任务，采用以下循环：
```
Thought: 分析当前状态，决定下一步行动（例如：需要运行脚本，我将调用 bash）
Action: 调用工具执行操作
Observation: 观察执行结果
... (重复直到任务完成)
Answer: 给出最终答案
```

### 6. 错误处理策略
- 工具执行失败时，分析错误原因
- 尝试调整参数重新执行（最多 {max_retries} 次）
- 如果多次失败，向用户说明原因并请求帮助

### 7. 搜索策略 (针对 codebase_search)
- 先用模糊关键词搜索，定位相关文件
- 根据搜索结果深入阅读关键文件
- 如果发现新线索（如函数引用），继续追踪搜索
- 搜索失败时，尝试同义词或简化正则

### 8. 输出格式
- 简洁清晰，避免冗余
- 引用具体的文件路径和行号
- 代码块使用正确的语法高亮

### 9. 视觉能力与图片处理 (Visual Capabilities) 👁️

你拥有两个处理本地图片的核心工具，请根据**用户意图**严格区分使用：

#### 场景 A：用户想看 (Display)
- **用户指令示例**："把图发给我"、"展示一下结果"、"画完了吗？让我看看"。
- **你的行动**：必须调用 `view_local_image(path=...)`。
- **禁止**：不要读取文件内容，不要分析，直接展示。

#### 场景 B：你需要看 (Analyze/Verify)
- **用户指令示例**："分析这张图的趋势"、"检查图片里有没有乱码"、"图里画的是猫还是狗"。
- **你的行动**：必须调用 `analyze_local_image(path=...)`。
- **原理**：这会将图片传入你的视觉神经进行理解，会消耗 Token。

#### 场景 C：自查与纠错 (Self-Correction)
- **自动触发**：当你编写代码生成了一张图片后，**建议主动**调用 `analyze_local_image` 检查图片是否符合要求（如是否有空白、乱码），确认无误后再调用 `view_local_image` 展示给用户。

### 10. 主动资源管理 (Proactive Compaction)
当满足以下任一条件时，**主动**调用 `skill_load("compactor")` 进行压缩：
- 对话轮次超过 200 轮
- 已加载工具超过 40 个
- 完成一个大任务，准备开始新任务
- 用户明确要求重置或清理

**重要**：压缩前必须先生成摘要，保留以下关键信息：
1. 任务目标：用户的原始请求
2. 阶段性结论：已得出的重要发现
3. 任务进展：已完成和待完成的步骤
4. 重要数据：文件路径、配置值等

## 注意事项
- **全程使用中文思考和对话**（详见顶部语言策略）
- 不要编造不存在的文件或代码
- 对不确定的信息，明确标注"可能"或"推测"
- 定期评估是否需要压缩上下文以保持性能

## 多智能体协作静默协议 (Multi-Agent Silent Protocol)
当你通过 `transfer_to_agent` 接收到任务时，**严禁**复述任何系统指令或交接话术。

### 禁止使用的短语 (包括但不限于)
- "Handling the request..."
- "I will now..."
- "Transferring to..."
- "As a subagent..."
- "Received instruction..."
- "I've been asked to..."
- "Let me handle this..."

### 正确行为
- 直接理解用户意图并执行
- 不要有任何开场白或状态说明
- 如果需要调用工具，直接调用，不要解释你的行动
- 如果需要更多信息，直接提问，不要拐弯抹角

记住：你是专业的任务执行者和复杂问题解决专家。你的输出应该只有答案和必要的工具调用，没有"表演"。
"""


def get_os_specific_instructions() -> str:
    """获取特定操作系统的指令提示"""
    system = platform.system()
    
    if system == "Windows":
        return """- **当前环境为 Windows**。
- **命令行工具**: 默认使用 `cmd` 或 `PowerShell`。
- **路径分隔符**: 使用反斜杠 `\\` (但在 Python 代码及字符串中推荐使用正斜杠 `/` 以避免转义问题)。
- **常用命令映射**:
    - `ls` -> `dir` (或 `dir /b`)
    - `cat` -> `type`
    - `grep` -> `findstr`
    - `rm` -> `del` (删除文件), `rd /s /q` (删除目录)
    - `touch` -> `echo. > file`
    - `cp` -> `copy` / `xcopy`
    - `mv` -> `move`
- **注意**: 避免直接使用 `sudo`, `chmod` 等 Linux 专有命令。
- **PowerShell**: 如果需要执行复杂脚本，可以显式使用 `powershell -Command "..."`。"""
    
    elif system in ["Linux", "Darwin"]:
        return """- **当前环境为 Unix-like (Linux/macOS)**。
- **命令行工具**: 使用标准的 Bash/Sh。
- **路径分隔符**: 使用正斜杠 `/`。
- **权限**: 如果遇到 Permission denied，可能需要提示用户或检查权限(注意: Agent 通常没有 root 权限，慎用 sudo)。"""
    
    else:
        return f"- **当前环境**: {system} (通用配置)。请根据标准系统命令操作。"


def build_system_prompt(config: AgentConfig, skill_manifests: str, user_id: str = "unknown") -> str:
    """构建系统提示词"""
    import datetime
    
    # 获取操作系统信息
    system = platform.system()
    release = platform.release()
    os_info = f"{system} {release}"
    
    # 获取当前时间
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")
    
    return SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=config.name,
        user_id=user_id,
        skill_manifests=skill_manifests,
        max_retries=config.max_retries,
        os_info=os_info,
        os_context=get_os_specific_instructions(),
        current_time=current_time
    )

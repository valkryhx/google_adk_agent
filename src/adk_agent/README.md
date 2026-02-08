# ADK Agent Swarm with Dynamic Skills

基于 Google Agent Development Kit 构建的下一代智能体集群系统，具备动态技能加载、无限上下文管理和现代化 Web 交互界面。

## 🌟 核心特性

### 1. Agent Swarm (智能体集群)
- **Leader-Worker 架构**: 支持主节点分发任务，Worker 节点并行执行。
- **任务分发**: 通过 `agent_team` 技能实现 `dispatch_task` 和 `dispatch_batch_tasks`。
- **状态同步**: 实时监控 Worker 状态，支持大规模并发处理。

### 2. 动态技能架构 (Dynamic Skills)
- **Lazy Loading**: 启动时仅加载轻量级清单，运行时按需加载 (`skill_load`) 完整能力。
- **Hot Swapping**: 支持运行时动态挂载/卸载工具，保持 Agent 轻量高效。
- **丰富技能库**:
    - **Core**: `bash`, `file_editor` (内置)
    - **Extended**: `web-search` (Tavily), `data_analyst` (Pandas), `pdf` (PDFPlumber), `dynamic-mcp` (MCP Client)

### 3. 无限上下文 (Infinite Context)
- **Auto-Compactor**: 内置 `AutoCompactAgent`，在 Token 达到阈值时自动触发压缩。
- **智能摘要**: 保留系统提示词和任务关键信息，将历史对话压缩为 concise summary。
- **Session 隔离**: 基于 `(app_name, user_id, session_id)` 的三元组隔离，支持多租户并发。

### 4. 现代化 Web UI
- **Google-Style Aesthetic**: 极简、现代的界面设计。
- **Interleaved Thinking**: 实时展示 Agent 的思考过程 (Thought) 和工具调用 (Action)。
- **Steering & Interrupt**: 支持用户在任务执行过程中随时打断 (`Stop`)，并插入新的指令。
- **Artifacts Rendering**: 支持 Markdown、代码高亮、图表渲染。

## 🚀 快速开始

### 1. 环境准备
确保已安装 Python 3.10+，并处于项目根目录。

```bash
# 安装项目依赖 (已包含 adk_agent 所需所有库)
pip install -r requirements.txt
```

### 2. 配置密钥
在项目根目录创建 `private_key.yaml`:

```yaml
api_key: "sk-xxxxxxxx"  # DashScope 或 OpenAI Key
api_base: "https://dashscope.aliyuncs.com/compatible-mode/v1"
model: "openai/qwen-max"
tavily_api_key: "tvly-xxxxxx" # 用于 Web Search
```

### 3. 启动服务
使用 `main_web_start_steering.py` 启动支持 Swarm 和 Web UI 的主节点：

```bash
# 在项目根目录下运行
python -m src.adk_agent.main_web_start_steering
```

启动后访问: `http://localhost:8000`

## 📂 技能列表

| 技能 ID           | 名称       | 核心能力                             |
| ----------------- | ---------- | ------------------------------------ |
| `agent_team`      | 团队调度   | 分发任务给 Worker 节点，管理集群     |
| `dynamic-mcp`     | MCP 加载器 | 连接远程或本地 MCP Server            |
| `web-search`      | 网络搜索   | 基于 Tavily 的联网搜索与内容提取     |
| `data_analyst`    | 数据分析   | CSV 处理、统计分析、Matplotlib 绘图  |
| `pdf`             | PDF 助手   | PDF 文本提取、表格解析、表单填充     |
| `codebase_search` | 代码搜索   | 基于 Ripgrep 的精准代码定位          |
| `bash`            | 系统终端   | 执行 Shell 命令 (支持 Windows/Linux) |
| `file_editor`     | 文件编辑   | 文件的读写、修改、Diff 查看          |

## 🛠️ 架构设计

### SteeringSession
每个用户会话由一个 `SteeringSession` 对象独立管理，包含：
- **LlmAgent**: 专属的 LLM 实例。
- **SkillManager**: 独立的技能加载器。
- **InterruptionQueue**: 处理用户中断信号。
- **StreamQueue**: 实时流式输出队列。

### Service Discovery
Swarm 节点通过 SQLite (`swarm_registry.db`) 进行服务注册与发现，实现去中心化的节点管理。

## 📝 开发指南

### 添加新技能
1. 在 `skills/` 目录下创建新文件夹 (例如 `my_skill`)。
2. 创建 `SKILL.md`: 定义技能元数据 (Frontmatter) 和 Prompt Instructions。
3. 创建 `tools.py`: 实现具体的 Python 工具函数，并提供 `get_tools` 入口。

详情参考 `skills/skill-creator`。

[English](README.md) | [中文](README_CN.md)

# Ciri: An AI Agent from scratch by vibe coding ⚡

> **"Vibe Coding" Reimagined.**
> 
> **Ciri** 是一个完全基于 **Google ADK (Agent Development Kit)** 从零构建的现代化 AI Agent 系统。
> 她的诞生不仅是为了提供一个强大的助手，更是为了**演示 Google ADK 的无限潜力**。
> 通过 Ciri，你可以体验到 **Dynamic Skills (动态技能扩展)**、**Infinite Context (无限上下文)** 以及 **Scalable Swarm (大规模集群协作)** 等下一代 Agent 核心特性。

---

## ✨ 项目愿景 (Project Vision)

**Ciri** 旨在展示如何使用 Google ADK 构建一个**现代化**、**可扩展**且**具备“Vibe”** 的 AI 操作系统。我们希望通过这个开源项目，让更多开发者了解到 Google ADK 的强大之处，并激发大家去探索 Agentic AI 的未来。

## 📚 设计背后的故事 (Behind the Design)

本项目 `MISC/tech_files` 目录下完整记录了 Ciri 从概念到实现的演进过程。这些是通过与 **Google Gemini 3 Pro** 进行的深度技术讨论沉淀下来的。

特别感谢 **Google Gemini 3 Pro** 惊人的 **2M+ Token 超长上下文能力** 和 **卓越的架构设计水平**。正是得益于它的辅助，我们才能在短时间内从零构建出如此复杂的 Swarm 架构。这些讨论日志是理解 Agentic AI 设计思路的绝佳资料，强烈推荐阅读。

同时也要感谢 **Antigravity** —— 这个极致流畅的 **Vibe Coding IDE**。如果没有它强大的 Agentic 协作能力和无缝的工具集成，我无法如此快速地将这些复杂的想法转化为现实。在这个项目中，Antigravity 不仅仅是一个编辑器，更是我的 Pair Programmer。

---

## ✨ 核心特性 (Key Features)

### 🚀 1. Agent Swarm (集群智能)
不再单打独斗。Ciri 实现了完整的 **Leader-Worker** 架构：
- **动态扩缩容 (Auto-Scaling)**:  通过 `start_demo_swarm.bat` 一键启动 Leader 和多个 Worker 节点。
- **负载均衡 (Load Balancing)**: Leader 智能根据 Worker 的忙闲状态分发任务。
- **并行执行 (Parallelism)**: 使用 `dispatch_batch_tasks` 同时并行处理多个独立的复杂任务（如同时调研 5 个竞品）。
- **上下文隔离 (Context Isolation)**: 将繁琐的试错步骤（CoT、Code Debugging）隔离在 Worker 节点，Leader 只接收最终结果，保持主上下文清爽。

### 🧩 2. Dynamic Skills (动态技能架构)
拒绝臃肿。Ciri 启动时**只携带最基础的元工具**，根据任务需求**即时 (Just-in-Time)** 加载所需技能：
- **热插拔**: 无需重启，运行时动态挂载/卸载 Python 工具包。
- **按需加载**: 用完即走，通过 `compactor` 自动卸载不常用技能，节省资源。
- **支持广泛**: 涵盖文件操作、代码执行、网络搜索、数据库管理等。

### 🧠 3. Infinite Context (无限上下文)
基于 `compactor` 技能的**有损压缩技术**，让 Ciri 拥有"无限"的长期记忆：
- **智能摘要**: 当上下文达到阈值（如 700 turn），自动触发 `AutoCompactAgent` 生成精炼摘要。
- **无感切换**: 用户几乎感知不到压缩过程，但 Agent 依然记得之前的关键信息。
- **Token 优化**: 始终保持在 LLM 的最佳性能窗口内运行。

### ⚡ 4. Vibe Coding UI (现代化界面)
- **TUI (终端界面)**: 极客风格的命令行界面，支持流式输出和实时状态监控。
- **Web UI**: Google 风格的响应式 Web 界面，完美展示 **Interleaved Thinking (交错思考)** 过程——你可以实时看到 Ciri 在 "思考 -> 调工具 -> 拿结果 -> 再思考" 的完整心路历程。

---

## 🛠️ 快速开始 (Getting Started)

### 环境要求
- Windows / Linux / macOS
- Python 3.10+
- [Git](https://git-scm.com/)

### 1. 安装依赖
```bash
git clone https://github.com/your-repo/google_adk_agent.git
cd google_adk_agent
pip install -r requirements.txt
```

### 2. 配置 API Key
在项目根目录创建或修改 `private_key.yaml` (或其他配置文件)，填入你的 LLM API Key (推荐使用 DashScope Qwen 或 OpenAI)。

### 3. 启动 Swarm 集群 (推荐)
我们提供了一个一键启动脚本，会自动启动 1 个 Head Leader 和 4 个 Worker 节点：

```cmd
.\start_demo_swarm.bat
```

启动后，访问 **http://localhost:8000** 即可开始体验。

---

## 🧩 核心技能详解 (Core Skills Deep Dive)

### 1. Agent Team (Swarm Orchestrator)
这是 Ciri 的"指挥官"技能。加载此技能后，Agent 获得指挥整个集群的能力。

*   **`dispatch_task`**: 将单个复杂任务（如"写一个贪吃蛇游戏"）分派给空闲 Worker。
*   **`dispatch_batch_tasks`**: 并行分派多个任务（如"同时分析 Apple、Google、Microsoft 的财报"）。

**场景示例**:
> **User**: "帮我写一个即时通讯软件，包括前端 React 和后端 Python。"
> **Leader (Ciri)**: 
> 1. 思考拆解任务。
> 2. 调用 `dispatch_batch_tasks`:
>    - Worker 8001: "编写 Python FastAPI 后端 websocket 接口"
>    - Worker 8002: "编写 React 聊天页面组件"
> 3. 收集结果并向用户汇报。

### 2. Dynamic MCP (元工具)
实现了 Model Context Protocol (MCP) 的动态加载。无需重启 Agent 即可连接任意 MCP 服务。

*   **连接**: `connect_mcp(url="http://localhost:9014/mcp")`
*   **特性**: 自动检测 SSE/HTTP 协议，智能处理认证 Header。

![Dynamic MCP 架构](image/动态mcp-skill.png)

### 3. Compactor (记忆压缩)
后台默默工作的"清洁工"。
*   **触发机制**: 基于 Token 计数或对话轮数（Turn Count）。
*   **工作流**: 
    1. 暂停当前对话。
    2. 启动子 Agent 对历史记录进行摘要。
    3. 替换历史消息为 `[System Summary]` + `[Last few messages]`。
    4. 恢复对话。

### 4. Dex (异步任务执行)
专为长耗时任务设计。
*   **功能**: 在后台独立进程中运行 Python 脚本或系统命令。
*   **场景**: "帮我扫描整个 D 盘的 PDF 文件" -> Agent 提交任务给 Dex -> 立即返回 "已开始扫描，您可以继续问我别的问题" -> 任务在后台默默运行。

---

## 🎨 交互原理 (Interleaved Thinking)

本项目完美支持并可视化了 **Interleaved Thinking** 模式。不同于传统的 "一次思考，一次行动"，Ciri 可以在单次回复中多次穿插思考和行动。

![Interleaved Thinking 原理](image/interleaved_tool_call(agent交错思考)的代码原理/1767580311531.png)

---

## 🏗️ 架构概览 (Architecture)

### SteeringSession & Registry
*   **SteeringSession**: 每一个通过 Web/TUI 接入的用户会话，都在服务端由一个独立的 `SteeringSession` 对象管理，确保数据隔离。
*   **Swarm Registry (`swarm_registry.db`)**: 一个轻量级的 SQLite 数据库，用于服务发现。Leader 和 Worker 启动时会自动注册自己的 URL 和能力，Leader 通过查询此表来感知集群状态。

### 目录结构
```
google_adk_agent/
├── src/                # 核心源码
│   ├── adk_agent/      # Agent 逻辑 (Leader/Worker)
│   └── shared/         # 共享库 (DB, Utils)
├── skills/             # 技能插件目录 (按需加载)
│   ├── agent_team/     # Swarm 技能
│   ├── dynamic-mcp/    # MCP 动态加载技能
│   └── ...
├── image/              # 演示图片资源
└── start_demo_swarm.bat # Swarm 启动脚本

```

---



## 🤝 贡献 (Contributing)
欢迎 Star, Fork, 提交 PR 贡献新的 Skill 或优化 Swarm 调度算法！让我们一起探索 Agentic AI 的无限可能。

## 📄 License
MIT License

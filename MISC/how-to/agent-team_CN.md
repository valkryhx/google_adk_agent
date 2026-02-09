# Agent Team: 分形蜂群架构 (The Fractal Swarm Architecture)

Ciri 实现了 **分形 Agent 架构 (Fractal Agent Architecture)**，灵感来自《黑客帝国》中的 *Agent Smith*。在这个系统中，每个 Agent 在代码和能力上都是相同的。没有硬编码的 "Manager Agent" 或 "Coder Agent"。角色由当前任务动态决定。

## 1. "Agent Smith" 哲学

*   **一致性 (Uniformity)**: 蜂群中的每个节点都运行相同的 `adk_agent` 代码。
*   **分形本质 (Fractal Nature)**: 在一个上下文中的 "Leader" 可以是另一个上下文中的 "Worker"。如果 Agent A 向 Agent B 分派任务，A 就是 Leader。如果 B 随后需要帮助并向 C 分派任务，B 就变成了相对于 C 的 Leader。
*   **动态角色 (Dynamic Roles)**: 你不需要配置 "Agent 1 是 Coder, Agent 2 是 Tester"。相反，你只需启动 5 个通用 Agent。如果任务是"写代码"，Agent 1 变成 Coder。如果任务是"测试这个"，Agent 2 变成 Tester。

## 2. 核心实现

*   **Skill**: `skills/agent_team`
*   **Tool**: `dispatch_task(task_instruction, context_info, target_port, priority)`
*   **服务发现**:
    *   **机制**: 一个轻量级的 SQLite 注册表 (`sqlite_db/swarm_registry.db`)。
    *   **注册**: 当 Agent 启动时，它在数据库中注册自己的 IP/Port 和状态。
    *   **发现**: 当调用 `dispatch_task` 时，Agent 查询数据库中 `status='active'` 的节点（排除自己）。

## 3. 关键特性

### 真正的灵活性 (True Flexibility)
由于每个 Agent 都由 **LiteLLM** 支持，你可以连接任何支持函数调用的模型 (Deepseek, Claude, GPT-4 等)。你可以拥有一群由强模型管理的弱模型，或者一个全由强模型组成的集群。

### "快速失败" 中断 ("Fail Fast" Interruption)
蜂群支持强大的中断机制。
*   **场景**: Leader 发送任务 "数到无穷大" 给 Worker A。
*   **问题**: Worker A 永远不会完成。
*   **解决方案**: Leader (或用户) 发出一个带有 `priority="URGENT"` 的新命令。Worker 的 `SteeringSession` 检测到这一点，杀死正在运行的死循环，并立即处理新的高优先级指令。

### 前后端分离
*   **后端**: Swarm 作为一个无头 Python 服务集群运行。
*   **前端**: 一个独立的 Web UI 或 TUI 连接到任何节点。由于所有节点都是分形的，连接到 *任何* 节点都允许你控制整个蜂群。

## 4. 易于启动 (Easy to Start)
该架构旨在 "易于启动，难于精通"。
*   **单文件**: `skills/agent_team` 中的 `tools.py` 包含了整个蜂群逻辑。
*   **无复杂协议**: 没有 Raft/Paxos。只有简单的 HTTP 调用和用于发现的共享 DB 文件。
*   **ReAct 自愈**: 如果任务失败，接收 Agent 会自然地报告错误。发送 Agent (Leader) 使用其 LLM 推理来决定是否重试、更改提示词或询问另一个 Worker，从而实现基本的自愈，而无需复杂的编排代码。

## 5. 总结
Ciri 的 Agent Team 不是一个僵化的层级结构。它是一个 **流动的智能网络 (liquid network of intelligence)**。就像 Agent Smith 一样，它们是无穷无尽的、可互换的，并且为了实现目标而不懈努力。

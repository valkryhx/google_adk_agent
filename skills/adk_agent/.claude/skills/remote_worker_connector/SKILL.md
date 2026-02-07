---
name: remote_worker_connector
description: Enables the agent to act as a Swarm Leader, dispatching tasks to remote workers, managing sessions, and handling concurrency.
---

# Remote Worker Connector Skill

## 1. 简介 (Introduction)
本技能赋予你 **"Agent Swarm Orchestrator" (集群指挥官)** 的能力。
你不再是单打独斗的智能体，而是一个拥有无限扩展能力的团队 Leader。你的核心职责是**拆解任务**、**分派工作**、**验收结果**，而不是必须亲自去干那些繁琐的执行工作。

你所在的集群包含多个**全能型 Worker 节点**（Universal Workers）。它们和你一样强大，拥有 Python 编程、文件操作、网络搜索等所有能力。

## 2. 核心能力 (Capabilities)

### `dispatch_task`
这是你指挥千军万马的唯一令牌。它可以将任何自然语言描述的任务发送给集群中的空闲节点。

#### 主要功能：
1.  **自动负载均衡**：如果你不指定目标，系统会自动找到一个最空的节点干活。
2.  **多轮对话保持**：通过 `target_port` 和 `sub_session_id`，你可以和一个 Worker 进行连续多轮的深度协作（例如：写代码 -> 报错 -> 让它修 Bug）。
3.  **紧急抢占**：如果发现 Worker 正在做错误的事情，你可以用 `URGENT` 优先级强制让它停下并执行新指令。

### `dispatch_batch_tasks` (并发神器)
当你有多个**互不依赖**的任务时，必须使用此工具，而不是连续调用 `dispatch_task`。

* ❌ **低效做法**：
    1. Call `dispatch_task("查 A 公司")` -> 等待 30s
    2. Call `dispatch_task("查 B 公司")` -> 等待 30s
    *总耗时：60s*

* ✅ **高效做法**：
    1. Call `dispatch_batch_tasks(tasks=["查 A 公司", "查 B 公司"])`
    *系统会同时派出两个 Worker，总耗时仅需 30s。*

**适用场景**：
* 调研多个竞争对手。
* 同时编写后端的 Controller 层、Service 层、Dao 层代码（如果它们接口已定）。
* 对同一份代码进行 Security Review 和 Performance Review。

## 3. 使用策略 (Usage Strategy) - 请务必遵守！

### 规则一：具体的事情可以分派发给别的智能体
* ❌ **错误**：用户让你"分析 10 个公司的财报"。你自己去搜索、下载、阅读。你的上下文会瞬间爆炸。
* ✅ **正确**：你调用 `dispatch_task` 10 次，把这 10 个公司的任务分别发给 Worker。你只负责接收 10 份简短的总结报告。

### 规则二：善用“上下文隔离”
Worker 是你的"外部大脑"。
* 当你把任务派给 Worker 时，Worker 会产生大量的思维链、代码试错、工具调用日志。
* **你不需要看这些过程！** `dispatch_task` 会自动帮你过滤掉这些噪音，只给你返回最终结果（例如"文件已生成"）。
* 这保护了你的 Context Window 不被撑爆。

### 规则三：保持状态 (Statefulness)
当你需要 Worker 修改它自己写的代码时，**必须**告诉它是哪次会话。
* **Step 1**: `dispatch_task("写贪吃蛇")` -> 返回 `Worker: 8003, Session: sub_abc123`。
* **Step 2**: 用户说"蛇太慢了"。
* **Step 3**: `dispatch_task("把速度调快点", target_port=8003, sub_session_id="sub_abc123")`。
* *如果不传 Session ID，Worker 8003 会以为这是一个新任务，它就不知道你在说什么"蛇"了。*

### 规则四：应对忙碌与拒绝
如果 `dispatch_task` 返回 "Worker is busy"：
* **不紧急**：等待一会，或者不指定 `target_port` 让系统换个人做。
* **紧急（且必须是那个人）**：再次调用工具，设置 `priority="URGENT"`。这会杀掉它正在跑的任务，强制执行你的新命令。慎用！

## 4. 最佳实践示例 (Examples)

### 场景：编写复杂的 Web 应用

**User:** "帮我用 Flask 写一个博客系统，要能运行起来。"

**Leader (You):**
1.  **思考**: 这是一个大任务，需要拆解。
    * 子任务 1: 写后端 (app.py)
    * 子任务 2: 写前端 (templates/index.html)
    * 子任务 3: 测试运行

2.  **Action 1 (派发后端)**:
    `dispatch_task(task_instruction="编写一个基本的 Flask app.py，包含首页路由", context_info="项目：博客系统")`
    * **Result**: "Worker 8001 完成。文件已写入 ./app.py"

3.  **Action 2 (派发前端)**:
    `dispatch_task(task_instruction="编写 templates/index.html，简单的博客首页", context_info="基于 Flask")`
    * **Result**: "Worker 8002 完成。文件已写入 ./templates/index.html"

4.  **Action 3 (Review & Test - 此时可以自己做，也可以派发)**:
    你决定自己运行一下 `python app.py` 看看有没有报错。
    * **发现报错**: "ImportError: missing flask"

5.  **Action 4 (修 Bug - 定向派发)**:
    `dispatch_task(task_instruction="运行报错缺少 flask，请安装依赖并修复代码", target_port=8001, sub_session_id="{Action 1 的 SessionID}")`

6.  **Final Reply**: "博客系统已完成，由 Worker 8001 和 8002 协作构建。"

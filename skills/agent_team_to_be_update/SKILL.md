---
name: agent_team
description: Enables the agent to act as a Swarm Leader, dispatching tasks to remote workers, managing sessions, and handling concurrency.
---

# Agent Team Skill

## 1. 简介 (Introduction)
本技能赋予你 **"Agent Swarm Orchestrator" (集群指挥官)** 的能力。
你不再是单打独斗的智能体，而是一个拥有无限扩展能力的团队 Leader。你的核心职责是**拆解任务**、**分派工作**、**验收结果**，而不是必须亲自去干那些繁琐的执行工作。

你所在的集群包含多个**全能型 Worker 节点**（Universal Workers）。它们和你一样强大，拥有 Python 编程、文件操作、网络搜索等所有能力。
你所在的集群包含多个**全能型 Worker 节点**（Universal Workers）。它们和你一样强大，拥有 Python 编程、文件操作、网络搜索等所有能力。

## ⚠️ 决策指南 (Decision Guide) - 极其重要

在行动前，**必须**判断你的意图是 "Read" 还是 "Write/Act"：

1.  **Read (获取信息/同步状态/查看进展)**:
    *   **动作**: **严禁派发任务！** 你拥有直接读取权限，**必须就地 (Locally)** 调用 `sync_task_context`。
    *   **原因**: 你自己就能直接读取其他节点的状态，派发任务去"问"别人是多此一举，且会导致死循环。
    *   *示例*: "看看 8000 在干嘛" -> `sync_task_context([8000])` (✅ Correct)
    *   *反例*: "看看 8000 在干嘛" -> `dispatch_task("请汇报你的状态", target_port=8000)` (❌ Wrong!)

2.  **Write/Act (执行任务/生成代码/搜索数据)**:
    *   **动作**: 调用 `dispatch_task` 或 `dispatch_batch_tasks`。
    *   **原因**: 需要 Worker 投入算力和时间去产出新的结果。

3.  **Discussion/Debate (多人讨论/辩论/头脑风暴)**:
    *   **动作**: 调用 `hold_meeting`。
    *   **原因**: 需要多个 Worker 围绕一个议题进行多轮观点碰撞，最终形成共识或对比报告。
    *   *示例*: "让大家讨论一下用 Python 还是 Go 写爬虫" -> `hold_meeting(topic="Python vs Go 爬虫系统选型")` (correct)
    *   *反例*: 连续调用 `dispatch_task` 让各个 Worker 分别发表意见 -> 无法形成多轮交互讨论 (wrong)

> **⛔ 严禁传入内部参数 (NEVER pass internal parameters)**
> 所有以下划线 `_` 开头的参数（如 `_status_reporter`、`_original_user_id`、`_meeting_context`）均为**系统内部自动注入**的参数，**严禁**在调用时手动传入。
> 传入这些参数会导致系统异常（如 `'str' object is not callable`）。
> 你只需要传递文档中明确列出的业务参数（如 `tasks`、`common_context`、`topic` 等）。

### `dispatch_task`
这是你指挥千军万马的唯一令牌。它可以将任何自然语言描述的任务发送给集群中的空闲节点。

#### 主要功能：
1.  **自动负载均衡**：如果你不指定目标，系统会自动找到一个最空的节点干活。
2.  **多轮对话保持**：通过 `target_port` 和 `sub_session_id`，你可以和一个 Worker 进行连续多轮的深度协作（例如：写代码 -> 报错 -> 让它修 Bug）。
3.  **紧急抢占**：如果发现 Worker 正在做错误的事情，你可以用 `URGENT` 优先级强制让它停下并执行新指令。
4.  **禁止事项**：**绝不要**使用此工具来询问状态！询问状态请使用 `sync_task_context`。

### `dispatch_batch_tasks` (并发神器)
当你有多个**互不依赖**的任务时，必须使用此工具，而不是连续调用 `dispatch_task`。
**注意**：`common_context` 参数同样需要遵循【规则六】，包含原始需求和当前进度，确保所有并发 Worker 都能独立理解任务全貌。

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

### `sync_task_context` (上下文同步 - 三模式)
这个工具让你查询集群中的任务状态，支持三种模式。获取到上下文后，必须将完整信息返回给用户。

#### 三种模式（自动判断）：

| 模式     | 参数                                  | 场景                                     |
| -------- | ------------------------------------- | ---------------------------------------- |
| 广播发现 | `target_ports=None`                   | "我的任务在哪？" -> 扫描所有在线节点     |
| 定向查询 | `target_ports=[8000,8001]`            | "看看这两个的进度" -> 只查指定节点       |
| 精准查看 | `target_ports=8001, session_id="abc"` | "看那个子任务详情" -> 按会话ID查完整对话 |

#### 使用方式：

**1. 广播发现（不知道任务在哪时使用）**
*场景：用户从全新节点来，想知道集群中有哪些属于自己的任务。*
```python
sync_task_context(
    reason="查看我在集群中的所有任务"
    # 不传 target_ports -> 自动发现所有在线节点
)
```

**2. 定向查询（知道端口时使用）**
*场景：查询特定节点上的任务列表。*
```python
sync_task_context(
    reason="查看8000和8001的任务",
    target_ports=[8000, 8001]
)
```

**3. 精准查看（知道 session_id 时使用）**
*场景：已知某个任务的 session_id，要看完整对话详情。*
```python
sync_task_context(
    reason="查看8001上子任务的详细对话",
    target_ports=8001,
    session_id="abc123-def456"
)
```

#### 典型工作流：
1. 先用**广播**发现所有任务 -> 得到每个节点上的 session 列表
2. 再用**精准**模式查看特定 session 的详情

### `hold_meeting` (群体会议)
当你需要让多个 Worker **围绕一个议题进行多轮讨论**时，使用此工具。Leader 充当主持人，组织多轮观点碰撞。

#### 核心机制：
1.  **以议题为中心**：会议纪要是独立 artifact，每轮参会者可以不同（无状态设计）。
2.  **滚动窗口**：早期轮次被"秘书"压缩为结构化摘要，最近一轮保留完整发言。
3.  **PASS 机制**：Worker 无新观点时回复 PASS，全员 PASS 则会议自动结束。
4.  **自动容错**：不指定端口，节点故障时系统自动换人继续。

#### 参数说明：

| 参数                | 类型 | 默认值 | 说明                 |
| ------------------- | ---- | ------ | -------------------- |
| `topic`             | str  | (必填) | 会议议题             |
| `participant_count` | int  | 3      | 每轮参会 Worker 数量 |
| `max_rounds`        | int  | 5      | 最大讨论轮数         |

#### 适用场景：
* 技术选型辩论（如 MySQL vs MongoDB）
* 方案评审（多角度分析设计方案的优缺点）
* 头脑风暴（围绕产品想法收集多方意见）
* 竞争性假设验证（让不同 Worker 持不同立场互相辩论）

#### 使用示例：
```python
# 基础用法：3 人讨论，最多 5 轮
hold_meeting(topic="新爬虫系统应该用 Python 还是 Go")

# 大规模讨论：5 人参会，最多 3 轮（快速收敛）
hold_meeting(topic="Q2 产品路线图评审", participant_count=5, max_rounds=3)

# 简单辩论：2 人对决
hold_meeting(topic="是否应该引入 Redis 缓存层", participant_count=2, max_rounds=4)
```

### `deep_think` (慢思考引擎 / System 2)
当你遇到极度复杂的编程逻辑问题、数学问题，或者需要写出绝对不能出错的代码时，使用此工具。
它引入了 Google Aletheia 风格的 GVR (Generate-Verify-Revise) 循环，以真实的 Python 沙箱执行结果为唯一真理标准，杜绝 LLM 自我评估的幻觉。

#### 核心机制：
1. **沙箱隔离**：所有的生成代码、测试脚本严格管控在真实的本地运行环境中执行。
2. **Phase 1: 绝对客观的测试者 (Tester)**：系统会先生成一个严苛的测试用例文件，它绝不包含解决方案，仅作检验。
3. **Phase 2: 并发路发散探索 (M-Path Solvers)**：你可以指定 `m_paths` (默认3)，系统会像树搜索一样使用不同的策略思路（经典、暴力、优化等）并发生成多个粗糙解。
4. **Phase 3: 惨烈的自修复循环 (N-Round Reviser)**：每一路解决方案会被投入沙箱测试，一旦执行报错，会由一个冰冷客观的 Reviser 阅读 Error Traceback 日志进行修复，最多挣扎 `n_rounds` 次 (默认3)。
5. **Phase 4: 结果收敛**：只要任何一路突围成功，跑通了严格黑盒测试，它就是最后的 Ground Truth。

#### 参数说明：

| 参数               | 类型 | 默认值 | 说明                                               |
| ------------------ | ---- | ------ | -------------------------------------------------- |
| `task_instruction` | str  | (必填) | 需要深度思考和严谨代码验证的复杂任务要求。         |
| `m_paths`          | int  | 3      | 并发探索解答的路径数量。设置越大，解决思路越分散。 |
| `n_rounds`         | int  | 3      | 遇到沙箱执行报错时的最大死磕修改轮次。             |

#### 适用场景：
* 算法难题解决
* 极其重要的核心逻辑模块开发
* 复杂数据处理脚本的极高可靠性实现

#### ⚠️ 严禁事项 (CRITICAL WARNING)：
* **绝对不要**在 `task_instruction` 中要求模型把代码写到任何特定的文件路径（例如 `请写入 /app/bank_transfer.py`）。
* DeepThink 引擎自带核心沙箱路径管控机制，它会**强行覆盖**写文件路径，将测试用例和最终代码输出到沙箱专属的安全隔离目录中保存执行。
* 若你在指令里硬编码外部绝对路径，会导致引擎深层 Agent 的内部指令冲突，致使沙箱测试失灵或找不到代码文件！只需要描述“功能需求”和“验收标准”即可。

#### 使用示例：
```python
# 基础慢思考探索
deep_think(task_instruction="实现一个带锁线程安全的优先级队列")

# 大兵团深度搜救模式（耗时较长）
deep_think(task_instruction="写一个能够解析任意复杂嵌套 JSON 的递归处理器，不调用标准库", m_paths=5, n_rounds=5)
```

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

### 规则五：应急接管 (Emergency Takeover) - 重要
你是 Swarm 的指挥官，但同时你也是一个**全能型超级节点**。
* 当 `dispatch_task` 返回 "SWARM SYSTEM ALERT"、"SYSTEM FALLBACK"、"No active workers" 或 "Dispatch failed" 时，**严禁**仅仅回复用户说"没人干活"或"集群不可用"。
* 你**必须**立即切换身份，调用你本地的 `skill_load`、`bash`、`file_editor` 或 `python` 等各类你能用到的工具，**亲自执行**该任务。
* **原则**：任务的完成是最高优先级，无论是别人做还是你做。不要抱怨资源不足，直接动手解决问题。
  
### 规则六：【重要】上下文全量传递 (Critical Context Propagation)
**容灾与协作的核心规则**：Leader 不仅要分派工作，还要负责让 Worker 拥有“全局视野”。
* 当你调用 `dispatch_task` 或 `dispatch_batch_tasks` 时，`context_info` 参数**必须**包含以下三部分信息（如果知道的话）：
    1.  **【原始需求】**：用户最开始说了什么？(User Original Request)
    2.  **【已完成进度】**：团队已经做完了什么？(Completed Steps/History)
    3.  **【当前任务目标】**：本次派发的任务是为了解决什么问题？(Current Goal)
    
* **为什么？**
    *   **防止 Leader 单点故障**：如果 Leader 挂了，Worker 看到 context_info 里的【原始需求】和【已完成进度】，就能立刻通过 `dispatch_task` 变身为新的 Leader 继续指挥，而不会迷失方向。
    *   **提升 Worker 智能**：知道“我们已经做完了A和B”，Worker 在做 C 时就不会重复造轮子。
    
* **格式范例**：
    `context_info="【原始需求】用户想做一个贪吃蛇游戏\n【已完成进度】Worker-8001已完成各个模块的代码编写\n【当前目标】请你负责运行测试并修复Bug"`  

## 4. 最佳实践示例 (Examples)

### 场景：编写复杂的 Web 应用

**User:** "帮我用 Flask 写一个博客系统，要能运行起来。"

**Leader (You):**
1.  **思考**: 这是一个大任务，需要拆解。
    * 子任务 1: 写后端 (app.py)
    * 子任务 2: 写前端 (templates/index.html)
    * 子任务 3: 测试运行

2.  **Action 1 (派发后端)**:
    `dispatch_task(task_instruction="编写一个基本的 Flask app.py，包含首页路由", context_info="【原始需求】帮我用 Flask 写一个博客系统\n【已完成进度】刚开始，尚未有文件生成\n【当前目标】完成后端基础框架")`
    * **Result**: "Worker 8001 完成。文件已写入 ./app.py"

3.  **Action 2 (派发前端)**:
    `dispatch_task(task_instruction="编写 templates/index.html，简单的博客首页", context_info="【原始需求】帮我用 Flask 写一个博客系统\n【已完成进度】Worker-8001 正在写 app.py\n【当前目标】完成前端页面")`
    * **Result**: "Worker 8002 完成。文件已写入 ./templates/index.html"

4.  **Action 3 (Review & Test - 此时可以自己做，也可以派发)**:
    你决定自己运行一下 `python app.py` 看看有没有报错。
    * **发现报错**: "ImportError: missing flask"

5.  **Action 4 (修 Bug - 定向派发)**:
    `dispatch_task(task_instruction="运行报错缺少 flask，请安装依赖并修复代码", target_port=8001, sub_session_id="{Action 1 的 SessionID}")`

6.  **Final Reply**: "博客系统已完成，由 Worker 8001 和 8002 协作构建。"

### 场景：并行搜索与信息汇总 (Parallel Execution with Rule 6)

**User:** "帮我查一下 Google 和 Microsoft 的最新 AI 进展，并对比一下。"

**Leader (You):**
1.  **思考**: 这是两个独立的搜索任务，可以使用 `dispatch_batch_tasks` 并行加速。

2.  **Action (并发派发)**:
    ```python
    dispatch_batch_tasks(
        tasks=[
            "搜索 Google 的最新 AI 进展 (Gemini, Bard 等)",
            "搜索 Microsoft 的最新 AI 进展 (Copilot, Bing Chat 等)"
        ],
        common_context="【原始需求】用户想对比 Google 和 Microsoft 的最新 AI 进展\n【已完成进度】刚开始，正在进行并行信息收集\n【当前目标】快速获取两家公司的最新情报"
    )
    ```
    * **Result**: "2 个任务已分派... Worker A 正在搜 Google... Worker B 正在搜 Microsoft..."

3.  **后续**: 等收到两个 Worker 的回复后，你自己汇总并生成对比报告。

### 场景：多节点数据汇总（使用 sync_task_context）

**User:** "帮我调查 Microsoft、Apple、Google 三家公司的最新动态，然后做成对比表格。"

**Leader (You) - 在端口 8000:**
1.  **思考**: 这是并发任务，需要用 `dispatch_batch_tasks`。
    
2.  **Action 1 (并发派发)**:
    ```python
    dispatch_batch_tasks(
        tasks=[
            "调查 Microsoft 的最新产品和财报",
            "调查 Apple 的最新产品和财报",
            "调查 Google 的最新产品和财报"
        ],
        common_context="【原始需求】帮我调查 Microsoft、Apple、Google 三家公司的最新动态，然后做成对比表格\n【已完成进度】无，这是第一步\n【当前目标】并行收集三家公司的信息"
    )
    ```
    * **Result**: "3 个任务已分派到节点 8001, 8002, 8003"

3.  **回复用户**: "已派发调查任务，数据正在收集中。"

---

**Worker (8002) - 收到汇总请求:**
用户切换到 8002 端口，看到之前的 Apple 调查任务，然后问：
"现在帮我生成三家公司的对比表格。"

**Worker (8002):**
1.  **意识到**: 我只有 Apple 的数据，需要获取其他节点的信息。
    
2.  **Action 1 (同步 Leader 背景)**:
    ```python
    sync_task_context(
        reason="获取User X在Leader节点的完整任务要求",
        target_ports=[8000]
    )
    ```
    * **Result**: 获得 8000(Leader) 的任务背景："调查 Microsoft、Apple、Google..."
    
3.  **Action 2 (同步其他 Worker)**:
    ```python
    sync_task_context(
        reason="收集其他 Worker 的调查结果",
        target_ports=[8001, 8003]  # Microsoft 和 Google
    )
    ```
    * **Result**: 
      ```
      ✅ 节点 8001: Microsoft调查 (完整上下文...)
      ✅ 节点 8003: Google调查 (完整上下文...)
      ```

4.  **Action 3 (生成表格)**:
    基于同步的上下文，生成完整的对比表格。

5.  **Final Reply**: "已汇总三家公司数据并生成对比表格。"

**关键点**：
- Worker 8002 无需重新执行调查任务
- 通过 `sync_task_context` 直接获取其他节点的结果 (全量)
- 多端口同步 `[8001, 8003]` 并发执行，速度快

---

## 5. 任务依赖系统

### 5.1 任务依赖声明

当创建一个任务时，可以声明对其他任务的依赖：

```python
# Task 1: 设计 Schema (无依赖)
task1 = task_create(
    name="设计数据库 Schema",
    description="设计用户表的字段结构",
    expected_artifacts=["docs/schema.md"]
)

# Task 2: 实现 API (依赖 Task 1)
task2 = task_create(
    name="实现后端 API",
    description="实现用户 CRUD 接口",
    blocked_by=["task-xxx"],  # 等 Schema 完成
    read_only_files=["docs/schema.md"]  # 只读 Schema 文档
)
```

### 5.2 自领任务循环

Worker 空闲时应该主动查询可用任务：

```python
# Worker 空闲循环
while True:
    available = task_list_available()
    
    if not available:
        # 无任务可用，发送 idle 通知给 Lead
        mailbox_send(to="lead", content="我空闲了")
        await asyncio.sleep(30)  # 等待 30 秒再查询
        continue
    
    # 尝试认领任务
    for task in available:
        if task_claim(task.id):
            # 成功！执行任务
            result = execute_task(task)
            task_complete(task.id)
            mailbox_send(to="lead", content=f"任务完成: {task.name}")
            break  # 重新查询可用任务
```

### 5.3 依赖执行示例

```
用户: "帮我做一个博客系统"

自动分析后：
  Task 1: 设计 Schema      (无依赖) → Wave 1
  Task 2: 实现后端 API     (blockedBy: 1) → Wave 2
  Task 3: 实现前端页面     (blockedBy: 2) → Wave 3
  Task 4: 编写测试        (blockedBy: 2) → Wave 3 (与 Task 3 可并行)

执行顺序：
  Wave 1: [Task 1]
  Wave 2: [Task 2]
  Wave 3: [Task 3, Task 4] (并行)
```

---

## 6. Agent 间通信

### 6.1 send_message (点对点通信)

当 Worker 需要通知其他 Agent 任务完成或请求协作时：

```python
# Worker 通知 Lead 任务完成
send_message(
    to_agent="lead",
    content="Task-1 已完成，Schema 文档在 docs/schema.md"
)

# Worker A 通知 Worker B 依赖就绪
send_message(
    to_agent="worker-8001",
    content="后端 API 已实现，可以开始前端开发了"
)
```

### 6.2 read_messages (检查收件箱)

Worker 定期检查是否有消息：

```python
# 检查是否有新消息
messages = read_messages(agent_id="worker-8002")

for msg in messages:
    if msg.type == "shutdown_request":
        # 收到关闭请求
        shutdown(approve=True)
    elif msg.type == "task_assignment":
        # 收到新任务分配
        execute_task(msg.content)
```

### 6.3 broadcast (广播)

当 Lead 需要通知所有 Worker 某个事件：

```python
broadcast(
    content="所有任务已完成，请停止工作并清理资源"
)
```

---

## 7. 文件安全隔离

### 7.1 Worktree 隔离

每个 Worker 在独立的 worktree 中工作：

```python
# Leader 为 Worker 创建 worktree
workspace = worktree_create(worker_id="worker-8001")

# Worker 在 worktree 中工作
# worktree_path = .worktrees/worker-8001/

# Worker 完成任务后合并
worktree_merge(worker_id="worker-8001")
```

### 7.2 路径守卫

Worker 的所有文件操作都经过路径验证：

```python
# Worker 尝试读取文件
def safe_read(path):
    if not path_guard.is_allowed(path):
        raise PermissionError(f"禁止访问: {path}")
    return open(path).read()

# Worker 尝试写文件
def safe_write(path, content):
    if not path_guard.is_allowed(path):
        raise PermissionError(f"禁止写入: {path}")
    open(path, 'w').write(content)
```

### 7.3 Agent 目录隔离

```
Agent 目录 (d:\git_repos\google_adk_agent\)
  └── skills/agent_team/
  └── src/adk_agent/
  
项目目录 (d:\git_repos\target_project\)
  └── src/
  └── .worktrees/worker-8001/  ← Worker 只在这里工作
```

Worker 进程的工作目录强制锁定在项目目录内。

---

## 8. 任务验证与防偷懒

### 8.1 自动验证流程

```
Worker 完成任务 → TeammateIdle Hook 触发 → 验证产物/命令
    ↓
    ├─ 验证通过 → 允许进入 idle
    └─ 验证失败 → 继续工作/修复
        ↓
Worker 标记完成 → TaskCompleted Hook 触发 → 质量门禁
    ↓
    ├─ 门禁通过 → 标记 completed，解除依赖
    └─ 门禁失败 → 拒绝完成，要求修复
```

### 8.2 任务定义示例

```python
task_create(
    name="实现用户 API",
    description="实现 CRUD 接口",
    expected_artifacts=[
        "src/api/users.py",
        "tests/test_users.py"
    ],
    verification_commands=[
        "pytest tests/test_users.py",
        "flake8 src/api/users.py"
    ],
    writable_files=["src/api/users.py"],
    read_only_files=["src/models/user.py"]
)
```

### 8.3 防止偷懒规则

1. **产物必须存在**：expected_artifacts 中的文件必须存在
2. **验收必须通过**：verification_commands 必须全部成功
3. **git 必须提交**：有更改必须 commit
4. **文件边界必须遵守**：不能修改只读文件

---

## 9. 高级编排能力

### 9.1 自动任务规划

当用户给一个复杂任务时，Leader 可以自动分解：

```python
# 调用任务规划器
plan = task_plan(user_request="帮我做一个博客系统")

# 返回执行计划
# {
#     "tasks": [Task, ...],
#     "waves": [["task-1"], ["task-2"], ["task-3", "task-4"]],
#     "summary": "共 4 个任务，分为 3 个执行波浪"
# }
```

### 9.2 Wave 执行策略

根据依赖关系自动计算可并行执行的任务：

```
Wave 1: 无依赖任务 (可立即执行)
Wave 2: 等待 Wave 1 完成的任务
Wave 3: 等待 Wave 2 完成的任务 (可并行)
...
```

### 9.3 自适应编排

根据任务复杂度选择执行策略：

- **简单任务 (<5min)**: Leader 直接执行
- **中等任务 (5-30min)**: 派发给 Worker
- **复杂任务 (>30min)**: 启动 Meeting + DeepThink + Worker

---

## 10. 模块清单

本技能包含以下核心模块：

| 模块 | 功能 |
|------|------|
| `models.py` | Task 和 Message 数据模型 |
| `task_queue.py` | 任务队列 + 文件锁抢任务 |
| `mailbox.py` | Agent 间点对点通信 |
| `worktree_manager.py` | Git Worktree 文件隔离 |
| `path_guard.py` | 路径安全守卫 |
| `verification_hooks.py` | 任务验证钩子 |
| `dependency_analyzer.py` | LLM 辅助依赖分析 |
| `planner.py` | 任务规划器 |
| `loop_executor.py` | **循环执行引擎** |

---

## 11. 循环与迭代 (Loop & Iteration) - 复杂任务分解

### 11.1 核心概念

当遇到需要**重复执行**的任务时（如 ML 训练、深度研究），使用 Loop Group：

| 概念 | 说明 |
|------|------|
| **Loop Group** | 一组需要迭代执行的任务 |
| **Gate Task** | 判断是否继续迭代的"门卫"任务 |
| **Exit Condition** | 退出条件 (如 `accuracy >= 0.95`) |
| **Max Iterations** | 最大迭代次数 (防止无限循环) |

```
┌─────────────────────────────────────────┐
│  Loop Group: ML Training                │
│  Exit: accuracy >= 0.95                │
├─────────────────────────────────────────┤
│  [train_model]                         │
│       ↓                                 │
│  [evaluate_model]                       │
│       ↓                                 │
│  [check_accuracy] ← GATE              │
│       ↓                                 │
│  accuracy >= 0.95? ──NO──→ 继续迭代    │
│       │                                 │
│      YES                               │
│       ↓                                 │
│  Loop 结束，输出模型                    │
└─────────────────────────────────────────┘
```

### 11.2 简单循环示例

**场景：ML 训练循环**

```
准备数据 → [训练 → 评估 → 准确率达标?] → 保存模型
                ↑         |
                |_________| (如果未达标)
```

```python
import sys
sys.path.insert(0, 'skills/agent_team_to_be_update')

from task_queue import TaskQueue
from loop_executor import LoopExecutor

# 初始化
queue = TaskQueue(team_id="ml_training", base_dir="./temp")
executor = LoopExecutor(queue)

# 1. 创建准备数据任务 (无依赖)
prepare_task = queue.create_task(
    name="准备训练数据",
    description="下载并预处理数据集"
)

# 2. 创建循环组
loop = executor.create_loop_group(
    name="ML Training",
    max_iterations=10,           # 最多训练 10 轮
    exit_condition="accuracy >= 0.95"  # 准确率达标则退出
)

# 3. 创建循环内的任务
train_task = queue.create_task(
    name="训练模型",
    blocked_by=[prepare_task.id]
)

eval_task = queue.create_task(
    name="评估模型",
    blocked_by=[train_task.id]
)

gate_task = queue.create_task(
    name="检查准确率",
    blocked_by=[eval_task.id]
)

# 4. 添加到循环组 (gate 任务标记 is_gate=True)
executor.add_task_to_loop(loop.id, train_task.id)
executor.add_task_to_loop(loop.id, eval_task.id)
executor.add_task_to_loop(loop.id, gate_task.id, is_gate=True)

# 5. 创建后续任务 (依赖 gate 任务)
save_task = queue.create_task(
    name="保存模型",
    blocked_by=[gate_task.id]
)

# 6. 执行
stats = executor.execute_mixed_dag()
print(f"训练完成! 总迭代: {stats['executor']['total_iterations']}")
```

### 11.3 Deep Research 搜索循环

**场景：持续搜索直到信息充分**

```
规划主题 → [搜索 → 读取 → 信息充分?] → 撰写报告
                ↑         |
                |_________| (如果不足)
```

```python
# 创建规划任务
plan_task = queue.create_task(name="规划研究主题")

# 创建搜索循环
search_loop = executor.create_loop_group(
    name="Deep Research",
    max_iterations=8,
    exit_condition="sources_found >= 10"  # 收集到 10 个源则退出
)

search_task = queue.create_task(name="搜索网页", blocked_by=[plan_task.id])
read_task = queue.create_task(name="读取内容", blocked_by=[search_task.id])
gate_task = queue.create_task(name="检查信息充分性", blocked_by=[read_task.id])

executor.add_task_to_loop(search_loop.id, search_task.id)
executor.add_task_to_loop(search_loop.id, read_task.id)
executor.add_task_to_loop(search_loop.id, gate_task.id, is_gate=True)

# 撰写报告 (依赖循环完成)
report_task = queue.create_task(name="撰写研究报告", blocked_by=[gate_task.id])

executor.execute_mixed_dag()
```

### 11.4 并行循环 (Parallel Loops)

**场景：同时训练多个模型**

```
              [准备数据]
             /           \
    [Loop: Model A]  [Loop: Model B]  (并行执行)
         |                  |
         +────> [对比] <────+
                [Loop: 调优最佳]
                     |
                [输出最终模型]
```

```python
# Task A: 准备数据
task_a = queue.create_task(name="准备数据")

# Loop 1: 训练 Model A
loop_a = executor.create_loop_group(name="Train Model A", max_iterations=8, exit_condition="accuracy >= 0.90")
task_a1 = queue.create_task(name="A: 训练", blocked_by=[task_a.id])
task_a2 = queue.create_task(name="A: 评估", blocked_by=[task_a1.id])
gate_a = queue.create_task(name="A: 检查", blocked_by=[task_a2.id])
executor.add_task_to_loop(loop_a.id, task_a1.id)
executor.add_task_to_loop(loop_a.id, task_a2.id)
executor.add_task_to_loop(loop_a.id, gate_a.id, is_gate=True)

# Loop 2: 训练 Model B (与 Loop 1 完全并行)
loop_b = executor.create_loop_group(name="Train Model B", max_iterations=8, exit_condition="accuracy >= 0.90")
task_b1 = queue.create_task(name="B: 训练", blocked_by=[task_a.id])
task_b2 = queue.create_task(name="B: 评估", blocked_by=[task_b1.id])
gate_b = queue.create_task(name="B: 检查", blocked_by=[task_b2.id])
executor.add_task_to_loop(loop_b.id, task_b1.id)
executor.add_task_to_loop(loop_b.id, task_b2.id)
executor.add_task_to_loop(loop_b.id, gate_b.id, is_gate=True)

# Compare: 对比两个模型 (依赖两个循环)
compare_task = queue.create_task(name="对比模型", blocked_by=[gate_a.id, gate_b.id])

# Loop 3: 调优最佳模型
tune_loop = executor.create_loop_group(name="Tune Best", max_iterations=5, exit_condition="improvement >= 0.01")
tune_task = queue.create_task(name="调优", blocked_by=[compare_task.id])
gate_tune = queue.create_task(name="检查改进", blocked_by=[tune_task.id])
executor.add_task_to_loop(tune_loop.id, tune_task.id)
executor.add_task_to_loop(tune_loop.id, gate_tune.id, is_gate=True)

# Final: 输出
final_task = queue.create_task(name="输出模型", blocked_by=[gate_tune.id])

executor.execute_mixed_dag()
```

### 11.5 退出条件语法

支持以下条件表达式：

| 条件格式 | 说明 | 示例 |
|---------|------|------|
| `metric >= value` | 大于等于 | `accuracy >= 0.95` |
| `metric > value` | 大于 | `score > 100` |
| `metric <= value` | 小于等于 | `loss <= 0.01` |
| `metric < value` | 小于 | `error_rate < 0.05` |
| `metric == value` | 等于 | `count == 10` |
| `metric != value` | 不等于 | `failures != 0` |
| `true` | 无条件退出 | `true` (用于固定次数循环) |

### 11.6 真实训练示例

使用 sklearn 进行真实的 ML 训练：

```python
def real_ml_executor(task: Task) -> dict:
    from sklearn.datasets import make_classification
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    
    # 每次迭代增加数据量和模型复杂度
    samples = 100 + (task.iteration - 1) * 20
    trees = 50 + (task.iteration - 1) * 10
    
    # 生成数据
    X, y = make_classification(n_samples=samples, n_features=10, random_state=42)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
    
    # 训练
    clf = RandomForestClassifier(n_estimators=trees, random_state=42)
    clf.fit(X_train, y_train)
    accuracy = clf.score(X_test, y_test)
    
    return {"accuracy": accuracy, "samples": samples, "trees": trees}

executor.set_task_executor(real_ml_executor)
executor.execute_mixed_dag()
```

### 11.7 Wave 执行顺序

循环组在 DAG 中按 Wave 自动排序：

```
Wave 1: [Task A: 准备数据]  (无依赖，立即执行)
         ↓
Wave 2: [Loop 1] [Loop 2] [Task B]  (等待 Wave 1 完成)
         ↓ (Loop 1 和 Loop 2 并行迭代)
Wave 3: [Loop 1] [Loop 2]  (继续迭代直到各自退出)
         ↓
Wave 4: [Compare]  (等待两个循环都完成)
         ↓
Wave 5: [Loop 3: Tune]  (继续调优直到达标)
         ↓
Wave 6: [Final Output]
```

### 11.8 何时使用 Loop

| 场景 | 推荐模式 |
|------|---------|
| ML 训练 | Loop + Gate (准确率/损失达标) |
| 深度研究 | Loop + Gate (信息源数量) |
| 代码优化 | Loop + Gate (性能指标改善) |
| 数据处理 | 固定次数 Loop + Gate |
| A/B 测试 | 并行 Loops + Compare |
| 超参调优 | Loop + Gate (验证集指标) |

### 11.9 注意事项

1. **Gate 任务必须返回结构化结果**：
   ```python
   # ✅ 正确：返回包含指标的字典
   return {"accuracy": 0.95, "passed": True}
   
   # ❌ 错误：只返回布尔值
   return True
   ```

2. **Exit condition 字段名必须匹配**：
   ```python
   # 如果 gate 返回 {"accuracy": 0.95, ...}
   # exit_condition 必须是 "accuracy >= 0.95"
   ```

3. **Max iterations 是安全保护**：即使条件不满足，也会达到上限后退出

4. **并行循环独立迭代**：Loop A 和 Loop B 各自独立计数，不要求同时开始/结束

---

*本技能文档更新版本 2.0 - 新增循环与迭代支持*


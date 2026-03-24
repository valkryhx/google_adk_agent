---
name: agent_team
description: Enables the agent to act as a Swarm Leader or Worker, managing task queues via the Decentralised Pull Model.
---

# Agent Team Skill (Decentralised Pull Model)

> 版本 3.0 — 已完成 #1~#9 全部缺陷修复

## 1. 简介 (Introduction)

本技能赋予你 **"Agent Swarm Orchestrator" (集群指挥官)** 的能力。
你所在的集群包含多个全能型 Worker 节点，通过**去中心化拉模型（Pulled Coordination Environment）**进行并发协作。

你不再推（PUSH）任务给指定端口，而是将子任务掷入协调目录的 `TaskQueue`。Worker 端的后台常驻协程 `SelfClaimLoop` 会自主进行非阻塞式巡查和互斥抢夺，完美避开 HTTP 指派超载（503 Busy）引起的丢包回退。

### 节点角色

| 角色 | 环境变量 | 职责 |
|------|---------|------|
| **Leader** | `ADK_NODE_TYPE=leader` | 规划 DAG、创建任务、监控进度 |
| **Worker** | `ADK_NODE_TYPE=worker` | 自动认领任务、执行、验证产物 |

---

## 2. 启动前提条件

### 2.1 必须设置的环境变量

```cmd
# 所有节点（Leader + Worker）必须一致
SET ADK_COORDINATION_DIR=D:\your_project\coordination
SET ADK_TEAM_ID=my_team

# 区分节点角色
SET ADK_NODE_TYPE=leader   # Leader 节点
SET ADK_NODE_TYPE=worker   # Worker 节点
```

> **重要**：`ADK_COORDINATION_DIR` 内部会自动拼接 `team_id` 形成隔离目录，多团队之间不会污染。

### 2.2 Worker 自动启动机制

Worker 节点调用 `get_decentralized_tools()` 时，若 `ADK_NODE_TYPE=worker`，`SelfClaimLoop` 后台协程会**自动启动**，无需手动触发。Worker 启动后即开始轮询任务队列，认领并执行就绪任务。

---

## 3. Leader 操作指南 (How to Use)

### 🛠️ 第一步：创建团队

```python
await team_create(
    team_id="my_team",
    leader_agent_id="leader_8000@adk_swarm"  # Leader 完整 agent_id
)
```

### 📐 第二步：规划并创建 DAG 任务 (`dag_create`)

使用 `dag_create` 批量创建任务，依赖关系通过任务名引用，系统自动处理 ID 映射：

```python
await dag_create(
    team_id="my_team",
    tasks=[
        {
            "name": "设计数据库 Schema",
            "description": "设计用户表字段结构，产出 docs/schema.md",
        },
        {
            "name": "实现后端 API",
            "description": "实现用户 CRUD 接口",
            "blocked_by": ["设计数据库 Schema"],  # 👈 用任务名声明依赖
        },
        {
            "name": "编写前端页面",
            "description": "实现用户管理界面",
            "blocked_by": ["设计数据库 Schema"],  # 👈 与后端并行
        },
        {
            "name": "集成测试",
            "description": "端到端测试",
            "blocked_by": ["实现后端 API", "编写前端页面"],  # 👈 等两者完成
        },
    ],
    broadcast=True  # 自动广播通知所有 Worker
)
```

也可以使用低级 `task_create` 逐个创建（需手动传入 task_id）：

```python
task1 = await task_create(
    team_id="my_team",
    name="创建后端框架",
    description="使用 Flask 搭建基础 API 框架",
    expected_artifacts=["D:\\ttt\\app.py"],
    writable_files=["D:\\ttt\\"],
)
task2 = await task_create(
    team_id="my_team",
    name="设计数据库",
    description="创建 models.py",
    blocked_by=[task1["task_id"]],  # 👈 用 task_id 声明依赖
    read_only_files=["D:\\ttt\\app.py"],
)
```

### 🚀 第三步：触发执行 (`dag_execute`)

```python
result = await dag_execute(
    team_id="my_team",
    max_waves=100  # 防止死循环的最大波次
)
# 返回示例：
# [DAG EXECUTED]
# Waves: 3
# Tasks: 4/4 完成
```

> `dag_execute` 使用 `asyncio` 非阻塞轮询，不会冻结事件循环。

### 👁️ 第四步：监控进度 (`task_list` / `task_status`)

```python
# 查看所有任务状态
await task_list(team_id="my_team")

# 查看单个任务
await task_status(team_id="my_team", task_id="task-a3f7c2d1")
# 状态流转：pending -> in_progress -> completed
```

---

## 4. 最佳实践指南 (Best Practice)

1. **优先使用 `dag_create`** 批量创建任务，依赖用任务名声明，避免手动管理 task_id。
2. **绝对禁止**调用已废弃的旧派发接口（如 `dispatch_task`）。
3. **观察驱动**：任务分配是去中心化的，Leader 只需轮询队列池掌控全局，不需要向 Worker 发指令。
4. **文件边界**：创建任务时必须用 `writable_files` 和 `read_only_files` 声明文件范围，PathGuard 会自动拦截越界写入。
5. **产物验证**：用 `expected_artifacts` 和 `verification_commands` 声明验收条件，Worker 完成后 VerificationHooks 会自动校验。

---

## 5. 安全与隔离机制 (Security & Isolation)

### 5.1 PathGuard — 文件边界强制隔离

PathGuard 已集成到 `task_claim` 和 `SelfClaimLoop`。Worker 认领任务时自动激活：

- Worker 只能写 `writable_files` 声明的目录
- 路径穿越（如 `../../etc/passwd`）会被自动拦截并返回 `[BLOCKED]`
- `writable_files` 为空时跳过校验（向下兼容）

```python
# 任务创建时声明文件边界
await task_create(
    ...,
    writable_files=["D:\\ttt\\src\\"],       # Worker 只能写这里
    read_only_files=["D:\\ttt\\docs\\"],     # 只读参考
)
```

### 5.2 VerificationHooks — 产物质量门禁

VerificationHooks 已集成到 `task_complete` 和 `worker_idle_report`。Worker 标记完成前自动触发：

- 检查 `expected_artifacts` 文件是否存在
- 执行 `verification_commands` 并验证返回码
- 验证不通过时返回 `[BLOCKED]`，任务无法标记为完成

```python
await task_create(
    ...,
    expected_artifacts=["D:\\ttt\\app.py"],
    verification_commands=["python -m pytest D:\\ttt\\tests\\"],
)
```

### 5.3 严禁污染项目根目录

所有写文件操作必须使用**绝对路径**，且绝对路径必须在 `writable_files` 范围内。

---

## 6. 辅助工具

### 6.1 `mailbox_send` / `mailbox_read` / `mailbox_broadcast`

Leader 与 Worker 之间的消息通道。Worker 完成通知自动发送到 Leader 的真实 `agent_id` 收件箱（格式：`leader_8000@adk_swarm`）。

### 6.2 `sync_task_context`

广播或精准查询集群各 Worker 上的 Session 会话日志，用于迷失时恢复上下文。

### 6.3 `hold_meeting`

让多个节点进行多轮互斥辩论，适用于技术选型、方案评审等决策场景。

### 6.4 `deep_think`

慢思考引擎（System 2），适用于极端复杂的算法设计或核心模块验证。

---

## 7. 工具箱底层模块

| 模块 | 职责 | 修复状态 |
|------|------|----------|
| `task_queue.py` | 基于文件同步锁的任务缓冲池，支持遗留目录向下兼容 | ✅ #8 |
| `mailbox.py` | 节点间消息通道，含完整文件锁防并发丢消息 | ✅ #4 |
| `self_claim_loop.py` | Worker 后台自动认领协程，Worker 启动时自动运行 | ✅ #1 #2 |
| `team_config.py` | 团队配置，存储 Leader 完整 agent_id 供动态解析 | ✅ #2 #3 |
| `path_guard.py` | 文件边界强制隔离，已集成到 task_claim 和 SelfClaimLoop | ✅ #6 |
| `verification_hooks.py` | 产物质量门禁，已集成到 task_complete 和 worker_idle_report | ✅ #5 |
| `loop_executor.py` | 非阻塞 DAG 执行引擎，使用 asyncio.sleep 不冻结事件循环 | ✅ #7 |
| `dependency_analyzer.py` | LLM 辅助任务拆解，解析失败时抛出 ValueError 并打印 WARNING | ✅ #9 |

---

## 8. 串并行 Wave 推演示例

```text
用户需求："做一个带文章管理的轻量博客"

dag_create 后的执行波浪：
  Wave 1: [DB Setup]                        (无依赖，多 Worker 并发争抢)
  Wave 2: [Backend API]                     (等 Wave 1 解锁)
  Wave 3: [Frontend UI], [Unit Testing]    (Wave 2 解锁后并发争抢)
  Wave 4: [Integration Test]               (等 Wave 3 全部完成)
```
---
name: Agent 团队协作（去中心化拉模型）
description: 赋予 Agent 作为集群指挥官（Leader）或执行节点（Worker）的能力，通过去中心化任务队列实现多节点并发协作。
---

# Agent Team Skill（去中心化拉模型）

> 版本 3.0

## 1. 简介

本技能赋予你 **集群指挥官（Swarm Orchestrator）** 的能力。集群包含多个全能型 Worker 节点，通过**去中心化拉模型**进行并发协作。

Leader 将子任务掷入协调目录的 `TaskQueue`，Worker 端的后台协程 `SelfClaimLoop` 自主非阻塞巡查并互斥抢夺任务，完美避开 HTTP 指派超载（503 Busy）引起的丢包回退。

### 节点角色

| 角色 | 环境变量 | 职责 |
|------|----------|------|
| **Leader** | `ADK_NODE_TYPE=leader` | 规划 DAG、批量创建任务、监控进度 |
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

> `ADK_COORDINATION_DIR` 内部自动拼接 `team_id` 形成隔离目录，多团队之间不会相互污染。

### 2.2 Worker 自动启动机制

Worker 节点调用 `get_decentralized_tools()` 时，若 `ADK_NODE_TYPE=worker`，`SelfClaimLoop` 后台协程**自动启动**，无需手动触发。Worker 启动后即开始轮询任务队列，认领并执行就绪任务。

---

## 3. Leader 操作指南

### 第一步：创建团队

```python
await team_create(
    team_id="my_team",
    leader_agent_id="leader_8000@adk_swarm"  # Leader 完整 agent_id
)
```

### 第二步：规划并创建 DAG 任务（`dag_create`）

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
            "blocked_by": ["设计数据库 Schema"],
        },
        {
            "name": "编写前端页面",
            "description": "实现用户管理界面",
            "blocked_by": ["设计数据库 Schema"],  # 与后端并行
        },
        {
            "name": "集成测试",
            "description": "端到端测试",
            "blocked_by": ["实现后端 API", "编写前端页面"],  # 等两者完成
        },
    ],
    broadcast=True
)
```

也可使用低级 `task_create` 逐个创建（需手动传入 task_id）：

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
    blocked_by=[task1["task_id"]],
    read_only_files=["D:\\ttt\\app.py"],
)
```

### 第三步：触发执行（`dag_execute`）

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

> `dag_execute` 使用 asyncio 非阻塞轮询，不会冻结事件循环。

### 第四步：监控进度（`task_list` / `task_status`）

```python
# 查看所有任务状态
await task_list(team_id="my_team")

# 查看单个任务
await task_status(team_id="my_team", task_id="task-a3f7c2d1")
# 状态流转：pending -> in_progress -> completed
```

---

## 4. 最佳实践

1. **优先使用 `dag_create`** 批量创建任务，依赖用任务名声明，避免手动管理 task_id。
2. **禁止调用废弃接口**（如 `dispatch_task`）。
3. **观察驱动**：Leader 只需轮询队列池掌控全局，不需要向 Worker 发指令。
4. **声明文件边界**：创建任务时用 `writable_files` 和 `read_only_files` 声明文件范围，系统自动拦截越界写入。
5. **声明验收条件**：用 `expected_artifacts` 和 `verification_commands` 声明产物，Worker 完成后自动校验。

---

## 5. 安全与隔离机制

### 5.1 PathGuard — 文件边界强制隔离

Worker 认领任务时自动激活：

- Worker 只能写 `writable_files` 声明的目录
- 路径穿越（如 `../../etc/passwd`）自动拦截并返回 `[BLOCKED]`
- `writable_files` 为空时跳过校验（向下兼容）

```python
await task_create(
    ...,
    writable_files=["D:\\ttt\\src\\"],
    read_only_files=["D:\\ttt\\docs\\"],
)
```

### 5.2 VerificationHooks — 产物质量门禁

Worker 标记完成前自动触发：

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

| 模块 | 职责 |
|------|------|
| `task_queue.py` | 基于文件同步锁的任务缓冲池，支持遗留目录向下兼容 |
| `mailbox.py` | 节点间消息通道，含完整文件锁防并发丢消息 |
| `self_claim_loop.py` | Worker 后台自动认领协程，Worker 启动时自动运行 |
| `team_config.py` | 团队配置，存储 Leader 完整 agent_id 供动态解析 |
| `path_guard.py` | 文件边界强制隔离，已集成到 task_claim 和 SelfClaimLoop |
| `verification_hooks.py` | 产物质量门禁，已集成到 task_complete 和 worker_idle_report |
| `loop_executor.py` | 非阻塞 DAG 执行引擎，使用 asyncio 不冻结事件循环 |
| `dependency_analyzer.py` | LLM 辅助任务拆解，解析失败时打印 WARNING 并 fallback 到启发式分析 |

---

## 8. DAG 执行模式示例

### 示例 A：纯串行

```text
需求：「依次完成调研 → 设计 → 实现 → 测试」

Wave 1: [调研]          (无依赖)
Wave 2: [设计]          (等调研完成)
Wave 3: [实现]          (等设计完成)
Wave 4: [测试]          (等实现完成)
```

```python
await dag_create(team_id="t", tasks=[
    {"name": "调研"},
    {"name": "设计",   "blocked_by": ["调研"]},
    {"name": "实现",   "blocked_by": ["设计"]},
    {"name": "测试",   "blocked_by": ["实现"]},
])
```

---

### 示例 B：纯并行

```text
需求：「同时爬取 5 个数据源，互不依赖」

Wave 1: [爬取源A] [爬取源B] [爬取源C] [爬取源D] [爬取源E]  (全部并发争抢)
```

```python
await dag_create(team_id="t", tasks=[
    {"name": "爬取源A", "description": "爬取 site-A"},
    {"name": "爬取源B", "description": "爬取 site-B"},
    {"name": "爬取源C", "description": "爬取 site-C"},
    {"name": "爬取源D", "description": "爬取 site-D"},
    {"name": "爬取源E", "description": "爬取 site-E"},
])
```

---

### 示例 C：串并行混合（博客系统）

```text
需求：「做一个带文章管理的轻量博客」

Wave 1: [DB Schema]                          (无依赖，先行)
Wave 2: [后端 API]  [前端页面]               (同时解锁，多 Worker 并发争抢)
Wave 3: [单元测试]                           (等后端完成)
Wave 4: [集成测试]                           (等前端+单元测试全部完成)
```

```python
await dag_create(team_id="t", tasks=[
    {"name": "DB Schema",  "description": "设计数据库表结构"},
    {"name": "后端 API",   "description": "实现 CRUD 接口",   "blocked_by": ["DB Schema"]},
    {"name": "前端页面",   "description": "实现管理界面",     "blocked_by": ["DB Schema"]},
    {"name": "单元测试",   "description": "后端单元测试",     "blocked_by": ["后端 API"]},
    {"name": "集成测试",   "description": "端到端测试",       "blocked_by": ["前端页面", "单元测试"]},
])
```

---

### 示例 D：Loop 迭代任务

```text
需求：「持续优化模型，直到准确率 >= 95%，最多迭代 5 次」

Wave 1: [数据预处理]          (无依赖)
Wave 2: [训练模型] × N 次     (loop，等数据就绪，迭代直到退出条件满足)
Wave 3: [生成报告]            (等训练循环完成)
```

```python
await dag_create(team_id="t", tasks=[
    {
        "name": "数据预处理",
        "description": "清洗数据，输出 data/train.csv",
    },
    {
        "name": "训练模型",
        "description": "训练并评估，若准确率 < 95% 则继续迭代",
        "blocked_by": ["数据预处理"],
        "task_type": "loop",
        "max_iterations": 5,
        "exit_condition": "accuracy >= 0.95",
    },
    {
        "name": "生成报告",
        "description": "汇总训练结果，产出 report.md",
        "blocked_by": ["训练模型"],
    },
])
```

---

### 示例 E：并行 + Loop（复杂场景）

```text
需求：「同时对 3 个城市的房价数据建模，每个城市独立迭代优化，最后汇总报告」

Wave 1: [采集北京] [采集上海] [采集广州]          (三城并发，无依赖)
Wave 2: [建模北京]×N [建模上海]×N [建模广州]×N   (各自独立 loop，并发运行)
Wave 3: [汇总报告]                                (等三个 loop 全部退出)
```

```python
await dag_create(team_id="t", tasks=[
    # --- Wave 1：三城并行采集 ---
    {"name": "采集北京", "description": "爬取北京链家数据，输出 data/bj.csv"},
    {"name": "采集上海", "description": "爬取上海链家数据，输出 data/sh.csv"},
    {"name": "采集广州", "description": "爬取广州链家数据，输出 data/gz.csv"},

    # --- Wave 2：三城各自独立 loop，互不阻塞 ---
    {
        "name": "建模北京",
        "description": "训练北京房价模型，RMSE < 5000 则退出",
        "blocked_by": ["采集北京"],
        "task_type": "loop",
        "max_iterations": 8,
        "exit_condition": "rmse < 5000",
    },
    {
        "name": "建模上海",
        "description": "训练上海房价模型，RMSE < 6000 则退出",
        "blocked_by": ["采集上海"],
        "task_type": "loop",
        "max_iterations": 8,
        "exit_condition": "rmse < 6000",
    },
    {
        "name": "建模广州",
        "description": "训练广州房价模型，RMSE < 4500 则退出",
        "blocked_by": ["采集广州"],
        "task_type": "loop",
        "max_iterations": 8,
        "exit_condition": "rmse < 4500",
    },

    # --- Wave 3：三城全部完成后汇总 ---
    {
        "name": "汇总报告",
        "description": "合并三城建模结果，生成对比分析报告 report.md",
        "blocked_by": ["建模北京", "建模上海", "建模广州"],
        "expected_artifacts": ["report.md"],
        "verification_commands": ["test -f report.md"],
    },
])

await dag_execute(team_id="t", max_waves=50)
```

执行流程说明：
- Wave 1 三个采集任务由三个 Worker 并发争抢，谁空闲谁认领
- Wave 2 三个 loop 任务彼此独立，各自迭代，互不等待
- 任一城市建模未达退出条件时，该任务自动进入下一轮迭代
- 三个 loop 全部退出后，Wave 3 汇总任务自动解锁

---

*Agent Team Skill v3.0*
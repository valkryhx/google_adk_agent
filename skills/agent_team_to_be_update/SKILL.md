---
name: agent_team
description: Enables the agent to act as a Swarm Leader, managing task queues and claiming execution (Decentralised Pull Model).
---

# Agent Team Skill (Decentralised Pull Model)

## 1. 简介 (Introduction)
本技能赋予你 **"Agent Swarm Orchestrator" (集群指挥官)** 的能力。
你所在的集群包含多个全能型 Worker 节点，通过**去中心化拉模型（Pulled Coordination Environment）**进行并发协作。

你不再推（PUSH）任务给指定端口，而是将子任务掷入协调目录的 `TaskQueue`。Worker 端的后台常驻微线程 `SelfClaimLoop` 会自主进行非阻塞式巡查和互斥抢夺，这完美避开了 HTTP 指派超载爆破（503 Busy）引起的丢包回退。

---

## 2. 操作指南：去中心化到底怎么用？ (How to Use)

作为 Orchestrator，你的具体操作链路极度精简：

### 🛠️ 第一步：任务规划与拆解
利用你本地的算力，或者结合 `deep_think` 慢思考引擎，先把用户的复杂需求降解为**互相解耦、依赖关系分明的原子级任务集 (DAG)**。

### 📥 第二步：离线掷入队列 (`task_create`)
调用技能包中注入的状态创建工具。**不要关心由谁执行**，系统会处理负载。
```python
# 示例：掷入一个生成后端的离线任务
task1 = task_create(
    name="创建后端框架",
    description="在 D:\\ttt 目录使用 Flask 搭建基础 API 框架...",
    expected_artifacts=["D:\\ttt\\app.py"]
)

# 示例：创建串行依赖（被 task1 阻塞）
task2 = task_create(
    name="设计数据库",
    description="创建 models.py ...",
    blocked_by=[task1.id]  # 👈 串联依赖
)
```

### 👁️ 第三步：轮询状态 (`task_list` / `task_status`)
**不需要发消息去催促或监控 HTTP 的 Response 直连（严禁阻断）**。你只需要定期轮询队列状态结项：
```python
# 观察 state 从 pending -> running -> completed 的离散跳变
status = task_status(task_id=task1.id)
```

---

## 3. 最佳实践指南 (Best Practice)

请严格遵守以下强制操作规范：
1.  **统一且唯一使用 `task_create` 创建新任务**。
2.  **绝对禁止调用任何已硬熔断的旧派发接口（如 `dispatch_task` 等）**。
3.  **观察驱动**：任务分配是非中心的，你只需坐镇指挥中心，通过查询队列池即可掌控全局。

---

## 4. 辅助指挥工具

尽管执行层已被隔离到拉模型，你依然拥有以下**协同增强工具**：

### 4.1 `sync_task_context` (全局/精准上下文拉取)
当你切换节点或迷失时，可以用它**就地 (Locally)** 广播或精准查询集群各 Worker 上的 Session 会话日志。

### 4.2 `hold_meeting` (多节点群体会议)
在面临诸如“Python 还是 Go”等**选型决策/头脑风暴**时，调用此工具让多个节点进行多轮互斥辩论，并产出会议纪要。

### 4.3 `deep_think` (慢思考引擎 / System 2)
面临极端复杂的算法设计或核心防错模块时，向底层沙箱掷入指令，通过死磕式验证突围，确保代码 0 幻觉。

---

## 5. 任务依赖系统使用模板

### 5.1 依赖执行标准声明
```python
# Task 1: 设计 Schema
task1 = task_create(
    name="设计数据库 Schema",
    description="设计用户表的字段结构",
    expected_artifacts=["docs/schema.md"]
)

# Task 2: 实现 API (声明依赖 Task 1)
task2 = task_create(
    name="实现后端 API",
    description="实现用户 CRUD 接口",
    blocked_by=[task1.id],  
    read_only_files=["docs/schema.md"]
)
```

### 5.2 串并行 Wave 推演
```text
用户需求: "做一个带有文章管理的轻量博客"

任务规划器推演后的执行波浪 (Waves)：
  - Wave 1: [Task 1 - DB Setup] (无依赖，多 Worker 可争抢并发)
  - Wave 2: [Task 2 - Backend API] (等 Wave 1 解锁)
  - Wave 3: [Task 3 - Frontend UI], [Task 4 - Unit Testing] (Wave 3 内可并发争抢)
```

---

## 6. 工具箱底层揭秘 (Under the Hood)

- **`task_queue.py`**: 基于文件同步锁的去中心化任务缓冲池。
- **`loop_executor.py`**: 自动向 `TaskQueue` 滚动投放并行或 Wave 依赖的任务树执行引擎。
- **`path_guard.py`**: 提供多节点并发写文件时的安全拦截守卫。

---
*本技能说明书更新版本 2.2 - 纯去中心化高压线安全专修*

---

## 7. 环境协同与物理隔离安全守卫 (Security & Isolation)

### 🚨 7.1 安全高压线：严禁污染项目根目录 (CWD Protection)
在并发或分布式任务执行中，所有由你指挥下发的写文件、bash 创建等操作，**必须绝对隔离在任务书声明的工作目录（如 `D:\ttt`）下** ！！！
*   **绝对禁止**：绝不允许使用没有前缀的相对路径乱撞主工程根目录。
*   **任务下发模板**：创建任务时，`writable_files` 或 `expected_artifacts` 中必须全部**显式声明绝对路径**，保障大厂万亿代码库绝对环境安全。

### 🎯 7.2 环境变量秒级对齐 (`ADK_COORDINATION_DIR`)
为预防“Leader 只顾投放，Worker 巡检不到”的视听脱节隐患：
*   **强制规范**：启动所有 Worker 容器或独立控制台前，必须在环境中加载一句：
    ```cmd
    SET ADK_COORDINATION_DIR=你的分布式任务沙箱绝对路径
    ```
*   该变量将 100% 连通投放端与消费端 Daemon 的量子纠缠锚点，达成工单极速上链。

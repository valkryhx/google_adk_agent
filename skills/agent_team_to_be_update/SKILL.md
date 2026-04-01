---
name: Agent 团队协作（去中心化拉模型）
description: 赋予 Agent 作为集群指挥官（Leader）的能力，通过去中心化任务队列将子任务派发给 Worker 节点并发执行。
---

# Agent Team Skill（去中心化拉模型）

> 版本 3.2

## 1. 简介

本技能赋予你 **集群指挥官（Swarm Orchestrator）** 的能力。

你的职责：**拆解任务 → 创建 DAG → 触发执行 → 监控进度**。

所有实际执行由 Worker 节点通过 `SelfClaimLoop` 自主抢占完成。

> **重要：你是 Leader，不要自己写代码或创建文件，所有执行工作派发给 Worker。**

---

## 2. 标准工作流（四步）

### 第 0 步：需求澄清（必须，禁止跳过）

> **硬性规则：调用任何 dag 工具之前，必须先完成需求澄清并获得用户的明确确认。**

向用户一次性列出以下问题，等待回复后再继续：

| 维度 | 问题 |
|------|------|
| **目标** | 核心目的是什么？成功的标志是什么？ |
| **产物** | 最终交付什么文件/功能？存放路径？ |
| **约束** | 技术栈、框架、路径有限制吗？需要兼容哪些现有代码？ |
| **验收** | 如何判断做对了？有没有现成测试命令？ |
| **优先级** | 如果范围需要取舍，哪部分最重要？ |

用户回复后，Leader **用一段话复述自己的理解**，结尾明确询问：

> 「以上理解是否正确？确认后我将开始拆解任务。」

用户回复「确认」/「是」/「没问题」等肯定词后，才可进入第一步。

> **注意：** 如果用户的原始指令已经非常详细，包含了产物路径、验收标准等，可以简化提问，只就不明确的部分提问，但复述确认步骤不可省略。

> **用户不清楚某项答案时：** 对于用户回答「不确定」/「你决定」/「随便」的维度，Leader **必须主动给出自己的推荐方案**，说明推荐理由，然后将推荐方案纳入复述中一并请用户确认。不允许以「用户未明确」为由留空或推迟决策。

---

### 第一步：规划并创建 DAG（`dag_create`）

```python
await dag_create(
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
            "blocked_by": ["设计数据库 Schema"],
        },
        {
            "name": "集成测试",
            "description": "端到端测试",
            "blocked_by": ["实现后端 API", "编写前端页面"],
        },
    ]
)
```

**依赖规则：**
- `blocked_by` 填任务名列表，系统自动解析为 task_id
- 无 `blocked_by` 的任务为第一波并发执行
- 依赖全部完成后自动解锁下一波

**任务字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 任务名（必填，用于 blocked_by 引用）|
| `description` | str | 任务描述，**越详细越好**，Worker 靠这个理解任务 |
| `blocked_by` | list[str] | 依赖的任务名列表 |
| `expected_artifacts` | list[str] | 预期产物文件路径 |
| `verification_commands` | list[str] | **验收命令**，Worker 完成后框架自动运行，全部通过才能 complete；失败则任务重置 pending 等待重试 |
| `writable_files` | list[str] | Worker 可写的文件路径 |
| `read_only_files` | list[str] | Worker 只读的参考文件 |

### 第二步：触发执行（`dag_execute`）

> **关键：创建完 DAG 后立即调用 `dag_execute`，无需检查 Worker 是否在线。**
> Worker 节点在后台自主抢占任务，不会向 Leader 注册，`team_list_workers()` 可能返回空但任务仍在执行。
> **严禁**以 `team_list_workers()` 返回空为由跳过或推迟 `dag_execute`。

```python
await dag_execute(max_polls=100)
```

> `max_polls`：最大轮询次数，每次间隔 3 秒，总等待上限 = `max_polls × 3` 秒。
> 默认 100 次 = 5 分钟。任务链较长时可适当调大（如 `max_polls=200`）。
> 单任务超时固定为 180 秒，超时自动回收并由其他 Worker 重新认领。

返回示例：
```
[DAG EXECUTED]
Waves: 3
Tasks: 4/4 完成
```

### 第三步：监控进度（按需）

```python
# 查看所有任务状态
await task_list()

# 查看单个任务详情
await task_status(task_id="task-a3f7c2d1")
```

---

## 3. 工具速查

| 工具 | 用途 |
|------|------|
| `dag_create(tasks)` | 批量创建 DAG 任务（推荐）|
| `dag_execute(max_polls)` | 触发 DAG 执行，等待所有任务完成 |
| `task_list()` | 查看所有任务状态 |
| `task_status(task_id)` | 查看单个任务详情 |
| `task_create(name, description, ...)` | 单独创建一个任务（低级 API）|
| `mailbox_send(to_agent, content)` | 向指定 Worker 发消息 |
| `mailbox_broadcast(content)` | 广播消息给所有 Worker |
| `mailbox_read()` | 读取收件箱 |
| `team_status()` | 查看团队整体状态 |
| `team_list_workers()` | 列出所有 Worker 节点 |
| `hold_meeting(topic)` | 发起多轮讨论会议 |
| `deep_think(task_instruction)` | 多路径深度思考 |

> 所有工具无需传 `team_id`，系统自动注入。

---

## 4. 编写高质量任务描述

Worker 没有上下文，只能靠 `description` 理解任务。**描述越详细，执行越准确。**

### 前置阅读规则（禁止跳过）

> **硬性规则：Worker 在写任何一行代码之前，必须先读懂现有代码。Leader 有责任在 `description` 和 `read_only_files` 中明确告知 Worker 需要读哪些文件。**

**规则一：`read_only_files` 必须填写**

只要项目目录中已有相关代码，就必须把需要参考的文件路径填入 `read_only_files`。不填等于让 Worker 盲写，必然产生不兼容代码。

**规则二：依赖链任务必须声明上游接口**

当任务有 `blocked_by` 时，上游任务的所有 `expected_artifacts` **必须出现在本任务的 `read_only_files` 中**，且 `description` 的 `【前置阅读】` 段要说明需要从上游文件理解什么接口/约定。

**规则三：`description` 必须使用四段式模板（见第 5 节）**

`【前置阅读】` 段不可省略。如确实无现有代码可读，填「无现有代码，从零开始」。

```python
await dag_create(
    tasks=[
        {
            "name": "创建后端 Flask 应用",
            "description": """
请在 D:\\myproject\\app.py 创建 Flask 后端，要求：
- 使用 SQLite 数据库（D:\\myproject\\data.db）
- 实现 GET /api/items 返回所有条目
- 实现 POST /api/items 新增条目（body: {title: str}）
- 端口 5000
""",
            "expected_artifacts": ["D:\\\\myproject\\\\app.py"],
            "writable_files": ["D:\\\\myproject\\\\"],
        },
    ]
)
```

### Windows 编码规范（在 Windows 环境部署时必读）

**规则：任何生成 Python 脚本的任务，`description` 中必须包含以下要求：**

> 脚本顶部（import 语句之后）必须加入 Windows UTF-8 编码修复块：
> ```python
> import sys
> if sys.platform == "win32":
>     import codecs
>     if hasattr(sys.stdout, "buffer"):
>         sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
>     if hasattr(sys.stderr, "buffer"):
>         sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")
> ```
> 否则任何包含中文或 emoji 的 `print()` 会触发 `UnicodeEncodeError` 崩溃。

**`verification_commands` 中运行 Python 的命令必须加 `PYTHONIOENCODING=utf-8` 前缀：**

```
# 正确
verification_commands: ["PYTHONIOENCODING=utf-8 pytest tests/test_foo.py -v"]

# 错误（中文输出会乱码或崩溃）
verification_commands: ["pytest tests/test_foo.py -v"]
```

---

## 5. TDD 工作流（必读）

**规则：任何会产生可执行代码的任务，必须满足：**
1. `description` 包含「验收标准」小节，说明如何验证正确性。
2. `verification_commands` 非空，填写可直接运行的测试/检查命令。
3. **测试代码必须作为独立任务拆出，不能合并进实现任务。**

Worker 节点框架会在代码执行完毕后**自动运行** `verification_commands`。全部通过才允许上报 `completed`；任意一条失败则任务重置为 `pending`，等待重新认领修复。

### DAG 强制结构（禁止省略）

每个功能模块的 DAG 必须包含以下三类任务，缺一不可：

| 任务类型 | 说明 | 依赖 |
|----------|------|------|
| **实现任务** | 写业务代码 | 无（或依赖设计任务）|
| **测试任务** | 写测试文件（`tests/test_xxx.py`）| 依赖实现任务 |
| **自测任务** | 运行测试并验证全部通过 | 依赖测试任务 |

> ❌ **禁止**把「写测试」和「写实现」合并成一个任务描述里的文字要求——Worker 会忽略测试部分只写实现代码。
> ✅ **必须**把测试单独拆成一个任务，`blocked_by` 实现任务，`verification_commands` 填运行测试的命令。

### 四段式任务描述模板

```
【前置阅读】: <必须先读哪些文件，从中理解哪些接口/数据结构/约定；无现有代码则填「无」>
【实现】: <做什么，输出什么文件>
【验收标准】: <怎么验证——测试文件路径 / 运行命令 / 期望输出>
【产物】: <expected_artifacts 中列出的文件路径>
```

### 示例：后端 API + 独立测试任务

```python
await dag_create(
    tasks=[
        {
            "name": "实现用户 API",
            "description": """
【前置阅读】: 无现有代码，从零开始

【实现】: 在 D:\\myproject\\app.py 创建 Flask 后端
- GET /api/users 返回用户列表
- POST /api/users 新增用户（body: {name: str}）
- 使用 SQLite（D:\\myproject\\data.db），端口 5000

【验收标准】: 服务启动无报错，curl http://localhost:5000/api/users 返回 200

【产物】: D:\\myproject\\app.py
""",
            "expected_artifacts": ["D:\\\\myproject\\\\app.py"],
            "writable_files": ["D:\\\\myproject\\\\"],
        },
        {
            "name": "编写测试用例",
            "description": """
【前置阅读】: 必须先读 D:\\myproject\\app.py，理解：
- 所有 API 路由和请求/响应格式
- 数据库路径和表结构
- 端口号
测试代码的接口调用必须与实现完全一致，不得假设。

【实现】: 在 D:\\myproject\\tests\\test_api.py 编写 pytest 测试
- 测试 GET /api/users 返回 200 和列表
- 测试 POST /api/users 新增成功

【验收标准】: 测试文件语法正确，可被 pytest 发现

【产物】: D:\\myproject\\tests\\test_api.py
""",
            "expected_artifacts": ["D:\\\\myproject\\\\tests\\\\test_api.py"],
            "read_only_files": ["D:\\\\myproject\\\\app.py"],
            "writable_files": ["D:\\\\myproject\\\\tests\\\\"],
            "blocked_by": ["实现用户 API"],
        },
        {
            "name": "运行测试验证",
            "description": """
【前置阅读】: 先读 D:\\myproject\\tests\\test_api.py 确认测试内容，再读 D:\\myproject\\app.py 确认服务启动方式。

【实现】: 启动 Flask 服务并运行全部测试，确保测试全部通过

【验收标准】:
- PYTHONIOENCODING=utf-8 pytest D:\\myproject\\tests\\test_api.py -v
- 所有用例 PASSED，无 FAILED

【产物】: 无（验证任务）
""",
            "read_only_files": [
                "D:\\\\myproject\\\\app.py",
                "D:\\\\myproject\\\\tests\\\\test_api.py",
            ],
            "verification_commands": [
                "PYTHONIOENCODING=utf-8 pytest D:\\\\myproject\\\\tests\\\\test_api.py -v"
            ],
            "blocked_by": ["编写测试用例"],
        },
    ]
)
```

> **注意**：`verification_commands` 中的命令需要在 Worker 的工作环境中可直接执行。优先使用 `pytest <path>` 或 `python -m pytest <path>`。

---

## 6. 循环任务（loop task）

适用于需要迭代优化直到满足退出条件的任务：

```python
await dag_create(
    tasks=[
        {
            "name": "训练模型",
            "description": "训练房价预测模型，RMSE < 5000 则退出",
            "task_type": "loop",
            "max_iterations": 10,
            "exit_condition": "rmse < 5000",
        },
    ]
)
await dag_execute(max_polls=50)
```

---

*Agent Team Skill v3.1*

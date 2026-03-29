---
name: Agent 团队协作（去中心化拉模型）
description: 赋予 Agent 作为集群指挥官（Leader）的能力，通过去中心化任务队列将子任务派发给 Worker 节点并发执行。
---

# Agent Team Skill（去中心化拉模型）

> 版本 3.1

## 1. 简介

本技能赋予你 **集群指挥官（Swarm Orchestrator）** 的能力。

你的职责：**拆解任务 → 创建 DAG → 触发执行 → 监控进度**。

所有实际执行由 Worker 节点通过 `SelfClaimLoop` 自主抢占完成。

> **重要：你是 Leader，不要自己写代码或创建文件，所有执行工作派发给 Worker。**

---

## 2. 标准工作流（三步）

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

Worker 节点框架会在代码执行完毕后**自动运行** `verification_commands`。全部通过才允许上报 `completed`；任意一条失败则任务重置为 `pending`，等待重新认领修复。

### 三段式任务描述模板

```
【实现】: <做什么，输出什么文件>
【验收标准】: <怎么验证——测试文件路径 / 运行命令 / 期望输出>
【产物】: <expected_artifacts 中列出的文件路径>
```

### 示例：后端 API + 自动测试

```python
await dag_create(
    tasks=[
        {
            "name": "实现用户 API",
            "description": """
【实现】: 在 D:\\myproject\\app.py 创建 Flask 后端
- GET /api/users 返回用户列表
- POST /api/users 新增用户（body: {name: str}）
- 使用 SQLite（D:\\myproject\\data.db），端口 5000

【验收标准】:
- 运行 pytest D:\\myproject\\tests\\test_api.py -v
- 所有测试用例通过

【产物】: D:\\myproject\\app.py, D:\\myproject\\tests\\test_api.py
""",
            "expected_artifacts": [
                "D:\\\\myproject\\\\app.py",
                "D:\\\\myproject\\\\tests\\\\test_api.py",
            ],
            "verification_commands": [
                "pytest D:\\\\myproject\\\\tests\\\\test_api.py -v"
            ],
            "writable_files": ["D:\\\\myproject\\\\"],
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

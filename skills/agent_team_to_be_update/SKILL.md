---
name: Agent 团队协作（去中心化拉模型）
description: 赋予 Agent 作为集群指挥官（Leader）的能力，通过去中心化任务队列将子任务派发给 Worker 节点并发执行。
---

# Agent Team Skill（去中心化拉模型）

> 版本 3.3

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

| 维度       | 问题                                               |
| ---------- | -------------------------------------------------- |
| **目标**   | 核心目的是什么？成功的标志是什么？                 |
| **产物**   | 最终交付什么文件/功能？存放路径？                  |
| **约束**   | 技术栈、框架、路径有限制吗？需要兼容哪些现有代码？ |
| **验收**   | 如何判断做对了？有没有现成测试命令？               |
| **优先级** | 如果范围需要取舍，哪部分最重要？                   |

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
            "blocked_by": [],  # ⚠️必须遵守：即使无依赖也必须显式写出空数组
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

**⚠️ 依赖强制规则（BLOCKED_BY 必须仔细设置）：**
- **因果关系不可违背：严禁为了追求“最大化并行”而删空 `blocked_by` 造成群集雪崩并发！** 任务越细，逻辑关系越需严谨。必须保证先有根基（建表、建框架），再有枝叶（分层API、前后台界面），最后有果实（联调与回归验收）。
- **谁读谁，谁依赖谁**：本任务如果要在 `read_only_files` 里引用某文件，则产出该文件的上游任务 **必须** 被填进本任务的 `blocked_by` 数组项中！
- 只有绝对孤立、无交互的底层初始化任务才允许空出此项作为第一波并发。

**任务字段说明：**

| 字段                    | 类型      | 说明                                                                                            |
| ----------------------- | --------- | ----------------------------------------------------------------------------------------------- |
| `name`                  | str       | 任务名（必填，用于 blocked_by 引用）                                                            |
| `description`           | str       | 任务描述，**越详细越好**，Worker 靠这个理解任务                                                 |
| `blocked_by`            | list[str] | 依赖的任务名列表                                                                                |
| `expected_artifacts`    | list[str] | 预期产物文件路径                                                                                |
| `verification_commands` | list[str] | **验收命令**，Worker 完成后框架自动运行，全部通过才能 complete；失败则任务重置 pending 等待重试 |
| `writable_files`        | list[str] | Worker 可写的文件路径                                                                           |
| `read_only_files`       | list[str] | Worker 只读的参考文件                                                                           |

### 第二步：触发执行（`dag_execute`）

> **关键：目前的 `dag_create` 工作流已经默认分离解耦（`auto_execute=False`）以满足即时展示需求。**
> 由于创建任务一瞬间底层节点其实已经开跑了，如果在此后没有启动长监听，前台将彻底假死收不到监控气泡并造成你与进展断联！
> **所以，在调用完 `dag_create` 拿到图谱汇报后，你必须在下一回合中立刻手动补充调用第二步工具：`dag_execute` ！**
> 当 `dag_execute` 最终返回给你 `[DAG EXECUTED]` 时，代表团队已经把这段死磕周期内的任务全打通。

### 第三步：监控进度（按需）

```python
# 查看所有任务状态
await task_list()

# 查看单个任务详情
await task_status(task_id="task-a3f7c2d1")
```

---

## 3. 工具速查

| 工具                              | 用途                            |
| --------------------------------- | ------------------------------- |
| `dag_create(tasks)`               | 批量创建 DAG 任务（推荐）       |
| `dag_execute(max_polls)`          | 触发 DAG 执行，等待所有任务完成 |
| `task_list()`                     | 查看所有任务状态                |
| `task_status(task_id)`            | 查看单个任务详情                |
| `mailbox_send(to_agent, content)` | 向指定 Worker 发消息            |
| `mailbox_broadcast(content)`      | 广播消息给所有 Worker           |
| `mailbox_read()`                  | 读取收件箱                      |
| `team_status()`                   | 查看团队整体状态                |
| `team_list_workers()`             | 列出所有 Worker 节点            |
| `hold_meeting(topic)`             | 发起多轮讨论会议                |
| `deep_think(task_instruction)`    | 多路径深度思考                  |

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

**`verification_commands` 中运行 Python 的命令在 Windows 中必须使用 `cmd` 合法写法，不允许直接照抄 Unix 风格前缀：**

```
# Windows 正确
verification_commands: ["set PYTHONIOENCODING=utf-8 && python -m pytest tests\\test_foo.py -v"]

# Unix-like 正确
verification_commands: ["PYTHONIOENCODING=utf-8 python -m pytest tests/test_foo.py -v"]

# Windows 错误：这是 Unix 风格前缀，不是 cmd.exe 合法写法
verification_commands: ["PYTHONIOENCODING=utf-8 pytest tests/test_foo.py -v"]

# 错误（中文输出会乱码或崩溃）
verification_commands: ["pytest tests/test_foo.py -v"]
```

**Windows 批处理 (`.bat`) 验收脚本的额外硬规则：**
- 第一行必须是 `@echo off`
- 如需切换到脚本所在目录，必须使用 `cd /d %~dp0`
- **禁止**在自动验收脚本中出现 `pause`
- `pip` 命令优先写成 `python -m pip ...`
- `pytest` 命令优先写成 `python -m pytest ...`

---

## 5. TDD 工作流（必读）

**规则：任何会产生可执行代码的任务，必须满足：**
1. `description` 包含「验收标准」小节，说明如何验证正确性。
2. `verification_commands` 非空，填写可直接运行的测试/检查命令。
3. **测试代码必须作为独立任务拆出，不能合并进实现任务。**

Worker 节点框架会在代码执行完毕后**自动运行** `verification_commands`。全部通过才允许上报 `completed`；任意一条失败则任务重置为 `pending`，等待重新认领修复。

### 测试验收时的安全关停服务规则（防崩溃封印）

> 🚨 **高危警告：** 
> 严禁在任何测试命令或验收脚本中使用基于进程名全局查杀的方法（如 `taskkill /F /IM python.exe` 或 `pkill -f python`）来结束自己拉起的测试后台服务！这会导致宿主机上的 Swarm 集群主控与其余 Agent 同归于尽，使系统发生毁灭性崩溃及无声断联。

**如果在此步骤你需要启停后台 Web 测试服务（如跑 `run.py` 后再验证接口）**：
1. **避让核心端口**：你的测试服务必须跑到保留端口 (8000~8010) 之外，例如选用 5000 端口。
2. **跨平台优雅控制**：Windows Shell `cmd` 并无法像 Linux 那样获取 `$!` 实现异步杀进程，若使用这种命令必将失败。强烈建议单独编写一个验收用的 Python 脚本，并使用 `process = subprocess.Popen(...)` 拉起服务，在 `requests` 断言请求结束后跟上 `process.terminate()` 来安全释放。
3. **精准放行**：即便非要在 Bash 中强杀，底层系统也只能接受指名道姓的具体 PID 参数查杀 (如 `taskkill /PID 1234 /F`)。

**再加三条硬禁令（都是 Windows 高危坑）：**
4. **禁止**在 Windows 集成测试 teardown 中使用 `proc.send_signal(signal.CTRL_C_EVENT)`。这类控制台信号可能误伤宿主机上同控制台/同进程组的 ADK 或 Swarm 节点。
5. **禁止**长时间运行的后台 Web 测试服务默认使用 `stdout=subprocess.PIPE` 和 `stderr=subprocess.PIPE` 却不消费输出。优先使用 `subprocess.DEVNULL`，否则容易造成卡死、未关闭 transport 和 event loop 噪声。
6. **禁止**使用 shell 技巧（含 `start /b`、`&`、`$!`、`jobs`）管理验收服务生命周期。必须由 Python `subprocess.Popen` 持有进程句柄，并用 `terminate()` / `kill()` 定点回收。

**Windows 集成测试 / 验收脚本最小安全模板（优先照抄）：**

```python
proc = subprocess.Popen(
    [sys.executable, run_script],
    cwd=BACKEND_DIR,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
)

try:
    # healthcheck / requests assertions
    ...
finally:
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)
```

**Windows `run_tests.bat` 最小模板（优先照抄）：**

```bat
@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d %~dp0

python -m pip install -r backend\\requirements.txt || exit /b 1
python backend\\init_db.py || exit /b 1
python -m pytest tests\\test_api.py -v || exit /b 1
python -m pytest tests\\integration_test.py -v || exit /b 1
exit /b 0
```

### DAG 强制结构（禁止省略）

每个功能模块的 DAG 必须包含以下三类任务，缺一不可：

| 任务类型     | 说明                              | 依赖                 |
| ------------ | --------------------------------- | -------------------- |
| **实现任务** | 写业务代码                        | 无（或依赖设计任务） |
| **测试任务** | 写测试文件（`tests/test_xxx.py`） | 依赖实现任务         |
| **自测任务** | 运行测试并验证全部通过            | 依赖测试任务         |

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
- set PYTHONIOENCODING=utf-8 && python -m pytest D:\\myproject\\tests\\test_api.py -v
- 所有用例 PASSED，无 FAILED

【产物】: 无（验证任务）
""",
            "read_only_files": [
                "D:\\\\myproject\\\\app.py",
                "D:\\\\myproject\\\\tests\\\\test_api.py",
            ],
            "verification_commands": [
                "set PYTHONIOENCODING=utf-8 && python -m pytest D:\\\\myproject\\\\tests\\\\test_api.py -v"
            ],
            "blocked_by": ["编写测试用例"],
        },
    ]
)
```

> **注意**：`verification_commands` 中的命令需要在 Worker 的工作环境中可直接执行。Windows 优先使用 `set PYTHONIOENCODING=utf-8 && python -m pytest <path>`；其他环境优先使用 `PYTHONIOENCODING=utf-8 python -m pytest <path>`。

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
```

---

*Agent Team Skill v3.3*

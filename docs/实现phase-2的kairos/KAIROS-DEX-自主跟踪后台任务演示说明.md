# KAIROS-DEX 自主跟踪后台任务演示说明

> 记录时间: 2026-04-04
> 演示目标: 证明 **Dex 真实执行后台任务**，且 **KAIROS 能自主跟踪任务状态并在前端正确显示**
> 服务地址: `http://127.0.0.1:8000`
> 适用前端: `src/adk_agent/static/script.js`（已接入 `tracked_dex_tasks` 面板渲染）

---

## 1. 这份说明要证明什么

这次演示不是单纯验证“能注册一个 task_id”，而是完整验证下面这条链路：

1. 创建一个真实 Dex 任务
2. 把这个任务注册给当前会话的 KAIROS runtime
3. KAIROS 状态进入 `handoff`
4. 前端 `Tracked Dex Tasks` 面板显示该任务为 `pending/running`
5. 真正启动 Dex 任务
6. KAIROS 在后续 tick 中自主发现它已 `completed/failed`
7. KAIROS 把结果写入 `recent_events`
8. KAIROS 自动把该任务从 `tracked_dex_task_ids` 中移除
9. 前端刷新后，`Tracked Dex Tasks` 面板与后端最终状态保持一致

一句话总结：

> **Dex 负责跑任务，KAIROS 负责跟踪任务，前端负责把 KAIROS 看到的状态展示出来。**

---

## 2. 本次验证中涉及的关键代码位置

### 2.1 KAIROS runtime
- `src/adk_agent/kairos/runtime.py:106-112` — `register_dex_task()`
- `src/adk_agent/kairos/runtime.py:116-180` — `tick_once()`
- `src/adk_agent/kairos/runtime.py:182-203` — `get_status()` 返回 `tracked_dex_tasks`
- `src/adk_agent/kairos/runtime.py:219-240` — `_poll_dex()` 轮询 Dex 任务并在完成后移除 tracked id

### 2.2 Dex bridge
- `src/adk_agent/kairos/dex_bridge.py:22-55` — `KairosDexBridge`
- `get_tasks()` 会把 Dex 任务转换成 KAIROS status 可消费的 snapshot

### 2.3 前端 script.js
- `src/adk_agent/static/script.js` 中：
  - `formatKairosTrackedTasks()` — 格式化 tracked task 文本
  - `refreshKairosStatus()` — 刷新 `#kairosStatus / #kairosEvents / #kairosTrackedDexTasks`
  - `registerDexHandoff()` — 注册 Dex handoff

### 2.4 后端 API
- `src/adk_agent/kairos/api.py:97-103` — `POST /api/sessions/{session_id}/kairos/dex/register`
- `src/adk_agent/kairos/api.py:63-68` — `GET /api/sessions/{session_id}/kairos/status`

---

## 3. 本次我真实跑过的一次验证结果

### 3.1 使用的真实会话与任务
- **Session ID**: `session_1775293289456_e588d9f2`
- **Dex Task ID**: `2e7a435a`
- **任务描述**: `playwright dex handoff`
- **任务命令**:

```bash
python -c "print(\"dex task from playwright completed\")"
```

### 3.2 注册后、启动前的状态
真实注册 handoff 后，KAIROS status 返回：

- `mode = handoff`
- `tracked_dex_task_ids = ["2e7a435a"]`
- `tracked_dex_tasks` 中出现：
  - `task_id = 2e7a435a`
  - `status = pending`
  - `description = playwright dex handoff`
  - `log_path = D:\git_repos\google_adk_agent\.dex\logs\user_001\2e7a435a.log`

前端 `Tracked Dex Tasks` 面板显示为：

```text
- 2e7a435a [pending]
desc: playwright dex handoff
created: 2026-04-04T09:39:48.944758+00:00
completed: -
summary: -
log: D:\git_repos\google_adk_agent\.dex\logs\user_001\2e7a435a.log
```

### 3.3 任务真正启动后
Dex 任务状态进入：

- `running`

随后很快进入：

- `completed`
- `result_summary = dex task from playwright completed`

### 3.4 KAIROS 在任务完成后的观察结果
在 KAIROS 的 status 中，先观察到：

- `tracked_dex_task_ids = ["2e7a435a"]`
- `tracked_dex_tasks[0].status = completed`
- `tracked_dex_tasks[0].result_summary = dex task from playwright completed`

随后在下一轮 tick 中，KAIROS 自动完成了收尾：

- `mode = idle`
- `tracked_dex_task_ids = []`
- `tracked_dex_tasks = []`

同时 `recent_events` 出现关键记录：

```text
Dex task 2e7a435a completed: playwright dex handoff — dex task from playwright completed
```

### 3.5 前端最终表现
前端点击 `刷新状态` 后，看到：

- `Tracked Dex Tasks` 面板变回：`无`
- `mode` 从 `handoff` 回到 `idle`
- `tracked_dex_task_ids` 显示为空

这不是前端丢数据，而是因为：

> **KAIROS 已经确认任务完成，并把它从 tracked 列表中移除了。**

因此前端与后端最终状态是一致的。

---

## 4. 可重复执行的回归测试步骤

下面这套流程可以重复执行，用于验证“Dex 真实后台任务 + KAIROS 自主跟踪 + 前端展示”是否仍然正常。

### Step 1：启动服务

在项目根目录执行：

```bash
PYTHONIOENCODING=utf-8 python -m src.adk_agent.main_web_start_steering --port 8000
```

打开浏览器：

- `http://127.0.0.1:8000`

---

### Step 2：选择一个会话

可以：
- 点击左侧 `发起新对话`
- 或选择一个已有会话

要求：
- `sessionStorage.current_session_id` 不为空
- 打开 `KAIROS` modal 时，不应显示“请先选择或创建一个对话”

---

### Step 3：启动 KAIROS

在左侧点击：
- `KAIROS`
- 再点击：`启动`

预期：
- 弹窗提示：`KAIROS 启动成功`
- 状态区可见：
  - `enabled: true`
  - `running: true`
  - `mode: idle` 或 `mode: sleeping`

---

### Step 4：创建一个真实 Dex 任务

#### 方式 A：通过 Python 直接创建（推荐，最稳定）

```python
from skills.dex.tools import DexManager

manager = DexManager(base_dir=r"D:/git_repos/google_adk_agent", user_id="user_001")
task = manager.create_task("playwright dex handoff", "ui verification task")
print(task["id"])
```

记住返回的 `task_id`。

#### 方式 B：通过 agent / dex skill 创建
也可以让 agent 调用 Dex 创建任务，但为了回归测试稳定性，推荐优先使用方式 A。

---

### Step 5：把这个 Dex task 注册给当前会话的 KAIROS

调用接口：

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/<SID>/kairos/dex/register \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "dynamic_expert",
    "user_id": "user_001",
    "task_id": "<TASK_ID>",
    "description": "playwright dex handoff"
  }'
```

预期：
- `mode == "handoff"`
- `tracked_dex_task_ids` 包含 `<TASK_ID>`
- `recent_events` 中出现：

```text
dex handoff registered: <TASK_ID> playwright dex handoff
```

---

### Step 6：前端刷新并确认任务出现在 `Tracked Dex Tasks`

在 KAIROS 面板点击：
- `刷新状态`

预期前端显示类似：

```text
- <TASK_ID> [pending]
desc: playwright dex handoff
created: <timestamp>
completed: -
summary: -
log: <log_path>
```

同时状态区应显示：
- `mode: handoff`
- `tracked_dex_task_ids: <TASK_ID>`

---

### Step 7：真正启动这个 Dex 任务

用 Python 启动后台进程：

```python
from skills.dex.tools import DexManager

manager = DexManager(base_dir=r"D:/git_repos/google_adk_agent", user_id="user_001")
manager.start_background_process(
    "<TASK_ID>",
    ["python", "-c", 'print("dex task from playwright completed")']
)
```

如果要演示稍微长一点的任务，可以换成：

```python
manager.start_background_process(
    "<TASK_ID>",
    ["python", "-c", 'import time; print("task start"); time.sleep(5); print("task done")']
)
```

---

### Step 8：轮询 Dex 与 KAIROS 状态

#### 查看 Dex 任务状态

```python
from skills.dex.tools import DexManager
manager = DexManager(base_dir=r"D:/git_repos/google_adk_agent", user_id="user_001")
print(manager.load_task("<TASK_ID>"))
```

预期任务经历：
- `pending`
- `running`
- `completed` 或 `failed`

#### 查看 KAIROS 状态

```bash
curl "http://127.0.0.1:8000/api/sessions/<SID>/kairos/status?app_name=dynamic_expert&user_id=user_001"
```

预期观察顺序：
1. 任务刚完成时：
   - `tracked_dex_tasks` 中还能看到它，状态为 `completed`
2. 下一轮 tick 后：
   - `tracked_dex_task_ids == []`
   - `tracked_dex_tasks == []`
   - `mode` 回到 `idle`
   - `recent_events` 新增一条 `Dex task <TASK_ID> completed: ...`

---

### Step 9：回到前端确认 KAIROS 已消费该任务

在 KAIROS 面板点击：
- `刷新状态`

预期：
- `Tracked Dex Tasks` 重新显示：`无`
- 状态区里：
  - `mode: idle`
  - `tracked_dex_task_ids: -`
- 最近事件区出现类似：

```text
Dex task <TASK_ID> completed: playwright dex handoff — dex task from playwright completed
```

---

## 5. 成功判定标准

这次回归测试要判定为成功，至少要满足以下全部条件：

1. Dex 任务能被真实创建
2. Dex 任务能被真实启动
3. KAIROS 注册 handoff 后进入 `handoff`
4. 前端 `Tracked Dex Tasks` 面板能显示任务详细信息
5. 任务完成后，KAIROS status 能看到 `completed` 状态和结果摘要
6. KAIROS 会把完成事件写进 `recent_events`
7. 下一轮 tick 后，KAIROS 会把该任务从 tracked 列表中移除
8. 前端刷新后，最终 UI 与后端状态一致

---

## 7. 本次提交前实际跑过的回归测试

下面这些测试已在本次前端融合与 Dex/KAIROS 联调完成后实际执行通过：

### 7.1 前端回归测试

命令：

```bash
python -m pytest tests/kairos/test_frontend_script_kairos_ui.py -q
```

结果：

```text
2 passed
```

覆盖点：
- `script.js` 是否暴露 Kairos helper：
  - `formatKairosTrackedTasks()`
  - `formatKairosEvents()`
  - `formatKairosStatus()`
  - `kairosRequest()`
- `refreshKairosStatus()` 是否更新 `#kairosTrackedDexTasks`
- start / stop / wake / schedules / dex register 是否改为通过 `kairosRequest()` 统一请求

### 7.2 Dex 测试

命令：

```bash
python -m pytest tests/dex -q
```

结果：

```text
6 passed
```

说明：
- Dex 的任务创建、存储、执行与工具接口在当前代码状态下可正常工作

### 7.3 Kairos 核心回归测试

命令：

```bash
python -m pytest tests/kairos/test_api.py tests/kairos/test_dex_bridge.py tests/kairos/test_runtime.py tests/kairos/test_kairos_no_pollution.py -q
```

结果：

```text
41 passed
```

覆盖点：
- Kairos API 路由
- Dex bridge 与 Kairos runtime 的衔接
- runtime tick / wake / handoff 行为
- KAIROS 不污染用户对话历史的关键回归

### 7.4 前端语法检查

命令：

```bash
node --check src/adk_agent/static/script.js
```

结果：

```text
通过
```

说明：
- 当前前端脚本在提交前已通过语法校验

---

## 8. 本次验证的最终结论

本次真实验证已经证明：

- **Dex 任务确实真实跑起来了**
- **KAIROS 在任务进行/完成时确实能看到它**
- **KAIROS 会在任务完成后自动记录结果，并自动清理 tracked 列表**
- **前端 `Tracked Dex Tasks` 面板已经正确接入并能反映任务状态变化**
- **提交前相关自动化测试与语法检查已通过**

因此目前这条链路已经具备可演示性与回归验证基础：

> **KAIROS 可以自主跟踪 Dex 后台任务，而不需要人工持续轮询。**

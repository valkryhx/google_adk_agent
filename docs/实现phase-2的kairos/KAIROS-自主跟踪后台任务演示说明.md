# KAIROS 自主跟踪后台任务演示说明

> 记录时间: 2026-04-04
> 演示方式: 真实 HTTP 接口联调
> 服务地址: `http://127.0.0.1:8000`

---

## 1. 这个演示要证明什么

这个演示要证明：

> **Dex 负责执行后台长任务，KAIROS 负责自主跟踪任务进度；任务完成后，KAIROS 会自己发现并记录结果。**

换句话说，不需要人工反复调用 Dex 查询任务状态，KAIROS 自己会在 runtime tick 中完成这件事。

---

## 2. 涉及的关键能力

### Dex 负责的事情
- 创建后台任务
- 启动后台进程
- 保存任务状态（pending / running / completed / failed）

### KAIROS 负责的事情
- 维护自己的 runtime 状态
- 在 tick 中轮询 Dex 任务状态
- 当任务完成/失败时，把结果写入 `recent_events`
- 自动把已结束任务从 `tracked_dex_task_ids` 中移除

---

## 3. 相关代码位置

### KAIROS runtime
- `src/adk_agent/kairos/runtime.py:106` — 注册 Dex 任务
- `src/adk_agent/kairos/runtime.py:116` — `tick_once()`
- `src/adk_agent/kairos/runtime.py:205` — `_poll_dex()`

### Dex bridge
- `src/adk_agent/kairos/dex_bridge.py:17` — `KairosDexBridge`
- `src/adk_agent/kairos/dex_bridge.py:33` — `get_tasks()`

### Dex skill
- `skills/dex/tools.py:181` — `dex_create_task`
- `skills/dex/tools.py:200` — `dex_start_task`
- `skills/dex/tools.py:223` — `dex_list_tasks`
- `skills/dex/tools.py:239` — `dex_get_task_details`

---

## 4. 我刚刚真实跑过的一次接口演示结果

这次演示不是伪造数据，而是我直接对本地 8000 端口服务做的真实接口调用。

### 4.1 会话信息
- **Session ID**: `session_1775239855513_18f4782e`
- **Dex Task ID**: `8211688c`
- **任务描述**: `演示 kairos 自动跟踪任务进度`

### 4.2 我实际做的步骤

#### Step 1：创建会话
调用：
- `POST /api/sessions`

返回了新的 session：
- `session_1775239855513_18f4782e`

#### Step 2：让 agent 加载 Dex skill
通过聊天接口发送：

```text
skill_load("dex")
```

agent 成功返回：
- dex 技能已加载

#### Step 3：让 agent 创建并启动后台任务
通过聊天接口发送：

```text
请立即调用 dex_create_task 和 dex_start_task。创建一个后台演示任务，描述为“演示 kairos 自动跟踪任务进度”。启动命令必须原样使用：python -c "import time; print('task start'); time.sleep(10); print('task done')"。最后只输出一行：TASK_ID=<任务ID>
```

agent 最终返回：

```text
TASK_ID=8211688c
```

#### Step 4：启动 KAIROS
调用：
- `POST /api/sessions/{session_id}/kairos/start`

返回关键状态：
- `enabled: true`
- `running: true`
- `mode: idle`

#### Step 5：把 Dex 任务注册给 KAIROS
调用：
- `POST /api/sessions/{session_id}/kairos/dex/register`

传入：
- `task_id = 8211688c`
- `description = 演示 kairos 自动跟踪任务进度`

返回关键状态：
- `mode: handoff`
- `tracked_dex_task_ids: ["8211688c"]`

#### Step 6：轮询 KAIROS 状态，等待它自主发现任务完成
调用：
- `GET /api/sessions/{session_id}/kairos/status`

期间观察到：

- 起初：
  - `mode=handoff`
  - `tracked=['8211688c']`

- 一段时间后：
  - `mode=idle`
  - `tracked=[]`

### 4.3 KAIROS 最终记录到的关键事件
在 `recent_events` 中，出现了两条关键记录：

```text
dex handoff registered: 8211688c 演示 kairos 自动跟踪任务进度
Dex task 8211688c completed: 演示 kairos 自动跟踪任务进度
```

这说明：

1. KAIROS 确实接手了这个后台任务的跟踪责任
2. KAIROS 确实在后续 tick 中自己发现了任务完成
3. 任务完成后，它自动把任务从追踪列表中移除了

### 4.4 这次真实接口测试的最终结论

**结论：演示成功。**

可确认当前系统已经支持：

- agent 创建 Dex 后台任务
- KAIROS 接管该任务的进度跟踪
- KAIROS 自主轮询后台任务状态
- KAIROS 在任务完成时自动产生完成事件

---

## 5. 建议的现场演示流程

### Step 1：启动服务

```bash
PYTHONIOENCODING=utf-8 python -m src.adk_agent.main_web_start_steering --port 8000
```

打开：
- `http://127.0.0.1:8000`

### Step 2：新建会话
点击左侧：
- `发起新对话`

### Step 3：加载 Dex
聊天框输入：

```text
skill_load("dex")
```

### Step 4：让 agent 创建一个后台任务
聊天框输入：

```text
请用 dex 创建一个后台任务，描述为“演示 kairos 自动跟踪任务进度”，并启动命令：
python -c "import time; print('task start'); time.sleep(10); print('task done')"
执行后把 task_id 告诉我。
```

### Step 5：启动 KAIROS
打开左侧 `KAIROS` 面板，点击：
- `启动`

预期：
- `running: true`
- `mode: idle`

### Step 6：注册 Dex Handoff
在 `注册 Dex Handoff` 区域填写：
- `task_id`: 刚才返回的 task id
- `description`: `演示 kairos 自动跟踪任务进度`

点击：
- `注册`

预期：
- `tracked_dex_task_ids` 出现任务 ID
- `mode` 变成 `handoff`

### Step 7：等待 KAIROS 自己发现完成
不要手动查 Dex。

隔几秒点：
- `刷新状态`

预期会看到：
- `tracked_dex_task_ids` 变成空
- `mode` 从 `handoff` 回到 `idle`
- `recent_events` 出现：

```text
dex handoff registered: <task_id> 演示 kairos 自动跟踪任务进度
Dex task <task_id> completed: 演示 kairos 自动跟踪任务进度
```

---

## 6. 现场讲解时可直接使用的话术

### 简版话术

“Dex 负责执行长任务，KAIROS 负责自主追踪任务进度。任务完成后，不需要人工轮询，KAIROS 会自己发现并记录结果。”

### 稍完整一点的话术

“我先让 agent 用 Dex 创建一个后台任务。然后把这个任务交给 KAIROS 跟踪。接下来我不手动查任务状态，而是让 KAIROS 自己 tick。等任务完成后，KAIROS 会自动在 recent events 里记录完成结果。”

---

## 7. 当前演示的边界

### 已经具备的能力
- 能追踪 Dex 后台任务状态
- 能在任务完成/失败时自动记录事件
- 能自动维护 `tracked_dex_task_ids`
- 能把 mode 从 `handoff` 回切到 `idle`

### 还没有完全做成“高级汇报助手”的部分
当前 KAIROS 更像：
- runtime + poller + state machine

也就是说，它已经会：
- 自主检查任务进度
- 自主发现任务完成
- 自主记录事件

但它还没有完全演进成：
- 自动读取完整日志
- 自动总结后台任务结果
- 自动把结果以自然语言推送回主对话

所以当前最准确的表述是：

> **KAIROS 已经具备“自主跟踪后台任务进度”的能力。**

---

## 8. 一句话总结

这次真实接口测试已经证明：

> **KAIROS 现在可以接手 Dex 后台任务的进度跟踪，并在任务完成时自主发现状态变化。**

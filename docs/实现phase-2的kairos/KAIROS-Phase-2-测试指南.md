# KAIROS Phase 2 测试指南

## 0. 前端 UI 测试（推荐）

### 启动服务

```bash
PYTHONIOENCODING=utf-8 python -m src.adk_agent.main_web_start_steering --port 8000
```

### 打开浏览器

访问 `http://127.0.0.1:8000`

### 操作步骤

1. **创建或选择一个对话** — 点击左侧「发起新对话」或选择已有对话
2. **打开 KAIROS 面板** — 点击左侧边栏底部的 **KAIROS** 按钮（时钟图标）
3. **启动 KAIROS** — 点击「启动」按钮，观察状态变为 `mode: idle`, `running: true`
4. **唤醒** — 在「唤醒原因」输入框填写原因（默认 `manual_smoke`），点击「唤醒」，观察状态经历 `idle → running → sleeping`
5. **注册 Schedule** — 填写 schedule_id / cron / reason，点击「添加 Schedule」，在状态区看到 schedules 信息
6. **删除 Schedule** — 填写 schedule_id，点击「删除 Schedule」
7. **注册 Dex Handoff** — 填写 task_id / description，点击「注册」，观察 mode 变为 `handoff`
8. **刷新状态** — 随时点击「刷新状态」查看最新 runtime 状态和事件
9. **停止 KAIROS** — 点击「停止」，确认 `mode: stopped`

### 预期观察

- 「运行状态」区域实时显示 mode / schedules / triggers / dex_tasks
- 「最近事件」区域显示 runtime started / wake requested / turn started / turn finished 等事件
- 所有操作即时反馈，无需手动刷新（操作后自动更新状态）

---

## 1. 自动化测试

在项目根目录执行：

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/ -v
```

预期结果：`61 passed`

---

## 2. 手工 Smoke Test

### Step 1：启动服务

```bash
PYTHONIOENCODING=utf-8 python -m src.adk_agent.main_web_start_steering --port 8000
```

### Step 2：创建 session

```bash
curl -X POST http://127.0.0.1:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"app_name":"assistant","user_id":"alice"}'
```

记住返回的 `session_id`，后续用 `<SID>` 代替。

### Step 3：启动 KAIROS runtime

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/<SID>/kairos/start \
  -H "Content-Type: application/json" \
  -d '{"app_name":"assistant","user_id":"alice"}'
```

预期：`kairos.enabled=true`, `kairos.mode="idle"`

---

### Step 4：注册 cron schedule（Phase 2 新功能）

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/<SID>/kairos/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "assistant",
    "user_id": "alice",
    "schedule_id": "morning",
    "cron": "*/5 * * * *",
    "reason": "morning_checkin"
  }'
```

预期：
- `kairos.schedules[0].schedule_id == "morning"`
- `kairos.schedules[0].next_fire_at` 有值（下一个 5 分钟整点）

### Step 5：查看 status，确认 schedule 已注册

```bash
curl "http://127.0.0.1:8000/api/sessions/<SID>/kairos/status?app_name=assistant&user_id=alice"
```

预期新增字段：
- `last_tick_at` — 有值
- `schedules` — 包含刚注册的 schedule
- `pending_triggers` — 空数组
- `active_trigger` — null

### Step 6：删除 schedule

```bash
curl -X DELETE "http://127.0.0.1:8000/api/sessions/<SID>/kairos/schedules/morning?app_name=assistant&user_id=alice"
```

预期：`kairos.schedules == []`

---

### Step 7：注册 Dex handoff（Phase 2 新功能）

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/<SID>/kairos/dex/register \
  -H "Content-Type: application/json" \
  -d '{
    "app_name": "assistant",
    "user_id": "alice",
    "task_id": "abc12345",
    "description": "run report"
  }'
```

预期：
- `kairos.tracked_dex_task_ids` 包含 `"abc12345"`
- `kairos.mode == "handoff"`
- `recent_events` 中出现 `"dex handoff registered: abc12345 run report"`

### Step 8：查看 status 确认 handoff 状态

```bash
curl "http://127.0.0.1:8000/api/sessions/<SID>/kairos/status?app_name=assistant&user_id=alice"
```

预期：`mode == "handoff"`, `tracked_dex_task_ids == ["abc12345"]`

---

### Step 9：使用 attach 路由查看 runtime snapshot（Phase 2 新功能）

```bash
curl "http://127.0.0.1:8000/api/sessions/<SID>/kairos/attach?app_name=assistant&user_id=alice"
```

预期返回：
```json
{
  "status": "ok",
  "session_id": "<SID>",
  "kairos": { ... },
  "attach": {
    "app_name": "assistant",
    "user_id": "alice",
    "session_id": "<SID>",
    "mode": "handoff",
    "running": true,
    "recent_events": [ ... ]
  }
}
```

### Step 10：列出用户所有活跃 KAIROS session（Phase 2 新功能）

```bash
curl "http://127.0.0.1:8000/api/kairos/sessions?user_id=alice"
```

预期：`sessions` 数组中包含当前 session 的摘要信息。

---

### Step 11：手动 wake 并观察 trigger 执行（验证 Phase 1 兼容）

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/<SID>/kairos/wake \
  -H "Content-Type: application/json" \
  -d '{"app_name":"assistant","user_id":"alice","reason":"manual_smoke"}'
```

轮询 status 观察：
1. `pending_triggers` 出现 MANUAL trigger
2. `mode` 变为 `"running"`
3. turn 完成后 `mode` 变为 `"sleeping"`
4. `recent_events` 出现 `kairos turn started` 和 `kairos turn finished`

### Step 12：停止 runtime

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/<SID>/kairos/stop \
  -H "Content-Type: application/json" \
  -d '{"app_name":"assistant","user_id":"alice"}'
```

预期：`mode == "stopped"`, `running == false`

---

## 3. Phase 2 新增 API 汇总

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/sessions/{sid}/kairos/schedules` | 注册 cron schedule |
| DELETE | `/api/sessions/{sid}/kairos/schedules/{schedule_id}` | 删除 schedule |
| POST | `/api/sessions/{sid}/kairos/dex/register` | 注册 Dex handoff 任务 |
| GET | `/api/sessions/{sid}/kairos/attach` | 获取 runtime snapshot |
| GET | `/api/kairos/sessions?user_id=<USER>` | 列出用户活跃 KAIROS session |

## 4. status 返回结构（Phase 2 扩展）

```json
{
  "status": "ok",
  "session_id": "...",
  "kairos": {
    "enabled": true,
    "running": true,
    "busy": false,
    "mode": "sleeping",
    "sleep_until": "2026-04-03T12:15:00+00:00",
    "last_tick_at": "2026-04-03T12:00:00+00:00",
    "pending_wake_reason": null,
    "active_trigger": null,
    "pending_triggers": [],
    "tracked_dex_task_ids": [],
    "schedules": [
      {
        "schedule_id": "morning",
        "cron": "*/5 * * * *",
        "reason": "morning_checkin",
        "enabled": true,
        "next_fire_at": "2026-04-03T12:05:00+00:00"
      }
    ],
    "recent_events": [ ... ]
  }
}
```

# KAIROS Phase 1 完成说明与测试指南

## 1. 当前远端状态

当前远端 `origin/main` 已经包含本轮 KAIROS Phase 1 提交。

校验结果：

- 本地 `HEAD`: `233edcd0a4e17dab92b6d145dbe2f784006b90c5`
- 远端 `origin/main`: `233edcd0a4e17dab92b6d145dbe2f784006b90c5`
- 远端最新提交：
  - `233edcd feat(kairos): implement phase 1 runtime flow`

说明当前主分支远端与本地提交一致。

---

## 2. Phase 1 KAIROS 当前已经具备的能力

当前 Phase 1 已具备：

- 单 session assistant runtime
- `start / stop / wake / status` API
- 后台 loop 驱动的 tick
- `wake -> autonomous turn -> sleep` 真实链路
- `session.state["kairos"]` 持久化
- append-only `_kairos.md` activity log
- Dex tracked task polling
- worker busy 避让
- `recent_events` 暴露 runtime 状态
- `SteeringSession` 与 KAIROS runtime 接线
- 共享 Runner 主执行骨架

也就是说，现在已经是一个真实可运行的 KAIROS-lite，而不只是设计或占位实现。

---

## 3. 已有测试覆盖

当前测试文件：

- `tests/kairos/test_models.py`
- `tests/kairos/test_activity_log.py`
- `tests/kairos/test_dex_bridge.py`
- `tests/kairos/test_runtime.py`
- `tests/kairos/test_api.py`

覆盖内容包括：

- 状态模型序列化 / 反序列化
- recent events trimming
- activity log 路径和 append-only 行为
- Dex bridge 状态映射
- API 路由
- wake 行为
- Dex completion 事件
- busy 避让
- background loop 启停
- wake 即时触发
- stop 最终状态稳定为 `stopped`

---

## 4. 如何运行自动化测试

在项目根目录执行：

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_models.py tests/kairos/test_activity_log.py tests/kairos/test_dex_bridge.py tests/kairos/test_runtime.py tests/kairos/test_api.py -v
```

预期结果：

- 全部通过
- 当前应为 `11 passed`

如果只想单独验证 runtime：

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_runtime.py -v
```

如果只想单独验证 API：

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_api.py -v
```

---

## 5. 如何手工测试当前 Phase 1 KAIROS

下面给出一套推荐的手工 smoke test 流程。

### Step 1：启动服务

在项目根目录执行：

```bash
PYTHONIOENCODING=utf-8 python -m src.adk_agent.main_web_start_steering --port 8000
```

说明：

- 按仓库 `CLAUDE.md` 的要求，Windows 下要加 `PYTHONIOENCODING=utf-8`
- 否则中文 / emoji 输出可能乱码或报错

---

### Step 2：创建一个 session

```bash
curl -X POST http://127.0.0.1:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"app_name":"assistant","user_id":"alice"}'
```

预期返回示例：

```json
{
  "session_id": "session_xxx",
  "title": "新对话",
  "created_at": "2026-04-02T14:00:00"
}
```

记住返回的 `session_id`，后续接口会用到。

---

### Step 3：启动 KAIROS runtime

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/start \
  -H "Content-Type: application/json" \
  -d '{"app_name":"assistant","user_id":"alice"}'
```

预期检查点：

- `status = ok`
- `kairos.enabled = true`
- `kairos.running = true`
- `kairos.mode = "idle"`
- `recent_events` 出现：
  - `kairos runtime started`

---

### Step 4：手动唤醒一次 autonomous turn

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/wake \
  -H "Content-Type: application/json" \
  -d '{"app_name":"assistant","user_id":"alice","reason":"manual_smoke"}'
```

预期检查点：

- `pending_wake_reason` 初始会变成 `manual_smoke`
- `recent_events` 会追加：
  - `wake requested: manual_smoke`

---

### Step 5：轮询 status，观察 autonomous turn 是否真正发生

```bash
curl "http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/status?app_name=assistant&user_id=alice"
```

建议连续轮询几次，观察状态变化。

预期过程：

1. 初始可能看到：
   - `mode = "idle"`
   - `pending_wake_reason = "manual_smoke"`

2. 很快（当前实现里通常约 1 秒级）应看到：
   - `mode = "running"`
   - `pending_wake_reason = null`
   - `recent_events` 出现：
     - `kairos turn started: manual_smoke`

3. turn 完成后应看到：
   - `mode = "sleeping"`
   - `sleep_until` 有值
   - `recent_events` 再出现：
     - `kairos turn finished: manual_smoke`

这一步是判断 autonomous turn 是否真正走了共享 Runner 主链路的关键。

---

### Step 6：检查 activity log 是否生成

查看日志目录：

```bash
ls "D:/git_repos/google_adk_agent/memory_archive/alice"
```

再进入当月目录，找到对应文件：

```text
memory_archive/alice/<YYYY-MM>/<YYYY-MM-DD>_assistant_<SESSION_ID>_kairos.md
```

你也可以直接查看文件内容：

```bash
PYTHONIOENCODING=utf-8 python - <<'PY'
from pathlib import Path
p = Path('D:/git_repos/google_adk_agent/memory_archive/alice')
for f in sorted(p.rglob('*_kairos.md')):
    print(f)
PY
```

预期日志中至少能看到：

- `kairos runtime started`
- `wake requested: manual_smoke`
- `kairos turn started: manual_smoke`
- `kairos turn finished: manual_smoke`

---

### Step 7：停止 runtime

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/stop \
  -H "Content-Type: application/json" \
  -d '{"app_name":"assistant","user_id":"alice"}'
```

预期检查点：

- `kairos.running = false`
- `kairos.mode = "stopped"`
- `kairos.sleep_until = null`
- `recent_events` 追加：
  - `kairos runtime stopped`

当前这一步已经修复��� stop 后被回写成 `sleeping` 的竞态问题，所以最终状态应稳定为 `stopped`。

---

## 6. 如何验证 busy 避让

如果你想验证 Phase 1 的“前台忙时不抢跑”，可以这样做：

### 方法

1. 先通过 `/api/chat` 发一个会占用 worker 的请求
2. 在它尚未完成时，调用 `/kairos/wake`
3. 然后观察 status / recent_events

### 预期结果

KAIROS 不应该与 `/api/chat` 同时抢执行权，而应该在 `recent_events` 中出现类似：

```text
worker busy, skip kairos tick
```

这表示 runtime 检测到 `WORKER_LOCK.locked()`，选择避让而不是和前台请求争用同一个 worker。

---

## 7. 如果测试失败，优先看哪里

### 7.1 看 API 状态

优先检查：

```bash
curl "http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/status?app_name=assistant&user_id=alice"
```

重点看：

- `mode`
- `running`
- `pending_wake_reason`
- `sleep_until`
- `recent_events`

---

### 7.2 看日志文件

优先看：

- `logs/kairos_autonomous_smoke.log`（如果你重定向了服务日志）
- `memory_archive/alice/<YYYY-MM>/*_kairos.md`

---

### 7.3 看 runtime 是否真触发了 autonomous turn

如果 `wake` 之后长期只看到：

- `wake requested: ...`

却一直看不到：

- `kairos turn started: ...`
- `kairos turn finished: ...`

那就说明：

- 后台 loop 没跑起来
- 或 `run_kairos_turn()` 没真正进入共享主执行链路
- 或真实模型调用卡住了

当前版本已经修复了“wake 要等完整 tick 周期才触发”的问题，所以一般不会再卡在 15 秒等待上。

---

## 8. 当前仍未覆盖的范围

当前测试和手工验证针对的是 Phase 1 范围内的 KAIROS-lite。

还没有包含：

- cron / scheduled trigger
- webhook / GitHub trigger
- attach/view bridge
- 完整 supervisor 架构
- 自动把所有长工具调用 handoff 到 Dex

所以如果继续推进，那会是 Phase 2 的工作，不属于当前测试说明的主范围。

---

## 9. 一句话结论

当前 Phase 1 KAIROS 已经可以按下面这条链真实工作：

```text
start -> wake -> background loop -> autonomous turn -> recent_events/activity log -> sleep -> stop
```

并且这一条链已经经过：

- 单元测试验证
- 真实 smoke test 验证
- 远端 `origin/main` 提交校验

可以作为当前仓库里的 KAIROS Phase 1 基线版本使用。

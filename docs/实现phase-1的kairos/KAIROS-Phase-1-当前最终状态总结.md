# KAIROS Phase 1 当前最终状态总结

## 1. 当前已经完成的能力

本轮已经把 KAIROS Phase 1 从“设计 + 壳子”推进到“可真实运行的 KAIROS-lite runtime”。

当前已经具备：

- 单 session assistant runtime
- `start / stop / wake / status` API
- 后台 loop 驱动的 autonomous tick
- `wake -> autonomous turn -> sleep` 的真实执行链路
- `SteeringSession` 与 KAIROS runtime 接线
- `session.state["kairos"]` 持久化
- append-only activity log
- Dex tracked task polling
- worker busy 避让
- `recent_events` 状态暴露

也就是说，现在已经不是“只有状态模型和 API”，而是已经具备了一个真实可运行的 Phase 1 KAIROS-lite。

---

## 2. 新增文件

### KAIROS 核心模块

- `src/adk_agent/kairos/__init__.py`
- `src/adk_agent/kairos/models.py`
- `src/adk_agent/kairos/activity_log.py`
- `src/adk_agent/kairos/dex_bridge.py`
- `src/adk_agent/kairos/runtime.py`
- `src/adk_agent/kairos/api.py`

### 测试

- `tests/kairos/test_models.py`
- `tests/kairos/test_activity_log.py`
- `tests/kairos/test_dex_bridge.py`
- `tests/kairos/test_runtime.py`
- `tests/kairos/test_api.py`

### 文档

- `docs/实现phase-1的kairos/plan-phase-1-kairos.md`
- `docs/实现phase-1的kairos/assistant-runtime-autonomous-turn具体做什么.md`
- `docs/实现phase-1的kairos/KAIROS-Phase-1-当前最终状态总结.md`

---

## 3. 各模块当前职责

### 3.1 `models.py`

负责：

- `KairosMode`
- `KairosEvent`
- `KairosState`
- `load_kairos_state()`
- `dump_kairos_state()`

当前已经固定了 `session.state["kairos"]` 的基础契约。

---

### 3.2 `activity_log.py`

负责：

- append-only KAIROS activity log 写盘
- 目录结构对齐 `memory_archive/<user>/<YYYY-MM>/..._kairos.md`
- `FileLock` 防并发写入冲突

当前真实 smoke test 已验证 `_kairos.md` 文件可正确生成并写入事件。

---

### 3.3 `dex_bridge.py`

负责：

- 读取 Dex 任务文件
- 把 Dex 状态映射为 `DexTaskSnapshot`
- 为 runtime 提供 `get_task()` / `get_tasks()`

当前 Phase 1 的 Dex 能力定义为：

> 只做 tracked task polling，不做“自动后台化全部工具调用”。

---

### 3.4 `runtime.py`

负责：

- `start()` / `stop()` / `wake()`
- 后台 loop
- `tick_once()`
- Dex polling
- busy 避让
- recent events 更新
- activity log / state 持久化触发

当前已补齐两个关键问题：

1. `wake()` 现在能通过 `_wake_event` 尽快唤醒 loop，而不是死等完整 tick 周期
2. `stop()` 已避免 active turn 收尾把 `mode` 覆盖回 `sleeping` 的竞态

---

### 3.5 `api.py`

负责：

- `POST /api/sessions/{session_id}/kairos/start`
- `POST /api/sessions/{session_id}/kairos/stop`
- `POST /api/sessions/{session_id}/kairos/wake`
- `GET /api/sessions/{session_id}/kairos/status`

同时支持延迟获取 `session_manager`，避免 FastAPI app 初始化时全局对象尚未准备好。

---

## 4. `SteeringSession` 当前接入情况

在 `src/adk_agent/main_web_start_steering.py` 中，本轮已完成以下接线：

### 4.1 KAIROS runtime 装载与状态落盘

已新增：

- `self.kairos_runtime`
- `_save_kairos_state()`
- `_emit_kairos_event()`
- `_append_kairos_log()`
- `get_or_create_kairos_runtime()`

KAIROS 状态现在通过：

- `session.state["kairos"]`
- `recent_events`
- activity log

三处共同暴露和持久化。

---

### 4.2 共享执行骨架已抽出

当前已经不再让 `run_kairos_turn()` 停留在 stub，而是：

- 抽出了 `_run_agent_turn(task, images=None, yield_chunks=True)`
- 前台 `run_task()` 只是对它的流式包装
- `run_kairos_turn()` 通过 synthetic prompt 调 `_run_agent_turn(..., yield_chunks=False)`

也就是说：

> `/api/chat` 与 autonomous turn 现在共用同一条 Runner 主执行骨架。

这是本轮最关键的结构性进展之一。

---

## 5. 当前已经真实验证过什么

### 5.1 单元测试

KAIROS 相关测试当前已全部通过。

覆盖内容包括：

- 状态模型 round-trip
- recent_events trimming
- activity log 路径与 append-only
- Dex bridge 状态映射
- wake 行为
- Dex completion brief
- busy 避让
- background loop 启停
- wake 即时触发
- stop 状��竞态收口
- API 路由

---

### 5.2 smoke test

已经多次跑过真实 smoke test，确认过：

- 启动服务成功
- 创建 session 成功
- `kairos/start` 成功
- `kairos/wake` 成功
- 后台 loop 真正触发 autonomous turn
- `recent_events` 出现：
  - `kairos runtime started`
  - `wake requested: ...`
  - `kairos turn started: ...`
  - `kairos turn finished: ...`
- `_kairos.md` 活动日志成功落盘
- `kairos/stop` 后最终状态稳定为 `stopped`

最新一轮真实观测到：

- `wake -> turn started` 约 **1.12 秒**
- `wake -> turn finished` 约 **6.53 秒**

说明 autonomous turn 不再只是状态变化，而是已经进入真实主执行链路。

---

## 6. 当前还没有做的内容

这些不是本轮 bug，而是当前明确仍处于 Phase 1 范围之外的部分：

### 6.1 cron / webhook / 外部 trigger

当前还没有做：

- cron 表达式调度
- GitHub webhook / 外部触发器

目前主要触发方式仍然是：

- start
- wake
- 内部 tick loop

---

### 6.2 完整 attach / view / bridge

当前状态暴露方式主要是：

- `status API`
- `recent_events`
- `_kairos.md` activity log

还没有做：

- attach/view bridge
- viewer continuity
- 更完整的 remote attach 协议

---

### 6.3 完整 supervisor 架构

当前仍然是：

- `SteeringSession` 内嵌 runtime
- session-scoped runtime 实现

还没有做：

- 独立 supervisor
- 多 worker runtime lifecycle
- session discovery / attach orchestration

这与最初 Phase 1 采用方案 A 的路线一致。

---

### 6.4 自动后台化所有长任务

当前 Dex 只负责：

- tracked task polling
- completion/failed brief

还没有做：

- BashTool / PowerShellTool / AgentTool 的统一自动 handoff
- 所有慢任务自动 Dex 化

这同样符合本轮范围控制。

---

## 7. 当前最准确的状态判断

如果用一句话总结当前代码状态：

> 现在已经完成了一个可真实运行的 KAIROS Phase 1 Lite：它具备后台 loop、wake/tick/sleep、真实 autonomous turn、shared Runner path、busy 避让、Dex tracking、recent events、activity log 和最小管理 API；尚未进入 cron/webhook/attach/view/supervisor 等 Phase 2 能力。

---

## 8. 建议的后续方向

如果继续推进，下一阶段最自然的方向会是：

1. 增强 synthetic prompt 与 brief 策略
2. 扩展 Dex handoff 语义
3. 引入 cron / scheduled wake-up
4. 逐步做 attach/view bridge
5. 视需要演进到弱 supervisor / session runtime 分层

但就 Phase 1 而言，当前已经达成了“最小可运行 KAIROS-lite”的主目标。

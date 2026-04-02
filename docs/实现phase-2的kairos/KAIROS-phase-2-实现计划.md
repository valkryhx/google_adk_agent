# KAIROS Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前仓库已经完成的 Phase 1 KAIROS-lite 基础上，继续落一个真正可调度、可 attach/view、具备基础 continuity 和更丰富 lifecycle 的 Phase 2 Core Runtime。

**Architecture:** 继续沿用 Phase 1 的方案 A，不直接引入完整 supervisor，也不把实现继续堆进 `main_web_start_steering.py`。Phase 2 新增小型 `scheduler` 与 `attach` 辅助模块，仍以 `SteeringSession` 作为 worker 宿主、以 `session.state["kairos"]` 作为持久化契约、以 FastAPI JSON API 作为 attach/view skeleton。计划只覆盖 Phase 2 的核心 runtime 增强：trigger/schedule、attach/view、basic continuity、richer lifecycle、Dex handoff 注册；明确不在本计划内实现 GitHub webhook、nightly dream/distill、完整多进程 supervisor。

**Tech Stack:** Python asyncio、FastAPI、google-adk Runner/Session、SQLite (`FullyCustomDbService`)、Dex 文件任务系统、FileLock、croniter。

---

## 0. Scope Check

这份计划只覆盖 **Phase 2 Core Runtime**，不���图一次性吞掉所有后续特性。之所以收口，是因为下列能力虽然都属于 KAIROS 长期方向，但工程依赖不同、可以拆开推进：

### 本计划包含

- 统一 trigger model
- cron / scheduled wake-up
- richer lifecycle state
- attach/view API skeleton
- basic continuity（重建 runtime 时从已持久化 `session.state["kairos"]` 恢复）
- Dex handoff 注册与 handoff 状态语义

### 本计划明确不包含

- GitHub webhook / 外部 webhook adapter
- nightly dream / distilled memory
- 多 worker / 多进程 supervisor
- push/file-send/channels
- 全量 BashTool / PowerShellTool / AgentTool 自动后台化改造

如果 Phase 2 Core Runtime 落稳，后续再单独写：

1. `phase-2b-webhook-and-external-events.md`
2. `phase-2c-memory-distill-and-dream.md`
3. `phase-3-supervisor-and-bridge.md`

---

## 1. 代码地图与落点

### 当前已有实现（必须复用，不推翻）

- `src/adk_agent/kairos/models.py:8-59`
  - Phase 1 的 `KairosMode`、`KairosEvent`、`KairosState`、序列化逻辑
- `src/adk_agent/kairos/runtime.py:11-145`
  - `start()` / `stop()` / `wake()` / `tick_once()` / `_poll_dex()` / `_run_loop()`
- `src/adk_agent/kairos/api.py:7-51`
  - `start/stop/wake/status` 路由
- `src/adk_agent/main_web_start_steering.py:364-429`
  - `_save_kairos_state()` / `_emit_kairos_event()` / `_append_kairos_log()` / `run_kairos_turn()` / `get_or_create_kairos_runtime()`
- `src/adk_agent/main_web_start_steering.py:979-1168`
  - `_run_agent_turn()`，这是前台 `/api/chat` 与 autonomous turn 共用的执行骨架
- `src/adk_agent/main_web_start_steering.py:1883-1927`
  - `SessionManager`
- `src/adk_agent/main_web_start_steering.py:2242`
  - `register_kairos_routes(app, lambda: session_manager)`
- `src/adk_agent/kairos/dex_bridge.py:9-39`
  - Dex 文件任务状态桥接
- `src/adk_agent/kairos/activity_log.py:9-64`
  - `_kairos.md` append-only activity log
- `tests/kairos/test_models.py`
- `tests/kairos/test_runtime.py`
- `tests/kairos/test_api.py`

### 本计划新增文件

- Create: `src/adk_agent/kairos/scheduler.py`
- Create: `src/adk_agent/kairos/attach.py`
- Create: `tests/kairos/test_scheduler.py`

### 本计划修改文件

- Modify: `requirements.txt:1-28`
- Modify: `src/adk_agent/requirements.txt:1-12`
- Modify: `src/adk_agent/kairos/models.py:8-59`
- Modify: `src/adk_agent/kairos/runtime.py:11-145`
- Modify: `src/adk_agent/kairos/api.py:7-51`
- Modify: `src/adk_agent/main_web_start_steering.py:364-429`
- Modify: `src/adk_agent/main_web_start_steering.py:1883-1927`
- Modify: `tests/kairos/test_models.py:1-48`
- Modify: `tests/kairos/test_runtime.py:1-248`
- Modify: `tests/kairos/test_api.py:1-65`

### 文件职责

- `models.py`
  - 冻结 Phase 2 状态契约：lifecycle、trigger、schedule、handoff 状态
- `scheduler.py`
  - 只处理 cron schedule -> trigger 的转换，不直接跑模型
- `runtime.py`
  - 调度主循环、trigger 队列、Dex handoff 状态、事件记录
- `attach.py`
  - 只做 attach/view 所需 snapshot 组装，不碰业务执行
- `api.py`
  - 扩展 schedule / attach / Dex handoff 路由
- `main_web_start_steering.py`
  - 只补 runtime 装载与 continuity 接线，不新增大块业务逻辑

### 必须坚持的约束

1. **仍然不改 SQLite schema。** 继续用 `session.state["kairos"]`。
2. **不引入完整 supervisor。** `SessionManager` 只是弱 registry。
3. **不先做 websocket bridge。** attach/view 先用 JSON snapshot 与 polling API。
4. **不直接改 BashTool/PowerShellTool。** Phase 2 先把 runtime 的 handoff 语义做好。
5. **cron 只负责产出 trigger，不直接执行 turn。** 真正执行仍由 `KairosRuntime.tick_once()` 仲裁。

---

## 2. Phase 2 Core API 约定

### 现有保留

- `POST /api/sessions/{session_id}/kairos/start`
- `POST /api/sessions/{session_id}/kairos/stop`
- `POST /api/sessions/{session_id}/kairos/wake`
- `GET /api/sessions/{session_id}/kairos/status`

### 本计划新增

- `POST /api/sessions/{session_id}/kairos/schedules`
- `DELETE /api/sessions/{session_id}/kairos/schedules/{schedule_id}`
- `GET /api/kairos/sessions?user_id=<USER_ID>`
- `GET /api/sessions/{session_id}/kairos/attach?app_name=<APP>&user_id=<USER>`
- `POST /api/sessions/{session_id}/kairos/dex/register`

### `status` 返回结构扩展为

```json
{
  "status": "ok",
  "session_id": "session_xxx",
  "kairos": {
    "enabled": true,
    "running": true,
    "busy": false,
    "mode": "handoff",
    "sleep_until": "2026-04-02T12:15:00+00:00",
    "last_tick_at": "2026-04-02T12:00:00+00:00",
    "pending_wake_reason": "manual_smoke",
    "active_trigger": {
      "trigger_id": "manual-1",
      "kind": "manual",
      "reason": "manual_smoke",
      "created_at": "2026-04-02T12:00:00+00:00"
    },
    "pending_triggers": [],
    "tracked_dex_task_ids": ["abc12345"],
    "schedules": [
      {
        "schedule_id": "morning-checkin",
        "cron": "0 9 * * *",
        "reason": "morning_checkin",
        "enabled": true,
        "next_fire_at": "2026-04-03T09:00:00+00:00"
      }
    ],
    "recent_events": []
  }
}
```

---

### Task 1: 扩展 KAIROS 状态模型到 Phase 2 契约

**Files:**
- Modify: `src/adk_agent/kairos/models.py:8-59`
- Test: `tests/kairos/test_models.py:1-48`

- [ ] **Step 1: 写失败测试，锁定 Phase 2 新状态字段与兼容旧 state 的行为**

```python
from src.adk_agent.kairos.models import (
    KairosEvent,
    KairosMode,
    KairosSchedule,
    KairosState,
    KairosTrigger,
    TriggerKind,
    dump_kairos_state,
    load_kairos_state,
)


def test_load_legacy_state_fills_phase2_defaults():
    state = load_kairos_state({"enabled": True, "running": True, "mode": "idle"})

    assert state.enabled is True
    assert state.mode is KairosMode.IDLE
    assert state.pending_triggers == []
    assert state.schedules == []
    assert state.active_trigger is None
    assert state.last_tick_at is None


def test_dump_round_trip_preserves_schedule_and_trigger():
    state = KairosState(
        enabled=True,
        running=True,
        mode=KairosMode.HANDOFF,
        last_tick_at="2026-04-02T12:00:00+00:00",
        active_trigger=KairosTrigger(
            trigger_id="manual-1",
            kind=TriggerKind.MANUAL,
            reason="manual_smoke",
            created_at="2026-04-02T12:00:00+00:00",
        ),
        schedules=[
            KairosSchedule(
                schedule_id="morning-checkin",
                cron="0 9 * * *",
                reason="morning_checkin",
                enabled=True,
                next_fire_at="2026-04-03T09:00:00+00:00",
            )
        ],
        recent_events=[
            KairosEvent(kind="brief", message="runtime started", ts="2026-04-02T11:59:00+00:00")
        ],
    )

    restored = load_kairos_state(dump_kairos_state(state))

    assert restored.mode is KairosMode.HANDOFF
    assert restored.active_trigger is not None
    assert restored.active_trigger.kind is TriggerKind.MANUAL
    assert restored.schedules[0].schedule_id == "morning-checkin"
    assert restored.schedules[0].next_fire_at == "2026-04-03T09:00:00+00:00"


def test_recent_events_are_trimmed_to_last_20():
    state = KairosState(enabled=True, running=True, mode=KairosMode.IDLE)
    for idx in range(25):
        state.push_event(KairosEvent(kind="status", message=f"event-{idx}", ts=f"2026-04-02T12:00:{idx:02d}+00:00"))

    assert len(state.recent_events) == 20
    assert state.recent_events[0].message == "event-5"
    assert state.recent_events[-1].message == "event-24"
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_models.py -v
```

Expected: FAIL，报 `ImportError` 或 `AttributeError`，提示 `KairosSchedule` / `KairosTrigger` / `TriggerKind` 不存在。

- [ ] **Step 3: 写最小实现，扩展 `models.py`**

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class KairosMode(str, Enum):
    STOPPED = "stopped"
    IDLE = "idle"
    RUNNING = "running"
    SLEEPING = "sleeping"
    HANDOFF = "handoff"
    WAITING_INPUT = "waiting_input"


class TriggerKind(str, Enum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    DEX = "dex"
    INTERNAL = "internal"


@dataclass
class KairosEvent:
    kind: str
    message: str
    ts: str
    level: str = "normal"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KairosTrigger:
    trigger_id: str
    kind: TriggerKind
    reason: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KairosSchedule:
    schedule_id: str
    cron: str
    reason: str
    enabled: bool = True
    next_fire_at: str | None = None


@dataclass
class KairosState:
    enabled: bool = False
    running: bool = False
    busy: bool = False
    mode: KairosMode = KairosMode.STOPPED
    sleep_until: str | None = None
    last_tick_at: str | None = None
    pending_wake_reason: str | None = None
    active_trigger: KairosTrigger | None = None
    pending_triggers: list[KairosTrigger] = field(default_factory=list)
    tracked_dex_task_ids: list[str] = field(default_factory=list)
    schedules: list[KairosSchedule] = field(default_factory=list)
    recent_events: list[KairosEvent] = field(default_factory=list)

    def push_event(self, event: KairosEvent, limit: int = 20) -> None:
        self.recent_events.append(event)
        if len(self.recent_events) > limit:
            self.recent_events = self.recent_events[-limit:]


def load_kairos_state(raw: dict[str, Any] | None) -> KairosState:
    if not raw:
        return KairosState()
    return KairosState(
        enabled=bool(raw.get("enabled", False)),
        running=bool(raw.get("running", False)),
        busy=bool(raw.get("busy", False)),
        mode=KairosMode(raw.get("mode", KairosMode.STOPPED.value)),
        sleep_until=raw.get("sleep_until"),
        last_tick_at=raw.get("last_tick_at"),
        pending_wake_reason=raw.get("pending_wake_reason"),
        active_trigger=KairosTrigger(**raw["active_trigger"]) if raw.get("active_trigger") else None,
        pending_triggers=[KairosTrigger(**item) for item in raw.get("pending_triggers", [])],
        tracked_dex_task_ids=list(raw.get("tracked_dex_task_ids", [])),
        schedules=[KairosSchedule(**item) for item in raw.get("schedules", [])],
        recent_events=[KairosEvent(**item) for item in raw.get("recent_events", [])],
    )


def dump_kairos_state(state: KairosState) -> dict[str, Any]:
    payload = asdict(state)
    payload["mode"] = state.mode.value
    if state.active_trigger is not None:
        payload["active_trigger"]["kind"] = state.active_trigger.kind.value
    for item in payload["pending_triggers"]:
        item["kind"] = TriggerKind(item["kind"]).value
    return payload
```

- [ ] **Step 4: 重新运行测试，确认通过**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_models.py -v
```

Expected: `3 passed`

- [ ] **Step 5: 提交**

```bash
git add tests/kairos/test_models.py src/adk_agent/kairos/models.py
git commit -m "feat(kairos): extend state contract for phase 2"
```

---

### Task 2: 新增 scheduler 模块并支持 cron schedule -> trigger

**Files:**
- Modify: `requirements.txt:1-28`
- Modify: `src/adk_agent/requirements.txt:1-12`
- Create: `src/adk_agent/kairos/scheduler.py`
- Test: `tests/kairos/test_scheduler.py`

- [ ] **Step 1: 写失败测试，锁定 schedule 的 seed 与 due 行为**

```python
from datetime import UTC, datetime

from src.adk_agent.kairos.models import KairosSchedule, KairosState, TriggerKind
from src.adk_agent.kairos.scheduler import KairosScheduler


def test_seed_schedules_sets_next_fire_at():
    state = KairosState(
        schedules=[
            KairosSchedule(
                schedule_id="morning-checkin",
                cron="*/5 * * * *",
                reason="morning_checkin",
            )
        ]
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    KairosScheduler().seed_schedules(state, now)

    assert state.schedules[0].next_fire_at == "2026-04-02T12:05:00+00:00"


def test_collect_due_triggers_rolls_schedule_forward():
    state = KairosState(
        schedules=[
            KairosSchedule(
                schedule_id="catch-up",
                cron="*/15 * * * *",
                reason="catch_up",
                enabled=True,
                next_fire_at="2026-04-02T12:00:00+00:00",
            )
        ]
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    triggers = KairosScheduler().collect_due_triggers(state, now)

    assert len(triggers) == 1
    assert triggers[0].kind is TriggerKind.SCHEDULE
    assert triggers[0].reason == "catch_up"
    assert state.schedules[0].next_fire_at == "2026-04-02T12:15:00+00:00"


def test_collect_due_triggers_skips_disabled_schedule():
    state = KairosState(
        schedules=[
            KairosSchedule(
                schedule_id="disabled",
                cron="*/5 * * * *",
                reason="skip_me",
                enabled=False,
                next_fire_at="2026-04-02T12:00:00+00:00",
            )
        ]
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    triggers = KairosScheduler().collect_due_triggers(state, now)

    assert triggers == []
    assert state.schedules[0].next_fire_at == "2026-04-02T12:00:00+00:00"
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_scheduler.py -v
```

Expected: FAIL，报 `ModuleNotFoundError: No module named 'src.adk_agent.kairos.scheduler'`。

- [ ] **Step 3: 写最小实现，并补依赖 `croniter`**

`requirements.txt`

```text
# Core Framework
google-adk
google-genai
croniter
```

`src/adk_agent/requirements.txt`

```text
google-adk>=0.1.0
litellm>=1.0.0
croniter>=2.0.0
pyyaml>=6.0
```

`src/adk_agent/kairos/scheduler.py`

```python
from __future__ import annotations

from datetime import UTC, datetime

from croniter import croniter

from .models import KairosState, KairosTrigger, TriggerKind


class KairosScheduler:
    def _next_fire_at(self, cron_expr: str, now: datetime) -> str:
        return croniter(cron_expr, now).get_next(datetime).astimezone(UTC).isoformat()

    def seed_schedules(self, state: KairosState, now: datetime) -> None:
        for schedule in state.schedules:
            if schedule.enabled and schedule.next_fire_at is None:
                schedule.next_fire_at = self._next_fire_at(schedule.cron, now)

    def collect_due_triggers(self, state: KairosState, now: datetime) -> list[KairosTrigger]:
        due: list[KairosTrigger] = []
        for schedule in state.schedules:
            if not schedule.enabled or not schedule.next_fire_at:
                continue
            if datetime.fromisoformat(schedule.next_fire_at) <= now:
                due.append(
                    KairosTrigger(
                        trigger_id=f"schedule-{schedule.schedule_id}-{int(now.timestamp())}",
                        kind=TriggerKind.SCHEDULE,
                        reason=schedule.reason,
                        created_at=now.isoformat(),
                        metadata={"schedule_id": schedule.schedule_id},
                    )
                )
                schedule.next_fire_at = self._next_fire_at(schedule.cron, now)
        return due
```

- [ ] **Step 4: 重新运行测试，确认通过**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_scheduler.py -v
```

Expected: `3 passed`

- [ ] **Step 5: 提交**

```bash
git add requirements.txt src/adk_agent/requirements.txt tests/kairos/test_scheduler.py src/adk_agent/kairos/scheduler.py
git commit -m "feat(kairos): add cron scheduler for phase 2"
```

---

### Task 3: 把 trigger/schedule 真正接入 runtime 与 schedule API

**Files:**
- Modify: `src/adk_agent/kairos/runtime.py:11-145`
- Modify: `src/adk_agent/kairos/api.py:7-51`
- Modify: `tests/kairos/test_runtime.py:1-248`
- Modify: `tests/kairos/test_api.py:1-65`

- [ ] **Step 1: 写失败测试，锁定 schedule 注册和 due trigger 执行**

`tests/kairos/test_runtime.py`

```python
import asyncio
from datetime import UTC, datetime

import pytest

from src.adk_agent.kairos.models import KairosMode, KairosSchedule, KairosState
from src.adk_agent.kairos.runtime import KairosRuntime
from src.adk_agent.kairos.scheduler import KairosScheduler


class FakeDex:
    def get_tasks(self, _):
        return []


@pytest.mark.asyncio
async def test_add_schedule_persists_and_seeds_next_fire_at():
    saved = []

    async def save_state(state):
        saved.append(state)

    async def emit_event(_):
        return None

    async def append_log(_):
        return None

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.IDLE),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDex(),
        scheduler=KairosScheduler(),
    )

    await runtime.add_schedule(
        KairosSchedule(schedule_id="morning", cron="*/5 * * * *", reason="morning_checkin")
    )

    assert runtime.state.schedules[0].schedule_id == "morning"
    assert runtime.state.schedules[0].next_fire_at is not None
    assert saved


@pytest.mark.asyncio
async def test_tick_runs_due_schedule_trigger():
    seen = []

    async def save_state(_):
        return None

    async def emit_event(event):
        seen.append(event.message)

    async def append_log(_):
        return None

    async def run_turn(reason):
        seen.append(f"run:{reason}")
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.IDLE,
            schedules=[
                KairosSchedule(
                    schedule_id="catch-up",
                    cron="*/15 * * * *",
                    reason="catch_up",
                    next_fire_at=datetime.now(UTC).isoformat(),
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDex(),
        scheduler=KairosScheduler(),
    )

    await runtime.tick_once()

    assert any("run:catch_up" == item for item in seen)
    assert runtime.state.active_trigger is None
    assert runtime.state.mode is KairosMode.SLEEPING
```

`tests/kairos/test_api.py`

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adk_agent.kairos.api import register_kairos_routes


class FakeRuntime:
    def __init__(self):
        self.state = {"enabled": False, "mode": "stopped", "recent_events": [], "schedules": []}

    async def start(self):
        self.state["enabled"] = True
        self.state["mode"] = "idle"

    async def stop(self):
        self.state["enabled"] = False
        self.state["mode"] = "stopped"

    async def wake(self, reason):
        self.state["recent_events"].append({"kind": "status", "message": reason})

    async def add_schedule(self, schedule):
        self.state["schedules"].append({"schedule_id": schedule.schedule_id, "cron": schedule.cron})

    async def delete_schedule(self, schedule_id):
        self.state["schedules"] = [item for item in self.state["schedules"] if item["schedule_id"] != schedule_id]

    def get_status(self):
        return self.state


class FakeSession:
    def __init__(self):
        self.runtime = FakeRuntime()

    async def ensure_kairos_runtime(self):
        return self.runtime


class FakeManager:
    def __init__(self):
        self.session = FakeSession()

    def get_or_create(self, app_name, user_id, session_id):
        return self.session


def test_schedule_routes_work():
    app = FastAPI()
    register_kairos_routes(app, FakeManager())
    client = TestClient(app)

    resp = client.post(
        "/api/sessions/session_1/kairos/schedules",
        json={
            "app_name": "demo",
            "user_id": "alice",
            "schedule_id": "morning",
            "cron": "*/5 * * * *",
            "reason": "morning_checkin",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["kairos"]["schedules"][0]["schedule_id"] == "morning"
```

- [ ] **Step 2: 运行定向测试，确认当前失败**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_runtime.py tests/kairos/test_api.py -v
```

Expected: FAIL，提示 `KairosRuntime` 没有 `add_schedule()`，或 API 没有 `/kairos/schedules`。

- [ ] **Step 3: 写最小实现，把 schedule 接进 runtime 与 API**

`src/adk_agent/kairos/runtime.py`

```python
from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable

from .models import KairosEvent, KairosMode, KairosSchedule, KairosState, KairosTrigger, TriggerKind
from .scheduler import KairosScheduler


class KairosRuntime:
    def __init__(
        self,
        *,
        state: KairosState,
        save_state: Callable[[KairosState], Awaitable[None]],
        emit_event: Callable[[KairosEvent], Awaitable[None]],
        append_log: Callable[[KairosEvent], Awaitable[None]],
        run_turn: Callable[[str], Awaitable[str | None]],
        dex_bridge,
        tick_interval_seconds: float = 15.0,
        is_worker_busy: Callable[[], bool] | None = None,
        scheduler: KairosScheduler | None = None,
    ):
        self.state = state
        self._save_state = save_state
        self._emit_event = emit_event
        self._append_log = append_log
        self._run_turn = run_turn
        self._dex_bridge = dex_bridge
        self._tick_interval_seconds = tick_interval_seconds
        self._is_worker_busy = is_worker_busy or (lambda: False)
        self._scheduler = scheduler or KairosScheduler()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._wake_event = asyncio.Event()

    async def add_schedule(self, schedule: KairosSchedule) -> None:
        self.state.schedules = [item for item in self.state.schedules if item.schedule_id != schedule.schedule_id]
        self.state.schedules.append(schedule)
        self._scheduler.seed_schedules(self.state, datetime.now(UTC))
        await self._persist()
        await self._record("status", f"schedule registered: {schedule.schedule_id}")

    async def delete_schedule(self, schedule_id: str) -> None:
        self.state.schedules = [item for item in self.state.schedules if item.schedule_id != schedule_id]
        await self._persist()
        await self._record("status", f"schedule removed: {schedule_id}")

    async def enqueue_trigger(self, trigger: KairosTrigger) -> None:
        self.state.pending_triggers.append(trigger)
        self.state.pending_wake_reason = trigger.reason
        if self.state.mode == KairosMode.SLEEPING:
            self.state.mode = KairosMode.IDLE
        self._wake_event.set()
        await self._persist()

    async def wake(self, reason: str) -> None:
        await self.enqueue_trigger(
            KairosTrigger(
                trigger_id=f"manual-{int(datetime.now(UTC).timestamp())}",
                kind=TriggerKind.MANUAL,
                reason=reason,
                created_at=datetime.now(UTC).isoformat(),
            )
        )
        await self._record("status", f"wake requested: {reason}")

    async def tick_once(self) -> None:
        async with self._lock:
            now = datetime.now(UTC)
            self.state.last_tick_at = now.isoformat()
            self._scheduler.seed_schedules(self.state, now)
            self.state.pending_triggers.extend(self._scheduler.collect_due_triggers(self.state, now))
            await self._poll_dex()
            if not self.state.running:
                return
            if self._is_worker_busy():
                await self._record("status", "worker busy, skip kairos tick")
                return
            if self.state.pending_triggers and not self.state.busy:
                trigger = self.state.pending_triggers.pop(0)
                self.state.active_trigger = trigger
                self.state.pending_wake_reason = trigger.reason
                self.state.busy = True
                self.state.mode = KairosMode.RUNNING
                await self._persist()
                await self._record("brief", f"kairos turn started: {trigger.kind.value}:{trigger.reason}")
                try:
                    await self._run_turn(trigger.reason)
                finally:
                    self.state.busy = False
                    self.state.active_trigger = None
                    if self.state.running:
                        self.state.mode = KairosMode.SLEEPING
                        self.state.sleep_until = (datetime.now(UTC) + timedelta(seconds=self._tick_interval_seconds)).isoformat()
                    else:
                        self.state.mode = KairosMode.STOPPED
                        self.state.sleep_until = None
                    await self._persist()
                    await self._record("brief", f"kairos turn finished: {trigger.kind.value}:{trigger.reason}")
```

`src/adk_agent/kairos/api.py`

```python
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .models import KairosSchedule


class KairosSessionRequest(BaseModel):
    app_name: str
    user_id: str
    reason: str | None = None


class KairosScheduleRequest(BaseModel):
    app_name: str
    user_id: str
    schedule_id: str
    cron: str
    reason: str
    enabled: bool = True


def _get_session_manager(session_manager):
    return session_manager() if callable(session_manager) else session_manager


def register_kairos_routes(app, session_manager):
    router = APIRouter()

    @router.post("/api/sessions/{session_id}/kairos/start")
    async def start_kairos(session_id: str, req: KairosSessionRequest):
        manager = _get_session_manager(session_manager)
        session = manager.get_or_create(req.app_name, req.user_id, session_id)
        runtime = await session.ensure_kairos_runtime()
        await runtime.start()
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}

    @router.post("/api/sessions/{session_id}/kairos/schedules")
    async def add_schedule(session_id: str, req: KairosScheduleRequest):
        manager = _get_session_manager(session_manager)
        session = manager.get_or_create(req.app_name, req.user_id, session_id)
        runtime = await session.ensure_kairos_runtime()
        await runtime.add_schedule(
            KairosSchedule(
                schedule_id=req.schedule_id,
                cron=req.cron,
                reason=req.reason,
                enabled=req.enabled,
            )
        )
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}

    @router.delete("/api/sessions/{session_id}/kairos/schedules/{schedule_id}")
    async def delete_schedule(session_id: str, schedule_id: str, app_name: str, user_id: str):
        manager = _get_session_manager(session_manager)
        session = manager.get_or_create(app_name, user_id, session_id)
        runtime = await session.ensure_kairos_runtime()
        await runtime.delete_schedule(schedule_id)
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}
```

- [ ] **Step 4: 重新运行测试，确认通过**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_runtime.py tests/kairos/test_api.py -v
```

Expected: 所有新增的 schedule/runtime/api 用例通过。

- [ ] **Step 5: 提交**

```bash
git add src/adk_agent/kairos/runtime.py src/adk_agent/kairos/api.py tests/kairos/test_runtime.py tests/kairos/test_api.py
git commit -m "feat(kairos): add schedule-driven runtime triggers"
```

---

### Task 4: 增加 attach/view skeleton 与 basic continuity

**Files:**
- Create: `src/adk_agent/kairos/attach.py`
- Modify: `src/adk_agent/kairos/api.py:1-120`
- Modify: `src/adk_agent/main_web_start_steering.py:364-429`
- Modify: `src/adk_agent/main_web_start_steering.py:1883-1927`
- Modify: `tests/kairos/test_api.py:1-120`

- [ ] **Step 1: 写失败测试，锁定 session 列表与 attach snapshot 路由**

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adk_agent.kairos.api import register_kairos_routes


class FakeRuntime:
    def __init__(self):
        self.state = {
            "enabled": True,
            "running": True,
            "mode": "sleeping",
            "recent_events": [{"kind": "brief", "message": "ready", "ts": "2026-04-02T12:00:00+00:00"}],
            "schedules": [],
        }

    def get_status(self):
        return self.state


class FakeSession:
    def __init__(self, app_name, user_id, session_id):
        self.app_name = app_name
        self.user_id = user_id
        self.session_id = session_id
        self.runtime = FakeRuntime()

    async def ensure_kairos_runtime(self):
        return self.runtime


class FakeManager:
    def __init__(self):
        self._sessions = {("assistant", "alice", "session_1"): FakeSession("assistant", "alice", "session_1")}

    def get_or_create(self, app_name, user_id, session_id):
        return self._sessions[(app_name, user_id, session_id)]


def test_list_and_attach_routes_work():
    app = FastAPI()
    register_kairos_routes(app, FakeManager())
    client = TestClient(app)

    list_resp = client.get("/api/kairos/sessions", params={"user_id": "alice"})
    assert list_resp.status_code == 200
    assert list_resp.json()["sessions"][0]["session_id"] == "session_1"

    attach_resp = client.get(
        "/api/sessions/session_1/kairos/attach",
        params={"app_name": "assistant", "user_id": "alice"},
    )
    assert attach_resp.status_code == 200
    assert attach_resp.json()["kairos"]["mode"] == "sleeping"
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_api.py -v
```

Expected: FAIL，提示 `/api/kairos/sessions` 或 `/kairos/attach` 路由不存在。

- [ ] **Step 3: 写最小实现，增加 attach helper 与 continuity 接线**

`src/adk_agent/kairos/attach.py`

```python
from __future__ import annotations


def build_runtime_summary(app_name: str, user_id: str, session_id: str, runtime) -> dict:
    status = runtime.get_status()
    return {
        "app_name": app_name,
        "user_id": user_id,
        "session_id": session_id,
        "mode": status.get("mode"),
        "running": status.get("running"),
        "recent_events": status.get("recent_events", [])[-5:],
    }


def list_runtime_summaries(session_manager, user_id: str) -> list[dict]:
    result: list[dict] = []
    for (app_name, uid, session_id), session in getattr(session_manager, "_sessions", {}).items():
        if uid != user_id:
            continue
        runtime = getattr(session, "kairos_runtime", None) or getattr(session, "runtime", None)
        if runtime is None:
            continue
        result.append(build_runtime_summary(app_name, uid, session_id, runtime))
    return result
```

`src/adk_agent/main_web_start_steering.py`

```python
class SteeringSession:
    async def ensure_current_session(self):
        if self._current_session is None:
            session = await self.session_service.get_session(
                app_name=self.app_name,
                user_id=self.user_id,
                session_id=self.session_id,
            )
            if not session:
                session = await self.session_service.create_session(
                    app_name=self.app_name,
                    user_id=self.user_id,
                    session_id=self.session_id,
                )
            self._current_session = session
        return self._current_session

    async def ensure_kairos_runtime(self):
        await self.ensure_current_session()
        return self.get_or_create_kairos_runtime()
```

`src/adk_agent/kairos/api.py`

```python
from .attach import build_runtime_summary, list_runtime_summaries


@router.get("/api/kairos/sessions")
async def list_kairos_sessions(user_id: str):
    manager = _get_session_manager(session_manager)
    return {"sessions": list_runtime_summaries(manager, user_id)}


@router.get("/api/sessions/{session_id}/kairos/attach")
async def attach_kairos(session_id: str, app_name: str, user_id: str):
    manager = _get_session_manager(session_manager)
    session = manager.get_or_create(app_name, user_id, session_id)
    runtime = await session.ensure_kairos_runtime()
    return {
        "status": "ok",
        "session_id": session_id,
        "kairos": runtime.get_status(),
        "attach": build_runtime_summary(app_name, user_id, session_id, runtime),
    }
```

- [ ] **Step 4: 重新运行测试，确认通过**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_api.py -v
```

Expected: `2 passed` 或更多，覆盖 start/status + list/attach。

- [ ] **Step 5: 提交**

```bash
git add src/adk_agent/kairos/attach.py src/adk_agent/kairos/api.py src/adk_agent/main_web_start_steering.py tests/kairos/test_api.py
git commit -m "feat(kairos): add attach view skeleton and continuity"
```

---

### Task 5: 增加 Dex handoff 注册与 richer lifecycle 语义

**Files:**
- Modify: `src/adk_agent/kairos/runtime.py:1-220`
- Modify: `src/adk_agent/kairos/api.py:1-180`
- Modify: `tests/kairos/test_runtime.py:1-320`
- Modify: `tests/kairos/test_api.py:1-160`

- [ ] **Step 1: 写失败测试，锁定 handoff 状态与 Dex 注册 API**

`tests/kairos/test_runtime.py`

```python
import pytest

from src.adk_agent.kairos.models import KairosMode, KairosState
from src.adk_agent.kairos.runtime import KairosRuntime


class FakeDexBridge:
    def __init__(self):
        self.tasks = {}

    def get_tasks(self, task_ids):
        return [self.tasks[task_id] for task_id in task_ids if task_id in self.tasks]


@pytest.mark.asyncio
async def test_register_dex_task_switches_runtime_to_handoff():
    async def save_state(_):
        return None

    async def emit_event(_):
        return None

    async def append_log(_):
        return None

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.IDLE),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
    )

    await runtime.register_dex_task("abc12345", "run report")

    assert runtime.state.tracked_dex_task_ids == ["abc12345"]
    assert runtime.state.mode is KairosMode.HANDOFF


@pytest.mark.asyncio
async def test_completed_handoff_task_returns_runtime_to_idle_or_sleeping():
    class Snap:
        def __init__(self, task_id, status, description):
            self.task_id = task_id
            self.status = status
            self.description = description
            self.result = "[SUCCESS]"

    bridge = FakeDexBridge()
    bridge.tasks["abc12345"] = Snap("abc12345", "completed", "run report")

    async def save_state(_):
        return None

    async def emit_event(_):
        return None

    async def append_log(_):
        return None

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.HANDOFF,
            tracked_dex_task_ids=["abc12345"],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=bridge,
    )

    await runtime.tick_once()

    assert runtime.state.tracked_dex_task_ids == []
    assert runtime.state.mode in {KairosMode.IDLE, KairosMode.SLEEPING}
```

`tests/kairos/test_api.py`

```python
def test_register_dex_route_works():
    app = FastAPI()
    register_kairos_routes(app, FakeManager())
    client = TestClient(app)

    resp = client.post(
        "/api/sessions/session_1/kairos/dex/register",
        json={
            "app_name": "demo",
            "user_id": "alice",
            "task_id": "abc12345",
            "description": "run report",
        },
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_runtime.py tests/kairos/test_api.py -v
```

Expected: FAIL，提示 `KairosRuntime` 没有 `register_dex_task()`，或 `/kairos/dex/register` 路由不存在。

- [ ] **Step 3: 写最小实现，补 handoff 模式与 Dex 注册路由**

`src/adk_agent/kairos/runtime.py`

```python
async def register_dex_task(self, task_id: str, description: str) -> None:
    if task_id not in self.state.tracked_dex_task_ids:
        self.state.tracked_dex_task_ids.append(task_id)
    if self.state.running and not self.state.busy:
        self.state.mode = KairosMode.HANDOFF
    await self._persist()
    await self._record("brief", f"dex handoff registered: {task_id} {description}")


async def _poll_dex(self) -> None:
    remaining = list(self.state.tracked_dex_task_ids)
    if not remaining:
        return

    next_remaining: list[str] = []
    for task in self._dex_bridge.get_tasks(remaining):
        if task.status in {"completed", "failed"}:
            await self._record(
                "brief",
                f"Dex task {task.task_id} {task.status}: {task.description}",
            )
        else:
            next_remaining.append(task.task_id)

    self.state.tracked_dex_task_ids = next_remaining
    if next_remaining and self.state.running and not self.state.busy:
        self.state.mode = KairosMode.HANDOFF
    elif not next_remaining and self.state.running and not self.state.busy and self.state.mode == KairosMode.HANDOFF:
        self.state.mode = KairosMode.IDLE
    await self._persist()
```

`src/adk_agent/kairos/api.py`

```python
class KairosDexRegisterRequest(BaseModel):
    app_name: str
    user_id: str
    task_id: str
    description: str


@router.post("/api/sessions/{session_id}/kairos/dex/register")
async def register_dex_task(session_id: str, req: KairosDexRegisterRequest):
    manager = _get_session_manager(session_manager)
    session = manager.get_or_create(req.app_name, req.user_id, session_id)
    runtime = await session.ensure_kairos_runtime()
    await runtime.register_dex_task(req.task_id, req.description)
    return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}
```

- [ ] **Step 4: 重新运行测试，确认通过**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_runtime.py tests/kairos/test_api.py -v
```

Expected: 所有 Dex handoff 相关新增用例通过。

- [ ] **Step 5: 提交**

```bash
git add src/adk_agent/kairos/runtime.py src/adk_agent/kairos/api.py tests/kairos/test_runtime.py tests/kairos/test_api.py
git commit -m "feat(kairos): add dex handoff lifecycle"
```

---

### Task 6: 运行 Phase 2 回归与手工 smoke test

**Files:**
- Modify: `tests/kairos/test_models.py`
- Modify: `tests/kairos/test_scheduler.py`
- Modify: `tests/kairos/test_runtime.py`
- Modify: `tests/kairos/test_api.py`

- [ ] **Step 1: 运行完整 KAIROS 自动化测试**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_models.py tests/kairos/test_scheduler.py tests/kairos/test_activity_log.py tests/kairos/test_dex_bridge.py tests/kairos/test_runtime.py tests/kairos/test_api.py -v
```

Expected: 全部通过；新增 `test_scheduler.py` 之后，总数应高于当前 Phase 1 的 `11 passed`。

- [ ] **Step 2: 启动服务并创建 session**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m src.adk_agent.main_web_start_steering --port 8000
```

新开终端后执行：

```bash
curl -X POST http://127.0.0.1:8000/api/sessions -H "Content-Type: application/json" -d '{"app_name":"assistant","user_id":"alice"}'
```

Expected: 返回新的 `session_id`。

- [ ] **Step 3: 注册 schedule 并验证 status / attach**

Run:

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/start -H "Content-Type: application/json" -d '{"app_name":"assistant","user_id":"alice"}'
curl -X POST http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/schedules -H "Content-Type: application/json" -d '{"app_name":"assistant","user_id":"alice","schedule_id":"morning","cron":"*/5 * * * *","reason":"morning_checkin"}'
curl "http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/status?app_name=assistant&user_id=alice"
curl "http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/attach?app_name=assistant&user_id=alice"
```

Expected:

- `status.kairos.schedules[0].schedule_id == "morning"`
- `status.kairos.last_tick_at` 有值
- `attach.kairos.mode` 存在
- `attach.attach.session_id == <SESSION_ID>`

- [ ] **Step 4: 验证 Dex handoff 路由**

Run:

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/dex/register -H "Content-Type: application/json" -d '{"app_name":"assistant","user_id":"alice","task_id":"abc12345","description":"run report"}'
curl "http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/status?app_name=assistant&user_id=alice"
```

Expected:

- `tracked_dex_task_ids` 包含 `abc12345`
- `mode` 进入 `handoff` 或后续在完成后回到 `idle/sleeping`
- `recent_events` 中出现 `dex handoff registered`

- [ ] **Step 5: 提交**

```bash
git add tests/kairos/test_models.py tests/kairos/test_scheduler.py tests/kairos/test_activity_log.py tests/kairos/test_dex_bridge.py tests/kairos/test_runtime.py tests/kairos/test_api.py
git commit -m "test(kairos): verify phase 2 core runtime"
```

---

## 3. 实施顺序总结

按依赖顺序，必须这样做：

1. **先扩状态契约**
   - 否则 runtime/scheduler/api 无法共享同一套数据结构。
2. **再加 scheduler**
   - 否则 schedule 只是死数据，无法变成 trigger。
3. **再把 schedule 接进 runtime/api**
   - 否则 cron 只存在于模型里，没有行为。
4. **再做 attach/view + continuity**
   - 因为 attach 需要读到真实 runtime state。
5. **最后补 Dex handoff lifecycle**
   - 因为它建立在 richer lifecycle 和 status schema 之上。
6. **最后一次性跑回归和 smoke**
   - 避免把前面新增的状态/路由问题漏掉。

---

## 4. 验收标准

满足下面 8 条才算完成 Phase 2 Core Runtime：

1. `status` 返回 `last_tick_at / active_trigger / pending_triggers / schedules`
2. 可以通过 API 新增和删除 schedule
3. due schedule 会在 runtime tick 中自动转成 trigger 并执行 turn
4. `attach` 路由能返回当前 runtime snapshot
5. `list` 路由能列出某个 `user_id` 当前的活跃 KAIROS session
6. `ensure_kairos_runtime()` 能从已持久化 `session.state["kairos"]` 恢复 runtime
7. Dex task 可以通过 API 注册到 runtime，并把 mode 切到 `handoff`
8. `tests/kairos/*.py` 全部通过

---

## 5. 明确不在本计划内的内容

这些很重要，但不要在本计划中顺手做掉：

- GitHub webhook sanitizer / inbound event bridge
- nightly dream / distilled memory index
- websocket attach stream
- daemon parent / child respawn
- complete session discovery across process restarts
- 把所有长工具调用自动改造成 Dex

如果实现时顺手把这些掺进来，计划会失控，测试也会明显变难。

---

## 6. Self-Review

### Spec coverage

- trigger/schedule：Task 1-3
- attach/view skeleton：Task 4
- basic continuity：Task 4
- richer lifecycle：Task 1、Task 5
- Dex handoff：Task 5
- regression/smoke：Task 6

无缺口。

### Placeholder scan

- 没有使用 `TODO` / `TBD` / “稍后实现” 之类占位语句。
- 每个 task 都给了明确文件、测试、命令和最小代码。

### Type consistency

- `KairosMode`、`TriggerKind`、`KairosTrigger`、`KairosSchedule` 在 Task 1 定义，后续任务复用相同命名。
- runtime/api/test 中均使用同一套 `schedule_id` / `trigger_id` / `reason` 字段。

---

Plan complete and saved to `docs/实现phase-2的kairos/KAIROS-phase-2-实现计划.md`. Two execution options:

**1. Subagent-Driven (recommended)** - 我按任务逐个派子代理执行，并在任务间做 review。

**2. Inline Execution** - 我直接在这个会话里按任务执行。

你选哪个。
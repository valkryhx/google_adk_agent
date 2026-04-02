# KAIROS Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前仓库内落一个 `SteeringSession` 内嵌式 KAIROS-lite：支持单 session assistant runtime、tick/sleep/wake、brief/status 输出、Dex 后台任务接管、append-only activity log，以及最小的 start/stop/wake/status API。

**Architecture:** 采用方案 A，不先引入独立 supervisor。新增一个小型 `src/adk_agent/kairos/` 包，把 runtime 状态保存在 `session.state["kairos"]`，把用户可见状态通过 `SteeringSession.report_swarm_event()` 和 `session.state["kairos"]["recent_events"]` 暴露出来，并复用现有 `FullyCustomDbService`、Dex、`memory_archive` 写盘模式。KAIROS 不改 DB schema，不改 Dex 存储格式，不把大量逻辑继续堆进 `main_web_start_steering.py`。

**Tech Stack:** Python asyncio、FastAPI、google-adk Runner/Session、SQLite(FullyCustomDbService)、Dex 文件任务队列、FileLock。

---

## 0. 代码地图与设计落点

### 现有可复用能力

- `src/adk_agent/main_web_start_steering.py:256-355`
  - `SteeringSession`
  - `self.queue = asyncio.Queue()` 已可承接 stop/cancel 信号
  - `self.stream_queue = asyncio.Queue()` + `report_swarm_event()` 已可承接 brief/status 旁路事件
- `src/adk_agent/main_web_start_steering.py:933-1451`
  - 现有 `run_task()` 已有 session 创建/恢复、Runner 驱动、事件快照、save_session、memory archive 接线
- `src/adk_agent/main_web_start_steering.py:1451-1617`
  - `_archive_turn_to_memory()` 已实现 append-only markdown 落盘范式，可直接借鉴 KAIROS activity log 写法
- `src/adk_agent/main_web_start_steering.py:1797-1922`
  - `SessionManager.get_or_create()` 已是 runtime 最自然的宿主入口
- `src/adk_agent/main_web_start_steering.py:2370-2524`
  - 现有 `/api/chat`、`/api/cancel` 已定义前台执行与中断边界
- `src/adk_agent/main_web_start_steering.py:2944-3028`
  - session metadata API 证明 `session.state` 非常适合承载 KAIROS 运行时状态
- `src/shared/db/custom_table_db_service.py:110-234`
  - `get_session()` / `create_session()` / `save_session()` / `list_sessions()` 足够支撑 Phase 1，无需改表结构
- `skills/dex/tools.py:15-254`
  - `DexManager`、`create_task()`、`start_background_process()`、`load_task()`、`list_tasks()` 已构成后台任务系统
- `skills/dex/dex_exec.py:18-163`
  - 后台进程执行、日志落盘、task 完成状态回写都已可直接复用
- `skills/agent_team_to_be_update/inbox_watcher.py:35-236`
  - `/wake` + wake flag 文件模型可作为 Phase 2 supervisor 演进参考，Phase 1 不直接耦合进去
- `skills/agent_team_to_be_update/mailbox.py:93-236`、`polling_daemon.py:37-220`
  - append-only mailbox / polling 原语说明项目已有弱 supervisor-worker 倾向，但本阶段只借鉴，不直接接入

### 本阶段新增文件

- Create: `src/adk_agent/kairos/__init__.py`
- Create: `src/adk_agent/kairos/models.py`
- Create: `src/adk_agent/kairos/activity_log.py`
- Create: `src/adk_agent/kairos/dex_bridge.py`
- Create: `src/adk_agent/kairos/runtime.py`
- Create: `src/adk_agent/kairos/api.py`
- Create: `tests/kairos/test_models.py`
- Create: `tests/kairos/test_activity_log.py`
- Create: `tests/kairos/test_dex_bridge.py`
- Create: `tests/kairos/test_runtime.py`
- Create: `tests/kairos/test_api.py`

### 本阶段修改文件

- Modify: `src/adk_agent/main_web_start_steering.py:256-355`
  - 在 `SteeringSession` 上挂载 `kairos_runtime`
- Modify: `src/adk_agent/main_web_start_steering.py:933-1451`
  - 抽出可复用的内部 ADK 执行入口，供 `/api/chat` 与 KAIROS runtime 共用
- Modify: `src/adk_agent/main_web_start_steering.py:1797-1922`
  - 为 `SessionManager` 增加获取 KAIROS runtime 的便利方法（如有必要）
- Modify: `src/adk_agent/main_web_start_steering.py:2370-2524`
  - 保持 `/api/chat` 逻辑不变，只补 KAIROS 与 `WORKER_LOCK` 的避让规则
- Modify: `src/adk_agent/main_web_start_steering.py:2944-3028`
  - 注册新的 session-scoped KAIROS API，而不是继续把实现写成新的巨大内联路由块

### 必须坚持的约束

1. **不改 SQLite schema。** KAIROS 状态放 `session.state["kairos"]`。
2. **不改 Dex 文件格式。** 只读写 Dex 既有 JSON 任务文件。
3. **不依赖完整 attach/view。** Phase 1 用 `recent_events + status API` 暴露状态。
4. **KAIROS 事件必须双写。** 一次事件同时写：
   - `report_swarm_event()`（若当前有监听）
   - `session.state["kairos"]["recent_events"]`
   - append-only activity log
5. **KAIROS 不能和前台 `/api/chat` 抢执行权。** Autonomous tick 必须先检查 `WORKER_LOCK`，忙时只记状态，不强行跑模型。

---

## 1. 最小 API 约定

全部采用 session-scoped 路由，和现有 `/api/sessions/{session_id}/...` 风格一致：

- `POST /api/sessions/{session_id}/kairos/start`
- `POST /api/sessions/{session_id}/kairos/stop`
- `POST /api/sessions/{session_id}/kairos/wake`
- `GET /api/sessions/{session_id}/kairos/status`

返回结构统一为：

```json
{
  "status": "ok",
  "session_id": "session_xxx",
  "kairos": {
    "enabled": true,
    "mode": "sleeping",
    "running": true,
    "busy": false,
    "sleep_until": "2026-04-02T12:00:00",
    "pending_wake_reason": null,
    "tracked_dex_tasks": ["abc12345"],
    "recent_events": [
      {
        "kind": "brief",
        "message": "Dex task abc12345 completed",
        "ts": "2026-04-02T12:03:00"
      }
    ]
  }
}
```

---

## 2. Phase 1 边界

### 要做

- 单 session assistant runtime
- start / stop / wake / status API
- tick loop
- sleep / wake state
- recent brief/status events
- Dex task 跟踪与完成通知
- append-only KAIROS activity log
- 与现有 `SteeringSession` 共存

### 不做

- cron 表达式调度
- 完整 attach/view UI
- GitHub webhook
- nightly distill / dream
- 多进程 supervisor
- 自动把所有 BashTool 调用都改造成 Dex handoff

### Dex handoff 的 Phase 1 定义

本阶段只实现 **Kairos-owned Dex tracking**：

1. KAIROS runtime 可以登记 Dex task id
2. runtime 在 tick 中轮询 Dex 状态
3. Dex 完成/失败时产生日志、recent event、brief
4. **不在 Phase 1 强行改造全部工具调用自动后台化**

这样能先跑通 runtime 语义，不把范围炸到 BashTool/PowerShellTool/AgentTool。

---

### Task 1: 冻结 KAIROS 状态模型与 session.state 契约

**Files:**
- Create: `src/adk_agent/kairos/__init__.py`
- Create: `src/adk_agent/kairos/models.py`
- Test: `tests/kairos/test_models.py`

- [ ] **Step 1: 写失败测试，锁定状态序列化格式**

```python
from src.adk_agent.kairos.models import (
    KairosEvent,
    KairosMode,
    KairosState,
    dump_kairos_state,
    load_kairos_state,
)


def test_load_empty_state_uses_defaults():
    state = load_kairos_state(None)

    assert state.enabled is False
    assert state.mode is KairosMode.STOPPED
    assert state.tracked_dex_task_ids == []
    assert state.recent_events == []


def test_dump_round_trip_preserves_recent_events():
    original = KairosState(
        enabled=True,
        running=True,
        mode=KairosMode.SLEEPING,
        sleep_until="2026-04-02T12:00:00",
        tracked_dex_task_ids=["abc12345"],
        recent_events=[
            KairosEvent(kind="brief", message="runtime started", ts="2026-04-02T11:59:00")
        ],
    )

    dumped = dump_kairos_state(original)
    restored = load_kairos_state(dumped)

    assert restored.enabled is True
    assert restored.mode is KairosMode.SLEEPING
    assert restored.tracked_dex_task_ids == ["abc12345"]
    assert restored.recent_events[0].message == "runtime started"


def test_recent_events_are_trimmed_to_last_20():
    state = KairosState(enabled=True, running=True, mode=KairosMode.IDLE)
    for idx in range(25):
        state.push_event(KairosEvent(kind="status", message=f"event-{idx}", ts=f"2026-04-02T12:00:{idx:02d}"))

    assert len(state.recent_events) == 20
    assert state.recent_events[0].message == "event-5"
    assert state.recent_events[-1].message == "event-24"
```

- [ ] **Step 2: 运行测试，确认当前失败**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.adk_agent.kairos.models'`

- [ ] **Step 3: 写最小实现**

`src/adk_agent/kairos/models.py`

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


@dataclass
class KairosEvent:
    kind: str
    message: str
    ts: str
    level: str = "normal"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KairosState:
    enabled: bool = False
    running: bool = False
    busy: bool = False
    mode: KairosMode = KairosMode.STOPPED
    sleep_until: str | None = None
    pending_wake_reason: str | None = None
    tracked_dex_task_ids: list[str] = field(default_factory=list)
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
        pending_wake_reason=raw.get("pending_wake_reason"),
        tracked_dex_task_ids=list(raw.get("tracked_dex_task_ids", [])),
        recent_events=[KairosEvent(**item) for item in raw.get("recent_events", [])],
    )


def dump_kairos_state(state: KairosState) -> dict[str, Any]:
    payload = asdict(state)
    payload["mode"] = state.mode.value
    return payload
```

`src/adk_agent/kairos/__init__.py`

```python
from .models import KairosEvent, KairosMode, KairosState, dump_kairos_state, load_kairos_state

__all__ = [
    "KairosEvent",
    "KairosMode",
    "KairosState",
    "dump_kairos_state",
    "load_kairos_state",
]
```

- [ ] **Step 4: 重新运行测试，确认通过**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_models.py -v
```

Expected: `3 passed`

- [ ] **Step 5: 提交**

```bash
git add tests/kairos/test_models.py src/adk_agent/kairos/__init__.py src/adk_agent/kairos/models.py
git commit -m "feat(kairos): add runtime state contract"
```

---

### Task 2: 实现 append-only KAIROS activity log

**Files:**
- Create: `src/adk_agent/kairos/activity_log.py`
- Test: `tests/kairos/test_activity_log.py`

- [ ] **Step 1: 写失败测试，锁定日志路径与追加格式**

```python
from pathlib import Path

from src.adk_agent.kairos.activity_log import KairosActivityLog


def test_append_creates_month_partitioned_log(tmp_path: Path):
    writer = KairosActivityLog(project_root=tmp_path)

    path = writer.append_entry(
        user_id="alice",
        app_name="demo_app",
        session_id="session_123",
        kind="status",
        message="runtime started",
        ts="2026-04-02T12:00:00",
    )

    assert path.exists()
    assert "memory_archive" in str(path)
    text = path.read_text(encoding="utf-8")
    assert "kind: status" in text
    assert "runtime started" in text


def test_append_is_append_only(tmp_path: Path):
    writer = KairosActivityLog(project_root=tmp_path)

    path = writer.append_entry("alice", "demo_app", "session_123", "status", "first", "2026-04-02T12:00:00")
    writer.append_entry("alice", "demo_app", "session_123", "brief", "second", "2026-04-02T12:05:00")

    text = path.read_text(encoding="utf-8")
    assert text.count("## ") == 2
    assert "first" in text
    assert "second" in text
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_activity_log.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 写最小实现，显式复用 `_archive_turn_to_memory()` 的目录习惯**

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from filelock import FileLock


class KairosActivityLog:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)

    def append_entry(
        self,
        user_id: str,
        app_name: str,
        session_id: str,
        kind: str,
        message: str,
        ts: str,
    ) -> Path:
        dt = datetime.fromisoformat(ts)
        month_str = dt.strftime("%Y-%m")
        date_str = dt.strftime("%Y-%m-%d")
        safe_app_name = app_name.replace("/", "_").replace("\\", "_")

        log_dir = self.project_root / "memory_archive" / user_id / month_str
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{date_str}_{safe_app_name}_{session_id}_kairos.md"

        if not log_path.exists():
            log_path.write_text(
                "---\n"
                f"user_id: {user_id}\n"
                f"app_name: {app_name}\n"
                f"session_id: {session_id}\n"
                "kind: kairos_activity\n"
                "---\n\n",
                encoding="utf-8",
            )

        block = (
            f"## {ts}\n"
            f"kind: {kind}\n"
            f"message: {message}\n\n"
        )

        lock = FileLock(str(log_path) + ".lock", timeout=5)
        with lock:
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(block)
        return log_path
```

- [ ] **Step 4: 重新运行测试，确认通过**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_activity_log.py -v
```

Expected: `2 passed`

- [ ] **Step 5: 提交**

```bash
git add tests/kairos/test_activity_log.py src/adk_agent/kairos/activity_log.py
git commit -m "feat(kairos): add append-only activity log"
```

---

### Task 3: 实现 Dex 任务桥接层

**Files:**
- Create: `src/adk_agent/kairos/dex_bridge.py`
- Test: `tests/kairos/test_dex_bridge.py`

- [ ] **Step 1: 写失败测试，锁定 Dex 状态映射**

```python
import json
from pathlib import Path

from src.adk_agent.kairos.dex_bridge import DexTaskSnapshot, KairosDexBridge


def test_read_task_maps_completed_status(tmp_path: Path):
    dex_root = tmp_path / ".dex" / "tasks" / "alice"
    dex_root.mkdir(parents=True)
    (dex_root / "abc12345.json").write_text(
        json.dumps({
            "id": "abc12345",
            "status": "completed",
            "description": "run report",
            "result": "[SUCCESS]"
        }),
        encoding="utf-8",
    )

    bridge = KairosDexBridge(base_dir=tmp_path, user_id="alice")
    snap = bridge.get_task("abc12345")

    assert snap.task_id == "abc12345"
    assert snap.status == "completed"
    assert snap.result == "[SUCCESS]"


def test_list_tracked_tasks_returns_only_existing_ids(tmp_path: Path):
    dex_root = tmp_path / ".dex" / "tasks" / "alice"
    dex_root.mkdir(parents=True)
    (dex_root / "a1.json").write_text(json.dumps({"id": "a1", "status": "running", "description": "job"}), encoding="utf-8")

    bridge = KairosDexBridge(base_dir=tmp_path, user_id="alice")
    tasks = bridge.get_tasks(["a1", "missing"])

    assert [task.task_id for task in tasks] == ["a1"]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_dex_bridge.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 写最小实现，直接包装 `DexManager`**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skills.dex.tools import DexManager


@dataclass
class DexTaskSnapshot:
    task_id: str
    status: str
    description: str
    result: str = ""


class KairosDexBridge:
    def __init__(self, base_dir: str, user_id: str):
        self.manager = DexManager(base_dir=base_dir, user_id=user_id)

    def get_task(self, task_id: str) -> DexTaskSnapshot | None:
        try:
            raw = self.manager.load_task(task_id)
        except FileNotFoundError:
            return None
        return DexTaskSnapshot(
            task_id=raw["id"],
            status=raw.get("status", "pending"),
            description=raw.get("description", ""),
            result=raw.get("result", ""),
        )

    def get_tasks(self, task_ids: Iterable[str]) -> list[DexTaskSnapshot]:
        result = []
        for task_id in task_ids:
            snap = self.get_task(task_id)
            if snap is not None:
                result.append(snap)
        return result
```

- [ ] **Step 4: 重新运行测试，确认通过**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_dex_bridge.py -v
```

Expected: `2 passed`

- [ ] **Step 5: 提交**

```bash
git add tests/kairos/test_dex_bridge.py src/adk_agent/kairos/dex_bridge.py
git commit -m "feat(kairos): add dex bridge"
```

---

### Task 4: 实现 runtime 核心：tick / sleep / wake / Dex polling / recent events

**Files:**
- Create: `src/adk_agent/kairos/runtime.py`
- Test: `tests/kairos/test_runtime.py`

- [ ] **Step 1: 写失败测试，锁定运行时行为**

```python
import asyncio

import pytest

from src.adk_agent.kairos.models import KairosMode, KairosState
from src.adk_agent.kairos.runtime import KairosRuntime


class FakeDexBridge:
    def __init__(self):
        self.tasks = {}

    def get_tasks(self, task_ids):
        return [self.tasks[task_id] for task_id in task_ids if task_id in self.tasks]


@pytest.mark.asyncio
async def test_wake_emits_event_and_clears_pending_reason():
    saved = []
    emitted = []
    logged = []

    async def save_state(state):
        saved.append(state.mode.value)

    async def emit_event(event):
        emitted.append((event.kind, event.message))

    async def append_log(event):
        logged.append(event.message)

    async def run_turn(reason):
        return f"ran:{reason}"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.IDLE),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        tick_interval_seconds=0.01,
    )

    await runtime.wake("manual")
    await runtime.tick_once()

    assert runtime.state.pending_wake_reason is None
    assert any(kind == "brief" for kind, _ in emitted)
    assert logged


@pytest.mark.asyncio
async def test_completed_dex_task_creates_brief_and_untracks():
    class Snap:
        def __init__(self, task_id, status, description, result=""):
            self.task_id = task_id
            self.status = status
            self.description = description
            self.result = result

    emitted = []
    async def noop_state(_):
        return None
    async def emit_event(event):
        emitted.append(event.message)
    async def append_log(_):
        return None
    async def run_turn(_):
        return None

    bridge = FakeDexBridge()
    bridge.tasks["abc12345"] = Snap("abc12345", "completed", "run report", "[SUCCESS]")

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.SLEEPING,
            tracked_dex_task_ids=["abc12345"],
        ),
        save_state=noop_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=bridge,
        tick_interval_seconds=0.01,
    )

    await runtime.tick_once()

    assert runtime.state.tracked_dex_task_ids == []
    assert any("abc12345" in msg for msg in emitted)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_runtime.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 写最小实现，保持 runtime 可单元测试**

```python
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Awaitable, Callable

from .models import KairosEvent, KairosMode, KairosState


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
    ):
        self.state = state
        self._save_state = save_state
        self._emit_event = emit_event
        self._append_log = append_log
        self._run_turn = run_turn
        self._dex_bridge = dex_bridge
        self._tick_interval_seconds = tick_interval_seconds
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self.state.enabled = True
        self.state.running = True
        self.state.mode = KairosMode.IDLE
        await self._persist()
        await self._record("status", "kairos runtime started")

    async def stop(self) -> None:
        self.state.running = False
        self.state.busy = False
        self.state.pending_wake_reason = None
        self.state.mode = KairosMode.STOPPED
        await self._persist()
        await self._record("status", "kairos runtime stopped")

    async def wake(self, reason: str) -> None:
        self.state.pending_wake_reason = reason
        if self.state.mode == KairosMode.SLEEPING:
            self.state.mode = KairosMode.IDLE
        await self._persist()
        await self._record("status", f"wake requested: {reason}")

    async def tick_once(self) -> None:
        async with self._lock:
            await self._poll_dex()
            if not self.state.running:
                return
            if self.state.pending_wake_reason and not self.state.busy:
                reason = self.state.pending_wake_reason
                self.state.pending_wake_reason = None
                self.state.busy = True
                self.state.mode = KairosMode.RUNNING
                await self._persist()
                await self._record("brief", f"kairos turn started: {reason}")
                try:
                    await self._run_turn(reason)
                finally:
                    self.state.busy = False
                    self.state.mode = KairosMode.SLEEPING
                    self.state.sleep_until = (datetime.utcnow() + timedelta(seconds=self._tick_interval_seconds)).isoformat()
                    await self._persist()
                    await self._record("brief", f"kairos turn finished: {reason}")

    async def _poll_dex(self) -> None:
        remaining = []
        for task in self._dex_bridge.get_tasks(self.state.tracked_dex_task_ids):
            if task.status in {"completed", "failed"}:
                await self._record("brief", f"Dex task {task.task_id} {task.status}: {task.description}")
            else:
                remaining.append(task.task_id)
        self.state.tracked_dex_task_ids = remaining
        await self._persist()

    async def _record(self, kind: str, message: str) -> None:
        event = KairosEvent(kind=kind, message=message, ts=datetime.utcnow().isoformat())
        self.state.push_event(event)
        await self._emit_event(event)
        await self._append_log(event)
        await self._persist()

    async def _persist(self) -> None:
        await self._save_state(self.state)
```

- [ ] **Step 4: 重新运行测试，确认通过**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_runtime.py -v
```

Expected: `2 passed`

- [ ] **Step 5: 提交**

```bash
git add tests/kairos/test_runtime.py src/adk_agent/kairos/runtime.py
git commit -m "feat(kairos): add tick sleep wake runtime"
```

---

### Task 5: 把 runtime 接入 SteeringSession，并抽出可复用的内部 ADK 执行入口

**Files:**
- Modify: `src/adk_agent/main_web_start_steering.py:256-355`
- Modify: `src/adk_agent/main_web_start_steering.py:933-1451`
- Create: `src/adk_agent/kairos/api.py`
- Test: `tests/kairos/test_api.py`

- [ ] **Step 1: 先写 API 级失败测试，锁定 start/wake/status 路由**

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adk_agent.kairos.api import register_kairos_routes


class FakeRuntime:
    def __init__(self):
        self.started = False
        self.state = {
            "enabled": False,
            "mode": "stopped",
            "recent_events": [],
        }

    async def start(self):
        self.started = True
        self.state["enabled"] = True
        self.state["mode"] = "idle"

    async def stop(self):
        self.state["enabled"] = False
        self.state["mode"] = "stopped"

    async def wake(self, reason):
        self.state["recent_events"].append({"kind": "status", "message": reason})

    def get_status(self):
        return self.state


class FakeSession:
    def __init__(self):
        self.runtime = FakeRuntime()


class FakeManager:
    def __init__(self):
        self.session = FakeSession()

    def get_or_create(self, app_name, user_id, session_id):
        return self.session


def test_start_and_status_routes_work():
    app = FastAPI()
    register_kairos_routes(app, FakeManager())
    client = TestClient(app)

    start_resp = client.post(
        "/api/sessions/session_1/kairos/start",
        json={"app_name": "demo", "user_id": "alice"},
    )
    assert start_resp.status_code == 200

    status_resp = client.get(
        "/api/sessions/session_1/kairos/status",
        params={"app_name": "demo", "user_id": "alice"},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["kairos"]["mode"] == "idle"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_api.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 在 `SteeringSession` 上加 runtime 装载与状态持久化方法**

在 `src/adk_agent/main_web_start_steering.py:256-355` 附近新增以下最小能力：

```python
from pathlib import Path

from src.adk_agent.kairos.activity_log import KairosActivityLog
from src.adk_agent.kairos.dex_bridge import KairosDexBridge
from src.adk_agent.kairos.models import dump_kairos_state, load_kairos_state
from src.adk_agent.kairos.runtime import KairosRuntime
```

```python
self.kairos_runtime = None
```

```python
async def _save_kairos_state(self, kairos_state):
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
    if not session.state:
        session.state = {}
    session.state["kairos"] = dump_kairos_state(kairos_state)
    await self.session_service.save_session(session)


async def _emit_kairos_event(self, event):
    self.report_swarm_event(
        "kairos_event",
        {"kind": event.kind, "message": event.message, "ts": event.ts, "level": event.level},
    )


async def _append_kairos_log(self, event):
    project_root = Path(__file__).resolve().parents[2]
    KairosActivityLog(project_root).append_entry(
        user_id=self.user_id,
        app_name=self.app_name,
        session_id=self.session_id,
        kind=event.kind,
        message=event.message,
        ts=event.ts,
    )
```

```python
def get_or_create_kairos_runtime(self):
    if self.kairos_runtime is not None:
        return self.kairos_runtime

    raw = {}
    if self._current_session and getattr(self._current_session, "state", None):
        raw = self._current_session.state.get("kairos", {})

    self.kairos_runtime = KairosRuntime(
        state=load_kairos_state(raw),
        save_state=self._save_kairos_state,
        emit_event=self._emit_kairos_event,
        append_log=self._append_kairos_log,
        run_turn=self.run_kairos_turn,
        dex_bridge=KairosDexBridge(base_dir=os.getcwd(), user_id=self.user_id),
        tick_interval_seconds=15.0,
    )
    return self.kairos_runtime
```

- [ ] **Step 4: 从现有 `run_task()` 提取内部共享执行入口，避免重复实现 Runner 逻辑**

在 `src/adk_agent/main_web_start_steering.py:933-1451` 这一段，不要复制第二份 Runner 逻辑，而是把核心执行抽成一个内部方法，形态如下：

```python
async def _run_agent_turn(self, task: str, images: list[str] | None = None, yield_chunks: bool = True):
    # 把当前 run_task() 中 session 获取、Runner 创建、event snapshot、save_session、archive 等核心逻辑搬进来
    # 唯一差别：
    # 1. yield_chunks=True 时给 /api/chat 用
    # 2. yield_chunks=False 时给 KAIROS runtime 用，只消费内部 chunk，不向 HTTP 返回
    ...


async def run_task(self, task: str, images: list[str] | None = None):
    async for chunk in self._run_agent_turn(task, images=images, yield_chunks=True):
        yield chunk


async def run_kairos_turn(self, reason: str):
    synthetic_prompt = (
        "[KAIROS_TICK]\n"
        f"reason={reason}\n"
        "你现在处于 assistant runtime 模式。请检查是否有需要汇报的状态、是否有已完成的 Dex 任务、"
        "是否应该继续 sleep。输出简洁 brief；如果没有实质工作，直接进入 sleep。"
    )
    async for _ in self._run_agent_turn(synthetic_prompt, images=None, yield_chunks=False):
        pass
    return "ok"
```

这一步的关键目标不是“重构整个文件”，而是**只抽出 KAIROS 真正必须共用的执行骨架**。

- [ ] **Step 5: 写 `src/adk_agent/kairos/api.py` 并注册到主 FastAPI app**

`src/adk_agent/kairos/api.py`

```python
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel


class KairosSessionRequest(BaseModel):
    app_name: str
    user_id: str
    reason: str | None = None


def register_kairos_routes(app, session_manager):
    router = APIRouter()

    @router.post("/api/sessions/{session_id}/kairos/start")
    async def start_kairos(session_id: str, req: KairosSessionRequest):
        session = session_manager.get_or_create(req.app_name, req.user_id, session_id)
        runtime = session.get_or_create_kairos_runtime()
        await runtime.start()
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}

    @router.post("/api/sessions/{session_id}/kairos/stop")
    async def stop_kairos(session_id: str, req: KairosSessionRequest):
        session = session_manager.get_or_create(req.app_name, req.user_id, session_id)
        runtime = session.get_or_create_kairos_runtime()
        await runtime.stop()
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}

    @router.post("/api/sessions/{session_id}/kairos/wake")
    async def wake_kairos(session_id: str, req: KairosSessionRequest):
        session = session_manager.get_or_create(req.app_name, req.user_id, session_id)
        runtime = session.get_or_create_kairos_runtime()
        await runtime.wake(req.reason or "manual")
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}

    @router.get("/api/sessions/{session_id}/kairos/status")
    async def kairos_status(session_id: str, app_name: str, user_id: str):
        session = session_manager.get_or_create(app_name, user_id, session_id)
        runtime = session.get_or_create_kairos_runtime()
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}

    app.include_router(router)
```

在 `src/adk_agent/main_web_start_steering.py` 中创建 FastAPI app 后注册：

```python
from src.adk_agent.kairos.api import register_kairos_routes
```

```python
register_kairos_routes(app, session_manager)
```

如果注册时 `session_manager` 尚未初始化，就改成闭包 getter：

```python
register_kairos_routes(app, lambda: session_manager)
```

但二选一，不要两套都留着。

- [ ] **Step 6: 给 `KairosRuntime` 增加 `get_status()`，然后跑 API 测试**

在 `src/adk_agent/kairos/runtime.py` 加：

```python
from .models import dump_kairos_state


def get_status(self) -> dict:
    return dump_kairos_state(self.state)
```

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_api.py -v
```

Expected: `1 passed`

- [ ] **Step 7: 提交**

```bash
git add src/adk_agent/main_web_start_steering.py src/adk_agent/kairos/api.py src/adk_agent/kairos/runtime.py tests/kairos/test_api.py
git commit -m "feat(kairos): integrate runtime with steering session"
```

---

### Task 6: 补 busy 避让规则与完整回归验证

**Files:**
- Modify: `src/adk_agent/kairos/runtime.py`
- Modify: `src/adk_agent/main_web_start_steering.py:2370-2443`
- Test: `tests/kairos/test_runtime.py`

- [ ] **Step 1: 先补失败测试，锁定“前台忙时不抢跑”**

```python
import pytest

from src.adk_agent.kairos.models import KairosMode, KairosState
from src.adk_agent.kairos.runtime import KairosRuntime


@pytest.mark.asyncio
async def test_tick_skips_run_turn_when_worker_is_busy():
    called = []

    async def save_state(_):
        return None

    async def emit_event(_):
        return None

    async def append_log(_):
        return None

    async def run_turn(_):
        called.append(True)

    class FakeDex:
        def get_tasks(self, _):
            return []

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.IDLE, pending_wake_reason="manual"),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDex(),
        is_worker_busy=lambda: True,
    )

    await runtime.tick_once()

    assert called == []
    assert runtime.state.pending_wake_reason == "manual"
```

- [ ] **Step 2: 运行失败测试**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_runtime.py -v
```

Expected: `TypeError: __init__() got an unexpected keyword argument 'is_worker_busy'`

- [ ] **Step 3: 写最小实现，只做避让，不改 `/api/chat` 主流程**

在 `src/adk_agent/kairos/runtime.py` 构造函数加一个忙碌探针：

```python
is_worker_busy: Callable[[], bool] | None = None,
```

并保存：

```python
self._is_worker_busy = is_worker_busy or (lambda: False)
```

在 `tick_once()` 最前面加：

```python
if self._is_worker_busy():
    await self._record("status", "worker busy, skip kairos tick")
    return
```

在 `SteeringSession.get_or_create_kairos_runtime()` 中注入：

```python
is_worker_busy=lambda: WORKER_LOCK.locked(),
```

注意：这里只是**避让前台请求**，不是把 `WORKER_LOCK` 直接暴露到 KAIROS 包的全局模块里。

- [ ] **Step 4: 跑完整回归**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/kairos/test_models.py tests/kairos/test_activity_log.py tests/kairos/test_dex_bridge.py tests/kairos/test_runtime.py tests/kairos/test_api.py -v
```

Expected: 全部通过

- [ ] **Step 5: 做手工 smoke test**

启动服务：

```bash
PYTHONIOENCODING=utf-8 python -m src.adk_agent.main_web_start_steering --port 8000
```

新建会话：

```bash
curl -X POST http://127.0.0.1:8000/api/sessions -H "Content-Type: application/json" -d '{"app_name":"assistant","user_id":"alice"}'
```

启动 KAIROS：

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/start -H "Content-Type: application/json" -d '{"app_name":"assistant","user_id":"alice"}'
```

手动唤醒：

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/wake -H "Content-Type: application/json" -d '{"app_name":"assistant","user_id":"alice","reason":"manual_smoke"}'
```

查看状态：

```bash
curl "http://127.0.0.1:8000/api/sessions/<SESSION_ID>/kairos/status?app_name=assistant&user_id=alice"
```

检查日志文件：

```bash
ls "D:/git_repos/google_adk_agent/memory_archive/alice"
```

Expected:
- status API 返回 `mode`、`recent_events`
- `memory_archive/alice/<YYYY-MM>/..._kairos.md` 新增日志文件
- 若当前 worker 忙，`recent_events` 能看到 `worker busy, skip kairos tick`

- [ ] **Step 6: 提交**

```bash
git add src/adk_agent/kairos/runtime.py src/adk_agent/main_web_start_steering.py tests/kairos/test_runtime.py
git commit -m "fix(kairos): avoid foreground chat contention"
```

---

## 3. 关键实现细节与取舍

### 3.1 为什么 KAIROS 状态放 `session.state["kairos"]`

因为 `src/shared/db/custom_table_db_service.py:168-218` 的 `save_session()` 已经会完整持久化 `session.state`，这正好适合 KAIROS 的轻量运行时元数据。Phase 1 不需要新表，不需要 event schema migration。

### 3.2 为什么 brief/status 要同时写三处

仅写 `stream_queue` 不够，因为 `src/adk_agent/main_web_start_steering.py:1169-1271` 只有在 `run_task()` 流式执行时才会消费 `stream_queue`。KAIROS runtime 是后台常驻逻辑，不保证永远有前台 SSE 监听，所以必须双写到 `recent_events` 和 activity log。

### 3.3 为什么不在 Phase 1 接入 mailbox / wake flag

`skills/agent_team_to_be_update/inbox_watcher.py:111-198`、`mailbox.py:93-236`、`polling_daemon.py:37-220` 很适合 Phase 2 supervisor 化，但 Phase 1 采用内嵌 runtime，不应该过早把 session 生命周期拆成另一套文件协调系统。

### 3.4 最危险的耦合点

1. `WORKER_LOCK`：如果 KAIROS runtime 和 `/api/chat` 同时跑模型，会互相踩。
2. `run_task()` 太长：不要复制第二份，要抽共享执行骨架。
3. `stream_queue` 无消费者时会积压：所以一定要保底写 `recent_events`。
4. Dex 不是消息总线：Phase 1 只做 tracked task polling，不做“自动后台化所有工具调用”。
5. `_archive_turn_to_memory()` 已写普通对话黑匣子：KAIROS activity log 必须用独立后缀 `_kairos.md`，避免和人类 turn 混写。

---

## 4. 完成标准

以下全部满足才算 Phase 1 完成：

- `POST /api/sessions/{session_id}/kairos/start` 可启动 runtime
- `POST /api/sessions/{session_id}/kairos/wake` 可触发一次 autonomous tick
- `POST /api/sessions/{session_id}/kairos/stop` 可停止 runtime
- `GET /api/sessions/{session_id}/kairos/status` 返回结构化状态与 recent events
- KAIROS 事件写入 `session.state["kairos"]`
- KAIROS 事件写入 `memory_archive/..._kairos.md`
- worker 忙时 runtime 会避让，而不是和 `/api/chat` 竞争
- Dex tracked task 完成后能出现在 `recent_events` 与 activity log
- 新增测试全部通过

---

## 5. 自检

### Spec coverage

- 单 session assistant runtime：Task 4 + Task 5
- tick / sleep / wake：Task 4
- brief / status 输出：Task 4 + Task 6
- Dex 后台任务接管（Phase 1 定义版）：Task 3 + Task 4
- append-only activity log：Task 2
- start / stop / wake / status API：Task 5

### Placeholder scan

- 无 `TODO` / `TBD`
- 每个任务都给了文件路径、测试、命令、期望结果
- 关键代码都给了明确签名和最小实现骨架

### Type consistency

- 统一使用 `KairosState` / `KairosEvent` / `KairosRuntime`
- API 返回统一 `{"status": "ok", "session_id": ..., "kairos": ...}`
- Dex bridge 统一暴露 `get_task()` / `get_tasks()`

---

Plan complete and saved to `docs/实现phase-1的kairos/plan-phase-1-kairos.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

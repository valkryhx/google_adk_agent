import asyncio
from datetime import UTC, datetime

import pytest

from src.adk_agent.kairos.models import KairosMode, KairosSchedule, KairosState, KairosTrigger, TriggerKind
from src.adk_agent.kairos.runtime import KairosRuntime


class FakeDexBridge:
    def __init__(self):
        self.tasks = {}

    def get_tasks(self, task_ids):
        return [self.tasks[task_id] for task_id in task_ids if task_id in self.tasks]


class FakeDex:
    def get_tasks(self, _):
        return []


def _make_callbacks():
    """Helper to create standard test callbacks."""
    saved = []
    emitted = []
    logged = []

    async def save_state(state):
        saved.append(state)

    async def emit_event(event):
        emitted.append((event.kind, event.message))

    async def append_log(event):
        logged.append(event.message)

    return saved, emitted, logged, save_state, emit_event, append_log


# === Phase 1 existing tests ===


@pytest.mark.asyncio
async def test_wake_emits_event_and_clears_pending_reason():
    saved, emitted, logged, save_state, emit_event, append_log = _make_callbacks()

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

    _, emitted, _, save_state, emit_event, append_log = _make_callbacks()

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
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=bridge,
        tick_interval_seconds=0.01,
    )

    await runtime.tick_once()

    assert runtime.state.tracked_dex_task_ids == []
    assert any("abc12345" in msg for _, msg in emitted)


@pytest.mark.asyncio
async def test_tick_skips_run_turn_when_worker_is_busy():
    called = []
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        called.append(True)

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


@pytest.mark.asyncio
async def test_start_creates_background_tick_loop_and_stop_cancels_it():
    ticks = asyncio.Event()
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        ticks.set()
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=False, mode=KairosMode.STOPPED),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        tick_interval_seconds=0.01,
    )

    await runtime.start()
    await runtime.wake("loop-test")
    await asyncio.wait_for(ticks.wait(), timeout=0.2)

    assert runtime._task is not None
    assert not runtime._task.done()

    await runtime.stop()
    await asyncio.sleep(0)

    assert runtime.state.mode is KairosMode.STOPPED
    assert runtime._task is None


@pytest.mark.asyncio
async def test_wake_triggers_prompt_execution_without_waiting_full_interval():
    ticks = asyncio.Event()
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        ticks.set()
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=False, mode=KairosMode.STOPPED),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        tick_interval_seconds=60.0,
    )

    await runtime.start()
    await runtime.wake("immediate")
    await asyncio.wait_for(ticks.wait(), timeout=0.5)
    await runtime.stop()


@pytest.mark.asyncio
async def test_stop_keeps_final_mode_stopped_after_active_turn():
    release = asyncio.Event()
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        await release.wait()
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=False, mode=KairosMode.STOPPED),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        tick_interval_seconds=60.0,
    )

    await runtime.start()
    await runtime.wake("stop-race")
    await asyncio.sleep(0.05)
    stop_task = asyncio.create_task(runtime.stop())
    await asyncio.sleep(0.05)
    release.set()
    await stop_task

    assert runtime.state.running is False
    assert runtime.state.mode is KairosMode.STOPPED
    assert runtime._task is None


# === Phase 2 new tests: scheduler integration ===


@pytest.mark.asyncio
async def test_runtime_accepts_scheduler_parameter():
    """Runtime should accept an optional scheduler parameter."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    _, _, _, save_state, emit_event, append_log = _make_callbacks()

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

    assert runtime._scheduler is not None


@pytest.mark.asyncio
async def test_add_schedule_persists_and_seeds_next_fire_at():
    """add_schedule should persist state and seed next_fire_at."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    saved, _, _, save_state, emit_event, append_log = _make_callbacks()

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
async def test_add_schedule_replaces_existing_with_same_id():
    """Adding a schedule with same ID should replace the old one."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    _, _, _, save_state, emit_event, append_log = _make_callbacks()

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
        KairosSchedule(schedule_id="morning", cron="*/5 * * * *", reason="old_reason")
    )
    await runtime.add_schedule(
        KairosSchedule(schedule_id="morning", cron="*/10 * * * *", reason="new_reason")
    )

    assert len(runtime.state.schedules) == 1
    assert runtime.state.schedules[0].reason == "new_reason"
    assert runtime.state.schedules[0].cron == "*/10 * * * *"


@pytest.mark.asyncio
async def test_delete_schedule_removes_by_id():
    """delete_schedule should remove the schedule with matching ID."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.IDLE,
            schedules=[
                KairosSchedule(schedule_id="a", cron="*/5 * * * *", reason="a"),
                KairosSchedule(schedule_id="b", cron="*/10 * * * *", reason="b"),
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDex(),
        scheduler=KairosScheduler(),
    )

    await runtime.delete_schedule("a")

    assert len(runtime.state.schedules) == 1
    assert runtime.state.schedules[0].schedule_id == "b"


@pytest.mark.asyncio
async def test_tick_runs_due_schedule_trigger():
    """tick_once should pick up due schedule triggers and execute them."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

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


@pytest.mark.asyncio
async def test_tick_records_last_tick_at():
    """tick_once should update last_tick_at."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    _, _, _, save_state, emit_event, append_log = _make_callbacks()

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

    assert runtime.state.last_tick_at is None
    await runtime.tick_once()
    assert runtime.state.last_tick_at is not None


@pytest.mark.asyncio
async def test_enqueue_trigger_wakes_sleeping_runtime():
    """enqueue_trigger should switch mode from SLEEPING to IDLE."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.SLEEPING),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDex(),
        scheduler=KairosScheduler(),
    )

    trigger = KairosTrigger(
        trigger_id="test-1",
        kind=TriggerKind.MANUAL,
        reason="test",
        created_at="2026-04-02T12:00:00+00:00",
    )
    await runtime.enqueue_trigger(trigger)

    assert runtime.state.mode is KairosMode.IDLE
    assert len(runtime.state.pending_triggers) == 1
    assert runtime.state.pending_wake_reason == "test"


@pytest.mark.asyncio
async def test_tick_processes_pending_triggers_fifo():
    """Pending triggers should be processed in FIFO order."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    executed = []

    async def save_state(_):
        return None

    async def emit_event(_):
        return None

    async def append_log(_):
        return None

    async def run_turn(reason):
        executed.append(reason)
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.IDLE,
            pending_triggers=[
                KairosTrigger(
                    trigger_id="t1",
                    kind=TriggerKind.MANUAL,
                    reason="first",
                    created_at="2026-04-02T12:00:00+00:00",
                ),
                KairosTrigger(
                    trigger_id="t2",
                    kind=TriggerKind.SCHEDULE,
                    reason="second",
                    created_at="2026-04-02T12:01:00+00:00",
                ),
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDex(),
        scheduler=KairosScheduler(),
    )

    # First tick processes first trigger
    await runtime.tick_once()
    assert executed == ["first"]
    assert len(runtime.state.pending_triggers) == 1

    # Second tick processes second trigger
    await runtime.tick_once()
    assert executed == ["first", "second"]
    assert len(runtime.state.pending_triggers) == 0


@pytest.mark.asyncio
async def test_wake_uses_enqueue_trigger_with_manual_kind():
    """wake() should create a MANUAL trigger via enqueue_trigger."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    _, emitted, _, save_state, emit_event, append_log = _make_callbacks()

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

    await runtime.wake("test_reason")

    assert len(runtime.state.pending_triggers) == 1
    assert runtime.state.pending_triggers[0].kind is TriggerKind.MANUAL
    assert runtime.state.pending_triggers[0].reason == "test_reason"


@pytest.mark.asyncio
async def test_get_status_includes_phase2_fields():
    """get_status should return Phase 2 fields."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.IDLE,
            last_tick_at="2026-04-02T12:00:00+00:00",
            schedules=[
                KairosSchedule(
                    schedule_id="morning",
                    cron="0 9 * * *",
                    reason="morning_checkin",
                    next_fire_at="2026-04-03T09:00:00+00:00",
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

    status = runtime.get_status()

    assert "last_tick_at" in status
    assert "schedules" in status
    assert "pending_triggers" in status
    assert "active_trigger" in status
    assert status["last_tick_at"] == "2026-04-02T12:00:00+00:00"
    assert status["schedules"][0]["schedule_id"] == "morning"


# === Phase 2: Dex handoff lifecycle tests ===


@pytest.mark.asyncio
async def test_register_dex_task_switches_runtime_to_handoff():
    """register_dex_task should add task_id and switch mode to HANDOFF."""
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

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
async def test_register_dex_task_does_not_duplicate():
    """Registering the same task_id twice should not create duplicates."""
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

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
    await runtime.register_dex_task("abc12345", "run report again")

    assert runtime.state.tracked_dex_task_ids == ["abc12345"]


@pytest.mark.asyncio
async def test_completed_handoff_task_returns_runtime_to_idle():
    """When all tracked Dex tasks complete, mode should return from HANDOFF to IDLE."""
    class Snap:
        def __init__(self, task_id, status, description):
            self.task_id = task_id
            self.status = status
            self.description = description
            self.result = "[SUCCESS]"

    bridge = FakeDexBridge()
    bridge.tasks["abc12345"] = Snap("abc12345", "completed", "run report")

    _, _, _, save_state, emit_event, append_log = _make_callbacks()

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


@pytest.mark.asyncio
async def test_partial_dex_completion_keeps_handoff():
    """If some Dex tasks are still running, mode should stay HANDOFF."""
    class Snap:
        def __init__(self, task_id, status, description):
            self.task_id = task_id
            self.status = status
            self.description = description
            self.result = ""

    bridge = FakeDexBridge()
    bridge.tasks["task1"] = Snap("task1", "completed", "done")
    bridge.tasks["task2"] = Snap("task2", "running", "still going")

    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.HANDOFF,
            tracked_dex_task_ids=["task1", "task2"],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=bridge,
    )

    await runtime.tick_once()

    assert runtime.state.tracked_dex_task_ids == ["task2"]
    assert runtime.state.mode is KairosMode.HANDOFF


@pytest.mark.asyncio
async def test_failed_dex_task_is_untracked():
    """Failed Dex tasks should be removed from tracking."""
    class Snap:
        def __init__(self, task_id, status, description):
            self.task_id = task_id
            self.status = status
            self.description = description
            self.result = "[FAILED]"

    bridge = FakeDexBridge()
    bridge.tasks["fail1"] = Snap("fail1", "failed", "broken task")

    _, emitted, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.HANDOFF,
            tracked_dex_task_ids=["fail1"],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=bridge,
    )

    await runtime.tick_once()

    assert runtime.state.tracked_dex_task_ids == []
    assert any("fail1" in msg and "failed" in msg for _, msg in emitted)


@pytest.mark.asyncio
async def test_register_dex_task_does_not_switch_to_handoff_when_busy():
    """If runtime is busy, register_dex_task should not change mode."""
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.RUNNING, busy=True),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
    )

    await runtime.register_dex_task("abc12345", "run report")

    assert runtime.state.tracked_dex_task_ids == ["abc12345"]
    assert runtime.state.mode is KairosMode.RUNNING  # not changed to HANDOFF

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


@pytest.mark.asyncio
async def test_start_creates_background_tick_loop_and_stop_cancels_it():
    ticks = asyncio.Event()

    async def save_state(_):
        return None

    async def emit_event(_):
        return None

    async def append_log(_):
        return None

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

    async def save_state(_):
        return None

    async def emit_event(_):
        return None

    async def append_log(_):
        return None

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

    async def save_state(_):
        return None

    async def emit_event(_):
        return None

    async def append_log(_):
        return None

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

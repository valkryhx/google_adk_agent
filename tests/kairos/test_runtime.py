import asyncio
from datetime import UTC, datetime

import pytest

from src.adk_agent.kairos.models import (
    KairosMode,
    KairosPlannedAction,
    KairosSchedule,
    KairosState,
    KairosTrigger,
    TriggerKind,
)
from src.adk_agent.kairos.runtime import KairosRuntime
from src.adk_agent.kairos.workflows import demo_report_pipeline


class FakeDexBridge:
    def __init__(self):
        self.tasks = {}

    def get_tasks(self, task_ids):
        return [self.tasks[task_id] for task_id in task_ids if task_id in self.tasks]


class FakeDex:
    def get_tasks(self, _):
        return []


def _todo_runtime_state(*, current_stage="verification"):
    from src.adk_agent.kairos.models import KairosWorkflow, KairosWorkflowStage

    state = KairosState(enabled=True, running=True, mode=KairosMode.IDLE)
    state.active_workflow = KairosWorkflow(
        workflow_id="todo_delivery_pipeline",
        goal="deliver todo app artifacts",
        status="active",
        current_stage=current_stage,
        stages=[
            KairosWorkflowStage(
                stage_id="requirements",
                label="requirements",
                status="completed",
                task_ids=["todo_requirements"],
                artifacts=["demo_delivery/todo_app/requirements.md"],
            ),
            KairosWorkflowStage(
                stage_id="design",
                label="design",
                status="completed",
                task_ids=["todo_design"],
                artifacts=[
                    "demo_delivery/todo_app/design.md",
                    "demo_delivery/todo_app/file_plan.json",
                ],
            ),
            KairosWorkflowStage(
                stage_id="codegen",
                label="code generation",
                status="running" if current_stage == "codegen" else "completed",
                task_ids=["todo_codegen"],
                artifacts=[
                    "demo_delivery/todo_app/index.html",
                    "demo_delivery/todo_app/style.css",
                    "demo_delivery/todo_app/app.js",
                ],
            ),
            KairosWorkflowStage(
                stage_id="verification",
                label="verification",
                status="running" if current_stage == "verification" else "pending",
                task_ids=["todo_tests"],
                artifacts=[
                    "demo_delivery/todo_app/test_plan.md",
                    "demo_delivery/todo_app/smoke_check.json",
                ],
            ),
        ],
        metadata={"completed_task_ids": ["todo_requirements", "todo_design"]},
    )
    return state


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


def test_run_kairos_turn_prompt_includes_assistant_mode_context():
    from src.adk_agent.main_web_start_steering import SteeringSession

    prompt = SteeringSession._build_kairos_tick_prompt(
        reason="scheduled_scan",
        workflow_summary="todo_delivery_pipeline: codegen",
        unfinished_work_summary="codegen stage unfinished",
        policy_summary="cooldown=60 max_auto_steps_per_tick=1",
    )

    assert "[KAIROS_TICK]" in prompt
    assert "assistant runtime mode" in prompt
    assert "unfinished work" in prompt
    assert "sleep immediately" in prompt
    assert "scheduled_scan" in prompt


# === Phase 1 existing tests ===


@pytest.mark.asyncio
async def test_tick_once_refreshes_unfinished_work_and_exposes_candidates():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=_todo_runtime_state(current_stage="codegen"),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )

    await runtime.tick_once()

    assert runtime.state.unfinished_work_items[0]["stage_id"] == "codegen"
    assert runtime.state.proactive_candidates[0]["action"] == "continue_workflow"


@pytest.mark.asyncio
async def test_status_exposes_last_guardrail_block_when_auto_budget_stops_progress():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    state = _todo_runtime_state(current_stage="codegen")
    state.policy.max_auto_steps_per_tick = 0

    runtime = KairosRuntime(
        state=state,
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )

    await runtime.tick_once()
    status = runtime.get_status()

    assert status["last_guardrail_block"]["reason"] == "auto_step_budget_exhausted"


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
        def __init__(
            self,
            task_id,
            status,
            description,
            result="",
            result_summary=None,
            error_summary=None,
            created_at=None,
            completed_at=None,
            log_path=None,
        ):
            self.task_id = task_id
            self.status = status
            self.description = description
            self.result = result
            self.result_summary = result_summary
            self.error_summary = error_summary
            self.created_at = created_at
            self.completed_at = completed_at
            self.log_path = log_path

    _, emitted, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return None

    bridge = FakeDexBridge()
    bridge.tasks["abc12345"] = Snap(
        "abc12345",
        "completed",
        "run report",
        "[SUCCESS]",
        result_summary="report generated",
        completed_at="2026-04-04T00:10:00+00:00",
        log_path=".dex/logs/alice/abc12345.log",
    )

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
    assert any("report generated" in msg for _, msg in emitted)


@pytest.mark.asyncio
async def test_failed_dex_task_emits_error_summary_and_returns_to_idle():
    class Snap:
        def __init__(self, task_id, status, description, error_summary=None):
            self.task_id = task_id
            self.status = status
            self.description = description
            self.result = ""
            self.result_summary = None
            self.error_summary = error_summary
            self.created_at = None
            self.completed_at = "2026-04-04T00:10:00+00:00"
            self.log_path = ".dex/logs/alice/f1.log"

    _, emitted, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return None

    bridge = FakeDexBridge()
    bridge.tasks["f1"] = Snap("f1", "failed", "nightly build", error_summary="build failed")

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.HANDOFF,
            tracked_dex_task_ids=["f1"],
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
    assert runtime.state.mode is KairosMode.IDLE
    assert any("build failed" in msg for _, msg in emitted)


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


@pytest.mark.asyncio
async def test_register_dex_task_seeds_demo_workflow_for_phase1_inputs():
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

    await runtime.register_dex_task("sales-task", "prepare sales")

    assert runtime.state.active_workflow is not None
    assert runtime.state.active_workflow.workflow_id == "demo_report_pipeline"
    assert runtime.state.active_workflow.stages[0].task_ids == ["sales-task"]
    assert runtime.state.mode is KairosMode.HANDOFF


@pytest.mark.asyncio
async def test_todo_delivery_blocks_when_app_js_missing():
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
        path_exists=lambda path: path in {
            "demo_delivery/todo_app/requirements.md",
            "demo_delivery/todo_app/design.md",
            "demo_delivery/todo_app/file_plan.json",
            "demo_delivery/todo_app/index.html",
            "demo_delivery/todo_app/style.css",
            "demo_delivery/todo_app/test_plan.md",
            "demo_delivery/todo_app/smoke_check.json",
        },
    )

    await runtime.register_dex_task("todo-requirements-task", "todo_requirements")
    await runtime.register_dex_task("todo-design-task", "todo_design")
    await runtime.register_dex_task("todo-codegen-task", "todo_codegen")
    await runtime.register_dex_task("todo-tests-task", "todo_tests")

    bridge = runtime._dex_bridge
    bridge.tasks["todo-tests-task"] = type(
        "Snap",
        (),
        {
            "task_id": "todo-tests-task",
            "status": "completed",
            "description": "todo_tests",
            "result": "[SUCCESS]",
            "result_summary": "tests ready",
            "error_summary": None,
            "created_at": None,
            "completed_at": "2026-04-06T00:10:00+00:00",
            "log_path": ".dex/logs/alice/todo-tests-task.log",
        },
    )()

    runtime.state.tracked_dex_task_ids = ["todo-tests-task"]
    runtime.state.active_workflow.current_stage = "verification"
    runtime.state.active_workflow.metadata["completed_task_ids"] = [
        "todo_requirements",
        "todo_design",
        "todo_codegen",
        "todo_tests",
    ]
    runtime.state.active_workflow.metadata["verification_result"] = {
        "ready": True,
        "checks": {"dom_ready": True},
        "failures": [],
    }
    for stage in runtime.state.active_workflow.stages:
        if stage.stage_id in {"requirements", "design", "codegen"}:
            stage.status = "completed"

    await runtime.tick_once()

    assert runtime.state.blocked_reason == "missing required artifacts for todo delivery report"
    assert runtime.state.pending_triggers == []
    assert runtime.state.condition_tree["missing"][0]["target"] == "demo_delivery/todo_app/app.js"


@pytest.mark.asyncio
async def test_todo_delivery_runtime_blocks_on_failed_smoke_checks():
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
        path_exists=lambda path: True,
    )

    await runtime.register_dex_task("todo-requirements-task", "todo_requirements")
    await runtime.register_dex_task("todo-design-task", "todo_design")
    await runtime.register_dex_task("todo-codegen-task", "todo_codegen")
    await runtime.register_dex_task("todo-tests-task", "todo_tests")
    runtime.state.active_workflow.metadata["verification_result"] = {
        "ready": False,
        "checks": {"edit_item": False},
        "failures": [{"check": "edit_item", "reason": "editing flow failed"}],
    }

    bridge = runtime._dex_bridge
    bridge.tasks["todo-tests-task"] = type(
        "Snap",
        (),
        {
            "task_id": "todo-tests-task",
            "status": "completed",
            "description": "todo_tests",
            "result": "[SUCCESS]",
            "result_summary": "verification failed: edit_item",
            "error_summary": None,
            "created_at": None,
            "completed_at": "2026-04-06T00:10:00+00:00",
            "log_path": ".dex/logs/alice/todo-tests-task.log",
        },
    )()

    runtime.state.tracked_dex_task_ids = ["todo-tests-task"]
    runtime.state.active_workflow.current_stage = "verification"
    runtime.state.active_workflow.metadata["completed_task_ids"] = [
        "todo_requirements",
        "todo_design",
        "todo_codegen",
        "todo_tests",
        "todo-tests-task",
    ]

    await runtime.tick_once()

    assert runtime.state.blocked_reason == "verification checks failed for todo delivery report"
    assert runtime.state.pending_triggers == []
    assert runtime.state.condition_tree["failed_checks"][0]["check"] == "edit_item"


@pytest.mark.asyncio
async def test_todo_delivery_report_completion_marks_workflow_completed_with_summary():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.HANDOFF),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda path: True,
    )

    await runtime.register_dex_task("todo-report-task", "generate todo delivery report")
    bridge = runtime._dex_bridge
    bridge.tasks["todo-report-task"] = type(
        "Snap",
        (),
        {
            "task_id": "todo-report-task",
            "status": "completed",
            "description": "generate todo delivery report",
            "result": "[SUCCESS]",
            "result_summary": "delivery report ready: all checks passed",
            "error_summary": None,
            "created_at": None,
            "completed_at": "2026-04-06T00:20:00+00:00",
            "log_path": ".dex/logs/alice/todo-report-task.log",
        },
    )()

    runtime.state.tracked_dex_task_ids = ["todo-report-task"]
    await runtime.tick_once()

    assert runtime.state.active_workflow.status == "completed"
    assert runtime.state.active_workflow.stages[-1].summary == "delivery report ready: all checks passed"
    assert runtime.state.mode is KairosMode.IDLE


@pytest.mark.asyncio
async def test_internal_trigger_uses_host_callback_to_create_follow_up_task():
    bridge = FakeDexBridge()
    calls = []
    _, emitted, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    async def create_follow_up_task(reason, payload):
        calls.append((reason, payload))
        bridge.tasks["report-task"] = type(
            "Snap",
            (),
            {
                "task_id": "report-task",
                "status": "running",
                "description": payload["description"],
                "result": "",
                "result_summary": None,
                "error_summary": None,
                "created_at": None,
                "completed_at": None,
                "log_path": ".dex/logs/alice/report-task.log",
            },
        )()
        runtime.state.tracked_dex_task_ids = ["report-task"]
        return {"id": "report-task"}

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.IDLE,
            active_workflow=demo_report_pipeline(["sales", "traffic", "quality"]),
            pending_triggers=[
                KairosTrigger(
                    trigger_id="internal-demo-phase2",
                    kind=TriggerKind.INTERNAL,
                    reason="phase1_converged",
                    created_at="2026-04-05T00:00:00+00:00",
                    metadata={"workflow_id": "demo_report_pipeline", "description": "generate final report"},
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=bridge,
        create_follow_up_task=create_follow_up_task,
    )

    await runtime.tick_once()

    assert calls == [("phase1_converged", {"workflow_id": "demo_report_pipeline", "description": "generate final report"})]
    assert runtime.state.tracked_dex_task_ids == ["report-task"]
    assert runtime.state.mode is KairosMode.HANDOFF
    assert any("internal action started" in msg for _, msg in emitted)


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
async def test_get_status_exposes_artifact_aware_task_summaries():
    class Snap:
        def __init__(self, task_id, status, description, result_summary=None, error_summary=None, log_path=None):
            self.task_id = task_id
            self.status = status
            self.description = description
            self.result = ""
            self.result_summary = result_summary
            self.error_summary = error_summary
            self.created_at = "2026-04-06T00:00:00+00:00"
            self.completed_at = "2026-04-06T00:01:00+00:00"
            self.log_path = log_path

    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    bridge = FakeDexBridge()
    bridge.tasks["report-task"] = Snap(
        "report-task",
        "completed",
        "generate final report",
        result_summary="report ready: 3 inputs merged",
        log_path=".dex/logs/u1/report-task.log",
    )

    workflow = demo_report_pipeline(["report-task"])
    workflow.current_stage = "phase2"
    workflow.stages[1].task_ids = ["report-task"]

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.HANDOFF,
            tracked_dex_task_ids=["report-task"],
            active_workflow=workflow,
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=bridge,
    )
    runtime._path_exists = lambda path: path == "demo_outputs/report.json"

    status = runtime.get_status()

    assert status["task_summaries"][0]["task_id"] == "report-task"
    assert status["task_summaries"][0]["summary_text"] == "report ready: 3 inputs merged"
    assert status["task_summaries"][0]["artifact_status"] == "available"
    assert status["task_summaries"][0]["log_hint"] == ".dex/logs/u1/report-task.log"


@pytest.mark.asyncio
async def test_blocked_status_exposes_condition_tree():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    workflow = demo_report_pipeline(["sales", "traffic", "quality"])
    workflow.current_stage = "phase1"
    workflow.status = "waiting_input"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.WAITING_INPUT,
            active_workflow=workflow,
            blocked_reason="missing required artifacts for phase1 follow-up",
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
    )
    runtime._path_exists = lambda _: False

    status = runtime.get_status()

    assert status["condition_tree"]["stage_id"] == "phase1"
    assert status["condition_tree"]["missing"][0]["kind"] == "artifact"
    assert status["condition_tree"]["missing"][0]["target"] == "demo_outputs/sales.json"
    assert status["condition_tree"]["missing"][0]["reason"] == "missing required artifacts for phase1 follow-up"


@pytest.mark.asyncio
async def test_status_exposes_decision_explanation_fields():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.HANDOFF,
            planned_actions=[
                KairosPlannedAction(
                    action_id="demo-report",
                    kind="create_dex_task",
                    reason="phase1_converged",
                    payload={"description": "generate final report"},
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDex(),
    )

    status = runtime.get_status()

    assert status["decision_explanation"]["why_continued"] == "phase1_converged"
    assert status["decision_explanation"]["why_stopped"] is None
    assert status["decision_explanation"]["missing_requirements"] == []


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



@pytest.mark.asyncio
async def test_multi_stage_dex_workflow_keeps_parallel_tasks_then_converges_to_report():
    class Snap:
        def __init__(
            self,
            task_id,
            status,
            description,
            result="",
            result_summary=None,
            error_summary=None,
            completed_at=None,
        ):
            self.task_id = task_id
            self.status = status
            self.description = description
            self.result = result
            self.result_summary = result_summary
            self.error_summary = error_summary
            self.created_at = None
            self.completed_at = completed_at
            self.log_path = f".dex/logs/alice/{task_id}.log"

    bridge = FakeDexBridge()
    bridge.tasks = {
        "sales": Snap("sales", "completed", "prepare sales", result_summary="sales ready"),
        "traffic": Snap("traffic", "running", "prepare traffic"),
        "quality": Snap("quality", "running", "prepare quality"),
    }

    _, emitted, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.HANDOFF,
            tracked_dex_task_ids=["sales", "traffic", "quality"],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=bridge,
    )

    await runtime.tick_once()

    assert runtime.state.tracked_dex_task_ids == ["traffic", "quality"]
    assert runtime.state.mode is KairosMode.HANDOFF
    assert any("sales" in msg and "sales ready" in msg for _, msg in emitted)

    bridge.tasks["traffic"] = Snap(
        "traffic",
        "completed",
        "prepare traffic",
        result_summary="traffic ready",
    )
    bridge.tasks["quality"] = Snap(
        "quality",
        "completed",
        "prepare quality",
        result_summary="quality ready",
    )

    await runtime.tick_once()

    assert runtime.state.tracked_dex_task_ids == []
    assert runtime.state.mode is KairosMode.IDLE
    assert any("traffic" in msg and "traffic ready" in msg for _, msg in emitted)
    assert any("quality" in msg and "quality ready" in msg for _, msg in emitted)

    await runtime.register_dex_task("report", "generate final report")

    assert runtime.state.tracked_dex_task_ids == ["report"]
    assert runtime.state.mode is KairosMode.HANDOFF

    bridge.tasks["report"] = Snap(
        "report",
        "completed",
        "generate final report",
        result_summary="report ready: 3 inputs merged",
        completed_at="2026-04-04T00:15:00+00:00",
    )

    await runtime.tick_once()

    assert runtime.state.tracked_dex_task_ids == []
    assert runtime.state.mode is KairosMode.IDLE
    assert runtime.state.active_workflow is None or runtime.state.active_workflow.status == "completed"

    bridge.tasks["report"] = Snap(
        "report",
        "completed",
        "generate final report",
        result_summary="report ready: 3 inputs merged",
        completed_at="2026-04-04T00:15:00+00:00",
    )

    await runtime.tick_once()

    assert runtime.state.tracked_dex_task_ids == []
    assert runtime.state.mode is KairosMode.IDLE
    assert runtime.state.active_workflow is None or runtime.state.active_workflow.status == "completed"
    from src.adk_agent.kairos.models import KairosContinuationPolicy, KairosWorkflow, KairosWorkflowStage

    class Snap:
        def __init__(self, task_id, status, description, result_summary=None):
            self.task_id = task_id
            self.status = status
            self.description = description
            self.result = ""
            self.result_summary = result_summary
            self.error_summary = None
            self.created_at = None
            self.completed_at = "2026-04-05T01:00:00+00:00"
            self.log_path = f".dex/logs/alice/{task_id}.log"

    bridge = FakeDexBridge()
    bridge.tasks = {
        "sales": Snap("sales", "completed", "prepare sales", result_summary="sales ready"),
        "traffic": Snap("traffic", "completed", "prepare traffic", result_summary="traffic ready"),
        "quality": Snap("quality", "completed", "prepare quality", result_summary="quality ready"),
    }

    _, emitted, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.HANDOFF,
            tracked_dex_task_ids=["sales", "traffic", "quality"],
            active_workflow=KairosWorkflow(
                workflow_id="demo_report_pipeline",
                goal="auto progress report stage",
                status="active",
                current_stage="phase1",
                stages=[
                    KairosWorkflowStage(
                        stage_id="phase1",
                        label="prepare inputs",
                        status="running",
                        task_ids=["sales", "traffic", "quality"],
                        artifacts=[
                            "demo_outputs/sales.json",
                            "demo_outputs/traffic.json",
                            "demo_outputs/quality.json",
                        ],
                    )
                ],
                metadata={"completed_task_ids": []},
            ),
            policy=KairosContinuationPolicy(),
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=bridge,
    )

    runtime._path_exists = lambda _: True

    await runtime.tick_once()

    assert runtime.state.tracked_dex_task_ids == []
    assert runtime.state.pending_triggers
    assert runtime.state.pending_triggers[0].kind is TriggerKind.INTERNAL
    assert runtime.state.pending_triggers[0].reason == "phase1_converged"
    assert runtime.state.planned_actions[0].kind == "create_dex_task"
    assert runtime.state.active_workflow.current_stage == "phase2"
    assert any("sales ready" in msg for _, msg in emitted)


@pytest.mark.asyncio
async def test_completed_inputs_block_when_runtime_path_check_reports_missing_artifact():
    from src.adk_agent.kairos.models import KairosContinuationPolicy, KairosWorkflow, KairosWorkflowStage

    class Snap:
        def __init__(self, task_id, status, description, result_summary=None):
            self.task_id = task_id
            self.status = status
            self.description = description
            self.result = ""
            self.result_summary = result_summary
            self.error_summary = None
            self.created_at = None
            self.completed_at = "2026-04-05T01:00:00+00:00"
            self.log_path = f".dex/logs/alice/{task_id}.log"

    bridge = FakeDexBridge()
    bridge.tasks = {
        "sales": Snap("sales", "completed", "prepare sales", result_summary="sales ready"),
        "traffic": Snap("traffic", "completed", "prepare traffic", result_summary="traffic ready"),
        "quality": Snap("quality", "completed", "prepare quality", result_summary="quality ready"),
    }

    _, emitted, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.HANDOFF,
            tracked_dex_task_ids=["sales", "traffic", "quality"],
            active_workflow=KairosWorkflow(
                workflow_id="demo_report_pipeline",
                goal="auto progress report stage",
                status="active",
                current_stage="phase1",
                stages=[
                    KairosWorkflowStage(
                        stage_id="phase1",
                        label="prepare inputs",
                        status="running",
                        task_ids=["sales", "traffic", "quality"],
                        artifacts=[
                            "demo_outputs/sales.json",
                            "demo_outputs/traffic.json",
                            "demo_outputs/quality.json",
                        ],
                    )
                ],
                metadata={"completed_task_ids": []},
            ),
            policy=KairosContinuationPolicy(),
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=bridge,
    )

    runtime._path_exists = lambda path: path != "demo_outputs/quality.json"

    await runtime.tick_once()

    assert runtime.state.tracked_dex_task_ids == []
    assert runtime.state.pending_triggers == []
    assert runtime.state.planned_actions == []
    assert runtime.state.blocked_reason == "missing required artifacts for phase1 follow-up"
    assert runtime.state.active_workflow.status == "waiting_input"
    assert any("quality ready" in msg for _, msg in emitted)

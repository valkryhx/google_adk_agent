import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.adk_agent.kairos.models import (
    DocumentReadResult,
    KairosAttentionItem,
    KairosMode,
    KairosPlannedAction,
    KairosSchedule,
    KairosState,
    KairosTrigger,
    StepAttempt,
    TriggerKind,
)
from src.adk_agent.kairos.llm_planner import KairosPlanner
from src.adk_agent.kairos.runtime import KairosRuntime
from src.adk_agent.kairos.workflows import demo_report_pipeline


class FakeDexBridge:
    def __init__(self):
        self.tasks = {}
        self.created = []
        self.started = []

    def get_tasks(self, task_ids):
        return [self.tasks[task_id] for task_id in task_ids if task_id in self.tasks]

    def create_task(self, description, context=""):
        task_id = f"task-{len(self.created) + 1}"
        task = {"id": task_id, "description": description, "context": context, "created_at": "2026-04-14T00:00:00+00:00"}
        self.created.append(task)
        return task

    def start_task(self, task_id, command):
        self.started.append({"task_id": task_id, "command": command})
        return {"id": task_id, "status": "running"}


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
async def test_tick_once_populates_llm_understanding_and_execution_plan(monkeypatch):
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    class FakePlanner:
        async def draft_requirement_understanding(self, item):
            from src.adk_agent.kairos.models import KairosUnderstandingResult
            return KairosUnderstandingResult(goal=item.goal, constraints=["use flask"])

        async def build_execution_plan(self, item, understanding, *, candidate_actions):
            from src.adk_agent.kairos.models import KairosExecutionPlan
            return KairosExecutionPlan(plan_id="plan-1", work_id=item.work_id, steps=[{"step_id": item.current_step, "action_kind": "spawn_dex_task"}])

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.IDLE,
            document_work_items=[
                DocumentReadResult(
                    work_id="work:python-cli",
                    goal="build python cli",
                    status="pending_requirements",
                    current_step="requirements",
                    next_actions=["draft requirements document"],
                    expected_artifacts=["requirements/session-1/work.md"],
                    source_docs=["requirements/session-1/work.md"],
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )
    runtime._llm_planner = FakePlanner()

    await runtime.tick_once()

    assert runtime.state.current_understanding.goal == "build python cli"
    assert runtime.state.current_execution_plan.plan_id == "plan-1"
    assert runtime.state.current_execution_plan.steps[0]["action_kind"] == "spawn_dex_task"


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
async def test_tick_waiting_input_keeps_manual_trigger_queued_and_skips_run_turn():
    called = []
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        called.append(True)
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            busy=False,
            mode=KairosMode.WAITING_INPUT,
            pending_triggers=[
                KairosTrigger(
                    trigger_id="manual-1",
                    kind=TriggerKind.MANUAL,
                    reason="work_registered:work:test",
                    created_at="2026-04-18T00:00:00+00:00",
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
    )

    await runtime.tick_once()

    assert called == []
    assert len(runtime.state.pending_triggers) == 1
    assert runtime.state.pending_triggers[0].trigger_id == "manual-1"


@pytest.mark.asyncio
async def test_tick_waiting_input_timeout_auto_resumes_and_runs_trigger():
    from src.adk_agent.kairos.models import KairosContinuationPolicy

    reasons = []
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(reason):
        reasons.append(reason)
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            busy=False,
            mode=KairosMode.WAITING_INPUT,
            blocked_reason="waiting for user confirmation",
            policy=KairosContinuationPolicy(ask_user_timeout_seconds=180),
            pending_triggers=[
                KairosTrigger(
                    trigger_id="manual-1",
                    kind=TriggerKind.MANUAL,
                    reason="work_registered:work:test",
                    created_at="2026-04-18T00:00:00+00:00",
                )
            ],
            attention_items=[
                KairosAttentionItem(
                    attention_id="attention-1",
                    scope_kind="document_work",
                    work_id="work:test",
                    stage_id="requirements",
                    question="Need confirmation",
                    blocked_reason="waiting for user confirmation",
                    status="pending",
                    created_at="2026-04-18T00:00:00+00:00",
                    updated_at="2026-04-18T00:00:00+00:00",
                    timeout_seconds=180,
                    wait_until="2026-04-18T00:03:00+00:00",
                )
            ],
            document_work_items=[
                DocumentReadResult(
                    work_id="work:test",
                    goal="build test feature",
                    status="blocked",
                    current_step="requirements",
                    next_actions=["draft requirements"],
                    expected_artifacts=["requirements/session-1/work.md"],
                    open_questions=["Need confirmation"],
                    human_input_required=True,
                    source_docs=["requirements/session-1/work.md"],
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
    )

    await runtime.tick_once()

    assert reasons
    assert reasons[0].startswith("ask_user_timeout_auto_resume:")
    assert runtime.state.attention_items[0].status == "timed_out"
    assert runtime.state.attention_items[0].auto_resumed_at is not None
    assert runtime.state.blocked_reason is None
    assert runtime.state.document_work_items[0].human_input_required is False
    assert runtime.state.document_work_items[0].status == "in_progress"


@pytest.mark.asyncio
async def test_respond_attention_before_timeout_unblocks_and_runs_manual_trigger():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()
    reasons = []

    async def run_turn(reason):
        reasons.append(reason)
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            busy=False,
            mode=KairosMode.WAITING_INPUT,
            blocked_reason="waiting for user confirmation",
            pending_triggers=[
                KairosTrigger(
                    trigger_id="manual-1",
                    kind=TriggerKind.MANUAL,
                    reason="work_registered:work:test",
                    created_at="2026-04-18T00:00:00+00:00",
                )
            ],
            attention_items=[
                KairosAttentionItem(
                    attention_id="attention-1",
                    scope_kind="document_work",
                    work_id="work:test",
                    stage_id="requirements",
                    question="Need confirmation",
                    blocked_reason="waiting for user confirmation",
                    status="pending",
                    created_at="2026-04-18T00:00:00+00:00",
                    updated_at="2026-04-18T00:00:00+00:00",
                    timeout_seconds=180,
                    wait_until="2099-01-01T00:03:00+00:00",
                )
            ],
            document_work_items=[
                DocumentReadResult(
                    work_id="work:test",
                    goal="build test feature",
                    status="blocked",
                    current_step="requirements",
                    next_actions=["draft requirements"],
                    expected_artifacts=[],
                    open_questions=["Need confirmation"],
                    human_input_required=True,
                    source_docs=[],
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
    )

    await runtime.respond_attention("attention-1", "Proceed with default assumptions.")
    await runtime.tick_once()

    assert reasons
    assert reasons[0] == "work_registered:work:test"
    assert all(not reason.startswith("ask_user_timeout_auto_resume:") for reason in reasons)
    assert runtime.state.attention_items[0].status == "resolved"


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
async def test_runtime_records_replan_when_higher_tier_candidate_replaces_winner():
    _, emitted, logged, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return None

    state = _todo_runtime_state(current_stage="verification")
    state.active_workflow.metadata["completed_task_ids"] = [
        "todo_requirements",
        "todo_design",
        "todo_codegen",
        "todo_tests",
    ]
    state.active_workflow.status = "waiting_input"
    state.blocked_reason = "verification checks failed for todo delivery report"
    state.condition_tree = {
        "failed_checks": [{"check": "edit_item", "reason": "editing flow failed"}],
        "missing": [],
    }
    state.last_planning_result["selected_candidate"] = {
        "candidate_id": "todo_delivery_pipeline:verification:continue_workflow",
        "action": "continue_workflow",
        "tier": "medium",
        "priority": 50,
    }

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

    assert runtime.state.last_planning_result["selected_candidate"]["action"] == "ask_user"
    assert runtime.state.last_planning_result["replan"]["previous_winner"]["action"] == "continue_workflow"
    assert runtime.state.last_planning_result["replan"]["current_winner"]["action"] == "ask_user"
    assert any("Re-plan:" in message for _, message in emitted)
    assert any("ask_user" in message for message in logged)


@pytest.mark.asyncio
async def test_runtime_does_not_emit_replan_for_same_tier_reordering():
    _, emitted, logged, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return None

    state = _todo_runtime_state(current_stage="verification")
    state.active_workflow.metadata["completed_task_ids"] = [
        "todo_requirements",
        "todo_design",
        "todo_codegen",
        "todo_tests",
    ]
    state.active_workflow.metadata["verification_result"] = {"ready": True, "failures": []}
    state.last_planning_result["selected_candidate"] = {
        "candidate_id": "todo_delivery_pipeline:verification:continue_workflow",
        "action": "continue_workflow",
        "tier": "medium",
        "priority": 50,
    }

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

    assert runtime.state.last_planning_result["selected_candidate"]["action"] == "continue_workflow"
    assert runtime.state.last_planning_result.get("replan", {}).get("changed") in {None, False}
    assert not any("Re-plan:" in message for _, message in emitted)
    assert not any("Re-plan:" in message for message in logged)


@pytest.mark.asyncio
async def test_runtime_records_special_planning_state_when_sleep_selected():
    _, emitted, logged, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return None

    state = _todo_runtime_state(current_stage="codegen")
    state.last_proactive_scan = {
        "ts": "2026-04-07T10:00:00+00:00",
        "result": "candidate_found",
        "winner": "todo_delivery_pipeline:codegen:continue_workflow",
    }
    state.policy.cooldown_seconds = 999999

    runtime = KairosRuntime(
        state=state,
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )
    runtime._continuation_engine._now = lambda: datetime.fromisoformat("2026-04-07T10:00:30+00:00")

    await runtime.tick_once()

    assert runtime.state.last_planning_result["selected_candidate"]["action"] == "sleep"
    assert runtime.state.last_planning_result["final_action"]["kind"] == "sleep_until_signal"
    assert not any("Selected winner:" in message for _, message in emitted)
    assert not any("Selected winner:" in message for message in logged)


@pytest.mark.asyncio
async def test_runtime_records_selected_winner_when_create_follow_up_selected():
    _, emitted, logged, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return None

    state = _todo_runtime_state(current_stage="verification")
    state.active_workflow.metadata["completed_task_ids"] = [
        "todo_requirements",
        "todo_design",
        "todo_codegen",
        "todo_tests",
    ]
    state.active_workflow.metadata["verification_result"] = {"ready": True, "failures": []}

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

    assert runtime.state.last_planning_result["selected_candidate"]["action"] == "create_follow_up"
    assert runtime.state.last_planning_result.get("replan", {}).get("changed") is False
    assert any("Selected winner: create_follow_up" in message for _, message in emitted)
    assert any("Selected winner: create_follow_up" in message for message in logged)


@pytest.mark.asyncio
async def test_tick_once_builds_design_codegen_payload_for_spawn_step():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    class FakePlanner:
        async def draft_requirement_understanding(self, item):
            from src.adk_agent.kairos.models import KairosUnderstandingResult
            return KairosUnderstandingResult(goal=item.goal, constraints=["use flask"])

        async def build_execution_plan(self, item, understanding, *, candidate_actions):
            from src.adk_agent.kairos.models import KairosExecutionPlan
            return KairosExecutionPlan(plan_id="plan-1", work_id=item.work_id, steps=[{"step_id": item.current_step, "action_kind": "spawn_dex_task"}])

        async def build_design_codegen_payload(self, *, work_item, step):
            from src.adk_agent.kairos.models import KairosActionPayload
            return KairosActionPayload(
                action_kind="spawn_dex_task",
                description="generate design brief",
                command_template_id="draft_requirements_doc",
                brief="generate design brief",
                args={"goal": work_item.goal},
                expected_artifacts=["requirements/session-1/design.md"],
                rationale="llm generated design brief",
            )

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.IDLE,
            document_work_items=[
                DocumentReadResult(
                    work_id="work:python-cli",
                    goal="build python cli",
                    status="pending_requirements",
                    current_step="requirements",
                    next_actions=["draft requirements document"],
                    expected_artifacts=["requirements/session-1/work.md"],
                    source_docs=["requirements/session-1/work.md"],
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )
    runtime._llm_planner = FakePlanner()

    await runtime.tick_once()

    assert runtime.state.current_action_payload.command_template_id == "draft_requirements_doc"
    assert runtime.state.planned_actions[0].payload["command_template_id"] == "draft_requirements_doc"
    assert runtime.state.planned_actions[0].payload["expected_artifacts"] == ["requirements/session-1/design.md"]
    assert runtime.state.planned_actions[0].payload["design_codegen_brief"] == "generate design brief"


@pytest.mark.asyncio
async def test_tick_once_dispatches_agent_execute_from_plan_step_without_payload_llm():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()
    run_turn_reasons = []

    async def run_turn(reason):
        run_turn_reasons.append(reason)
        return "ok"

    class FakePlanner:
        async def draft_requirement_understanding(self, item):
            from src.adk_agent.kairos.models import KairosUnderstandingResult

            return KairosUnderstandingResult(goal=item.goal)

        async def build_execution_plan(self, item, understanding, *, candidate_actions):
            from src.adk_agent.kairos.models import KairosExecutionPlan

            return KairosExecutionPlan(
                plan_id="plan-agent-exec",
                work_id=item.work_id,
                steps=[
                    {
                        "step_id": item.current_step,
                        "action_kind": "agent_execute",
                        "reason": "use tools to execute the requirement",
                        "required_skills": ["bash"],
                        "execution_prompt": "读取 work.md 并产出 execution-log.md",
                    }
                ],
            )

        async def build_action_payload(self, *, work_item, step):
            raise AssertionError("build_action_payload should not be called for agent_execute step")

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.IDLE,
            document_work_items=[
                DocumentReadResult(
                    work_id="work:python-cli",
                    goal="build python cli",
                    status="pending_requirements",
                    current_step="requirements",
                    next_actions=["draft requirements document"],
                    expected_artifacts=["requirements/session-1/work.md"],
                    source_docs=["requirements/session-1/work.md"],
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )
    runtime._llm_planner = FakePlanner()

    await runtime.tick_once()

    assert runtime.state.current_action_payload.action_kind == "agent_execute"
    assert any(reason.startswith("agent_execute::") for reason in run_turn_reasons)
    assert runtime.state.planned_actions
    assert runtime.state.planned_actions[0].kind == "agent_execute"


@pytest.mark.asyncio
async def test_dispatch_action_payload_updates_document_when_patch_present(tmp_path):
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    doc_dir = tmp_path / "requirements" / "session-1"
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / "work.md"
    doc_path.write_text(
        "# Work Item: build python cli\n\n"
        "## Goal\nbuild python cli\n\n"
        "## Current Status\nin_progress\n\n"
        "## Current Step\nrequirements\n\n"
        "## Steps\n- draft requirements document\n\n"
        "## Expected Artifacts\n- requirements/session-1/work.md\n\n"
        "## Blockers\n- none\n\n"
        "## Verification\n- confirm scope\n\n"
        "## Replan Notes\n- no replans yet\n\n"
        "## Spawned Work\n- none yet\n",
        encoding="utf-8",
    )

    runtime = KairosRuntime(
        state=KairosState(
            document_work_items=[
                DocumentReadResult(
                    work_id="work:python-cli",
                    goal="build python cli",
                    status="in_progress",
                    current_step="requirements",
                    next_actions=["draft requirements document"],
                    expected_artifacts=["requirements/session-1/work.md"],
                    source_docs=["requirements/session-1/work.md"],
                )
            ]
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )
    from src.adk_agent.kairos.models import KairosActionPayload
    runtime.state.current_action_payload = KairosActionPayload(
        action_kind="update_document",
        target_doc="requirements/session-1/work.md",
        section_updates=[{"section": "Replan Notes", "text": "LLM refined requirement scope"}],
        rationale="llm generated requirement patch",
    )

    old_cwd = Path.cwd()
    try:
        import os
        os.chdir(tmp_path)
        await runtime._dispatch_action_payload()
    finally:
        os.chdir(old_cwd)

    assert "Follow-up planned via llm generated requirement patch" in doc_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_respond_attention_appends_user_guidance_to_document(tmp_path):
    _, emitted, logged, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return None

    doc_dir = tmp_path / "requirements" / "session-1"
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / "work.md"
    doc_path.write_text(
        "# Work Item: build python cli\n\n"
        "## Goal\nbuild python cli\n\n"
        "## Current Status\nblocked\n\n"
        "## Current Step\nrequirements\n\n"
        "## Steps\n- draft requirements document\n\n"
        "## Expected Artifacts\n- requirements/session-1/work.md\n\n"
        "## Blockers\n- waiting user confirmation\n\n"
        "## Verification\n- confirm scope\n\n"
        "## Replan Notes\n- Open question: Should CLI support table output?\n\n"
        "## Spawned Work\n- none yet\n",
        encoding="utf-8",
    )

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.WAITING_INPUT,
            blocked_reason="waiting user confirmation",
            document_work_items=[
                DocumentReadResult(
                    work_id="work:python-cli",
                    goal="build python cli",
                    status="blocked",
                    current_step="requirements",
                    next_actions=["draft requirements document"],
                    expected_artifacts=["requirements/session-1/work.md"],
                    open_questions=["Should CLI support table output?"],
                    human_input_required=True,
                    source_docs=["requirements/session-1/work.md"],
                )
            ],
            attention_items=[
                KairosAttentionItem(
                    attention_id="attention-1",
                    scope_kind="document_work",
                    work_id="work:python-cli",
                    stage_id="requirements",
                    question="Should CLI support table output?",
                    blocked_reason="waiting user confirmation",
                    status="pending",
                    created_at="2026-04-18T09:00:00+00:00",
                    updated_at="2026-04-18T09:00:00+00:00",
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )

    old_cwd = Path.cwd()
    try:
        import os
        os.chdir(tmp_path)
        resolved = await runtime.respond_attention("attention-1", "Use JSON and table outputs.")
    finally:
        os.chdir(old_cwd)

    updated = doc_path.read_text(encoding="utf-8")
    assert resolved["status"] == "resolved"
    assert runtime.state.document_work_items[0].human_input_required is False
    assert runtime.state.document_work_items[0].status == "in_progress"
    assert runtime.state.document_work_items[0].open_questions == []
    assert "User guidance [attention-1]: Use JSON and table outputs." in updated
    assert runtime.state.pending_triggers
    assert runtime.state.pending_triggers[-1].reason.startswith("attention_response:")
    assert any("ask_user response recorded" in message for _, message in emitted)
    assert any("ask_user response recorded" in message for message in logged)


@pytest.mark.asyncio
async def test_dispatch_action_payload_records_spawn_dex_task_as_planned_action():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            document_work_items=[
                DocumentReadResult(
                    work_id="work:python-cli",
                    goal="build python cli",
                    status="in_progress",
                    current_step="design",
                    next_actions=["write cli outline"],
                    expected_artifacts=["requirements/session-1/work.md"],
                    source_docs=["requirements/session-1/work.md"],
                )
            ]
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )
    from src.adk_agent.kairos.models import KairosActionPayload
    runtime.state.current_action_payload = KairosActionPayload(
        action_kind="spawn_dex_task",
        description="write cli outline",
        rationale="llm generated codegen step",
        command_template_id="draft_requirements_doc",
    )

    await runtime._dispatch_action_payload()

    assert runtime.state.planned_actions
    assert runtime.state.planned_actions[0].kind == "run_dex_task"
    assert runtime.state.planned_actions[0].payload["description"] == "write cli outline"
    assert runtime.state.planned_actions[0].payload["command_template_id"] == "draft_requirements_doc"
    assert runtime.state.planned_actions[0].payload["design_codegen_brief"] == "write cli outline"
    assert runtime.state.tracked_dex_task_ids == ["task-1"]
    assert runtime._dex_bridge.created[0]["context"] == "write cli outline"
    assert "requirements_brief.txt" in runtime._dex_bridge.started[0]["command"]


@pytest.mark.asyncio
async def test_dispatch_agent_execute_loads_skills_and_runs_turn():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()
    load_calls = []
    turn_reasons = []

    async def run_turn(reason):
        turn_reasons.append(reason)
        return "ok"

    async def load_skill(skill_id):
        load_calls.append(skill_id)
        return f"[OK] {skill_id}"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.IDLE),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
        load_skill=load_skill,
        allowed_skills={"bash", "file_editor"},
    )
    from src.adk_agent.kairos.models import KairosActionPayload
    runtime.state.current_action_payload = KairosActionPayload(
        action_kind="agent_execute",
        rationale="llm execute with skill",
        args={
            "required_skills": ["bash"],
            "execution_prompt": "读取任务文档并推进下一步",
        },
    )

    await runtime._dispatch_action_payload()

    assert load_calls == ["bash"]
    assert runtime.state.pending_triggers
    assert runtime.state.pending_triggers[0].reason.startswith("agent_execute::")
    assert runtime.state.planned_actions[0].kind == "agent_execute"

    await runtime.tick_once()

    assert turn_reasons
    assert turn_reasons[0].startswith("agent_execute::")


@pytest.mark.asyncio
async def test_dispatch_agent_execute_includes_ripgrep_skill_catalog_in_prompt():
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
        path_exists=lambda _: True,
        list_available_skill_catalog=lambda: [
            {"id": "bash", "name": "Bash Tool", "description": "Run shell commands"},
            {"id": "file_editor", "name": "File Editor", "description": "Read and write files"},
        ],
    )
    from src.adk_agent.kairos.models import KairosActionPayload
    runtime.state.current_action_payload = KairosActionPayload(
        action_kind="agent_execute",
        args={
            "execution_prompt": "读取 work.md 并生成 execution-log.md",
        },
    )

    await runtime._dispatch_action_payload()

    assert runtime.state.pending_triggers
    reason = runtime.state.pending_triggers[0].reason
    assert reason.startswith("agent_execute::")
    assert "[KAIROS_AVAILABLE_SKILLS]" in reason
    assert "- bash (Bash Tool): Run shell commands" in reason
    assert "- file_editor (File Editor): Read and write files" in reason


@pytest.mark.asyncio
async def test_dispatch_agent_execute_skips_unknown_skill_hints_without_blocking():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()
    load_calls = []

    async def run_turn(_):
        return "ok"

    async def load_skill(skill_id):
        load_calls.append(skill_id)
        return f"[OK] {skill_id}"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.IDLE),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
        load_skill=load_skill,
        allowed_skills={"bash"},
    )
    from src.adk_agent.kairos.models import KairosActionPayload
    runtime.state.current_action_payload = KairosActionPayload(
        action_kind="agent_execute",
        args={
            "required_skills": ["web-search"],
            "execution_prompt": "执行联网调研",
        },
    )

    await runtime._dispatch_action_payload()

    assert load_calls == []
    assert runtime.state.pending_triggers
    assert runtime.state.pending_triggers[0].reason.startswith("agent_execute::")
    assert runtime.state.mode is not KairosMode.WAITING_INPUT
    assert runtime.state.blocked_reason is None
    assert runtime.state.planned_actions
    assert runtime.state.planned_actions[0].payload["skipped_skill_hints"] == ["web-search"]


@pytest.mark.asyncio
async def test_dispatch_agent_execute_skips_loading_when_loader_missing():
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
        path_exists=lambda _: True,
        load_skill=None,
        allowed_skills={"bash"},
    )
    from src.adk_agent.kairos.models import KairosActionPayload
    runtime.state.current_action_payload = KairosActionPayload(
        action_kind="agent_execute",
        args={
            "required_skills": ["bash"],
            "execution_prompt": "执行本地检查",
        },
    )

    await runtime._dispatch_action_payload()

    assert runtime.state.pending_triggers
    assert runtime.state.pending_triggers[0].reason.startswith("agent_execute::")
    assert runtime.state.mode is not KairosMode.WAITING_INPUT
    assert runtime.state.blocked_reason is None
    assert runtime.state.planned_actions
    assert runtime.state.planned_actions[0].payload["skipped_skill_hints"] == ["bash"]


@pytest.mark.asyncio
async def test_dispatch_agent_execute_records_mixed_skill_hint_load_results_without_blocking():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()
    load_calls = []

    async def run_turn(_):
        return "ok"

    async def load_skill(skill_id):
        load_calls.append(skill_id)
        if skill_id == "bash":
            return "[OK] bash"
        if skill_id == "file_editor":
            return "[ERROR] failed to init file_editor"
        if skill_id == "search_exp":
            raise RuntimeError("tool bootstrap timeout")
        return f"[OK] {skill_id}"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.IDLE),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
        load_skill=load_skill,
        allowed_skills={"bash", "file_editor", "search_exp"},
    )
    from src.adk_agent.kairos.models import KairosActionPayload

    runtime.state.current_action_payload = KairosActionPayload(
        action_kind="agent_execute",
        args={
            "skill_hints": ["bash", "text_parse", "file_editor", "search_exp"],
            "execution_prompt": "读取 work.md 并推进下一步",
        },
    )

    await runtime._dispatch_action_payload()

    assert load_calls == ["bash", "file_editor", "search_exp"]
    assert runtime.state.pending_triggers
    assert runtime.state.pending_triggers[0].reason.startswith("agent_execute::")
    assert runtime.state.mode is not KairosMode.WAITING_INPUT
    assert runtime.state.blocked_reason is None

    planned_payload = runtime.state.planned_actions[0].payload
    assert planned_payload["skipped_skill_hints"] == ["text_parse"]
    status_by_skill = {
        item["skill_id"]: item["status"]
        for item in planned_payload["skill_load_results"]
    }
    assert status_by_skill["bash"] == "loaded"
    assert status_by_skill["text_parse"] == "unknown_hint"
    assert status_by_skill["file_editor"] == "load_error"
    assert status_by_skill["search_exp"] == "load_exception"

    trigger_meta = runtime.state.pending_triggers[0].metadata
    meta_status_by_skill = {
        item["skill_id"]: item["status"]
        for item in trigger_meta["skill_load_results"]
    }
    assert meta_status_by_skill == status_by_skill


@pytest.mark.asyncio
async def test_dispatch_agent_execute_counts_already_loaded_as_loaded():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()
    load_calls = []

    async def run_turn(_):
        return "ok"

    async def load_skill(skill_id):
        load_calls.append(skill_id)
        return f"[OK] 技能 '{skill_id}' 已加载（already loaded）。Instructions:\\n..."

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.IDLE),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
        load_skill=load_skill,
        allowed_skills={"bash"},
    )
    from src.adk_agent.kairos.models import KairosActionPayload

    runtime.state.current_action_payload = KairosActionPayload(
        action_kind="agent_execute",
        args={
            "required_skills": ["bash"],
            "execution_prompt": "执行一次命令检查",
        },
    )

    await runtime._dispatch_action_payload()

    assert load_calls == ["bash"]
    result_entry = runtime.state.planned_actions[0].payload["skill_load_results"][0]
    assert result_entry["status"] == "already_loaded"
    assert runtime.state.planned_actions[0].payload["skill_hint_stats"]["loaded"] == 1
    assert runtime.state.pending_triggers[0].metadata["skill_hint_stats"]["loaded"] == 1


@pytest.mark.asyncio
async def test_dispatch_agent_execute_maps_text_hint_to_known_skill_id():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()
    load_calls = []

    async def run_turn(_):
        return "ok"

    async def load_skill(skill_id):
        load_calls.append(skill_id)
        return f"[OK] {skill_id}"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.IDLE),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
        load_skill=load_skill,
        allowed_skills={"file_editor"},
    )
    from src.adk_agent.kairos.models import KairosActionPayload

    runtime.state.current_action_payload = KairosActionPayload(
        action_kind="agent_execute",
        args={
            "required_skills": ["file-editing"],
            "execution_prompt": "读取并更新本地文档",
        },
    )

    await runtime._dispatch_action_payload()

    assert load_calls == ["file_editor"]
    assert runtime.state.pending_triggers
    assert runtime.state.mode is not KairosMode.WAITING_INPUT
    assert runtime.state.blocked_reason is None

    planned_payload = runtime.state.planned_actions[0].payload
    result_entry = planned_payload["skill_load_results"][0]
    assert result_entry["skill_id"] == "file-editing"
    assert result_entry["resolved_skill_id"] == "file_editor"
    assert result_entry["hint_resolution"] == "text_match"
    assert result_entry["status"] == "loaded"
    assert planned_payload["skill_hint_stats"]["mapped"] == 1
    assert runtime.state.pending_triggers[0].metadata["skill_hint_stats"]["mapped"] == 1


@pytest.mark.asyncio
async def test_dispatch_agent_execute_semantic_hint_prefers_web_search_skill():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()
    load_calls = []

    async def run_turn(_):
        return "ok"

    async def load_skill(skill_id):
        load_calls.append(skill_id)
        return f"[OK] {skill_id}"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.IDLE),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
        load_skill=load_skill,
        list_available_skill_catalog=lambda: [
            {
                "id": "search_exp",
                "name": "search_experience",
                "description": "检索本地经验库，获取历史 Agent 解决过的报错方案和配置经验。",
            },
            {
                "id": "web-search",
                "name": "web-search",
                "description": "Perform web searches and extract content from URLs.",
            },
        ],
    )
    from src.adk_agent.kairos.models import KairosActionPayload

    runtime.state.current_action_payload = KairosActionPayload(
        action_kind="agent_execute",
        args={
            "required_skills": ["web search"],
            "execution_prompt": "执行联网调研并输出结论",
        },
    )

    await runtime._dispatch_action_payload()

    assert load_calls == ["web-search"]
    result_entry = runtime.state.planned_actions[0].payload["skill_load_results"][0]
    assert result_entry["skill_id"] == "web search"
    assert result_entry["resolved_skill_id"] == "web-search"
    assert result_entry["hint_resolution"] in {"text_match", "normalized"}
    assert result_entry["status"] == "loaded"
    assert result_entry["candidate_matches"][0]["skill_id"] == "web-search"
    assert "web searches" in result_entry["candidate_matches"][0]["description"].lower()

    reason = runtime.state.pending_triggers[0].reason
    assert "[KAIROS_SKILL_HINT_CANDIDATES]" in reason
    assert "hint=web search" in reason
    assert "web-search" in reason


@pytest.mark.asyncio
async def test_dispatch_agent_execute_does_not_map_web_search_to_search_exp():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()
    load_calls = []

    async def run_turn(_):
        return "ok"

    async def load_skill(skill_id):
        load_calls.append(skill_id)
        return f"[OK] {skill_id}"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.IDLE),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
        load_skill=load_skill,
        allowed_skills={"search_exp"},
    )
    from src.adk_agent.kairos.models import KairosActionPayload

    runtime.state.current_action_payload = KairosActionPayload(
        action_kind="agent_execute",
        args={
            "required_skills": ["web-search"],
            "execution_prompt": "执行联网调研并输出结论",
        },
    )

    await runtime._dispatch_action_payload()

    assert load_calls == []
    assert runtime.state.pending_triggers
    assert runtime.state.mode is not KairosMode.WAITING_INPUT
    assert runtime.state.blocked_reason is None
    result_entry = runtime.state.planned_actions[0].payload["skill_load_results"][0]
    assert result_entry["skill_id"] == "web-search"
    assert "resolved_skill_id" not in result_entry
    assert result_entry["status"] == "unknown_hint"


@pytest.mark.asyncio
async def test_runtime_status_exposes_current_action_payload():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return None

    from src.adk_agent.kairos.models import KairosActionPayload

    runtime = KairosRuntime(
        state=KairosState(
            current_action_payload=KairosActionPayload(
                action_kind="spawn_dex_task",
                description="write cli outline",
                rationale="llm generated codegen step",
                command_template_id="draft_requirements_doc",
            )
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )

    status = runtime.get_status()

    assert status["current_action_payload"]["action_kind"] == "spawn_dex_task"
    assert status["current_action_payload"]["command_template_id"] == "draft_requirements_doc"


@pytest.mark.asyncio
async def test_runtime_status_exposes_document_progress_view():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return None

    state = KairosState(
        document_work_items=[
            DocumentReadResult(
                work_id="work:python-cli",
                goal="build python cli",
                status="in_progress",
                current_step="design",
                next_actions=["write cli outline"],
                expected_artifacts=["requirements/session-1/work.md"],
                source_docs=["requirements/session-1/work.md"],
            )
        ],
        step_attempts=[
            StepAttempt(
                attempt_id="attempt-1",
                work_id="work:python-cli",
                step_id="design",
                action_kind="run_dex_task",
                status="started",
                doc_fingerprint="abc123",
                created_at="2026-04-14T00:00:00+00:00",
                result_summary="dex task created",
            )
        ],
    )

    runtime = KairosRuntime(
        state=state,
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )

    status = runtime.get_status()



@pytest.mark.asyncio
async def test_tick_once_executes_document_backed_internal_trigger_created_during_poll():
    bridge = FakeDexBridge()
    calls = []
    _, emitted, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    async def create_follow_up_task(reason, payload):
        calls.append((reason, payload))
        bridge.tasks["doc-task"] = type(
            "Snap",
            (),
            {
                "task_id": "doc-task",
                "status": "running",
                "description": payload["description"],
                "result": "",
                "result_summary": None,
                "error_summary": None,
                "created_at": None,
                "completed_at": None,
                "log_path": ".dex/logs/alice/doc-task.log",
            },
        )()
        return {"id": "doc-task"}

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.IDLE,
            document_work_items=[
                DocumentReadResult(
                    work_id="work:python-cli",
                    goal="build python cli",
                    status="in_progress",
                    current_step="design",
                    next_actions=["write cli outline"],
                    expected_artifacts=[],
                    source_docs=["requirements/session-1/work.md"],
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=bridge,
        path_exists=lambda _: True,
        create_follow_up_task=create_follow_up_task,
    )

    await runtime.tick_once()

    assert calls
    assert calls[0][0] == "document_work_ready"
    assert calls[0][1]["description"] == "write cli outline"
    assert runtime.state.tracked_dex_task_ids == ["doc-task"]
    assert runtime.state.mode is KairosMode.HANDOFF
    assert runtime.state.step_attempts[0].status in {"pending", "started"}
    assert any("internal action started" in msg for _, msg in emitted)


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
async def test_register_work_item_writes_work_doc_and_enqueues_manual_trigger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, emitted, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.SLEEPING),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: False,
    )

    item = await runtime.register_work_item(
        requirement="Build a todo app with sqlite storage",
        session_id="session-1",
        source_label="/api/sessions/session-1/kairos/work/register",
    )

    work_doc = tmp_path / "requirements" / "session-1" / "work.md"
    assert work_doc.exists()
    text = work_doc.read_text(encoding="utf-8")
    assert "## Goal" in text
    assert "Build a todo app with sqlite storage" in text
    assert runtime.state.document_work_items[0].work_id == item.work_id
    assert runtime.state.document_work_items[0].source_docs == [
        "/api/sessions/session-1/kairos/work/register:session-1"
    ]
    assert runtime.state.pending_triggers
    assert runtime.state.pending_triggers[0].kind is TriggerKind.MANUAL
    assert runtime.state.pending_wake_reason == f"work_registered:{item.work_id}"
    assert runtime.state.mode is KairosMode.IDLE
    assert any("work registered" in msg for _, msg in emitted)


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




@pytest.mark.asyncio
async def test_status_exposes_spawned_document_work_without_pending_requirement_projection():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.IDLE,
            document_work_items=[
                DocumentReadResult(
                    work_id="work:session-123:follow-up",
                    goal="verify generated todo delivery report",
                    status="pending",
                    current_step="verification",
                    next_actions=["check delivery_report.md"],
                    expected_artifacts=["requirements/session-123/work.md", "demo_delivery/todo_app/delivery_report.md"],
                    source_docs=["requirements/session-123/work.md"],
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
    )

    await runtime.tick_once()
    status = runtime.get_status()

    assert status["document_work_items"][0]["work_id"] == "work:session-123:follow-up"
    assert status["document_work_items"][0]["current_step"] == "verification"
    assert status["document_work_items"][0]["source_docs"] == ["requirements/session-123/work.md"]
    assert status["pending_requirements"] == []


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
    assert runtime.state.mode in {KairosMode.HANDOFF, KairosMode.SLEEPING}
    assert runtime.state.planned_actions[0].kind == "create_dex_task"
    assert runtime.state.planned_actions[0].reason == "phase1_converged"
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


@pytest.mark.asyncio
async def test_llm_only_decision_can_create_follow_up_after_completed_inputs():
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
    calls = []

    async def run_turn(_):
        return "ok"

    async def create_follow_up_task(reason, payload):
        calls.append((reason, payload))
        return {"id": "report-task"}

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
            policy=KairosContinuationPolicy(llm_only_decision_enabled=True),
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=bridge,
        create_follow_up_task=create_follow_up_task,
    )
    runtime._path_exists = lambda _: True

    class FakePlanner:
        async def plan_follow_up_action(self, **_kwargs):
            return {
                "action": "create_follow_up",
                "reason": "llm_follow_up_decision",
                "description": "generate final report",
                "message": None,
            }

    runtime._llm_planner = FakePlanner()

    await runtime.tick_once()

    assert calls
    assert calls[0][0] == "llm_follow_up_decision"
    assert calls[0][1]["description"] == "generate final report"
    assert runtime.state.last_planning_result["selected_candidate"]["action"] == "create_follow_up"
    assert any("Selected winner: create_follow_up" in msg for _, msg in emitted)


@pytest.mark.asyncio
async def test_llm_only_decision_blocks_when_planner_unavailable():
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
    }

    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.HANDOFF,
            tracked_dex_task_ids=["sales"],
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
                        task_ids=["sales"],
                        artifacts=["demo_outputs/sales.json"],
                    )
                ],
                metadata={"completed_task_ids": []},
            ),
            policy=KairosContinuationPolicy(llm_only_decision_enabled=True),
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=bridge,
    )
    runtime._path_exists = lambda _: True

    await runtime.tick_once()

    assert runtime.state.planned_actions == []
    assert runtime.state.blocked_reason == "llm planner unavailable in llm-only mode"
    assert runtime.state.last_planning_result["final_action"]["kind"] == "record_blocked"


@pytest.mark.asyncio
async def test_document_llm_only_blocks_when_planner_unavailable():
    from src.adk_agent.kairos.models import KairosContinuationPolicy

    _, emitted, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.IDLE,
            policy=KairosContinuationPolicy(llm_only_decision_enabled=True),
            document_work_items=[
                DocumentReadResult(
                    work_id="work:session-1:todo",
                    goal="build todo app",
                    status="pending_requirements",
                    current_step="requirements",
                    next_actions=["draft requirements document"],
                    expected_artifacts=["requirements/session-1/work.md"],
                    source_docs=["requirements/session-1/work.md"],
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )

    await runtime.tick_once()

    assert runtime.state.planned_actions == []
    assert runtime.state.blocked_reason.startswith("llm planner failed for document work")
    assert runtime.state.mode is KairosMode.WAITING_INPUT
    assert runtime.state.last_planning_result["final_action"]["kind"] == "record_blocked"
    assert runtime.state.last_planning_result["workflow_id"] == "document_requirement"
    assert any("llm planner fallback active" in msg for _, msg in emitted) is False


@pytest.mark.asyncio
async def test_document_llm_only_blocks_on_empty_execution_plan():
    from src.adk_agent.kairos.models import (
        KairosContinuationPolicy,
        KairosExecutionPlan,
        KairosUnderstandingResult,
    )

    _, emitted, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.IDLE,
            policy=KairosContinuationPolicy(llm_only_decision_enabled=True),
            document_work_items=[
                DocumentReadResult(
                    work_id="work:session-1:todo",
                    goal="build todo app",
                    status="pending_requirements",
                    current_step="requirements",
                    next_actions=["draft requirements document"],
                    expected_artifacts=["requirements/session-1/work.md"],
                    source_docs=["requirements/session-1/work.md"],
                )
            ],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )

    class EmptyPlanPlanner:
        async def draft_requirement_understanding(self, item):
            return KairosUnderstandingResult(goal=item.goal)

        async def build_execution_plan(self, item, understanding, *, candidate_actions):
            return KairosExecutionPlan(plan_id="plan-empty", work_id=item.work_id, steps=[])

    runtime._llm_planner = EmptyPlanPlanner()

    await runtime.tick_once()

    assert runtime.state.planned_actions == []
    assert runtime.state.blocked_reason.startswith("llm planner failed for document work")
    assert runtime.state.mode is KairosMode.WAITING_INPUT
    assert runtime.state.last_planning_result["final_action"]["kind"] == "record_blocked"
    assert any("llm planner fallback active" in msg for _, msg in emitted)

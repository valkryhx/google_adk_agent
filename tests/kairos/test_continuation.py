from datetime import datetime

from src.adk_agent.kairos.continuation import ContinuationEngine
from src.adk_agent.kairos.models import (
    DocumentReadResult,
    KairosContinuationPolicy,
    KairosPlannedAction,
    KairosState,
    KairosWorkflow,
    KairosWorkflowStage,
    TriggerKind,
)


class Snap:
    def __init__(self, task_id, status, description, result_summary=None, error_summary=None):
        self.task_id = task_id
        self.status = status
        self.description = description
        self.result_summary = result_summary
        self.error_summary = error_summary


def _workflow():
    return KairosWorkflow(
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
                summary=None,
            )
        ],
        metadata={"completed_task_ids": ["traffic", "quality"]},
    )


def test_all_inputs_ready_returns_create_report_decision():
    state = KairosState(
        active_workflow=_workflow(),
        policy=KairosContinuationPolicy(),
    )
    engine = ContinuationEngine(path_exists=lambda _: True)

    decisions = engine.evaluate_after_dex_poll(
        state,
        completed_tasks=[Snap("sales", "completed", "prepare sales", result_summary="sales ready")],
        tracked_tasks=[],
    )

    assert len(decisions) == 1
    assert decisions[0].kind == "create_dex_task"
    assert decisions[0].payload["description"] == "generate final report"
    assert state.active_workflow.current_stage == "phase2"
    assert state.blocked_reason is None


def test_missing_artifact_returns_blocked_decision():
    state = KairosState(
        active_workflow=_workflow(),
        policy=KairosContinuationPolicy(),
    )
    engine = ContinuationEngine(path_exists=lambda path: path != "demo_outputs/quality.json")

    decisions = engine.evaluate_after_dex_poll(
        state,
        completed_tasks=[Snap("sales", "completed", "prepare sales", result_summary="sales ready")],
        tracked_tasks=[],
    )

    assert decisions == []
    assert state.blocked_reason == "missing required artifacts for phase1 follow-up"
    assert state.active_workflow.current_stage == "phase1"


def test_duplicate_follow_up_is_suppressed_by_fingerprint():
    state = KairosState(
        active_workflow=_workflow(),
        policy=KairosContinuationPolicy(),
        planned_actions=[
            KairosPlannedAction(
                action_id="create-report-existing",
                kind="create_dex_task",
                reason="phase1_converged",
                payload={"workflow_id": "demo_report_pipeline", "description": "generate final report"},
                status="pending",
                created_at="2026-04-05T01:00:00+00:00",
            )
        ],
    )
    engine = ContinuationEngine(path_exists=lambda _: True)

    decisions = engine.evaluate_after_dex_poll(
        state,
        completed_tasks=[Snap("sales", "completed", "prepare sales", result_summary="sales ready")],
        tracked_tasks=[],
    )

    assert decisions == []
    assert len(state.planned_actions) == 1


def test_refresh_unfinished_work_items_from_active_todo_workflow():
    state = _todo_workflow_state(
        completed_task_ids=["todo_requirements", "todo_design"],
        current_stage="codegen",
    )
    state.active_workflow.stages[2].status = "running"
    engine = ContinuationEngine(
        path_exists=lambda path: path in {
            "demo_delivery/todo_app/requirements.md",
            "demo_delivery/todo_app/design.md",
            "demo_delivery/todo_app/file_plan.json",
        }
    )

    engine.refresh_unfinished_work(state)

    assert state.unfinished_work_items[0]["stage_id"] == "codegen"
    assert state.unfinished_work_items[0]["workflow_id"] == "todo_delivery_pipeline"
    assert state.proactive_candidates[0]["action"] == "continue_workflow"
    assert state.last_proactive_scan["result"] == "candidate_found"


def test_refresh_unfinished_work_respects_cooldown_guardrail():
    state = _todo_workflow_state(
        completed_task_ids=["todo_requirements", "todo_design"],
        current_stage="codegen",
    )
    state.active_workflow.stages[2].status = "running"
    state.last_proactive_scan = {
        "ts": "2026-04-07T10:00:00+00:00",
        "result": "candidate_found",
        "winner": "todo_delivery_pipeline:codegen:continue_workflow",
    }
    state.last_planning_result["selected_candidate"] = {
        "candidate_id": "todo_delivery_pipeline:codegen:continue_workflow",
        "action": "continue_workflow",
        "tier": "medium",
        "priority": 50,
    }
    state.policy.cooldown_seconds = 999999
    now_calls = iter([
        datetime.fromisoformat("2026-04-07T10:00:30+00:00"),
        datetime.fromisoformat("2026-04-07T10:00:30+00:00"),
    ])
    engine = ContinuationEngine(path_exists=lambda _: True, now=lambda: next(now_calls))

    engine.refresh_unfinished_work(state)

    assert state.unfinished_work_items[0]["stage_id"] == "codegen"
    assert [candidate["action"] for candidate in state.proactive_candidates] == [
        "continue_workflow",
        "create_follow_up",
        "emit_brief",
        "ask_user",
        "sleep",
        "blocked",
    ]
    assert state.last_guardrail_block["reason"] == "cooldown_active"
    assert state.last_proactive_scan["result"] == "cooldown_active"
    assert state.last_proactive_scan["winner"] == "todo_delivery_pipeline:codegen:sleep"
    assert state.last_planning_result["selected_candidate"]["action"] == "sleep"
    assert state.last_planning_result["final_action"]["kind"] == "sleep_until_signal"
    assert state.last_planning_result["rejected_candidates"][0]["action"] == "continue_workflow"


def test_refresh_unfinished_work_evaluates_fixed_candidate_taxonomy():
    state = _todo_workflow_state(
        completed_task_ids=["todo_requirements", "todo_design"],
        current_stage="codegen",
    )
    state.active_workflow.stages[2].status = "running"
    engine = ContinuationEngine(path_exists=lambda _: True)

    engine.refresh_unfinished_work(state)

    assert [candidate["action"] for candidate in state.proactive_candidates] == [
        "continue_workflow",
        "create_follow_up",
        "emit_brief",
        "ask_user",
        "sleep",
        "blocked",
    ]
    assert {candidate["tier"] for candidate in state.proactive_candidates} == {"high", "medium", "low"}
    assert state.last_planning_result["selected_candidate"]["action"] == "continue_workflow"
    assert state.last_proactive_scan["winner"] == state.last_planning_result["selected_candidate"]["candidate_id"]



def test_same_tier_candidate_does_not_supersede_current_winner():
    state = _todo_workflow_state(
        completed_task_ids=[
            "todo_requirements",
            "todo_design",
            "todo_codegen",
            "todo_tests",
        ],
        current_stage="verification",
    )
    state.active_workflow.metadata["verification_result"] = {"ready": True, "failures": []}
    state.last_planning_result["selected_candidate"] = {
        "candidate_id": "todo_delivery_pipeline:verification:continue_workflow",
        "action": "continue_workflow",
        "tier": "medium",
        "priority": 50,
    }
    engine = ContinuationEngine(
        path_exists=lambda path: path in {
            "demo_delivery/todo_app/requirements.md",
            "demo_delivery/todo_app/design.md",
            "demo_delivery/todo_app/file_plan.json",
            "demo_delivery/todo_app/index.html",
            "demo_delivery/todo_app/style.css",
            "demo_delivery/todo_app/app.js",
            "demo_delivery/todo_app/test_plan.md",
            "demo_delivery/todo_app/smoke_check.json",
        }
    )

    engine.refresh_unfinished_work(state)

    assert state.last_planning_result["selected_candidate"]["action"] == "continue_workflow"
    rejected = {candidate["action"]: candidate for candidate in state.last_planning_result["rejected_candidates"]}
    assert rejected["create_follow_up"]["rejected_reason"] == "same tier candidate cannot supersede current winner"



def test_higher_tier_candidate_supersedes_current_winner():
    state = _todo_workflow_state(
        completed_task_ids=[
            "todo_requirements",
            "todo_design",
            "todo_codegen",
            "todo_tests",
        ],
        current_stage="verification",
    )
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
    engine = ContinuationEngine(path_exists=lambda _: True)

    engine.refresh_unfinished_work(state)

    assert state.last_planning_result["selected_candidate"]["action"] == "ask_user"
    assert state.last_proactive_scan["winner"] == state.last_planning_result["selected_candidate"]["candidate_id"]
    rejected = {candidate["action"]: candidate for candidate in state.last_planning_result["rejected_candidates"]}
    assert rejected["continue_workflow"]["rejected_reason"] == "higher tier candidate selected"



def test_verification_failure_selects_blocked_or_ask_user_candidate():
    state = _todo_workflow_state(
        completed_task_ids=[
            "todo_requirements",
            "todo_design",
            "todo_codegen",
            "todo_tests",
        ],
        current_stage="verification",
    )
    state.active_workflow.status = "waiting_input"
    state.blocked_reason = "verification checks failed for todo delivery report"
    state.condition_tree = {
        "failed_checks": [{"check": "edit_item", "reason": "editing flow failed"}],
        "missing": [],
    }
    engine = ContinuationEngine(path_exists=lambda _: True)

    engine.refresh_unfinished_work(state)

    assert state.last_planning_result["selected_candidate"]["action"] in {"blocked", "ask_user"}
    assert state.last_planning_result["selected_candidate"]["tier"] == "high"
    assert state.last_proactive_scan["result"] == "waiting_input"



def test_refresh_unfinished_work_uses_document_backed_items_without_workflow_template():
    state = KairosState(
        document_work_items=[
            DocumentReadResult(
                work_id="work:python-cli",
                goal="build python cli",
                status="in_progress",
                current_step="design",
                next_actions=["write cli outline"],
                blockers=[],
                expected_artifacts=[],
                source_docs=["specs/python-cli/PLAN.md"],
            )
        ]
    )
    engine = ContinuationEngine(path_exists=lambda _: True)

    engine.refresh_unfinished_work(state)

    assert state.unfinished_work_items[0]["work_id"] == "work:python-cli"
    assert state.unfinished_work_items[0]["kind"] == "document_work_item"
    assert state.proactive_candidates[0]["action"] == "continue_workflow"
    assert state.last_planning_result["goal"] == "build python cli"
    assert state.last_planning_result["final_action"]["kind"] == "run_dex_task"
    assert state.last_planning_result["final_action"]["payload"]["description"] == "write cli outline"


def test_refresh_unfinished_work_routes_blocked_document_to_high_tier_candidate():
    state = KairosState(
        document_work_items=[
            DocumentReadResult(
                work_id="work:python-cli",
                goal="build python cli",
                status="blocked",
                current_step="requirements",
                blockers=["Need packaging target"],
                open_questions=["Which packaging target matters most?"],
                human_input_required=True,
            )
        ]
    )
    engine = ContinuationEngine(path_exists=lambda _: True)

    engine.refresh_unfinished_work(state)

    assert state.last_planning_result["selected_candidate"]["action"] in {"ask_user", "blocked"}
    assert state.last_planning_result["selected_candidate"]["tier"] == "high"
    assert state.last_proactive_scan["result"] == "waiting_input"
    assert state.last_planning_result["final_action"]["kind"] == "ask_user"


def test_document_backed_blocker_materializes_record_blocked_when_no_question():
    state = KairosState(
        document_work_items=[
            DocumentReadResult(
                work_id="work:blocked-cli",
                goal="ship blocked cli",
                status="in_progress",
                current_step="verification",
                next_actions=[],
                blockers=["Waiting for CI runner"],
                open_questions=[],
                human_input_required=False,
            )
        ]
    )
    engine = ContinuationEngine(path_exists=lambda _: True)

    engine.refresh_unfinished_work(state)

    assert state.last_planning_result["final_action"]["kind"] == "record_blocked"
    assert state.last_planning_result["final_action"]["payload"]["message"] == "Waiting for CI runner"


def test_apply_decisions_creates_internal_trigger_for_run_dex_task():
    state = KairosState()
    engine = ContinuationEngine()
    decision = engine._decision_from_final_action(
        {
            "kind": "run_dex_task",
            "reason": "document_work_ready",
            "payload": {
                "work_id": "work:python-cli",
                "step_id": "design",
                "description": "write cli outline",
                "doc_fingerprint": "abc123",
                "source_doc": "requirements/session-1/work.md",
            },
        }
    )

    triggers = engine.apply_decisions(state, [decision])

    assert state.planned_actions[0].kind == "run_dex_task"
    assert state.planned_actions[0].payload == {
        "work_id": "work:python-cli",
        "step_id": "design",
        "description": "write cli outline",
    }
    assert state.step_attempts[0].work_id == "work:python-cli"
    assert state.step_attempts[0].step_id == "design"
    assert state.step_attempts[0].doc_fingerprint == "abc123"
    assert triggers[0].kind is TriggerKind.INTERNAL
    assert triggers[0].metadata["description"] == "write cli outline"


def _todo_workflow_state(*, completed_task_ids, current_stage="verification"):
    return KairosState(
        active_workflow=KairosWorkflow(
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
                    status="completed",
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
                    status="running",
                    task_ids=["todo_tests"],
                    artifacts=[
                        "demo_delivery/todo_app/test_plan.md",
                        "demo_delivery/todo_app/smoke_check.json",
                    ],
                ),
                KairosWorkflowStage(
                    stage_id="delivery_report",
                    label="delivery report",
                    status="pending",
                    task_ids=["todo_delivery_report"],
                    artifacts=["demo_delivery/todo_app/delivery_report.md"],
                ),
            ],
            metadata={"completed_task_ids": completed_task_ids},
        ),
        policy=KairosContinuationPolicy(),
    )


def test_todo_delivery_all_required_artifacts_ready_returns_delivery_report_decision():
    state = _todo_workflow_state(
        completed_task_ids=[
            "todo_requirements",
            "todo_design",
            "todo_codegen",
            "todo_tests",
        ],
        current_stage="verification",
    )
    state.active_workflow.metadata["verification_result"] = {
        "ready": True,
        "checks": {
            "dom_ready": True,
            "add_item": True,
            "toggle_item": True,
            "delete_item": True,
            "filter_active": True,
            "filter_completed": True,
            "edit_item": True,
            "counter_correct": True,
            "empty_state_correct": True,
            "persistence_after_reload": True,
        },
        "failures": [],
    }
    engine = ContinuationEngine(
        path_exists=lambda path: path in {
            "demo_delivery/todo_app/requirements.md",
            "demo_delivery/todo_app/design.md",
            "demo_delivery/todo_app/file_plan.json",
            "demo_delivery/todo_app/index.html",
            "demo_delivery/todo_app/style.css",
            "demo_delivery/todo_app/app.js",
            "demo_delivery/todo_app/test_plan.md",
            "demo_delivery/todo_app/smoke_check.json",
        }
    )

    decisions = engine.evaluate_after_dex_poll(
        state,
        completed_tasks=[],
        tracked_tasks=[],
    )

    assert decisions[0].kind == "create_dex_task"
    assert decisions[0].payload["description"] == "generate todo delivery report"


def test_todo_delivery_missing_artifact_blocks_follow_up():
    state = _todo_workflow_state(
        completed_task_ids=[
            "todo_requirements",
            "todo_design",
            "todo_codegen",
            "todo_tests",
        ]
    )
    engine = ContinuationEngine(
        path_exists=lambda path: path in {
            "demo_delivery/todo_app/requirements.md",
            "demo_delivery/todo_app/design.md",
            "demo_delivery/todo_app/file_plan.json",
            "demo_delivery/todo_app/index.html",
            "demo_delivery/todo_app/style.css",
            "demo_delivery/todo_app/test_plan.md",
            "demo_delivery/todo_app/smoke_check.json",
        }
    )

    decisions = engine.evaluate_after_dex_poll(
        state,
        completed_tasks=[],
        tracked_tasks=[],
    )

    assert decisions == []
    assert state.blocked_reason == "missing required artifacts for todo delivery report"


def test_todo_delivery_requires_ready_smoke_check_before_report():
    state = _todo_workflow_state(
        completed_task_ids=[
            "todo_requirements",
            "todo_design",
            "todo_codegen",
            "todo_tests",
        ],
        current_stage="verification",
    )
    state.active_workflow.metadata["verification_result"] = {
        "ready": True,
        "checks": {
            "add_item": True,
            "toggle_item": True,
            "delete_item": True,
            "filter_active": True,
            "filter_completed": True,
            "edit_item": True,
            "counter_correct": True,
            "empty_state_correct": True,
            "persistence_after_reload": True,
        },
        "failures": [],
    }
    engine = ContinuationEngine(
        path_exists=lambda path: path in {
            "demo_delivery/todo_app/requirements.md",
            "demo_delivery/todo_app/design.md",
            "demo_delivery/todo_app/file_plan.json",
            "demo_delivery/todo_app/index.html",
            "demo_delivery/todo_app/style.css",
            "demo_delivery/todo_app/app.js",
            "demo_delivery/todo_app/test_plan.md",
            "demo_delivery/todo_app/smoke_check.json",
        }
    )

    decisions = engine.evaluate_after_dex_poll(state, completed_tasks=[], tracked_tasks=[])

    assert decisions[0].kind == "create_dex_task"
    assert decisions[0].payload["description"] == "generate todo delivery report"


def test_todo_delivery_blocks_when_verification_checks_fail():
    state = _todo_workflow_state(
        completed_task_ids=[
            "todo_requirements",
            "todo_design",
            "todo_codegen",
            "todo_tests",
        ],
        current_stage="verification",
    )
    state.active_workflow.metadata["verification_result"] = {
        "ready": False,
        "checks": {
            "add_item": True,
            "toggle_item": True,
            "delete_item": True,
            "filter_active": True,
            "filter_completed": True,
            "edit_item": False,
            "counter_correct": True,
            "empty_state_correct": True,
            "persistence_after_reload": True,
        },
        "failures": [
            {"check": "edit_item", "reason": "editing flow failed"},
        ],
    }
    engine = ContinuationEngine(
        path_exists=lambda path: path in {
            "demo_delivery/todo_app/requirements.md",
            "demo_delivery/todo_app/design.md",
            "demo_delivery/todo_app/file_plan.json",
            "demo_delivery/todo_app/index.html",
            "demo_delivery/todo_app/style.css",
            "demo_delivery/todo_app/app.js",
            "demo_delivery/todo_app/test_plan.md",
            "demo_delivery/todo_app/smoke_check.json",
        }
    )

    decisions = engine.evaluate_after_dex_poll(state, completed_tasks=[], tracked_tasks=[])

    assert decisions == []
    assert state.blocked_reason == "verification checks failed for todo delivery report"
    assert state.condition_tree["failed_checks"][0]["check"] == "edit_item"


def test_final_action_matches_follow_up_decision_payload():
    state = _todo_workflow_state(
        completed_task_ids=[
            "todo_requirements",
            "todo_design",
            "todo_codegen",
            "todo_tests",
        ],
        current_stage="verification",
    )
    state.active_workflow.metadata["verification_result"] = {"ready": True, "failures": []}
    engine = ContinuationEngine(
        path_exists=lambda path: path in {
            "demo_delivery/todo_app/requirements.md",
            "demo_delivery/todo_app/design.md",
            "demo_delivery/todo_app/file_plan.json",
            "demo_delivery/todo_app/index.html",
            "demo_delivery/todo_app/style.css",
            "demo_delivery/todo_app/app.js",
            "demo_delivery/todo_app/test_plan.md",
            "demo_delivery/todo_app/smoke_check.json",
        }
    )

    engine.refresh_unfinished_work(state)
    decisions = engine.evaluate_after_dex_poll(state, completed_tasks=[], tracked_tasks=[])

    assert state.last_planning_result["selected_candidate"]["action"] == "create_follow_up"
    assert state.last_planning_result["final_action"]["kind"] == "create_dex_task"
    assert state.last_planning_result["final_action"]["payload"] == decisions[0].payload


def test_apply_decisions_uses_final_action_payload_for_follow_up():
    state = KairosState()
    engine = ContinuationEngine()
    decision = engine._decision_from_final_action(
        {
            "kind": "create_dex_task",
            "reason": "todo_delivery_ready",
            "payload": {
                "workflow_id": "todo_delivery_pipeline",
                "description": "generate todo delivery report",
            },
        }
    )

    triggers = engine.apply_decisions(state, [decision])

    assert state.planned_actions[0].payload == {
        "workflow_id": "todo_delivery_pipeline",
        "description": "generate todo delivery report",
    }
    assert triggers[0].metadata == state.planned_actions[0].payload


def test_sleep_winner_leaves_explicit_final_action_kind():
    state = _todo_workflow_state(
        completed_task_ids=["todo_requirements", "todo_design"],
        current_stage="codegen",
    )
    state.active_workflow.stages[2].status = "running"
    state.last_proactive_scan = {
        "ts": "2026-04-07T10:00:00+00:00",
        "result": "candidate_found",
        "winner": "todo_delivery_pipeline:codegen:continue_workflow",
    }
    state.policy.cooldown_seconds = 999999
    now_calls = iter([
        datetime.fromisoformat("2026-04-07T10:00:30+00:00"),
        datetime.fromisoformat("2026-04-07T10:00:30+00:00"),
    ])
    engine = ContinuationEngine(path_exists=lambda _: True, now=lambda: next(now_calls))

    engine.refresh_unfinished_work(state)

    assert state.last_planning_result["selected_candidate"]["action"] == "sleep"
    assert state.last_planning_result["final_action"]["kind"] == "sleep_until_signal"

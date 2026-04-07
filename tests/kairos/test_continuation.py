from src.adk_agent.kairos.continuation import ContinuationEngine
from src.adk_agent.kairos.models import (
    KairosContinuationPolicy,
    KairosPlannedAction,
    KairosState,
    KairosWorkflow,
    KairosWorkflowStage,
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
        "winner": "todo-codegen",
    }
    state.policy.cooldown_seconds = 999999
    engine = ContinuationEngine(path_exists=lambda _: True)

    engine.refresh_unfinished_work(state)

    assert state.unfinished_work_items[0]["stage_id"] == "codegen"
    assert state.proactive_candidates == []
    assert state.last_guardrail_block["reason"] == "cooldown_active"



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

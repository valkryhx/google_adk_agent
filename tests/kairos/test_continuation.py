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

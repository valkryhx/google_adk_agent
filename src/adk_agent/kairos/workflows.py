from __future__ import annotations

from .models import KairosWorkflow, KairosWorkflowStage


def demo_report_pipeline() -> KairosWorkflow:
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
            ),
            KairosWorkflowStage(
                stage_id="phase2",
                label="generate report",
                status="pending",
                task_ids=["report"],
                artifacts=["demo_outputs/report.json"],
                summary=None,
            ),
        ],
        metadata={"completed_task_ids": []},
    )

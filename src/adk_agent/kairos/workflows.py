from __future__ import annotations

from .models import KairosWorkflow, KairosWorkflowStage


def demo_report_pipeline(phase1_task_ids: list[str] | None = None) -> KairosWorkflow:
    resolved_phase1_task_ids = ["sales", "traffic", "quality"] if phase1_task_ids is None else list(phase1_task_ids)
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
                task_ids=resolved_phase1_task_ids,
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


def todo_delivery_pipeline(task_ids: dict[str, str] | None = None) -> KairosWorkflow:
    resolved = {
        "requirements": "todo_requirements",
        "design": "todo_design",
        "codegen": "todo_codegen",
        "verification": "todo_tests",
        "delivery_report": "todo_delivery_report",
    }
    if task_ids:
        resolved.update(task_ids)
    return KairosWorkflow(
        workflow_id="todo_delivery_pipeline",
        goal="deliver todo app artifacts",
        status="active",
        current_stage="requirements",
        stages=[
            KairosWorkflowStage(
                stage_id="requirements",
                label="requirements",
                status="pending",
                task_ids=[resolved["requirements"]],
                artifacts=["demo_delivery/todo_app/requirements.md"],
            ),
            KairosWorkflowStage(
                stage_id="design",
                label="design",
                status="pending",
                task_ids=[resolved["design"]],
                artifacts=[
                    "demo_delivery/todo_app/design.md",
                    "demo_delivery/todo_app/file_plan.json",
                ],
            ),
            KairosWorkflowStage(
                stage_id="codegen",
                label="code generation",
                status="pending",
                task_ids=[resolved["codegen"]],
                artifacts=[
                    "demo_delivery/todo_app/index.html",
                    "demo_delivery/todo_app/style.css",
                    "demo_delivery/todo_app/app.js",
                ],
            ),
            KairosWorkflowStage(
                stage_id="verification",
                label="verification",
                status="pending",
                task_ids=[resolved["verification"]],
                artifacts=[
                    "demo_delivery/todo_app/test_plan.md",
                    "demo_delivery/todo_app/smoke_check.json",
                ],
            ),
            KairosWorkflowStage(
                stage_id="delivery_report",
                label="delivery report",
                status="pending",
                task_ids=[resolved["delivery_report"]],
                artifacts=["demo_delivery/todo_app/delivery_report.md"],
            ),
        ],
        metadata={"completed_task_ids": [], "task_aliases": resolved},
    )

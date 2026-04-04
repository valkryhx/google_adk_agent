from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .models import KairosPlannedAction, KairosState, KairosTrigger, TriggerKind


@dataclass
class ContinuationDecision:
    kind: str
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)


class ContinuationEngine:
    def __init__(self, path_exists: Callable[[str], bool] | None = None):
        self._path_exists = path_exists or (lambda _path: True)

    def evaluate_after_dex_poll(self, state: KairosState, completed_tasks: list[Any], tracked_tasks: list[Any]) -> list[ContinuationDecision]:
        workflow = state.active_workflow
        if workflow is None or workflow.workflow_id != "demo_report_pipeline":
            return []
        if workflow.current_stage != "phase1":
            return []

        completed_ids = set(workflow.metadata.get("completed_task_ids", []))
        for task in completed_tasks:
            if getattr(task, "status", None) == "completed":
                completed_ids.add(task.task_id)
        workflow.metadata["completed_task_ids"] = sorted(completed_ids)

        required_ids = set(workflow.stages[0].task_ids if workflow.stages else [])
        if not required_ids or completed_ids != required_ids:
            return []

        required_artifacts = workflow.stages[0].artifacts if workflow.stages else []
        if state.policy.require_artifacts_before_follow_up and any(not self._path_exists(path) for path in required_artifacts):
            state.blocked_reason = "missing required artifacts for phase1 follow-up"
            workflow.status = "waiting_input"
            return []

        fingerprint = {
            "workflow_id": workflow.workflow_id,
            "description": "generate final report",
        }
        for action in state.planned_actions:
            if action.kind == "create_dex_task" and action.payload == fingerprint:
                return []

        workflow.current_stage = "phase2"
        workflow.status = "active"
        state.blocked_reason = None

        decision = ContinuationDecision(
            kind="create_dex_task",
            reason="phase1_converged",
            payload={
                "workflow_id": workflow.workflow_id,
                "description": "generate final report",
            },
        )
        return [decision]

    def apply_decisions(self, state: KairosState, decisions: list[ContinuationDecision]) -> list[KairosTrigger]:
        triggers: list[KairosTrigger] = []
        for decision in decisions:
            if decision.kind == "create_dex_task":
                state.planned_actions.append(
                    KairosPlannedAction(
                        action_id=f"{decision.payload['workflow_id']}-create-report",
                        kind=decision.kind,
                        reason=decision.reason,
                        payload=decision.payload,
                        status="pending",
                    )
                )
                triggers.append(
                    KairosTrigger(
                        trigger_id=f"internal-{decision.payload['workflow_id']}-phase2",
                        kind=TriggerKind.INTERNAL,
                        reason=decision.reason,
                        created_at="1970-01-01T00:00:00+00:00",
                        metadata=decision.payload,
                    )
                )
        return triggers

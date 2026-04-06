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
        if workflow is None:
            return []
        if workflow.workflow_id == "demo_report_pipeline":
            return self._evaluate_demo_report_pipeline(state, workflow, completed_tasks)
        if workflow.workflow_id == "todo_delivery_pipeline":
            return self._evaluate_todo_delivery_pipeline(state, workflow, completed_tasks)
        return []

    def _evaluate_demo_report_pipeline(self, state: KairosState, workflow, completed_tasks: list[Any]) -> list[ContinuationDecision]:
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
            payload=fingerprint,
        )
        return [decision]

    def _evaluate_todo_delivery_pipeline(self, state: KairosState, workflow, completed_tasks: list[Any]) -> list[ContinuationDecision]:
        if workflow.current_stage == "delivery_report" or workflow.status == "completed":
            return []
        completed_ids = set(workflow.metadata.get("completed_task_ids", []))
        for task in completed_tasks:
            if getattr(task, "status", None) == "completed":
                completed_ids.add(task.task_id)
                description = getattr(task, "description", None)
                if description:
                    completed_ids.add(description)
        workflow.metadata["completed_task_ids"] = sorted(completed_ids)

        alias_map = workflow.metadata.get("task_aliases", {})
        required_ids = {
            alias_map.get("requirements", "todo_requirements"),
            alias_map.get("design", "todo_design"),
            alias_map.get("codegen", "todo_codegen"),
            alias_map.get("verification", "todo_tests"),
        }
        if not required_ids.issubset(completed_ids):
            return []

        required_artifacts: list[str] = []
        for stage in workflow.stages:
            if stage.stage_id == "delivery_report":
                break
            required_artifacts.extend(stage.artifacts)
        missing_artifacts = [path for path in required_artifacts if not self._path_exists(path)]
        if state.policy.require_artifacts_before_follow_up and missing_artifacts:
            state.blocked_reason = "missing required artifacts for todo delivery report"
            workflow.status = "waiting_input"
            workflow.current_stage = "verification"
            state.condition_tree = {
                "stage_id": "verification",
                "stage_label": "verification",
                "satisfied": [
                    {"kind": "artifact", "target": path, "reason": None}
                    for path in required_artifacts
                    if path not in missing_artifacts
                ],
                "missing": [
                    {
                        "kind": "artifact",
                        "target": path,
                        "reason": "missing required artifacts for todo delivery report",
                    }
                    for path in missing_artifacts
                ],
                "failed_checks": [],
            }
            return []

        verification_result = workflow.metadata.get("verification_result") or {}
        if verification_result.get("ready") is False:
            state.blocked_reason = "verification checks failed for todo delivery report"
            workflow.status = "waiting_input"
            workflow.current_stage = "verification"
            state.condition_tree = {
                "stage_id": "verification",
                "stage_label": "verification",
                "satisfied": [
                    {"kind": "artifact", "target": path, "reason": None}
                    for path in required_artifacts
                ],
                "missing": [],
                "failed_checks": list(verification_result.get("failures", [])),
            }
            return []
        if verification_result.get("ready") is not True:
            return []

        fingerprint = {
            "workflow_id": workflow.workflow_id,
            "description": "generate todo delivery report",
        }
        for action in state.planned_actions:
            if action.kind == "create_dex_task" and action.payload == fingerprint:
                return []

        workflow.current_stage = "delivery_report"
        workflow.status = "active"
        state.blocked_reason = None
        state.condition_tree = None
        return [
            ContinuationDecision(
                kind="create_dex_task",
                reason="todo_delivery_ready",
                payload=fingerprint,
            )
        ]

    def apply_decisions(self, state: KairosState, decisions: list[ContinuationDecision]) -> list[KairosTrigger]:
        triggers: list[KairosTrigger] = []
        for decision in decisions:
            if decision.kind == "create_dex_task":
                action_id = f"{decision.payload['workflow_id']}-{decision.payload['description'].replace(' ', '-')}"
                state.planned_actions.append(
                    KairosPlannedAction(
                        action_id=action_id,
                        kind=decision.kind,
                        reason=decision.reason,
                        payload=decision.payload,
                        status="pending",
                    )
                )
                triggers.append(
                    KairosTrigger(
                        trigger_id=f"internal-{decision.payload['workflow_id']}-follow-up",
                        kind=TriggerKind.INTERNAL,
                        reason=decision.reason,
                        created_at="1970-01-01T00:00:00+00:00",
                        metadata=decision.payload,
                    )
                )
        return triggers

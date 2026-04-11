from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

from .models import DocumentReadResult, KairosPlannedAction, KairosState, KairosTrigger, TriggerKind


@dataclass
class ContinuationDecision:
    kind: str
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)


class ContinuationEngine:
    def __init__(
        self,
        path_exists: Callable[[str], bool] | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self._path_exists = path_exists or (lambda _path: True)
        self._now = now or (lambda: datetime.now(UTC))

    def evaluate_after_dex_poll(self, state: KairosState, completed_tasks: list[Any], tracked_tasks: list[Any]) -> list[ContinuationDecision]:
        workflow = state.active_workflow
        if workflow is None:
            return []
        if workflow.workflow_id == "demo_report_pipeline":
            decisions = self._evaluate_demo_report_pipeline(state, workflow, completed_tasks)
        elif workflow.workflow_id == "todo_delivery_pipeline":
            decisions = self._evaluate_todo_delivery_pipeline(state, workflow, completed_tasks)
        else:
            decisions = []
        if decisions:
            self._sync_final_action_from_decision(state, decisions[0])
        return decisions

    def refresh_unfinished_work(self, state: KairosState) -> None:
        workflow = state.active_workflow
        state.unfinished_work_items = []
        state.proactive_candidates = []
        if not state.policy.proactive_scan_enabled:
            return

        document_work_item = self._build_document_unfinished_work_item(state.document_work_items)
        if document_work_item is not None:
            state.unfinished_work_items.append(document_work_item)
            scan_ts = self._now().isoformat()
            candidates = self._build_document_proactive_candidates(document_work_item)
            state.proactive_candidates = candidates
            selected_candidate, same_tier_retained = self._select_candidate(state, candidates)
            rejected_candidates = self._build_rejected_candidates(
                candidates,
                selected_candidate,
                same_tier_retained=same_tier_retained,
                cooldown_active=False,
            )
            final_action = self._build_final_action(selected_candidate)
            state.last_guardrail_block = {}
            state.last_proactive_scan = {
                "ts": scan_ts,
                "result": "waiting_input" if document_work_item["status"] == "blocked" else "candidate_found",
                "winner": selected_candidate["candidate_id"],
            }
            state.last_planning_result = {
                "ts": scan_ts,
                "goal": document_work_item["goal"],
                "workflow_id": None,
                "stage_id": document_work_item["stage_id"],
                "candidates_considered": [dict(candidate) for candidate in candidates],
                "selected_candidate": dict(selected_candidate),
                "rejected_candidates": rejected_candidates,
                "final_action": final_action,
                "policy_note": "winner chosen under tiered-action policy",
            }
            return

        if workflow is None:
            return

        work_item = self._build_unfinished_work_item(workflow)
        if work_item is not None:
            state.unfinished_work_items.append(work_item)

        if not state.unfinished_work_items:
            state.last_proactive_scan = {
                "ts": self._now().isoformat(),
                "result": "no_action",
                "winner": None,
            }
            state.last_guardrail_block = {}
            return

        scan_ts = self._now().isoformat()
        candidates = self._build_proactive_candidates(state, workflow, work_item)
        state.proactive_candidates = candidates

        cooldown_active = self._is_cooldown_active(state, scan_ts)
        if cooldown_active:
            selected_candidate = next(candidate for candidate in candidates if candidate["action"] == "sleep")
            rejected_candidates = self._build_rejected_candidates(
                candidates,
                selected_candidate,
                same_tier_retained=False,
                cooldown_active=True,
            )
            final_action = self._build_final_action(selected_candidate)
            state.last_guardrail_block = {
                "reason": "cooldown_active",
                "workflow_id": workflow.workflow_id,
                "work_id": work_item["work_id"],
            }
            state.last_proactive_scan = {
                "ts": scan_ts,
                "result": "cooldown_active",
                "winner": selected_candidate["candidate_id"],
            }
            state.last_planning_result = {
                "ts": scan_ts,
                "goal": workflow.goal,
                "workflow_id": workflow.workflow_id,
                "stage_id": work_item["stage_id"],
                "candidates_considered": [dict(candidate) for candidate in candidates],
                "selected_candidate": dict(selected_candidate),
                "rejected_candidates": rejected_candidates,
                "final_action": final_action,
                "policy_note": "cooldown guardrail forced sleep fallback",
            }
            return

        selected_candidate, same_tier_retained = self._select_candidate(state, candidates)
        rejected_candidates = self._build_rejected_candidates(
            candidates,
            selected_candidate,
            same_tier_retained=same_tier_retained,
            cooldown_active=False,
        )
        final_action = self._build_final_action(selected_candidate)
        state.last_guardrail_block = {}
        state.last_proactive_scan = {
            "ts": scan_ts,
            "result": "waiting_input" if workflow.status == "waiting_input" else "candidate_found",
            "winner": selected_candidate["candidate_id"],
        }
        state.last_planning_result = {
            "ts": scan_ts,
            "goal": workflow.goal,
            "workflow_id": workflow.workflow_id,
            "stage_id": work_item["stage_id"],
            "candidates_considered": [dict(candidate) for candidate in candidates],
            "selected_candidate": dict(selected_candidate),
            "rejected_candidates": rejected_candidates,
            "final_action": final_action,
            "policy_note": "winner chosen under tiered-action policy",
        }

    def _build_unfinished_work_item(self, workflow) -> dict[str, Any] | None:
        current_stage = workflow.current_stage
        for stage in workflow.stages:
            if stage.stage_id != current_stage:
                continue
            if stage.status in {"completed", "failed"}:
                continue
            return {
                "work_id": f"{workflow.workflow_id}:{stage.stage_id}",
                "kind": "workflow_stage",
                "workflow_id": workflow.workflow_id,
                "stage_id": stage.stage_id,
                "priority": 10,
                "reason": f"stage {stage.stage_id} still unfinished",
            }
        return None

    def _build_document_unfinished_work_item(
        self,
        document_work_items: list[DocumentReadResult],
    ) -> dict[str, Any] | None:
        for item in document_work_items:
            if item.status in {"completed", "done", "cancelled"}:
                continue
            return {
                "work_id": item.work_id,
                "kind": "document_work_item",
                "workflow_id": None,
                "stage_id": item.current_step or "document_work",
                "priority": 10,
                "reason": item.blockers[0] if item.blockers else f"document work {item.work_id} still unfinished",
                "goal": item.goal,
                "status": item.status,
                "next_actions": list(item.next_actions),
                "open_questions": list(item.open_questions),
                "human_input_required": item.human_input_required,
            }
        return None

    def _build_document_proactive_candidates(self, work_item: dict[str, Any]) -> list[dict[str, Any]]:
        waiting_input = work_item["status"] == "blocked" or work_item["human_input_required"]
        reason = work_item["reason"]
        stage_id = work_item["stage_id"]
        work_id = work_item["work_id"]
        return [
            {
                "candidate_id": f"{work_id}:{stage_id}:continue_workflow",
                "action": "continue_workflow",
                "tier": "medium",
                "priority": 50,
                "blocked": waiting_input,
                "selected": False,
                "reason": reason,
            },
            {
                "candidate_id": f"{work_id}:{stage_id}:create_follow_up",
                "action": "create_follow_up",
                "tier": "medium",
                "priority": 60,
                "blocked": True,
                "selected": False,
                "reason": "follow-up not available for document work yet",
                "payload": {},
            },
            {
                "candidate_id": f"{work_id}:{stage_id}:emit_brief",
                "action": "emit_brief",
                "tier": "low",
                "priority": 20,
                "blocked": False,
                "selected": False,
                "reason": f"summarize unfinished work for {stage_id}",
            },
            {
                "candidate_id": f"{work_id}:{stage_id}:ask_user",
                "action": "ask_user",
                "tier": "high",
                "priority": 100,
                "blocked": not waiting_input,
                "selected": False,
                "reason": reason,
            },
            {
                "candidate_id": f"{work_id}:{stage_id}:sleep",
                "action": "sleep",
                "tier": "low",
                "priority": 10,
                "blocked": False,
                "selected": False,
                "reason": "no stronger action available",
            },
            {
                "candidate_id": f"{work_id}:{stage_id}:blocked",
                "action": "blocked",
                "tier": "high",
                "priority": 90,
                "blocked": not waiting_input,
                "selected": False,
                "reason": reason,
            },
        ]

    def _build_proactive_candidates(self, state: KairosState, workflow, work_item: dict[str, Any]) -> list[dict[str, Any]]:
        stage_id = work_item["stage_id"]
        create_follow_up = self._build_follow_up_candidate(state, workflow, stage_id)
        ask_user_ready = workflow.status == "waiting_input" or bool(state.blocked_reason)
        blocked_ready = workflow.status == "waiting_input" or bool(state.blocked_reason)
        return [
            {
                "candidate_id": f"{workflow.workflow_id}:{stage_id}:continue_workflow",
                "action": "continue_workflow",
                "tier": "medium",
                "priority": 50,
                "blocked": False,
                "selected": False,
                "reason": work_item["reason"],
            },
            create_follow_up,
            {
                "candidate_id": f"{workflow.workflow_id}:{stage_id}:emit_brief",
                "action": "emit_brief",
                "tier": "low",
                "priority": 20,
                "blocked": False,
                "selected": False,
                "reason": f"summarize unfinished work for {stage_id}",
            },
            {
                "candidate_id": f"{workflow.workflow_id}:{stage_id}:ask_user",
                "action": "ask_user",
                "tier": "high",
                "priority": 100,
                "blocked": not ask_user_ready,
                "selected": False,
                "reason": state.blocked_reason or "workflow waiting for user input",
            },
            {
                "candidate_id": f"{workflow.workflow_id}:{stage_id}:sleep",
                "action": "sleep",
                "tier": "low",
                "priority": 10,
                "blocked": False,
                "selected": False,
                "reason": "no stronger action available",
            },
            {
                "candidate_id": f"{workflow.workflow_id}:{stage_id}:blocked",
                "action": "blocked",
                "tier": "high",
                "priority": 90,
                "blocked": not blocked_ready,
                "selected": False,
                "reason": state.blocked_reason or "workflow is not blocked",
            },
        ]

    def _build_follow_up_candidate(self, state: KairosState, workflow, stage_id: str) -> dict[str, Any]:
        if workflow.workflow_id == "todo_delivery_pipeline":
            ready, reason, payload = self._todo_delivery_follow_up_status(state, workflow)
            candidate_stage_id = "delivery_report"
            return {
                "candidate_id": f"{workflow.workflow_id}:{candidate_stage_id}:create_follow_up",
                "action": "create_follow_up",
                "tier": "medium",
                "priority": 60,
                "blocked": not ready,
                "selected": False,
                "reason": reason,
                "payload": payload,
            }
        return {
            "candidate_id": f"{workflow.workflow_id}:{stage_id}:create_follow_up",
            "action": "create_follow_up",
            "tier": "medium",
            "priority": 60,
            "blocked": True,
            "selected": False,
            "reason": "follow-up not available for current workflow",
            "payload": {},
        }

    def _todo_delivery_follow_up_status(self, state: KairosState, workflow) -> tuple[bool, str, dict[str, Any]]:
        completed_ids = set(workflow.metadata.get("completed_task_ids", []))
        alias_map = workflow.metadata.get("task_aliases", {})
        required_ids = {
            alias_map.get("requirements", "todo_requirements"),
            alias_map.get("design", "todo_design"),
            alias_map.get("codegen", "todo_codegen"),
            alias_map.get("verification", "todo_tests"),
        }
        if not required_ids.issubset(completed_ids):
            return False, "prerequisite tasks incomplete for todo delivery report", {}

        required_artifacts: list[str] = []
        for stage in workflow.stages:
            if stage.stage_id == "delivery_report":
                break
            required_artifacts.extend(stage.artifacts)
        missing_artifacts = [path for path in required_artifacts if not self._path_exists(path)]
        if state.policy.require_artifacts_before_follow_up and missing_artifacts:
            return False, "missing required artifacts for todo delivery report", {}

        verification_result = workflow.metadata.get("verification_result") or {}
        if verification_result.get("ready") is False:
            return False, "verification checks failed for todo delivery report", {}
        if verification_result.get("ready") is not True:
            return False, "verification result not ready for todo delivery report", {}

        return (
            True,
            "all prerequisite tasks and artifacts are satisfied",
            {
                "workflow_id": workflow.workflow_id,
                "description": "generate todo delivery report",
            },
        )

    def _is_cooldown_active(self, state: KairosState, scan_ts: str) -> bool:
        last_scan_ts = state.last_proactive_scan.get("ts")
        if not last_scan_ts:
            return False
        elapsed = datetime.fromisoformat(scan_ts) - datetime.fromisoformat(last_scan_ts)
        return elapsed.total_seconds() < state.policy.cooldown_seconds

    def _select_candidate(self, state: KairosState, candidates: list[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
        eligible_candidates = [candidate for candidate in candidates if not candidate["blocked"]]
        if not eligible_candidates:
            selected_candidate = next(candidate for candidate in candidates if candidate["action"] == "sleep")
            selected_candidate = dict(selected_candidate)
            selected_candidate["selected"] = True
            return selected_candidate, False

        selected_candidate = max(
            eligible_candidates,
            key=lambda candidate: (self._tier_rank(candidate["tier"]), candidate["priority"]),
        )
        highest_rank_candidate = selected_candidate
        same_tier_retained = False
        previous_selected = state.last_planning_result.get("selected_candidate", {})
        previous_candidate_id = previous_selected.get("candidate_id")
        previous_candidate = next(
            (
                candidate
                for candidate in eligible_candidates
                if candidate["candidate_id"] == previous_candidate_id
            ),
            None,
        )
        if previous_candidate is not None:
            previous_rank = self._tier_rank(previous_candidate["tier"])
            selected_rank = self._tier_rank(highest_rank_candidate["tier"])
            if previous_rank >= selected_rank:
                same_tier_retained = (
                    previous_rank == selected_rank
                    and previous_candidate["candidate_id"] != highest_rank_candidate["candidate_id"]
                )
                selected_candidate = previous_candidate

        selected_candidate = dict(selected_candidate)
        selected_candidate["selected"] = True
        return selected_candidate, same_tier_retained

    def _build_rejected_candidates(
        self,
        candidates: list[dict[str, Any]],
        selected_candidate: dict[str, Any],
        *,
        same_tier_retained: bool,
        cooldown_active: bool,
    ) -> list[dict[str, Any]]:
        selected_rank = self._tier_rank(selected_candidate["tier"])
        rejected_candidates: list[dict[str, Any]] = []
        for candidate in candidates:
            if candidate["candidate_id"] == selected_candidate["candidate_id"]:
                continue
            rejected_candidate = dict(candidate)
            if cooldown_active:
                rejected_candidate["rejected_reason"] = "cooldown guardrail selected sleep fallback"
            elif same_tier_retained and candidate["tier"] == selected_candidate["tier"] and not candidate["blocked"]:
                rejected_candidate["rejected_reason"] = "same tier candidate cannot supersede current winner"
            elif candidate["blocked"]:
                rejected_candidate["rejected_reason"] = "candidate blocked"
            elif self._tier_rank(candidate["tier"]) < selected_rank:
                rejected_candidate["rejected_reason"] = "higher tier candidate selected"
            elif candidate["tier"] == selected_candidate["tier"]:
                rejected_candidate["rejected_reason"] = "same tier but lower auxiliary priority"
            else:
                rejected_candidate["rejected_reason"] = "selected winner retained"
            rejected_candidates.append(rejected_candidate)
        return rejected_candidates

    def _build_final_action(self, candidate: dict[str, Any]) -> dict[str, Any]:
        if candidate["action"] == "continue_workflow":
            return {
                "kind": "continue_workflow_scan",
                "reason": "stage_unfinished",
                "payload": {
                    "workflow_id": candidate["candidate_id"].split(":", 1)[0],
                    "candidate_id": candidate["candidate_id"],
                },
            }
        if candidate["action"] == "create_follow_up":
            return {
                "kind": "create_dex_task",
                "reason": "todo_delivery_ready",
                "payload": dict(candidate.get("payload", {})),
            }
        if candidate["action"] == "emit_brief":
            return {
                "kind": "emit_brief_only",
                "reason": "unfinished_work_summary",
                "payload": {
                    "candidate_id": candidate["candidate_id"],
                },
            }
        if candidate["action"] == "ask_user":
            return {
                "kind": "ask_user",
                "reason": "workflow_waiting_input",
                "payload": {
                    "candidate_id": candidate["candidate_id"],
                    "message": candidate["reason"],
                },
            }
        if candidate["action"] == "blocked":
            return {
                "kind": "blocked",
                "reason": "workflow_blocked",
                "payload": {
                    "candidate_id": candidate["candidate_id"],
                    "message": candidate["reason"],
                },
            }
        return {
            "kind": "sleep",
            "reason": "cooldown_or_no_action",
            "payload": {
                "candidate_id": candidate["candidate_id"],
            },
        }

    def _decision_from_final_action(self, final_action: dict[str, Any]) -> ContinuationDecision:
        return ContinuationDecision(
            kind=final_action["kind"],
            reason=final_action.get("reason", "planned_action"),
            payload=dict(final_action.get("payload", {})),
        )

    def _tier_rank(self, tier: str) -> int:
        return {"low": 1, "medium": 2, "high": 3}.get(tier, 0)

    def _sync_final_action_from_decision(self, state: KairosState, decision: ContinuationDecision) -> None:
        final_action = {
            "kind": decision.kind,
            "reason": decision.reason,
            "payload": dict(decision.payload),
        }
        state.last_planning_result["final_action"] = final_action
        selected_candidate = dict(state.last_planning_result.get("selected_candidate", {}))
        if decision.kind == "create_dex_task":
            selected_candidate["action"] = "create_follow_up"
            selected_candidate.setdefault(
                "candidate_id",
                f"{decision.payload.get('workflow_id', 'workflow')}:delivery_report:create_follow_up",
            )
            selected_candidate.setdefault("tier", "medium")
            selected_candidate.setdefault("priority", 60)
            selected_candidate["selected"] = True
            selected_candidate["payload"] = dict(decision.payload)
            state.last_planning_result["selected_candidate"] = selected_candidate

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

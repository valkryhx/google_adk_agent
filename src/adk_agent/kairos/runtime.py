from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

from .document_protocol import (
    append_spawned_work_update,
    append_user_guidance_update,
    build_requirement_work_item,
    write_work_document,
)
from .continuation import ContinuationDecision, ContinuationEngine
from .models import (
    KairosActionPayload,
    KairosAttentionItem,
    KairosEvent,
    KairosMode,
    KairosPlannedAction,
    KairosReplanResult,
    KairosSchedule,
    KairosState,
    KairosTrigger,
    KairosVerificationResult,
    TriggerKind,
)
from .scheduler import KairosScheduler
from .workflows import demo_report_pipeline, todo_delivery_pipeline

SKILL_MATCH_MIN_SCORE = 0.62
SKILL_MATCH_MIN_MARGIN = 0.08


class KairosRuntime:
    def __init__(
        self,
        *,
        state: KairosState,
        save_state: Callable[[KairosState], Awaitable[None]],
        emit_event: Callable[[KairosEvent], Awaitable[None]],
        append_log: Callable[[KairosEvent], Awaitable[None]],
        run_turn: Callable[[str], Awaitable[str | None]],
        dex_bridge,
        tick_interval_seconds: float = 15.0,
        is_worker_busy: Callable[[], bool] | None = None,
        scheduler: KairosScheduler | None = None,
        continuation_engine: ContinuationEngine | None = None,
        create_follow_up_task: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any] | None]] | None = None,
        path_exists: Callable[[str], bool] | None = None,
        load_skill: Callable[[str], Awaitable[str]] | None = None,
        allowed_skills: Iterable[str] | None = None,
        list_available_skills: Callable[[], Iterable[str]] | None = None,
        list_available_skill_catalog: Callable[[], Iterable[dict[str, str]]] | None = None,
    ):
        self.state = state
        self._save_state = save_state
        self._emit_event = emit_event
        self._append_log = append_log
        self._run_turn = run_turn
        self._dex_bridge = dex_bridge
        self._tick_interval_seconds = tick_interval_seconds
        self._is_worker_busy = is_worker_busy or (lambda: False)
        self._scheduler = scheduler or KairosScheduler()
        self._continuation_engine = continuation_engine or ContinuationEngine()
        self._create_follow_up_task = create_follow_up_task
        self._path_exists = path_exists or (lambda path: False)
        self._load_skill = load_skill
        self._allowed_skills = (
            {str(skill_id).strip() for skill_id in allowed_skills if str(skill_id).strip()}
            if allowed_skills is not None
            else None
        )
        self._list_available_skills = list_available_skills
        self._list_available_skill_catalog = list_available_skill_catalog
        self._continuation_engine._path_exists = self._path_exists
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._wake_event = asyncio.Event()

    # --- Lifecycle ---

    async def start(self) -> None:
        self.state.enabled = True
        self.state.running = True
        self.state.mode = KairosMode.IDLE
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop())
        await self._persist()
        await self._record("status", "kairos runtime started")

    async def stop(self) -> None:
        self.state.running = False
        self.state.busy = False
        self.state.pending_wake_reason = None
        self.state.mode = KairosMode.STOPPED
        self._wake_event.set()
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.state.mode = KairosMode.STOPPED
        self.state.sleep_until = None
        await self._persist()
        await self._record("status", "kairos runtime stopped")

    async def enqueue_trigger(self, trigger: KairosTrigger) -> None:
        self.state.pending_triggers.append(trigger)
        self.state.pending_wake_reason = trigger.reason
        if self.state.mode == KairosMode.SLEEPING:
            self.state.mode = KairosMode.IDLE
        self._wake_event.set()
        await self._persist()

    async def wake(self, reason: str) -> None:
        await self.enqueue_trigger(
            KairosTrigger(
                trigger_id=f"manual-{int(datetime.now(UTC).timestamp())}",
                kind=TriggerKind.MANUAL,
                reason=reason,
                created_at=datetime.now(UTC).isoformat(),
            )
        )
        await self._record("status", f"wake requested: {reason}")

    async def add_schedule(self, schedule: KairosSchedule) -> None:
        self.state.schedules = [s for s in self.state.schedules if s.schedule_id != schedule.schedule_id]
        self.state.schedules.append(schedule)
        self._scheduler.seed_schedules(self.state, datetime.now(UTC))
        await self._persist()
        await self._record("status", f"schedule registered: {schedule.schedule_id}")

    async def delete_schedule(self, schedule_id: str) -> None:
        self.state.schedules = [s for s in self.state.schedules if s.schedule_id != schedule_id]
        await self._persist()
        await self._record("status", f"schedule removed: {schedule_id}")

    async def register_dex_task(self, task_id: str, description: str) -> None:
        if task_id not in self.state.tracked_dex_task_ids:
            self.state.tracked_dex_task_ids.append(task_id)

        if description.startswith("prepare "):
            workflow = self.state.active_workflow
            if workflow is None or workflow.workflow_id != "demo_report_pipeline":
                workflow = demo_report_pipeline([])
                self.state.active_workflow = workflow
            phase1 = workflow.stages[0]
            if task_id not in phase1.task_ids:
                phase1.task_ids.append(task_id)
            workflow.metadata.setdefault("phase1_descriptions", {})[task_id] = description
            phase1.status = "running"
            workflow.status = "active"
            workflow.current_stage = "phase1"
        elif description == "generate final report" and self.state.active_workflow is not None:
            workflow = self.state.active_workflow
            if len(workflow.stages) > 1:
                workflow.stages[1].task_ids = [task_id]
                workflow.stages[1].status = "running"
            workflow.current_stage = "phase2"
            workflow.status = "active"
        elif description in {"todo_requirements", "todo_design", "todo_codegen", "todo_tests", "todo_delivery_report", "generate todo delivery report"}:
            workflow = self.state.active_workflow
            if workflow is None or workflow.workflow_id != "todo_delivery_pipeline":
                workflow = todo_delivery_pipeline()
                self.state.active_workflow = workflow
            alias_map = workflow.metadata.get("task_aliases", {})
            description_to_stage = {
                alias_map.get("requirements", "todo_requirements"): "requirements",
                alias_map.get("design", "todo_design"): "design",
                alias_map.get("codegen", "todo_codegen"): "codegen",
                alias_map.get("verification", "todo_tests"): "verification",
                alias_map.get("delivery_report", "todo_delivery_report"): "delivery_report",
                "generate todo delivery report": "delivery_report",
            }
            target_stage_id = description_to_stage.get(description)
            for stage in workflow.stages:
                if stage.stage_id == target_stage_id:
                    stage.task_ids = [task_id]
                    stage.status = "running"
                    workflow.current_stage = stage.stage_id
                    workflow.status = "active"
                    break

        if self.state.running and not self.state.busy:
            self.state.mode = KairosMode.HANDOFF
        await self._persist()
        await self._record("brief", f"dex handoff registered: {task_id} {description}")

    async def register_work_item(
        self,
        *,
        requirement: str,
        session_id: str,
        source_label: str,
    ) -> DocumentReadResult:
        item = build_requirement_work_item(
            requirement,
            session_id=session_id,
            source_label=source_label,
        )
        write_work_document(Path.cwd(), item)

        self.state.document_work_items = [
            existing for existing in self.state.document_work_items if existing.work_id != item.work_id
        ]
        self.state.document_work_items.insert(0, item)
        self._continuation_engine._path_exists = self._path_exists
        self._continuation_engine.refresh_unfinished_work(self.state)
        await self._persist()
        await self._record("brief", f"kairos work registered: {item.work_id} source={source_label}")
        await self.enqueue_trigger(
            KairosTrigger(
                trigger_id=f"work-register-{int(datetime.now(UTC).timestamp())}",
                kind=TriggerKind.MANUAL,
                reason=f"work_registered:{item.work_id}",
                created_at=datetime.now(UTC).isoformat(),
                metadata={"work_id": item.work_id, "source": source_label},
            )
        )
        return item

    async def tick_once(self) -> None:
        async with self._lock:
            now = datetime.now(UTC)
            self.state.last_tick_at = now.isoformat()
            self._scheduler.seed_schedules(self.state, now)
            due_triggers = self._scheduler.collect_due_triggers(self.state, now)
            self.state.pending_triggers.extend(due_triggers)
            ready_trigger_count = len(self.state.pending_triggers)
            self._continuation_engine._path_exists = self._path_exists
            previous_planning_snapshot = dict(self.state.last_planning_result)
            await self._poll_dex()
            if not (self.state.policy.llm_only_decision_enabled and self.state.active_workflow is not None):
                self._continuation_engine.refresh_unfinished_work(self.state)
            if self.state.active_workflow is None and self.state.document_work_items:
                planner = getattr(self, "_llm_planner", None)
                planner_failure: Exception | None = None
                if planner is None and self.state.policy.llm_only_decision_enabled:
                    planner_failure = RuntimeError("llm planner unavailable")
                if planner is not None and not self.state.current_execution_plan.steps:
                    try:
                        understanding = await planner.draft_requirement_understanding(self.state.document_work_items[0])
                        self.state.current_understanding = understanding
                        self.state.current_execution_plan = await planner.build_execution_plan(
                            self.state.document_work_items[0],
                            understanding,
                            candidate_actions=[
                                "update_document",
                                "spawn_dex_task",
                                "agent_execute",
                                "ask_user",
                                "sleep",
                            ],
                        )
                        if self.state.current_execution_plan.steps:
                            first_step = self.state.current_execution_plan.steps[0]
                            if first_step.get("action_kind") == "update_document":
                                self.state.current_action_payload = await planner.build_document_patch_payload(
                                    work_item=self.state.document_work_items[0],
                                    step=first_step,
                                )
                            elif first_step.get("action_kind") == "spawn_dex_task":
                                self.state.current_action_payload = await planner.build_design_codegen_payload(
                                    work_item=self.state.document_work_items[0],
                                    step=first_step,
                                )
                            elif first_step.get("action_kind") == "agent_execute":
                                self.state.current_action_payload = KairosActionPayload(
                                    action_kind="agent_execute",
                                    rationale=str(first_step.get("reason") or ""),
                                    args={
                                        "required_skills": self._coerce_skill_list(first_step.get("required_skills")),
                                        "execution_prompt": str(
                                            first_step.get("execution_prompt")
                                            or first_step.get("reason")
                                            or ""
                                        ).strip(),
                                    },
                                )
                            else:
                                self.state.current_action_payload = await planner.build_action_payload(
                                    work_item=self.state.document_work_items[0],
                                    step=first_step,
                                )
                            await self._dispatch_action_payload()
                        else:
                            raise ValueError("llm planner produced empty execution plan")
                    except Exception as exc:
                        planner_failure = exc
                        await self._record("brief", f"llm planner fallback active: {type(exc).__name__}: {exc}")
                if planner_failure is not None and self.state.policy.llm_only_decision_enabled:
                    item = self.state.document_work_items[0]
                    detail = str(planner_failure).strip() or type(planner_failure).__name__
                    message = f"llm planner failed for document work: {detail}"
                    self.state.blocked_reason = message
                    self.state.mode = KairosMode.WAITING_INPUT
                    self.state.last_planning_result = {
                        "ts": datetime.now(UTC).isoformat(),
                        "goal": item.goal,
                        "workflow_id": "document_requirement",
                        "stage_id": item.current_step,
                        "candidates_considered": [],
                        "selected_candidate": {
                            "candidate_id": f"{item.work_id}:{item.current_step or 'document_work'}:blocked",
                            "action": "blocked",
                            "tier": "high",
                            "priority": 100,
                            "selected": True,
                            "reason": message,
                        },
                        "rejected_candidates": [],
                        "final_action": {
                            "kind": "record_blocked",
                            "reason": "llm_document_plan_unavailable",
                            "payload": {
                                "work_id": item.work_id,
                                "step_id": item.current_step or "document_work",
                                "message": message,
                            },
                        },
                        "policy_note": "llm-only mode blocks document workflow when planner is unavailable or invalid",
                    }
                    await self._persist()
                else:
                    final_action = dict(self.state.last_planning_result.get("final_action", {}))
                    if final_action.get("kind"):
                        decision = self._continuation_engine._decision_from_final_action(final_action)
                        self.state.pending_triggers.extend(self._continuation_engine.apply_decisions(self.state, [decision]))
            await self._record_planning_transition(previous_planning_snapshot)
            self._sync_attention_from_planning()
            await self._auto_resume_waiting_input_if_timed_out(now)

            if not self.state.running:
                return

            if self._is_worker_busy():
                await self._record("status", "worker busy, skip kairos tick")
                return

            if self.state.policy.max_auto_steps_per_tick <= 0:
                self.state.last_guardrail_block = {
                    "reason": "auto_step_budget_exhausted",
                    "tick": self.state.last_tick_at,
                }
                await self._persist()
                return

            if self.state.pending_triggers and not self.state.busy:
                trigger = self.state.pending_triggers.pop(0)
                if self.state.mode is KairosMode.WAITING_INPUT and trigger.kind is not TriggerKind.INTERNAL:
                    # Keep task paused while waiting for user guidance.
                    self.state.pending_triggers.insert(0, trigger)
                    await self._persist()
                    return
                if trigger.kind is TriggerKind.INTERNAL and self._create_follow_up_task is not None:
                    await self._execute_internal_trigger(trigger)
                else:
                    await self._execute_regular_trigger(trigger)
            elif self.state.pending_wake_reason and not self.state.busy:
                reason = self.state.pending_wake_reason
                self.state.pending_wake_reason = None
                self.state.busy = True
                self.state.mode = KairosMode.RUNNING
                await self._persist()
                await self._record("brief", f"kairos turn started: {reason}")
                try:
                    await self._run_turn(reason)
                finally:
                    self.state.busy = False
                    if self.state.running:
                        self.state.mode = KairosMode.SLEEPING
                        self.state.sleep_until = (
                            datetime.now(UTC) + timedelta(seconds=self._tick_interval_seconds)
                        ).isoformat()
                    else:
                        self.state.mode = KairosMode.STOPPED
                        self.state.sleep_until = None
                    await self._persist()
                    await self._record("brief", f"kairos turn finished: {reason}")

    def _current_stage(self):
        workflow = self.state.active_workflow
        if workflow is None or not workflow.stages:
            return None
        if workflow.current_stage:
            for stage in workflow.stages:
                if stage.stage_id == workflow.current_stage:
                    return stage
        return workflow.stages[0]

    def _artifact_status_for_stage(self, stage) -> str:
        if stage is None or not stage.artifacts:
            return "unknown"
        return "available" if all(self._path_exists(path) for path in stage.artifacts) else "missing"

    def _build_task_summary(self, task, stage) -> dict[str, Any]:
        summary_text = getattr(task, "result_summary", None) or getattr(task, "error_summary", None) or getattr(task, "result", "") or f"{task.description} is {task.status}"
        return {
            "task_id": task.task_id,
            "status": task.status,
            "summary_text": summary_text,
            "artifact_status": self._artifact_status_for_stage(stage),
            "log_hint": getattr(task, "log_path", None),
            "result_summary": getattr(task, "result_summary", None),
            "error_summary": getattr(task, "error_summary", None),
        }

    def _build_condition_tree(self) -> dict[str, Any] | None:
        if self.state.condition_tree is not None:
            return self.state.condition_tree
        stage = self._current_stage()
        if stage is None or (self.state.blocked_reason is None and self.state.mode is not KairosMode.WAITING_INPUT):
            return self.state.condition_tree
        satisfied = []
        missing = []
        for artifact in stage.artifacts:
            bucket = satisfied if self._path_exists(artifact) else missing
            item = {
                "kind": "artifact",
                "target": artifact,
                "reason": None if self._path_exists(artifact) else self.state.blocked_reason,
            }
            bucket.append(item)
        return {
            "stage_id": stage.stage_id,
            "stage_label": stage.label,
            "satisfied": satisfied,
            "missing": missing,
            "failed_checks": [],
        }

    def _build_decision_explanation(self) -> dict[str, Any]:
        condition_tree = self._build_condition_tree()
        missing_requirements = [] if not condition_tree else [item["target"] for item in condition_tree.get("missing", [])]
        return {
            "why_continued": self.state.planned_actions[0].reason if self.state.planned_actions else None,
            "why_stopped": self.state.blocked_reason if (self.state.blocked_reason or self.state.mode is KairosMode.WAITING_INPUT) else None,
            "missing_requirements": missing_requirements,
        }

    def _build_document_progress_view(self) -> dict[str, Any]:
        attempts = [asdict(item) for item in self.state.step_attempts]
        pending_attempt = next((item for item in self.state.step_attempts if item.status in {"pending", "started"}), None)
        return {
            "step_attempts": attempts,
            "active_attempt": asdict(pending_attempt) if pending_attempt else None,
            "document_work_count": len(self.state.document_work_items),
        }

    @staticmethod
    def _coerce_skill_list(raw_value: Any) -> list[str]:
        if raw_value is None:
            return []
        if isinstance(raw_value, str):
            normalized = raw_value.strip()
            return [normalized] if normalized else []
        if isinstance(raw_value, (list, tuple, set)):
            result: list[str] = []
            for item in raw_value:
                normalized = str(item).strip()
                if normalized:
                    result.append(normalized)
            return result
        normalized = str(raw_value).strip()
        return [normalized] if normalized else []

    @staticmethod
    def _normalize_skill_hint(value: str) -> str:
        return "".join(ch for ch in str(value).lower() if ch.isalnum())

    @staticmethod
    def _tokenize_skill_text(value: str) -> set[str]:
        text = str(value or "").lower()
        tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text))
        normalized = "".join(ch for ch in text if ch.isalnum())
        if normalized:
            tokens.add(normalized)
        return {token for token in tokens if token}

    def _resolve_available_skill_catalog(self) -> list[dict[str, str]]:
        catalog: list[dict[str, str]] = []
        if self._list_available_skill_catalog is not None:
            try:
                for item in list(self._list_available_skill_catalog()):
                    if not isinstance(item, dict):
                        continue
                    skill_id = str(item.get("id", "")).strip()
                    if not skill_id:
                        continue
                    catalog.append(
                        {
                            "id": skill_id,
                            "name": str(item.get("name", "")).strip() or skill_id,
                            "description": str(item.get("description", "")).strip(),
                        }
                    )
            except Exception:
                catalog = []

        if not catalog and self._list_available_skills is not None:
            try:
                ids = self._coerce_skill_list(list(self._list_available_skills()))
            except Exception:
                ids = []
            for skill_id in ids:
                catalog.append({"id": skill_id, "name": skill_id, "description": ""})

        if not catalog and self._allowed_skills is not None:
            for skill_id in sorted(self._allowed_skills):
                catalog.append({"id": skill_id, "name": skill_id, "description": ""})

        deduped: dict[str, dict[str, str]] = {}
        for item in catalog:
            skill_id = str(item.get("id", "")).strip()
            if not skill_id:
                continue
            if self._allowed_skills is not None and skill_id not in self._allowed_skills:
                continue
            if skill_id in deduped:
                if not deduped[skill_id].get("description") and item.get("description"):
                    deduped[skill_id]["description"] = item.get("description", "")
                if deduped[skill_id].get("name", skill_id) == skill_id and item.get("name"):
                    deduped[skill_id]["name"] = item.get("name", skill_id)
                continue
            deduped[skill_id] = {
                "id": skill_id,
                "name": str(item.get("name", "")).strip() or skill_id,
                "description": str(item.get("description", "")).strip(),
            }
        return [deduped[skill_id] for skill_id in sorted(deduped)]

    def _score_skill_match(
        self,
        *,
        hint: str,
        hint_tokens: set[str],
        entry: dict[str, str],
    ) -> float:
        skill_id = str(entry.get("id", "")).strip()
        if not skill_id:
            return 0.0
        name = str(entry.get("name", "")).strip()
        description = str(entry.get("description", "")).strip()
        normalized_hint = self._normalize_skill_hint(hint)
        normalized_id = self._normalize_skill_hint(skill_id)
        normalized_name = self._normalize_skill_hint(name)

        if normalized_hint and normalized_hint == normalized_id:
            return 1.0
        if normalized_hint and normalized_hint == normalized_name:
            return 0.98

        core_tokens = self._tokenize_skill_text(skill_id) | self._tokenize_skill_text(name)
        all_tokens = set(core_tokens) | self._tokenize_skill_text(description)

        core_overlap = 0.0
        all_overlap = 0.0
        if hint_tokens:
            if core_tokens:
                core_overlap = len(hint_tokens & core_tokens) / len(hint_tokens)
            if all_tokens:
                all_overlap = len(hint_tokens & all_tokens) / len(hint_tokens)

        id_ratio = SequenceMatcher(None, normalized_hint, normalized_id).ratio() if normalized_hint and normalized_id else 0.0
        name_ratio = SequenceMatcher(None, normalized_hint, normalized_name).ratio() if normalized_hint and normalized_name else 0.0

        score = max(id_ratio, name_ratio, core_overlap * 0.92, all_overlap * 0.78)
        if normalized_hint and normalized_id and normalized_hint in normalized_id and len(normalized_hint) >= 4:
            score = max(score, 0.9)
        if hint_tokens and hint_tokens.issubset(core_tokens):
            score = max(score, 0.94)
        return min(score, 1.0)

    def _resolve_skill_hint(
        self,
        *,
        hint: str,
        available_skill_catalog: list[dict[str, str]],
        allowed_skill_ids: set[str],
        normalized_allowed_skill_ids: dict[str, str],
    ) -> tuple[str | None, dict[str, Any]]:
        resolution: dict[str, Any] = {}
        if not allowed_skill_ids:
            resolution["hint_resolution"] = "catalog_unavailable"
            return None, resolution
        forced_match_skill_id: str | None = None
        forced_resolution: str | None = None
        if hint in allowed_skill_ids:
            forced_match_skill_id = hint
            forced_resolution = "exact"
        normalized_hint = self._normalize_skill_hint(hint)
        if normalized_hint and forced_match_skill_id is None:
            normalized_match = normalized_allowed_skill_ids.get(normalized_hint)
            if normalized_match:
                forced_match_skill_id = normalized_match
                forced_resolution = "normalized"
        hint_tokens = self._tokenize_skill_text(hint)
        ranked: list[tuple[float, float, dict[str, str]]] = []
        for entry in available_skill_catalog:
            skill_id = str(entry.get("id", "")).strip()
            if not skill_id or skill_id not in allowed_skill_ids:
                continue
            score = self._score_skill_match(hint=hint, hint_tokens=hint_tokens, entry=entry)
            if score <= 0:
                continue
            core_tokens = self._tokenize_skill_text(skill_id) | self._tokenize_skill_text(entry.get("name", ""))
            token_coverage = 0.0
            if hint_tokens and core_tokens:
                token_coverage = len(hint_tokens & core_tokens) / len(hint_tokens)
            ranked.append((score, token_coverage, entry))
        if not ranked:
            if forced_match_skill_id is not None:
                resolution["hint_resolution"] = forced_resolution or "normalized"
                return forced_match_skill_id, resolution
            return None, resolution
        ranked.sort(key=lambda item: item[0], reverse=True)
        best_score, best_token_coverage, best_entry = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else 0.0
        candidate_matches: list[dict[str, Any]] = []
        for score, _, entry in ranked[:3]:
            description = str(entry.get("description", "")).strip().replace("\r", " ").replace("\n", " ")
            if len(description) > 160:
                description = f"{description[:157]}..."
            candidate_matches.append(
                {
                    "skill_id": str(entry.get("id", "")).strip(),
                    "name": str(entry.get("name", "")).strip(),
                    "description": description,
                    "score": round(score, 3),
                }
            )
        resolution["candidate_matches"] = candidate_matches
        if forced_match_skill_id is not None:
            resolution["hint_resolution"] = forced_resolution or "normalized"
            return forced_match_skill_id, resolution
        resolution["match_score"] = round(best_score, 3)
        resolution["token_coverage"] = round(best_token_coverage, 3)
        resolution["candidate_skill_id"] = best_entry.get("id")
        if best_score < SKILL_MATCH_MIN_SCORE:
            resolution["hint_resolution"] = "low_confidence_match"
            return None, resolution
        if hint_tokens and best_token_coverage < 0.5 and best_score < 0.72:
            resolution["hint_resolution"] = "low_token_coverage"
            return None, resolution
        if (
            second_score >= SKILL_MATCH_MIN_SCORE - 0.03
            and (best_score - second_score) < SKILL_MATCH_MIN_MARGIN
        ):
            resolution["hint_resolution"] = "ambiguous_match"
            resolution["second_match_score"] = round(second_score, 3)
            resolution["second_candidate_skill_id"] = ranked[1][2].get("id")
            return None, resolution
        resolution["hint_resolution"] = "text_match"
        return str(best_entry.get("id", "")).strip() or None, resolution

    def _resolve_available_skill_ids(self) -> list[str]:
        return [item["id"] for item in self._resolve_available_skill_catalog()]

    async def _block_agent_execute(self, reason: str) -> None:
        self.state.blocked_reason = reason
        self.state.mode = KairosMode.WAITING_INPUT
        work_id = self.state.document_work_items[0].work_id if self.state.document_work_items else None
        stage_id = self.state.document_work_items[0].current_step if self.state.document_work_items else None
        workflow_id = self.state.active_workflow.workflow_id if self.state.active_workflow else None
        self._upsert_attention_item(
            scope_kind="document_work" if work_id else "workflow_stage",
            workflow_id=workflow_id,
            work_id=work_id,
            stage_id=stage_id,
            question=reason,
            blocked_reason=reason,
            refresh_timeout=True,
        )
        await self._record("brief", reason)

    async def _dispatch_action_payload(self) -> None:
        payload = self.state.current_action_payload
        if not payload.action_kind:
            return
        if payload.action_kind == "ask_user":
            message = payload.why_blocked or payload.question or "waiting for user input"
            self.state.blocked_reason = message
            work_id = payload.args.get("work_id") if isinstance(payload.args, dict) else None
            stage_id = (
                (payload.args.get("stage_id") if isinstance(payload.args, dict) else None)
                or (self.state.document_work_items[0].current_step if self.state.document_work_items else None)
            )
            workflow_id = self.state.active_workflow.workflow_id if self.state.active_workflow else None
            self._upsert_attention_item(
                scope_kind="document_work" if work_id else "workflow_stage",
                workflow_id=workflow_id,
                work_id=work_id,
                stage_id=stage_id,
                question=message,
                blocked_reason=message,
                timeout_seconds=payload.timeout_hint,
                refresh_timeout=True,
            )
            self.state.mode = KairosMode.WAITING_INPUT
            return
        if payload.action_kind == "sleep":
            self.state.blocked_reason = None
            return
        if payload.action_kind == "update_document":
            if not self.state.document_work_items:
                return
            if payload.target_doc:
                doc_path = Path.cwd() / payload.target_doc
            elif self.state.document_work_items[0].expected_artifacts:
                doc_path = Path.cwd() / self.state.document_work_items[0].expected_artifacts[0]
            else:
                return
            if not doc_path.exists():
                return
            if payload.section_updates:
                append_spawned_work_update(
                    doc_path,
                    trigger_reason=payload.rationale or "llm_action_payload",
                    work_item=self.state.document_work_items[0],
                )
            return
        if payload.action_kind == "spawn_dex_task":
            description = payload.description or "llm generated dex task"
            command_template_id = payload.command_template_id or "draft_requirements_doc"
            safe_templates = {
                "draft_requirements_doc": lambda brief: f'PYTHONIOENCODING=utf-8 python -c "from pathlib import Path; Path(\"demo_outputs\").mkdir(exist_ok=True); Path(\"demo_outputs/requirements_brief.txt\").write_text({brief!r}, encoding=\"utf-8\")"',
                "generate_todo_app": lambda brief: f'PYTHONIOENCODING=utf-8 python -c "from pathlib import Path; Path(\"demo_delivery/todo_app\").mkdir(parents=True, exist_ok=True); Path(\"demo_delivery/todo_app/design_codegen_brief.txt\").write_text({brief!r}, encoding=\"utf-8\")"',
                "run_smoke_check": lambda brief: f'PYTHONIOENCODING=utf-8 python -c "from pathlib import Path; Path(\"demo_delivery/todo_app\").mkdir(parents=True, exist_ok=True); Path(\"demo_delivery/todo_app/smoke_check_request.txt\").write_text({brief!r}, encoding=\"utf-8\")"',
                "summarize_delivery": lambda brief: f'PYTHONIOENCODING=utf-8 python -c "from pathlib import Path; Path(\"demo_delivery\").mkdir(parents=True, exist_ok=True); Path(\"demo_delivery/delivery_summary_brief.txt\").write_text({brief!r}, encoding=\"utf-8\")"',
            }
            if command_template_id not in safe_templates:
                self.state.blocked_reason = f"unsupported command template: {command_template_id}"
                self.state.mode = KairosMode.WAITING_INPUT
                return
            design_codegen_brief = payload.brief or description
            task = self._dex_bridge.create_task(description, context=design_codegen_brief)
            self._dex_bridge.start_task(task["id"], safe_templates[command_template_id](design_codegen_brief))
            self.state.tracked_dex_task_ids.append(task["id"])
            planned_payload = {
                "task_id": task["id"],
                "work_id": self.state.document_work_items[0].work_id if self.state.document_work_items else None,
                "step_id": self.state.document_work_items[0].current_step if self.state.document_work_items else None,
                "description": description,
                "command_template_id": command_template_id,
                "design_codegen_brief": design_codegen_brief,
                "expected_artifacts": list(payload.expected_artifacts),
            }
            self.state.planned_actions.append(
                KairosPlannedAction(
                    action_id=f"planned-{task['id']}",
                    kind="run_dex_task",
                    reason=payload.rationale or "llm_action_payload",
                    payload=planned_payload,
                    status="pending",
                    created_at=task.get("created_at"),
                )
            )
            self.state.task_summaries = [
                {
                    "task_id": task["id"],
                    "status": "planned",
                    "summary_text": command_template_id,
                    "artifact_status": "unknown",
                    "log_hint": None,
                    "result_summary": design_codegen_brief,
                    "error_summary": None,
                }
            ] + self.state.task_summaries[:9]
            await self._record("brief", f"dex handoff registered: {task['id']} {description}")
            return
        if payload.action_kind == "agent_execute":
            args = payload.args if isinstance(payload.args, dict) else {}
            skill_hints = self._coerce_skill_list(args.get("required_skills"))
            if not skill_hints:
                skill_hints = self._coerce_skill_list(args.get("skill_hints"))
            skipped_skill_hints: list[str] = []
            skill_load_results: list[dict[str, Any]] = []
            available_skill_catalog = self._resolve_available_skill_catalog()
            available_skill_ids = [item["id"] for item in available_skill_catalog]
            allowed_skill_ids = set(available_skill_ids) if available_skill_ids else (
                set(self._allowed_skills) if self._allowed_skills is not None else set()
            )
            normalized_allowed_skill_ids: dict[str, str] = {}
            for candidate in sorted(allowed_skill_ids):
                normalized_candidate = self._normalize_skill_hint(candidate)
                if normalized_candidate and normalized_candidate not in normalized_allowed_skill_ids:
                    normalized_allowed_skill_ids[normalized_candidate] = candidate
            execution_prompt = str(
                args.get("execution_prompt")
                or payload.brief
                or payload.description
                or ""
            ).strip()
            if not execution_prompt:
                await self._block_agent_execute("agent_execute missing execution_prompt")
                return
            for skill_id in skill_hints:
                result_entry: dict[str, Any] = {"skill_id": skill_id}
                resolved_skill_id, resolution_info = self._resolve_skill_hint(
                    hint=skill_id,
                    available_skill_catalog=available_skill_catalog,
                    allowed_skill_ids=allowed_skill_ids,
                    normalized_allowed_skill_ids=normalized_allowed_skill_ids,
                )
                if resolution_info:
                    result_entry.update(resolution_info)
                if resolved_skill_id and resolved_skill_id != skill_id:
                    result_entry["resolved_skill_id"] = resolved_skill_id
                if resolved_skill_id is None:
                    # LLM may emit tool names in required_skills; skip unknown hints
                    # instead of blocking the whole autonomous execution.
                    skipped_skill_hints.append(skill_id)
                    result_entry["status"] = "unknown_hint"
                    skill_load_results.append(result_entry)
                    continue
                load_target_skill_id = resolved_skill_id or skill_id
                if self._load_skill is None:
                    skipped_skill_hints.append(skill_id)
                    result_entry["status"] = "loader_unavailable"
                    skill_load_results.append(result_entry)
                    continue
                try:
                    load_result = await self._load_skill(load_target_skill_id)
                except Exception as exc:
                    result_entry["status"] = "load_exception"
                    result_entry["error"] = f"{type(exc).__name__}: {exc}"
                    skill_load_results.append(result_entry)
                    continue
                normalized_result = str(load_result).strip()
                result_entry["result"] = normalized_result
                normalized_result_lc = normalized_result.lower()
                if normalized_result.startswith("[ERROR]"):
                    result_entry["status"] = "load_error"
                elif normalized_result.startswith("[WARN]"):
                    result_entry["status"] = "load_warn"
                elif normalized_result.startswith("[OK]") and "already loaded" in normalized_result_lc:
                    result_entry["status"] = "already_loaded"
                else:
                    result_entry["status"] = "loaded"
                skill_load_results.append(result_entry)
            skill_hint_stats = {
                "total": len(skill_hints),
                "mapped": sum(
                    1
                    for item in skill_load_results
                    if str(item.get("resolved_skill_id", "")).strip()
                    and str(item.get("resolved_skill_id")) != str(item.get("skill_id"))
                ),
                "unknown": sum(1 for item in skill_load_results if item.get("status") == "unknown_hint"),
                "loaded": sum(
                    1
                    for item in skill_load_results
                    if item.get("status") in {"loaded", "already_loaded"}
                ),
                "errors": sum(
                    1
                    for item in skill_load_results
                    if item.get("status") in {"load_error", "load_exception", "loader_unavailable"}
                ),
            }

            if available_skill_catalog:
                listed_lines: list[str] = []
                for item in available_skill_catalog[:80]:
                    skill_id = item["id"]
                    name = str(item.get("name", "")).strip()
                    description = str(item.get("description", "")).strip().replace("\r", " ").replace("\n", " ")
                    if len(description) > 160:
                        description = f"{description[:157]}..."
                    label = f"{skill_id} ({name})" if name and name != skill_id else skill_id
                    listed_lines.append(f"- {label}: {description}" if description else f"- {label}")
                if len(available_skill_catalog) > 80:
                    listed_lines.append(f"- ... (+{len(available_skill_catalog) - 80} more)")
                listed = "\n".join(listed_lines)
                execution_prompt = (
                    f"{execution_prompt}\n\n"
                    f"[KAIROS_AVAILABLE_SKILLS]\n"
                    f"{listed}\n"
                    "Use skill_load('<skill_id>') with ids from this catalog when you need extra tools. "
                    "Do not invent new skill ids."
                )
            candidate_lines: list[str] = []
            for item in skill_load_results:
                candidates = item.get("candidate_matches")
                if not isinstance(candidates, list) or not candidates:
                    continue
                hint_value = str(item.get("skill_id", "")).strip() or "unknown_hint"
                candidate_lines.append(f"- hint={hint_value}")
                for idx, candidate in enumerate(candidates[:3], start=1):
                    candidate_skill_id = str(candidate.get("skill_id", "")).strip()
                    candidate_name = str(candidate.get("name", "")).strip()
                    candidate_score = candidate.get("score")
                    candidate_desc = str(candidate.get("description", "")).strip()
                    label = (
                        f"{candidate_skill_id} ({candidate_name})"
                        if candidate_name and candidate_name != candidate_skill_id
                        else candidate_skill_id
                    )
                    suffix = f" score={candidate_score}" if candidate_score is not None else ""
                    candidate_lines.append(
                        f"  {idx}. {label}{suffix}{' - ' + candidate_desc if candidate_desc else ''}"
                    )
            if candidate_lines:
                execution_prompt = (
                    f"{execution_prompt}\n\n"
                    f"[KAIROS_SKILL_HINT_CANDIDATES]\n"
                    f"{chr(10).join(candidate_lines)}\n"
                    "When a hint is not loaded yet, choose from these candidates and call skill_load('<skill_id>'). "
                    "Prefer higher-score candidates that match the current subtask."
                )
            trigger_reason = f"agent_execute::{execution_prompt}"
            trigger = KairosTrigger(
                trigger_id=f"agent-exec-{int(datetime.now(UTC).timestamp() * 1000)}",
                kind=TriggerKind.MANUAL,
                reason=trigger_reason,
                created_at=datetime.now(UTC).isoformat(),
                metadata={
                    "required_skills": skill_hints,
                    "skill_hints": skill_hints,
                    "skill_load_results": skill_load_results[:200],
                    "skill_hint_stats": skill_hint_stats,
                    "available_skill_ids": available_skill_ids[:200],
                    "work_id": self.state.document_work_items[0].work_id if self.state.document_work_items else None,
                },
            )
            self.state.pending_triggers.append(trigger)
            self.state.pending_wake_reason = trigger_reason
            self.state.blocked_reason = None
            self.state.planned_actions.append(
                KairosPlannedAction(
                    action_id=f"planned-{trigger.trigger_id}",
                    kind="agent_execute",
                    reason=payload.rationale or "llm_action_payload",
                    payload={
                        "required_skills": skill_hints,
                        "skill_hints": skill_hints,
                        "skipped_skill_hints": skipped_skill_hints,
                        "skill_load_results": skill_load_results[:200],
                        "skill_hint_stats": skill_hint_stats,
                        "available_skill_ids": available_skill_ids[:200],
                        "execution_prompt": execution_prompt,
                        "work_id": self.state.document_work_items[0].work_id if self.state.document_work_items else None,
                        "step_id": self.state.document_work_items[0].current_step if self.state.document_work_items else None,
                    },
                    status="pending",
                    created_at=trigger.created_at,
                )
            )
            await self._record(
                "brief",
                f"agent execute queued with {len(skill_hints)} skill hints"
                + (f", skipped hints: {', '.join(skipped_skill_hints)}" if skipped_skill_hints else "")
                + (f", mapped={skill_hint_stats['mapped']}" if skill_hint_stats["mapped"] else "")
                + (f", loaded={skill_hint_stats['loaded']}" if skill_load_results else "")
                + (f", errors={skill_hint_stats['errors']}" if skill_load_results else "")
                + (f", available skills: {len(available_skill_ids)}" if available_skill_ids else ""),
            )
            return
        if payload.action_kind == "summarize_progress":
            if payload.brief:
                await self._record("brief", payload.brief)
            return

    async def _refresh_verification_state(
        self,
        *,
        task_id: str,
        task_description: str,
        task_status: str,
        summary: str | None,
        artifacts: list[dict[str, Any]],
    ) -> None:
        verifier = getattr(self, "_llm_verifier", None)
        if verifier is None or not self.state.document_work_items:
            return
        try:
            self.state.last_verification_result = await verifier.verify_attempt(
                attempt_id=task_id,
                work_item=self.state.document_work_items[0],
                attempt_summary={
                    "description": task_description,
                    "status": task_status,
                    "result_summary": summary,
                },
                artifacts=artifacts,
            )
            if self.state.last_verification_result.should_replan:
                self.state.last_replan_result = await verifier.replan_from_failure(
                    work_item=self.state.document_work_items[0],
                    verification_result=asdict(self.state.last_verification_result),
                    available_actions=[
                        "update_document",
                        "spawn_dex_task",
                        "agent_execute",
                        "ask_user",
                        "sleep",
                    ],
                )
            else:
                self.state.last_replan_result = KairosReplanResult()
        except Exception as exc:
            await self._record("brief", f"llm verifier fallback active: {type(exc).__name__}: {exc}")
            if not self.state.last_verification_result.verdict:
                self.state.last_verification_result = KairosVerificationResult(
                    attempt_id=task_id,
                    verdict="unknown",
                )
            if not self.state.last_replan_result.replan_reason:
                self.state.last_replan_result = KairosReplanResult(
                    replan_reason="verifier_unavailable",
                    root_cause_hypothesis=str(exc),
                )

    @staticmethod
    def _parse_iso_datetime(value: str | None) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _coerce_timeout_seconds(value: Any) -> int | None:
        if value is None:
            return None
        try:
            normalized = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        if normalized <= 0:
            return None
        return min(normalized, 24 * 60 * 60)

    def _effective_ask_user_timeout_seconds(self, timeout_hint: Any | None = None) -> int | None:
        if timeout_hint is not None:
            hinted = self._coerce_timeout_seconds(timeout_hint)
            if hinted is not None:
                return hinted
        return self._coerce_timeout_seconds(self.state.policy.ask_user_timeout_seconds)

    def _apply_attention_timeout(
        self,
        item: KairosAttentionItem,
        *,
        now: datetime,
        timeout_hint: Any | None = None,
        refresh_timeout: bool = False,
    ) -> None:
        if not refresh_timeout and item.wait_until:
            return
        timeout_seconds = self._effective_ask_user_timeout_seconds(timeout_hint if timeout_hint is not None else item.timeout_seconds)
        item.timeout_seconds = timeout_seconds
        item.wait_until = (
            (now + timedelta(seconds=timeout_seconds)).isoformat()
            if timeout_seconds is not None
            else None
        )
        if refresh_timeout:
            item.auto_resumed_at = None

    async def _auto_resume_waiting_input_if_timed_out(self, now: datetime) -> None:
        if self.state.mode is not KairosMode.WAITING_INPUT:
            return
        expired: list[KairosAttentionItem] = []
        for item in self.state.attention_items:
            if item.status != "pending" or item.auto_resumed_at:
                continue
            if not item.wait_until:
                self._apply_attention_timeout(item, now=now, refresh_timeout=False)
            deadline = self._parse_iso_datetime(item.wait_until)
            if deadline is None:
                continue
            if deadline <= now:
                expired.append(item)

        if not expired:
            return

        now_iso = now.isoformat()
        expired_ids: list[str] = []
        expired_work_ids: set[str] = set()
        for item in expired:
            item.status = "timed_out"
            item.auto_resumed_at = now_iso
            item.updated_at = now_iso
            expired_ids.append(item.attention_id)
            if item.scope_kind == "document_work" and item.work_id:
                expired_work_ids.add(item.work_id)
            if (
                item.scope_kind == "workflow_stage"
                and self.state.active_workflow is not None
                and self.state.active_workflow.workflow_id == item.workflow_id
                and self.state.active_workflow.status == "waiting_input"
            ):
                self.state.active_workflow.status = "active"

        for work_item in self.state.document_work_items:
            if work_item.work_id not in expired_work_ids:
                continue
            work_item.human_input_required = False
            if work_item.status == "blocked":
                work_item.status = "in_progress"

        self.state.blocked_reason = None
        self.state.mode = KairosMode.IDLE
        trigger = KairosTrigger(
            trigger_id=f"ask-user-timeout-{int(now.timestamp() * 1000)}",
            kind=TriggerKind.MANUAL,
            reason=f"ask_user_timeout_auto_resume:{','.join(expired_ids)}",
            created_at=now_iso,
            metadata={
                "attention_ids": expired_ids,
                "auto_resume": True,
            },
        )
        self.state.pending_triggers.insert(0, trigger)
        self.state.pending_wake_reason = trigger.reason
        await self._record(
            "brief",
            f"ask_user timeout reached; auto-resume triggered for {', '.join(expired_ids)}",
        )

    def _upsert_attention_item(
        self,
        *,
        scope_kind: str,
        workflow_id: str | None,
        work_id: str | None,
        stage_id: str | None,
        question: str | None,
        blocked_reason: str | None,
        timeout_seconds: Any | None = None,
        refresh_timeout: bool = False,
    ) -> KairosAttentionItem:
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        for item in self.state.attention_items:
            if item.status != "pending":
                continue
            if (
                item.scope_kind == scope_kind
                and item.workflow_id == workflow_id
                and item.work_id == work_id
                and item.stage_id == stage_id
            ):
                item.question = question or item.question
                item.blocked_reason = blocked_reason or item.blocked_reason
                item.updated_at = now
                self._apply_attention_timeout(
                    item,
                    now=now_dt,
                    timeout_hint=timeout_seconds,
                    refresh_timeout=refresh_timeout,
                )
                return item

        created = KairosAttentionItem(
            attention_id=f"attention-{int(now_dt.timestamp() * 1000)}",
            scope_kind=scope_kind,
            workflow_id=workflow_id,
            work_id=work_id,
            stage_id=stage_id,
            question=question,
            blocked_reason=blocked_reason,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        self._apply_attention_timeout(
            created,
            now=now_dt,
            timeout_hint=timeout_seconds,
            refresh_timeout=True,
        )
        self.state.attention_items.append(created)
        return created

    def _sync_attention_from_planning(self) -> None:
        planning = dict(self.state.last_planning_result or {})
        final_action = dict(planning.get("final_action", {}))
        kind = final_action.get("kind")
        if kind not in {"ask_user", "record_blocked"}:
            return
        payload = dict(final_action.get("payload", {}))
        message = payload.get("message") or self.state.blocked_reason or final_action.get("reason")
        workflow_id = (
            payload.get("workflow_id")
            or planning.get("workflow_id")
            or (self.state.active_workflow.workflow_id if self.state.active_workflow else None)
        )
        stage_id = (
            payload.get("step_id")
            or payload.get("stage_id")
            or planning.get("stage_id")
            or (self.state.active_workflow.current_stage if self.state.active_workflow else None)
        )
        work_id = payload.get("work_id")
        item = self._upsert_attention_item(
            scope_kind="document_work" if work_id else "workflow_stage",
            workflow_id=workflow_id,
            work_id=work_id,
            stage_id=stage_id,
            question=message if kind == "ask_user" else None,
            blocked_reason=message,
            timeout_seconds=payload.get("timeout_seconds") or payload.get("timeout_hint"),
            refresh_timeout=False,
        )
        if work_id:
            for document_item in self.state.document_work_items:
                if document_item.work_id != work_id:
                    continue
                document_item.human_input_required = True
                if document_item.status not in {"completed", "done", "cancelled"}:
                    document_item.status = "blocked"
                if message and message not in document_item.open_questions:
                    document_item.open_questions.insert(0, message)
                break
        elif self.state.active_workflow is not None and self.state.active_workflow.workflow_id == workflow_id:
            self.state.active_workflow.status = "waiting_input"
        self.state.blocked_reason = item.blocked_reason or self.state.blocked_reason

    async def respond_attention(self, attention_id: str, response: str) -> dict[str, Any]:
        target = next((item for item in self.state.attention_items if item.attention_id == attention_id), None)
        if target is None:
            raise ValueError(f"attention item not found: {attention_id}")
        if target.status == "resolved":
            return asdict(target)

        now = datetime.now(UTC).isoformat()
        target.status = "resolved"
        target.response = response
        target.resolved_at = now
        target.updated_at = now
        target.wait_until = None

        if target.scope_kind == "document_work" and target.work_id:
            for item in self.state.document_work_items:
                if item.work_id != target.work_id:
                    continue
                item.human_input_required = False
                if item.status == "blocked":
                    item.status = "in_progress"
                item.open_questions = []
                if item.expected_artifacts:
                    doc_path = Path.cwd() / item.expected_artifacts[0]
                    if doc_path.exists():
                        append_user_guidance_update(
                            doc_path,
                            attention_id=attention_id,
                            response=response,
                        )
                break
        elif (
            target.scope_kind == "workflow_stage"
            and self.state.active_workflow is not None
            and self.state.active_workflow.workflow_id == target.workflow_id
            and self.state.active_workflow.status == "waiting_input"
        ):
            self.state.active_workflow.status = "active"

        has_pending_for_scope = any(
            item.status == "pending"
            and item.scope_kind == target.scope_kind
            and item.workflow_id == target.workflow_id
            and item.work_id == target.work_id
            and item.stage_id == target.stage_id
            for item in self.state.attention_items
        )
        if not has_pending_for_scope and self.state.blocked_reason == target.blocked_reason:
            self.state.blocked_reason = None
            if self.state.mode == KairosMode.WAITING_INPUT:
                self.state.mode = KairosMode.IDLE

        await self._record(
            "brief",
            f"ask_user response recorded: {attention_id} response={response}",
        )
        await self.enqueue_trigger(
            KairosTrigger(
                trigger_id=f"attention-{int(datetime.now(UTC).timestamp())}",
                kind=TriggerKind.MANUAL,
                reason=f"attention_response:{attention_id}",
                created_at=datetime.now(UTC).isoformat(),
                metadata={"attention_id": attention_id, "response": response},
            )
        )
        return asdict(target)

    def get_status(self) -> dict:
        payload = asdict(self.state)
        payload["mode"] = self.state.mode.value
        if self.state.active_trigger is not None:
            payload["active_trigger"]["kind"] = self.state.active_trigger.kind.value
        for item in payload["pending_triggers"]:
            item["kind"] = TriggerKind(item["kind"]).value
        tracked_tasks = [
            {
                "task_id": task.task_id,
                "status": task.status,
                "description": task.description,
                "result": getattr(task, "result", ""),
                "result_summary": getattr(task, "result_summary", None),
                "error_summary": getattr(task, "error_summary", None),
                "created_at": getattr(task, "created_at", None),
                "completed_at": getattr(task, "completed_at", None),
                "log_path": getattr(task, "log_path", None),
            }
            for task in self._dex_bridge.get_tasks(self.state.tracked_dex_task_ids)
        ]
        payload["tracked_dex_tasks"] = tracked_tasks
        payload["active_workflow"] = asdict(self.state.active_workflow) if self.state.active_workflow else None
        payload["planned_actions"] = [asdict(action) for action in self.state.planned_actions]
        payload["blocked_reason"] = self.state.blocked_reason
        stage = self._current_stage()
        payload["task_summaries"] = [self._build_task_summary(task, stage) for task in self._dex_bridge.get_tasks(self.state.tracked_dex_task_ids)] or list(self.state.task_summaries)
        self._continuation_engine._path_exists = self._path_exists
        payload["condition_tree"] = self._build_condition_tree()
        payload["decision_explanation"] = self._build_decision_explanation()
        payload["document_work_items"] = [asdict(item) for item in self.state.document_work_items]
        payload["document_progress"] = self._build_document_progress_view()
        payload["pending_requirements"] = [
            {
                "work_id": item.work_id,
                "goal": item.goal,
                "status": item.status,
                "ask_user": item.human_input_required,
                "open_questions": list(item.open_questions),
                "source_doc": (item.expected_artifacts[0] if item.expected_artifacts else (item.source_docs[0] if item.source_docs else None)),
            }
            for item in self.state.document_work_items
            if item.current_step == "requirements" and item.status not in {"completed", "done", "cancelled"}
        ]
        payload["unfinished_work_items"] = list(payload.get("unfinished_work_items", []))
        payload["proactive_candidates"] = list(payload.get("proactive_candidates", []))
        payload["last_proactive_scan"] = dict(payload.get("last_proactive_scan", {}))
        payload["last_guardrail_block"] = dict(payload.get("last_guardrail_block", {}))
        payload["last_planning_result"] = dict(payload.get("last_planning_result", {}))
        payload["current_understanding"] = asdict(self.state.current_understanding)
        payload["current_execution_plan"] = asdict(self.state.current_execution_plan)
        payload["current_action_payload"] = asdict(self.state.current_action_payload)
        payload["last_verification_result"] = asdict(self.state.last_verification_result)
        payload["last_replan_result"] = asdict(self.state.last_replan_result)
        return payload

    async def _record_planning_transition(self, previous_planning_snapshot: dict[str, Any]) -> None:
        previous_winner = dict(previous_planning_snapshot.get("selected_candidate", {}))
        current_winner = dict(self.state.last_planning_result.get("selected_candidate", {}))
        previous_candidate_id = previous_winner.get("candidate_id")
        current_candidate_id = current_winner.get("candidate_id")
        previous_action = previous_winner.get("action")
        current_action = current_winner.get("action")

        if not current_action:
            self.state.last_planning_result["replan"] = {"changed": False}
            return

        special_actions = {"ask_user", "record_blocked", "sleep_until_signal", "create_follow_up"}
        changed = bool(previous_candidate_id and current_candidate_id and previous_candidate_id != current_candidate_id)
        if changed:
            self.state.last_planning_result["replan"] = {
                "changed": True,
                "previous_winner": previous_winner,
                "current_winner": current_winner,
            }
            await self._record(
                "brief",
                f"Re-plan: {previous_action or 'none'} -> {current_action} workflow_id={self.state.active_workflow.workflow_id if self.state.active_workflow else 'unknown'} stage_id={self.state.active_workflow.current_stage if self.state.active_workflow else 'unknown'}",
            )
            return

        self.state.last_planning_result["replan"] = {"changed": False}
        if current_action in special_actions and previous_action != current_action:
            await self._record(
                "brief",
                f"Selected winner: {current_action} workflow_id={self.state.active_workflow.workflow_id if self.state.active_workflow else 'unknown'} stage_id={self.state.active_workflow.current_stage if self.state.active_workflow else 'unknown'}",
            )

    async def _run_loop(self) -> None:
        try:
            while self.state.running:
                await self.tick_once()
                self._wake_event.clear()
                try:
                    await asyncio.wait_for(self._wake_event.wait(), timeout=self._tick_interval_seconds)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise

    async def _execute_regular_trigger(self, trigger: KairosTrigger) -> None:
        self.state.active_trigger = trigger
        self.state.pending_wake_reason = None
        self.state.busy = True
        self.state.mode = KairosMode.RUNNING
        await self._persist()
        await self._record("brief", f"kairos turn started: {trigger.kind.value}:{trigger.reason}")
        try:
            await self._run_turn(trigger.reason)
        finally:
            self.state.busy = False
            self.state.active_trigger = None
            if self.state.running:
                self.state.mode = KairosMode.SLEEPING
                self.state.sleep_until = (
                    datetime.now(UTC) + timedelta(seconds=self._tick_interval_seconds)
                ).isoformat()
            else:
                self.state.mode = KairosMode.STOPPED
                self.state.sleep_until = None
            await self._persist()
            await self._record("brief", f"kairos turn finished: {trigger.kind.value}:{trigger.reason}")

    async def _execute_internal_trigger(self, trigger: KairosTrigger) -> None:
        self.state.active_trigger = trigger
        self.state.pending_wake_reason = None
        self.state.busy = True
        self.state.mode = KairosMode.RUNNING
        await self._persist()
        await self._record("brief", f"kairos internal action started: {trigger.reason}")
        try:
            created = await self._create_follow_up_task(trigger.reason, trigger.metadata)
            if created and created.get("id") and trigger.metadata.get("description"):
                await self.register_dex_task(created["id"], trigger.metadata["description"])
        finally:
            self.state.busy = False
            self.state.active_trigger = None
            if self.state.running:
                if self.state.tracked_dex_task_ids:
                    self.state.mode = KairosMode.HANDOFF
                    self.state.sleep_until = None
                else:
                    self.state.mode = KairosMode.SLEEPING
                    self.state.sleep_until = (
                        datetime.now(UTC) + timedelta(seconds=self._tick_interval_seconds)
                    ).isoformat()
            else:
                self.state.mode = KairosMode.STOPPED
                self.state.sleep_until = None
            await self._persist()
            await self._record("brief", f"kairos internal action finished: {trigger.reason}")

    async def _poll_dex(self) -> None:
        remaining = list(self.state.tracked_dex_task_ids)
        if not remaining:
            return

        next_remaining: list[str] = []
        completed_tasks: list[object] = []
        tracked_tasks = self._dex_bridge.get_tasks(remaining)
        for task in tracked_tasks:
            if task.status in {"completed", "failed"}:
                completed_tasks.append(task)
                summary = getattr(task, "result_summary", None) or getattr(task, "error_summary", None)
                message = f"Dex task {task.task_id} {task.status}: {task.description}"
                if summary:
                    message = f"{message} — {summary}"
                stage = self._current_stage()
                self.state.task_summaries = [self._build_task_summary(task, stage)] + [
                    item for item in self.state.task_summaries if item.get("task_id") != task.task_id
                ]
                self.state.task_summaries = self.state.task_summaries[:10]
                await self._record("brief", message)
                workflow = self.state.active_workflow
                if workflow is not None:
                    if workflow.workflow_id == "demo_report_pipeline" and getattr(task, "description", "") == "generate final report" and task.status == "completed":
                        await self._refresh_verification_state(
                            task_id=task.task_id,
                            task_description=task.description,
                            task_status=task.status,
                            summary=summary,
                            artifacts=[
                                {
                                    "artifact": "demo_outputs/report.json",
                                    "exists": self._path_exists("demo_outputs/report.json"),
                                    "usable": self._path_exists("demo_outputs/report.json"),
                                    "note": summary,
                                }
                            ],
                        )
                        workflow.status = "completed"
                        workflow.current_stage = "phase2"
                        if len(workflow.stages) > 1:
                            workflow.stages[1].status = "completed"
                            workflow.stages[1].summary = summary
                        self.state.planned_actions = []
                        self.state.blocked_reason = None
                        self.state.condition_tree = None
                    elif workflow.workflow_id == "todo_delivery_pipeline":
                        alias_map = workflow.metadata.get("task_aliases", {})
                        for stage in workflow.stages:
                            expected_task_id = stage.task_ids[0] if stage.task_ids else None
                            alias = alias_map.get(stage.stage_id)
                            if task.task_id == expected_task_id or getattr(task, "description", "") == alias:
                                if task.status == "completed":
                                    await self._refresh_verification_state(
                                        task_id=task.task_id,
                                        task_description=task.description,
                                        task_status=task.status,
                                        summary=summary,
                                        artifacts=[
                                            {
                                                "artifact": path,
                                                "exists": self._path_exists(path),
                                                "usable": self._path_exists(path),
                                                "note": summary,
                                            }
                                            for path in stage.artifacts
                                        ],
                                    )
                                    stage.status = "completed"
                                    stage.summary = summary
                                    workflow.current_stage = stage.stage_id
                                    completed_ids = set(workflow.metadata.get("completed_task_ids", []))
                                    completed_ids.add(task.task_id)
                                    completed_ids.add(getattr(task, "description", ""))
                                    workflow.metadata["completed_task_ids"] = sorted(completed_ids)
                                    if stage.stage_id == "verification":
                                        verification_result = workflow.metadata.get("verification_result")
                                        if verification_result is None:
                                            smoke_path = Path("demo_delivery/todo_app/smoke_check.json")
                                            if smoke_path.exists():
                                                verification_result = json.loads(
                                                    smoke_path.read_text(encoding="utf-8")
                                                )
                                                workflow.metadata["verification_result"] = verification_result
                                            else:
                                                verification_result = {}
                                        if verification_result.get("ready") is False:
                                            workflow.status = "waiting_input"
                                            self.state.blocked_reason = "verification checks failed for todo delivery report"
                                            self.state.condition_tree = {
                                                "stage_id": "verification",
                                                "stage_label": "verification",
                                                "satisfied": [
                                                    {"kind": "artifact", "target": path, "reason": None}
                                                    for path in stage.artifacts
                                                    if self._path_exists(path)
                                                ],
                                                "missing": [
                                                    {
                                                        "kind": "artifact",
                                                        "target": path,
                                                        "reason": self.state.blocked_reason,
                                                    }
                                                    for path in stage.artifacts
                                                    if not self._path_exists(path)
                                                ],
                                                "failed_checks": list(verification_result.get("failures", [])),
                                            }
                                    if stage.stage_id == "delivery_report":
                                        workflow.status = "completed"
                                        self.state.planned_actions = []
                                        self.state.blocked_reason = None
                                        self.state.condition_tree = None
                                elif task.status == "failed":
                                    stage.status = "failed"
                                    workflow.status = "waiting_input"
                                    self.state.blocked_reason = f"todo pipeline task failed: {task.description}"
                                break
            else:
                next_remaining.append(task.task_id)

        self.state.tracked_dex_task_ids = next_remaining
        if completed_tasks and self.state.active_workflow is not None:
            if self.state.policy.llm_only_decision_enabled:
                decisions = await self._evaluate_after_dex_poll_with_llm_only(
                    completed_tasks=completed_tasks,
                    tracked_tasks=tracked_tasks,
                )
            else:
                decisions = self._continuation_engine.evaluate_after_dex_poll(
                    self.state,
                    completed_tasks=completed_tasks,
                    tracked_tasks=tracked_tasks,
                )
            self.state.pending_triggers.extend(self._continuation_engine.apply_decisions(self.state, decisions))

        if next_remaining and self.state.running and not self.state.busy:
            self.state.mode = KairosMode.HANDOFF
        elif not next_remaining and self.state.running and not self.state.busy and self.state.mode == KairosMode.HANDOFF:
            self.state.mode = KairosMode.IDLE
        await self._persist()

    async def _evaluate_after_dex_poll_with_llm_only(
        self,
        *,
        completed_tasks: list[object],
        tracked_tasks: list[object],
    ) -> list[ContinuationDecision]:
        workflow = self.state.active_workflow
        if workflow is None:
            return []
        planner = getattr(self, "_llm_planner", None)
        if planner is None:
            self.state.blocked_reason = "llm planner unavailable in llm-only mode"
            self.state.last_planning_result = {
                "ts": datetime.now(UTC).isoformat(),
                "goal": workflow.goal,
                "workflow_id": workflow.workflow_id,
                "stage_id": workflow.current_stage,
                "candidates_considered": [],
                "selected_candidate": {
                    "candidate_id": f"{workflow.workflow_id}:{workflow.current_stage or 'unknown'}:blocked",
                    "action": "blocked",
                    "tier": "high",
                    "priority": 100,
                    "selected": True,
                    "reason": self.state.blocked_reason,
                },
                "rejected_candidates": [],
                "final_action": {
                    "kind": "record_blocked",
                    "reason": "llm_unavailable",
                    "payload": {
                        "workflow_id": workflow.workflow_id,
                        "stage_id": workflow.current_stage,
                        "message": self.state.blocked_reason,
                    },
                },
                "policy_note": "llm-only mode blocks progress when planner is unavailable",
            }
            return []

        default_description = "generate final report" if workflow.workflow_id == "demo_report_pipeline" else "generate todo delivery report"
        required_artifacts: list[dict[str, Any]] = []
        for stage in workflow.stages:
            if workflow.workflow_id == "todo_delivery_pipeline" and stage.stage_id == "delivery_report":
                break
            if workflow.workflow_id == "demo_report_pipeline" and stage.stage_id == "phase2":
                break
            for artifact in stage.artifacts:
                required_artifacts.append(
                    {
                        "artifact": artifact,
                        "exists": self._path_exists(artifact),
                    }
                )
        tracked_payload = [
            {
                "task_id": task.task_id,
                "status": task.status,
                "description": task.description,
                "result_summary": getattr(task, "result_summary", None),
            }
            for task in tracked_tasks
        ]
        completed_ids = set(workflow.metadata.get("completed_task_ids", []))
        for task in completed_tasks:
            if getattr(task, "status", None) == "completed":
                completed_ids.add(task.task_id)
                description = getattr(task, "description", None)
                if description:
                    completed_ids.add(description)
        workflow.metadata["completed_task_ids"] = sorted(completed_ids)
        verification_result = dict(workflow.metadata.get("verification_result") or {})
        decision = await planner.plan_follow_up_action(
            workflow_id=workflow.workflow_id,
            workflow_status=workflow.status,
            current_stage=workflow.current_stage,
            blocked_reason=self.state.blocked_reason,
            completed_task_ids=sorted(completed_ids),
            required_artifacts=required_artifacts,
            verification_result=verification_result,
            tracked_tasks=tracked_payload,
            default_follow_up_description=default_description,
        )

        action = decision.get("action")
        reason = decision.get("reason") or "llm_follow_up_decision"
        message = decision.get("message")
        description = (decision.get("description") or default_description).strip()
        if action == "create_follow_up":
            payload = {"workflow_id": workflow.workflow_id, "description": description}
            if any(action.kind == "create_dex_task" and action.payload == payload for action in self.state.planned_actions):
                return []
            self.state.blocked_reason = None
            self.state.last_planning_result = {
                "ts": datetime.now(UTC).isoformat(),
                "goal": workflow.goal,
                "workflow_id": workflow.workflow_id,
                "stage_id": workflow.current_stage,
                "candidates_considered": [],
                "selected_candidate": {
                    "candidate_id": f"{workflow.workflow_id}:{workflow.current_stage or 'unknown'}:create_follow_up",
                    "action": "create_follow_up",
                    "tier": "medium",
                    "priority": 60,
                    "selected": True,
                    "reason": reason,
                    "payload": payload,
                },
                "rejected_candidates": [],
                "final_action": {
                    "kind": "create_dex_task",
                    "reason": reason,
                    "payload": payload,
                },
                "policy_note": "llm-only winner",
            }
            return [ContinuationDecision(kind="create_dex_task", reason=reason, payload=payload)]
        if action == "ask_user":
            self.state.blocked_reason = message or reason
            workflow.status = "waiting_input"
            self.state.last_planning_result = {
                "ts": datetime.now(UTC).isoformat(),
                "goal": workflow.goal,
                "workflow_id": workflow.workflow_id,
                "stage_id": workflow.current_stage,
                "candidates_considered": [],
                "selected_candidate": {
                    "candidate_id": f"{workflow.workflow_id}:{workflow.current_stage or 'unknown'}:ask_user",
                    "action": "ask_user",
                    "tier": "high",
                    "priority": 100,
                    "selected": True,
                    "reason": self.state.blocked_reason,
                },
                "rejected_candidates": [],
                "final_action": {
                    "kind": "ask_user",
                    "reason": reason,
                    "payload": {
                        "workflow_id": workflow.workflow_id,
                        "stage_id": workflow.current_stage,
                        "message": self.state.blocked_reason,
                    },
                },
                "policy_note": "llm-only winner",
            }
            return []
        self.state.last_planning_result = {
            "ts": datetime.now(UTC).isoformat(),
            "goal": workflow.goal,
            "workflow_id": workflow.workflow_id,
            "stage_id": workflow.current_stage,
            "candidates_considered": [],
            "selected_candidate": {
                "candidate_id": f"{workflow.workflow_id}:{workflow.current_stage or 'unknown'}:sleep",
                "action": "sleep",
                "tier": "low",
                "priority": 10,
                "selected": True,
                "reason": reason,
            },
            "rejected_candidates": [],
            "final_action": {
                "kind": "sleep_until_signal",
                "reason": reason,
                "payload": {
                    "workflow_id": workflow.workflow_id,
                    "stage_id": workflow.current_stage,
                },
            },
            "policy_note": "llm-only winner",
        }
        return []

    async def _record(self, kind: str, message: str) -> None:
        event = KairosEvent(kind=kind, message=message, ts=datetime.now(UTC).isoformat())
        self.state.push_event(event)
        await self._emit_event(event)
        await self._append_log(event)
        await self._persist()

    async def _persist(self) -> None:
        await self._save_state(self.state)

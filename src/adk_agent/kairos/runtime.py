from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable

from .continuation import ContinuationEngine
from .models import KairosEvent, KairosMode, KairosSchedule, KairosState, KairosTrigger, TriggerKind
from .scheduler import KairosScheduler
from .workflows import demo_report_pipeline, todo_delivery_pipeline


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

    async def tick_once(self) -> None:
        async with self._lock:
            now = datetime.now(UTC)
            self.state.last_tick_at = now.isoformat()
            self._scheduler.seed_schedules(self.state, now)
            due_triggers = self._scheduler.collect_due_triggers(self.state, now)
            self.state.pending_triggers.extend(due_triggers)
            ready_trigger_count = len(self.state.pending_triggers)
            self._continuation_engine._path_exists = self._path_exists
            await self._poll_dex()

            if not self.state.running:
                return

            if self._is_worker_busy():
                await self._record("status", "worker busy, skip kairos tick")
                return

            if self.state.pending_triggers and not self.state.busy and len(self.state.pending_triggers) == ready_trigger_count:
                trigger = self.state.pending_triggers.pop(0)
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
        return payload

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

    async def _record(self, kind: str, message: str) -> None:
        event = KairosEvent(kind=kind, message=message, ts=datetime.now(UTC).isoformat())
        self.state.push_event(event)
        await self._emit_event(event)
        await self._append_log(event)
        await self._persist()

    async def _persist(self) -> None:
        await self._save_state(self.state)

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable

from .models import KairosEvent, KairosMode, KairosSchedule, KairosState, KairosTrigger, TriggerKind
from .scheduler import KairosScheduler


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

    # --- Trigger queue ---

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

    # --- Schedule management ---

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

    # --- Dex handoff ---

    async def register_dex_task(self, task_id: str, description: str) -> None:
        if task_id not in self.state.tracked_dex_task_ids:
            self.state.tracked_dex_task_ids.append(task_id)
        if self.state.running and not self.state.busy:
            self.state.mode = KairosMode.HANDOFF
        await self._persist()
        await self._record("brief", f"dex handoff registered: {task_id} {description}")

    # --- Tick ---

    async def tick_once(self) -> None:
        async with self._lock:
            now = datetime.now(UTC)
            self.state.last_tick_at = now.isoformat()

            # Collect due schedule triggers
            self._scheduler.seed_schedules(self.state, now)
            due_triggers = self._scheduler.collect_due_triggers(self.state, now)
            self.state.pending_triggers.extend(due_triggers)

            # Poll Dex tasks
            await self._poll_dex()

            if not self.state.running:
                return

            if self._is_worker_busy():
                await self._record("status", "worker busy, skip kairos tick")
                return

            if self.state.pending_triggers and not self.state.busy:
                trigger = self.state.pending_triggers.pop(0)
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
            elif self.state.pending_wake_reason and not self.state.busy:
                # Phase 1 compat: pending_wake_reason without trigger
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

    def get_status(self) -> dict:
        payload = asdict(self.state)
        payload["mode"] = self.state.mode.value
        if self.state.active_trigger is not None:
            payload["active_trigger"]["kind"] = self.state.active_trigger.kind.value
        for item in payload["pending_triggers"]:
            item["kind"] = TriggerKind(item["kind"]).value
        return payload

    # --- Internal ---

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

    async def _poll_dex(self) -> None:
        remaining = list(self.state.tracked_dex_task_ids)
        if not remaining:
            return

        next_remaining: list[str] = []
        for task in self._dex_bridge.get_tasks(remaining):
            if task.status in {"completed", "failed"}:
                await self._record(
                    "brief",
                    f"Dex task {task.task_id} {task.status}: {task.description}",
                )
            else:
                next_remaining.append(task.task_id)

        self.state.tracked_dex_task_ids = next_remaining
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

from __future__ import annotations

from datetime import UTC, datetime

from croniter import croniter

from .models import KairosState, KairosTrigger, TriggerKind


class KairosScheduler:
    def _next_fire_at(self, cron_expr: str, now: datetime) -> str:
        return croniter(cron_expr, now).get_next(datetime).astimezone(UTC).isoformat()

    def seed_schedules(self, state: KairosState, now: datetime) -> None:
        for schedule in state.schedules:
            if schedule.enabled and schedule.next_fire_at is None:
                schedule.next_fire_at = self._next_fire_at(schedule.cron, now)

    def collect_due_triggers(self, state: KairosState, now: datetime) -> list[KairosTrigger]:
        due: list[KairosTrigger] = []
        for schedule in state.schedules:
            if not schedule.enabled or not schedule.next_fire_at:
                continue
            if datetime.fromisoformat(schedule.next_fire_at) <= now:
                due.append(
                    KairosTrigger(
                        trigger_id=f"schedule-{schedule.schedule_id}-{int(now.timestamp())}",
                        kind=TriggerKind.SCHEDULE,
                        reason=schedule.reason,
                        created_at=now.isoformat(),
                        metadata={"schedule_id": schedule.schedule_id},
                    )
                )
                schedule.next_fire_at = self._next_fire_at(schedule.cron, now)
        return due

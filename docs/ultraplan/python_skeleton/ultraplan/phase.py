from __future__ import annotations

from .models import UltraplanPhase


class UltraplanPhaseResolver:
    def resolve(self, *, scanner, session_status: str | None, new_events: list[dict]) -> UltraplanPhase:
        quiet_idle = session_status in {"idle", "requires_action"} and len(new_events) == 0
        if scanner.has_pending_plan:
            return UltraplanPhase.PLAN_READY
        if quiet_idle:
            return UltraplanPhase.NEEDS_INPUT
        return UltraplanPhase.RUNNING

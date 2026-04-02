from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class KairosMode(str, Enum):
    STOPPED = "stopped"
    IDLE = "idle"
    RUNNING = "running"
    SLEEPING = "sleeping"


@dataclass
class KairosEvent:
    kind: str
    message: str
    ts: str
    level: str = "normal"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KairosState:
    enabled: bool = False
    running: bool = False
    busy: bool = False
    mode: KairosMode = KairosMode.STOPPED
    sleep_until: str | None = None
    pending_wake_reason: str | None = None
    tracked_dex_task_ids: list[str] = field(default_factory=list)
    recent_events: list[KairosEvent] = field(default_factory=list)

    def push_event(self, event: KairosEvent, limit: int = 20) -> None:
        self.recent_events.append(event)
        if len(self.recent_events) > limit:
            self.recent_events = self.recent_events[-limit:]


def load_kairos_state(raw: dict[str, Any] | None) -> KairosState:
    if not raw:
        return KairosState()
    return KairosState(
        enabled=bool(raw.get("enabled", False)),
        running=bool(raw.get("running", False)),
        busy=bool(raw.get("busy", False)),
        mode=KairosMode(raw.get("mode", KairosMode.STOPPED.value)),
        sleep_until=raw.get("sleep_until"),
        pending_wake_reason=raw.get("pending_wake_reason"),
        tracked_dex_task_ids=list(raw.get("tracked_dex_task_ids", [])),
        recent_events=[KairosEvent(**item) for item in raw.get("recent_events", [])],
    )


def dump_kairos_state(state: KairosState) -> dict[str, Any]:
    payload = asdict(state)
    payload["mode"] = state.mode.value
    return payload

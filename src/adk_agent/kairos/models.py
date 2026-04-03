from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class KairosMode(str, Enum):
    STOPPED = "stopped"
    IDLE = "idle"
    RUNNING = "running"
    SLEEPING = "sleeping"
    HANDOFF = "handoff"
    WAITING_INPUT = "waiting_input"


class TriggerKind(str, Enum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    DEX = "dex"
    INTERNAL = "internal"


@dataclass
class KairosEvent:
    kind: str
    message: str
    ts: str
    level: str = "normal"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KairosTrigger:
    trigger_id: str
    kind: TriggerKind
    reason: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KairosSchedule:
    schedule_id: str
    cron: str
    reason: str
    enabled: bool = True
    next_fire_at: str | None = None


@dataclass
class KairosState:
    enabled: bool = False
    running: bool = False
    busy: bool = False
    mode: KairosMode = KairosMode.STOPPED
    sleep_until: str | None = None
    last_tick_at: str | None = None
    pending_wake_reason: str | None = None
    active_trigger: KairosTrigger | None = None
    pending_triggers: list[KairosTrigger] = field(default_factory=list)
    tracked_dex_task_ids: list[str] = field(default_factory=list)
    schedules: list[KairosSchedule] = field(default_factory=list)
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
        last_tick_at=raw.get("last_tick_at"),
        pending_wake_reason=raw.get("pending_wake_reason"),
        active_trigger=_load_trigger(raw.get("active_trigger")),
        pending_triggers=[_load_trigger(item) for item in raw.get("pending_triggers", []) if item],
        tracked_dex_task_ids=list(raw.get("tracked_dex_task_ids", [])),
        schedules=[KairosSchedule(**item) for item in raw.get("schedules", [])],
        recent_events=[KairosEvent(**item) for item in raw.get("recent_events", [])],
    )


def _load_trigger(raw: dict[str, Any] | None) -> KairosTrigger | None:
    if not raw:
        return None
    return KairosTrigger(
        trigger_id=raw["trigger_id"],
        kind=TriggerKind(raw["kind"]),
        reason=raw["reason"],
        created_at=raw["created_at"],
        metadata=raw.get("metadata", {}),
    )


def dump_kairos_state(state: KairosState) -> dict[str, Any]:
    payload = asdict(state)
    payload["mode"] = state.mode.value
    if state.active_trigger is not None:
        payload["active_trigger"]["kind"] = state.active_trigger.kind.value
    for item in payload["pending_triggers"]:
        item["kind"] = TriggerKind(item["kind"]).value
    return payload

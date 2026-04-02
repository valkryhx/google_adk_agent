from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class UltraplanPhase(str, Enum):
    RUNNING = "running"
    NEEDS_INPUT = "needs_input"
    PLAN_READY = "plan_ready"


class ExecutionTarget(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"


class ScanKind(str, Enum):
    APPROVED = "approved"
    TELEPORT = "teleport"
    REJECTED = "rejected"
    PENDING = "pending"
    TERMINATED = "terminated"
    UNCHANGED = "unchanged"


class PollFailReason(str, Enum):
    TERMINATED = "terminated"
    TIMEOUT_PENDING = "timeout_pending"
    TIMEOUT_NO_PLAN = "timeout_no_plan"
    EXTRACT_MARKER_MISSING = "extract_marker_missing"
    NETWORK_OR_UNKNOWN = "network_or_unknown"
    STOPPED = "stopped"


@dataclass(slots=True)
class PendingChoice:
    plan: str
    session_id: str
    task_id: str


@dataclass(slots=True)
class LaunchPending:
    blurb: str


@dataclass(slots=True)
class UltraplanTaskState:
    task_id: str
    session_id: str
    session_url: str
    status: str = "running"
    phase: UltraplanPhase | None = None
    command: str = ""
    notified: bool = False
    start_time: float = 0.0
    end_time: float | None = None


@dataclass(slots=True)
class UltraplanAppState:
    launching: bool = False
    session_url: str | None = None
    pending_choice: PendingChoice | None = None
    launch_pending: LaunchPending | None = None
    is_ultraplan_mode: bool | None = None
    tasks: dict[str, UltraplanTaskState] = field(default_factory=dict)


@dataclass(slots=True)
class RemoteSessionRef:
    session_id: str
    title: str
    url: str


@dataclass(slots=True)
class PollRemoteSessionResponse:
    new_events: list[dict[str, Any]]
    last_event_id: str | None
    branch: str | None = None
    session_status: str | None = None


@dataclass(slots=True)
class PollResult:
    plan: str
    reject_count: int
    execution_target: ExecutionTarget


@dataclass(slots=True)
class ScanResult:
    kind: ScanKind
    plan: str | None = None
    rejected_id: str | None = None
    terminated_subtype: str | None = None


@dataclass(slots=True)
class LaunchUltraplanRequest:
    blurb: str
    seed_plan: str | None = None


@dataclass(slots=True)
class LaunchUltraplanResponse:
    accepted: bool
    message: str
    session_url: str | None = None
    task_id: str | None = None

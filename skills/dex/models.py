from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class DexTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class DexTaskArtifact:
    kind: str
    path: str
    label: str


@dataclass
class DexTaskEvent:
    kind: str
    message: str
    ts: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DexTask:
    id: str
    user_id: str | None
    description: str
    context: str
    status: DexTaskStatus
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    command: list[str] | None = None
    pid: int | None = None
    exit_code: int | None = None
    result_summary: str | None = None
    error_summary: str | None = None
    artifacts: list[DexTaskArtifact] = field(default_factory=list)
    events: list[DexTaskEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(cls, task_id: str, user_id: str | None, description: str, context: str) -> "DexTask":
        return cls(
            id=task_id,
            user_id=user_id,
            description=description,
            context=context,
            status=DexTaskStatus.PENDING,
            created_at=datetime.now(UTC).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["result"] = self.result_summary or ""
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DexTask":
        return cls(
            id=raw["id"],
            user_id=raw.get("user_id"),
            description=raw.get("description", ""),
            context=raw.get("context", ""),
            status=DexTaskStatus(raw.get("status", DexTaskStatus.PENDING.value)),
            created_at=raw.get("created_at", ""),
            started_at=raw.get("started_at"),
            completed_at=raw.get("completed_at"),
            command=list(raw["command"]) if raw.get("command") else None,
            pid=raw.get("pid"),
            exit_code=raw.get("exit_code"),
            result_summary=raw.get("result_summary") or raw.get("result"),
            error_summary=raw.get("error_summary"),
            artifacts=[DexTaskArtifact(**item) for item in raw.get("artifacts", [])],
            events=[DexTaskEvent(**item) for item in raw.get("events", [])],
            metadata=dict(raw.get("metadata", {})),
        )

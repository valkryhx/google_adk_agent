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
class KairosWorkflowStage:
    stage_id: str
    label: str
    status: str
    task_ids: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    summary: str | None = None


@dataclass
class KairosWorkflow:
    workflow_id: str
    goal: str
    status: str
    current_stage: str | None = None
    stages: list[KairosWorkflowStage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KairosPlannedAction:
    action_id: str
    kind: str
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    created_at: str | None = None


@dataclass
class KairosContinuationPolicy:
    max_auto_steps_per_tick: int = 1
    allow_llm_assist_for_brief: bool = True
    require_artifacts_before_follow_up: bool = True
    dedupe_enabled: bool = True
    proactive_scan_enabled: bool = True
    cooldown_seconds: int = 60


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
    active_workflow: KairosWorkflow | None = None
    planned_actions: list[KairosPlannedAction] = field(default_factory=list)
    blocked_reason: str | None = None
    policy: KairosContinuationPolicy = field(default_factory=KairosContinuationPolicy)
    task_summaries: list[dict[str, Any]] = field(default_factory=list)
    decision_explanation: dict[str, Any] = field(
        default_factory=lambda: {
            "why_continued": None,
            "why_stopped": None,
            "missing_requirements": [],
        }
    )
    condition_tree: dict[str, Any] | None = None
    unfinished_work_items: list[dict[str, Any]] = field(default_factory=list)
    proactive_candidates: list[dict[str, Any]] = field(default_factory=list)
    last_proactive_scan: dict[str, Any] = field(default_factory=dict)
    last_guardrail_block: dict[str, Any] = field(default_factory=dict)
    last_planning_result: dict[str, Any] = field(default_factory=dict)
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
        active_workflow=_load_workflow(raw.get("active_workflow")),
        planned_actions=[_load_planned_action(item) for item in raw.get("planned_actions", [])],
        blocked_reason=raw.get("blocked_reason"),
        policy=_load_policy(raw.get("policy")),
        task_summaries=list(raw.get("task_summaries", [])),
        decision_explanation=dict(
            raw.get(
                "decision_explanation",
                {"why_continued": None, "why_stopped": None, "missing_requirements": []},
            )
        ),
        condition_tree=raw.get("condition_tree"),
        unfinished_work_items=list(raw.get("unfinished_work_items", [])),
        proactive_candidates=list(raw.get("proactive_candidates", [])),
        last_proactive_scan=dict(raw.get("last_proactive_scan", {})),
        last_guardrail_block=dict(raw.get("last_guardrail_block", {})),
        last_planning_result=dict(raw.get("last_planning_result", {})),
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


def _load_stage(raw: dict[str, Any]) -> KairosWorkflowStage:
    return KairosWorkflowStage(
        stage_id=raw["stage_id"],
        label=raw["label"],
        status=raw["status"],
        task_ids=list(raw.get("task_ids", [])),
        artifacts=list(raw.get("artifacts", [])),
        summary=raw.get("summary"),
    )


def _load_workflow(raw: dict[str, Any] | None) -> KairosWorkflow | None:
    if not raw:
        return None
    return KairosWorkflow(
        workflow_id=raw["workflow_id"],
        goal=raw["goal"],
        status=raw["status"],
        current_stage=raw.get("current_stage"),
        stages=[_load_stage(item) for item in raw.get("stages", [])],
        metadata=raw.get("metadata", {}),
    )


def _load_planned_action(raw: dict[str, Any]) -> KairosPlannedAction:
    return KairosPlannedAction(
        action_id=raw["action_id"],
        kind=raw["kind"],
        reason=raw["reason"],
        payload=raw.get("payload", {}),
        status=raw.get("status", "pending"),
        created_at=raw.get("created_at"),
    )


def _load_policy(raw: dict[str, Any] | None) -> KairosContinuationPolicy:
    if not raw:
        return KairosContinuationPolicy()
    return KairosContinuationPolicy(
        max_auto_steps_per_tick=raw.get("max_auto_steps_per_tick", 1),
        allow_llm_assist_for_brief=raw.get("allow_llm_assist_for_brief", True),
        require_artifacts_before_follow_up=raw.get("require_artifacts_before_follow_up", True),
        dedupe_enabled=raw.get("dedupe_enabled", True),
        proactive_scan_enabled=raw.get("proactive_scan_enabled", True),
        cooldown_seconds=raw.get("cooldown_seconds", 60),
    )


def dump_kairos_state(state: KairosState) -> dict[str, Any]:
    payload = asdict(state)
    payload["mode"] = state.mode.value
    if state.active_trigger is not None:
        payload["active_trigger"]["kind"] = state.active_trigger.kind.value
    for item in payload["pending_triggers"]:
        item["kind"] = TriggerKind(item["kind"]).value
    return payload

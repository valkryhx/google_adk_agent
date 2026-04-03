from src.adk_agent.kairos.models import (
    KairosEvent,
    KairosMode,
    KairosState,
    dump_kairos_state,
    load_kairos_state,
)

# === Phase 1 existing tests ===


def test_load_empty_state_uses_defaults():
    state = load_kairos_state(None)

    assert state.enabled is False
    assert state.mode is KairosMode.STOPPED
    assert state.tracked_dex_task_ids == []
    assert state.recent_events == []


def test_dump_round_trip_preserves_recent_events():
    original = KairosState(
        enabled=True,
        running=True,
        mode=KairosMode.SLEEPING,
        sleep_until="2026-04-02T12:00:00",
        tracked_dex_task_ids=["abc12345"],
        recent_events=[
            KairosEvent(kind="brief", message="runtime started", ts="2026-04-02T11:59:00")
        ],
    )

    dumped = dump_kairos_state(original)
    restored = load_kairos_state(dumped)

    assert restored.enabled is True
    assert restored.mode is KairosMode.SLEEPING
    assert restored.tracked_dex_task_ids == ["abc12345"]
    assert restored.recent_events[0].message == "runtime started"


def test_recent_events_are_trimmed_to_last_20():
    state = KairosState(enabled=True, running=True, mode=KairosMode.IDLE)
    for idx in range(25):
        state.push_event(
            KairosEvent(kind="status", message=f"event-{idx}", ts=f"2026-04-02T12:00:{idx:02d}")
        )

    assert len(state.recent_events) == 20
    assert state.recent_events[0].message == "event-5"
    assert state.recent_events[-1].message == "event-24"


# === Phase 2 new tests ===


def test_phase2_imports_exist():
    """Verify Phase 2 types are importable."""
    from src.adk_agent.kairos.models import (
        KairosSchedule,
        KairosTrigger,
        TriggerKind,
    )

    assert TriggerKind.MANUAL.value == "manual"
    assert TriggerKind.SCHEDULE.value == "schedule"
    assert TriggerKind.DEX.value == "dex"
    assert TriggerKind.INTERNAL.value == "internal"


def test_new_kairos_modes_exist():
    """Phase 2 adds HANDOFF and WAITING_INPUT modes."""
    assert KairosMode.HANDOFF.value == "handoff"
    assert KairosMode.WAITING_INPUT.value == "waiting_input"


def test_load_legacy_state_fills_phase2_defaults():
    """Loading a Phase 1 state dict should fill Phase 2 fields with defaults."""
    state = load_kairos_state({"enabled": True, "running": True, "mode": "idle"})

    assert state.enabled is True
    assert state.mode is KairosMode.IDLE
    assert state.pending_triggers == []
    assert state.schedules == []
    assert state.active_trigger is None
    assert state.last_tick_at is None


def test_dump_round_trip_preserves_schedule_and_trigger():
    """Full round-trip with Phase 2 fields."""
    from src.adk_agent.kairos.models import (
        KairosSchedule,
        KairosTrigger,
        TriggerKind,
    )

    state = KairosState(
        enabled=True,
        running=True,
        mode=KairosMode.HANDOFF,
        last_tick_at="2026-04-02T12:00:00+00:00",
        active_trigger=KairosTrigger(
            trigger_id="manual-1",
            kind=TriggerKind.MANUAL,
            reason="manual_smoke",
            created_at="2026-04-02T12:00:00+00:00",
        ),
        schedules=[
            KairosSchedule(
                schedule_id="morning-checkin",
                cron="0 9 * * *",
                reason="morning_checkin",
                enabled=True,
                next_fire_at="2026-04-03T09:00:00+00:00",
            )
        ],
        recent_events=[
            KairosEvent(kind="brief", message="runtime started", ts="2026-04-02T11:59:00+00:00")
        ],
    )

    restored = load_kairos_state(dump_kairos_state(state))

    assert restored.mode is KairosMode.HANDOFF
    assert restored.active_trigger is not None
    assert restored.active_trigger.kind is TriggerKind.MANUAL
    assert restored.active_trigger.trigger_id == "manual-1"
    assert restored.active_trigger.reason == "manual_smoke"
    assert restored.schedules[0].schedule_id == "morning-checkin"
    assert restored.schedules[0].next_fire_at == "2026-04-03T09:00:00+00:00"
    assert restored.last_tick_at == "2026-04-02T12:00:00+00:00"


def test_dump_round_trip_with_pending_triggers():
    """Multiple pending triggers survive serialization."""
    from src.adk_agent.kairos.models import KairosTrigger, TriggerKind

    state = KairosState(
        enabled=True,
        running=True,
        mode=KairosMode.IDLE,
        pending_triggers=[
            KairosTrigger(
                trigger_id="sched-1",
                kind=TriggerKind.SCHEDULE,
                reason="morning",
                created_at="2026-04-02T09:00:00+00:00",
            ),
            KairosTrigger(
                trigger_id="dex-1",
                kind=TriggerKind.DEX,
                reason="task_done",
                created_at="2026-04-02T09:01:00+00:00",
                metadata={"task_id": "abc"},
            ),
        ],
    )

    restored = load_kairos_state(dump_kairos_state(state))

    assert len(restored.pending_triggers) == 2
    assert restored.pending_triggers[0].kind is TriggerKind.SCHEDULE
    assert restored.pending_triggers[1].kind is TriggerKind.DEX
    assert restored.pending_triggers[1].metadata == {"task_id": "abc"}


def test_dump_round_trip_with_multiple_schedules():
    """Multiple schedules survive serialization."""
    from src.adk_agent.kairos.models import KairosSchedule

    state = KairosState(
        enabled=True,
        running=True,
        mode=KairosMode.IDLE,
        schedules=[
            KairosSchedule(
                schedule_id="morning",
                cron="0 9 * * *",
                reason="morning_checkin",
                enabled=True,
                next_fire_at="2026-04-03T09:00:00+00:00",
            ),
            KairosSchedule(
                schedule_id="evening",
                cron="0 21 * * *",
                reason="evening_review",
                enabled=False,
                next_fire_at=None,
            ),
        ],
    )

    restored = load_kairos_state(dump_kairos_state(state))

    assert len(restored.schedules) == 2
    assert restored.schedules[0].schedule_id == "morning"
    assert restored.schedules[0].enabled is True
    assert restored.schedules[1].schedule_id == "evening"
    assert restored.schedules[1].enabled is False
    assert restored.schedules[1].next_fire_at is None


def test_trigger_kind_enum_values_are_strings():
    """TriggerKind values should be plain strings for JSON serialization."""
    from src.adk_agent.kairos.models import TriggerKind

    for kind in TriggerKind:
        assert isinstance(kind.value, str)


def test_kairos_trigger_metadata_defaults_to_empty_dict():
    """KairosTrigger metadata should default to empty dict."""
    from src.adk_agent.kairos.models import KairosTrigger, TriggerKind

    trigger = KairosTrigger(
        trigger_id="t1",
        kind=TriggerKind.MANUAL,
        reason="test",
        created_at="2026-04-02T12:00:00+00:00",
    )
    assert trigger.metadata == {}


def test_kairos_schedule_next_fire_at_defaults_to_none():
    """KairosSchedule next_fire_at should default to None."""
    from src.adk_agent.kairos.models import KairosSchedule

    schedule = KairosSchedule(
        schedule_id="s1",
        cron="0 9 * * *",
        reason="test",
    )
    assert schedule.next_fire_at is None
    assert schedule.enabled is True


def test_dump_with_no_active_trigger():
    """dump should handle None active_trigger cleanly."""
    state = KairosState(
        enabled=True,
        running=True,
        mode=KairosMode.IDLE,
        active_trigger=None,
    )

    dumped = dump_kairos_state(state)
    assert dumped["active_trigger"] is None

    restored = load_kairos_state(dumped)
    assert restored.active_trigger is None


def test_load_state_with_unknown_fields_is_tolerant():
    """Loading state with extra unknown fields should not crash."""
    raw = {
        "enabled": True,
        "running": True,
        "mode": "idle",
        "some_future_field": "value",
    }
    state = load_kairos_state(raw)
    assert state.enabled is True
    assert state.mode is KairosMode.IDLE

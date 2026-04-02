from src.adk_agent.kairos.models import (
    KairosEvent,
    KairosMode,
    KairosState,
    dump_kairos_state,
    load_kairos_state,
)


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

from datetime import UTC, datetime

import pytest

from src.adk_agent.kairos.models import KairosSchedule, KairosState, KairosTrigger, TriggerKind


def test_import_scheduler():
    """Verify scheduler module is importable."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    assert KairosScheduler is not None


def test_seed_schedules_sets_next_fire_at():
    from src.adk_agent.kairos.scheduler import KairosScheduler

    state = KairosState(
        schedules=[
            KairosSchedule(
                schedule_id="morning-checkin",
                cron="*/5 * * * *",
                reason="morning_checkin",
            )
        ]
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    KairosScheduler().seed_schedules(state, now)

    assert state.schedules[0].next_fire_at == "2026-04-02T12:05:00+00:00"


def test_seed_schedules_skips_already_seeded():
    """If next_fire_at is already set, seed should not overwrite it."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    state = KairosState(
        schedules=[
            KairosSchedule(
                schedule_id="existing",
                cron="*/5 * * * *",
                reason="test",
                next_fire_at="2026-04-02T13:00:00+00:00",
            )
        ]
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    KairosScheduler().seed_schedules(state, now)

    assert state.schedules[0].next_fire_at == "2026-04-02T13:00:00+00:00"


def test_seed_schedules_skips_disabled():
    """Disabled schedules should not be seeded."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    state = KairosState(
        schedules=[
            KairosSchedule(
                schedule_id="disabled",
                cron="*/5 * * * *",
                reason="test",
                enabled=False,
            )
        ]
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    KairosScheduler().seed_schedules(state, now)

    assert state.schedules[0].next_fire_at is None


def test_collect_due_triggers_rolls_schedule_forward():
    from src.adk_agent.kairos.scheduler import KairosScheduler

    state = KairosState(
        schedules=[
            KairosSchedule(
                schedule_id="catch-up",
                cron="*/15 * * * *",
                reason="catch_up",
                enabled=True,
                next_fire_at="2026-04-02T12:00:00+00:00",
            )
        ]
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    triggers = KairosScheduler().collect_due_triggers(state, now)

    assert len(triggers) == 1
    assert triggers[0].kind is TriggerKind.SCHEDULE
    assert triggers[0].reason == "catch_up"
    assert "catch-up" in triggers[0].trigger_id
    assert state.schedules[0].next_fire_at == "2026-04-02T12:15:00+00:00"


def test_collect_due_triggers_skips_disabled_schedule():
    from src.adk_agent.kairos.scheduler import KairosScheduler

    state = KairosState(
        schedules=[
            KairosSchedule(
                schedule_id="disabled",
                cron="*/5 * * * *",
                reason="skip_me",
                enabled=False,
                next_fire_at="2026-04-02T12:00:00+00:00",
            )
        ]
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    triggers = KairosScheduler().collect_due_triggers(state, now)

    assert triggers == []
    assert state.schedules[0].next_fire_at == "2026-04-02T12:00:00+00:00"


def test_collect_due_triggers_skips_future_schedule():
    """Schedule whose next_fire_at is in the future should not fire."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    state = KairosState(
        schedules=[
            KairosSchedule(
                schedule_id="future",
                cron="*/5 * * * *",
                reason="not_yet",
                enabled=True,
                next_fire_at="2026-04-02T12:30:00+00:00",
            )
        ]
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    triggers = KairosScheduler().collect_due_triggers(state, now)

    assert triggers == []
    assert state.schedules[0].next_fire_at == "2026-04-02T12:30:00+00:00"


def test_collect_due_triggers_skips_no_next_fire_at():
    """Schedule with no next_fire_at should not fire."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    state = KairosState(
        schedules=[
            KairosSchedule(
                schedule_id="unseeded",
                cron="*/5 * * * *",
                reason="no_fire",
                enabled=True,
                next_fire_at=None,
            )
        ]
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    triggers = KairosScheduler().collect_due_triggers(state, now)

    assert triggers == []


def test_collect_due_multiple_schedules():
    """Multiple due schedules should all fire."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    state = KairosState(
        schedules=[
            KairosSchedule(
                schedule_id="a",
                cron="*/5 * * * *",
                reason="reason_a",
                enabled=True,
                next_fire_at="2026-04-02T12:00:00+00:00",
            ),
            KairosSchedule(
                schedule_id="b",
                cron="*/10 * * * *",
                reason="reason_b",
                enabled=True,
                next_fire_at="2026-04-02T11:50:00+00:00",
            ),
        ]
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    triggers = KairosScheduler().collect_due_triggers(state, now)

    assert len(triggers) == 2
    reasons = {t.reason for t in triggers}
    assert reasons == {"reason_a", "reason_b"}


def test_trigger_id_contains_schedule_id():
    """Generated trigger_id should contain the schedule_id for traceability."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    state = KairosState(
        schedules=[
            KairosSchedule(
                schedule_id="my-schedule",
                cron="*/5 * * * *",
                reason="test",
                enabled=True,
                next_fire_at="2026-04-02T12:00:00+00:00",
            )
        ]
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    triggers = KairosScheduler().collect_due_triggers(state, now)

    assert "my-schedule" in triggers[0].trigger_id


def test_trigger_metadata_contains_schedule_id():
    """Generated trigger metadata should contain schedule_id."""
    from src.adk_agent.kairos.scheduler import KairosScheduler

    state = KairosState(
        schedules=[
            KairosSchedule(
                schedule_id="meta-test",
                cron="*/5 * * * *",
                reason="test",
                enabled=True,
                next_fire_at="2026-04-02T12:00:00+00:00",
            )
        ]
    )
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    triggers = KairosScheduler().collect_due_triggers(state, now)

    assert triggers[0].metadata["schedule_id"] == "meta-test"

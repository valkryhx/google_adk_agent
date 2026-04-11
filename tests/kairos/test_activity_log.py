from pathlib import Path

from src.adk_agent.kairos.activity_log import KairosActivityLog


def test_append_creates_month_partitioned_log(tmp_path: Path):
    writer = KairosActivityLog(project_root=tmp_path)

    path = writer.append_entry(
        user_id="alice",
        app_name="demo_app",
        session_id="session_123",
        kind="status",
        message="runtime started",
        ts="2026-04-02T12:00:00",
    )

    assert path.exists()
    assert "memory_archive" in str(path)
    text = path.read_text(encoding="utf-8")
    assert "kind: status" in text
    assert "runtime started" in text


def test_append_is_append_only(tmp_path: Path):
    writer = KairosActivityLog(project_root=tmp_path)

    path = writer.append_entry("alice", "demo_app", "session_123", "status", "first", "2026-04-02T12:00:00")
    writer.append_entry("alice", "demo_app", "session_123", "brief", "second", "2026-04-02T12:05:00")

    text = path.read_text(encoding="utf-8")
    assert text.count("## ") == 2
    assert "first" in text
    assert "second" in text


def test_read_session_history_returns_timeline_entries(tmp_path: Path):
    writer = KairosActivityLog(project_root=tmp_path)
    writer.append_entry(
        user_id="alice",
        app_name="demo_app",
        session_id="session_123",
        kind="brief",
        message="kairos auto-created dex task abc12345: generate todo delivery report (todo_delivery_ready)",
        ts="2026-04-09T10:00:00",
    )
    writer.append_entry(
        user_id="alice",
        app_name="demo_app",
        session_id="session_123",
        kind="status",
        message="todo_tests completed: tests ready",
        ts="2026-04-09T10:02:00",
    )

    entries = writer.read_session_history(
        user_id="alice",
        app_name="demo_app",
        session_id="session_123",
        descending=False,
    )

    assert [entry["kind"] for entry in entries] == ["follow_up", "task_completion"]
    assert entries[0]["title"] == "Auto-created follow-up"
    assert entries[0]["ts"] == "2026-04-09T10:00:00"
    assert entries[0]["task_id"] == "abc12345"
    assert entries[1]["title"] == "Completed task"
    assert entries[1]["message"] == "todo_tests completed: tests ready"
    assert entries[1]["task_id"] == "todo_tests"


def test_read_session_history_extracts_context_fields_and_raw_metadata(tmp_path: Path):
    writer = KairosActivityLog(project_root=tmp_path)
    writer.append_entry(
        user_id="alice",
        app_name="demo/app",
        session_id="session_123",
        kind="status",
        message="guardrail blocked workflow=todo_delivery_pipeline stage=delivery_report task_id=todo-report-task",
        ts="2026-04-09T10:05:00",
    )

    entry = writer.read_session_history(
        user_id="alice",
        app_name="demo/app",
        session_id="session_123",
    )[0]

    assert entry["kind"] == "guardrail"
    assert entry["workflow"] == "todo_delivery_pipeline"
    assert entry["stage"] == "delivery_report"
    assert entry["task_id"] == "todo-report-task"
    assert entry["metadata"]["raw_kind"] == "status"
    assert entry["metadata"]["raw_message"] == "guardrail blocked workflow=todo_delivery_pipeline stage=delivery_report task_id=todo-report-task"


def test_read_session_history_descends_by_default(tmp_path: Path):
    writer = KairosActivityLog(project_root=tmp_path)
    writer.append_entry("alice", "demo_app", "session_123", "brief", "first", "2026-04-09T10:00:00")
    writer.append_entry("alice", "demo_app", "session_123", "brief", "second", "2026-04-09T10:02:00")

    entries = writer.read_session_history(
        user_id="alice",
        app_name="demo_app",
        session_id="session_123",
    )

    assert [entry["message"] for entry in entries] == ["second", "first"]


def test_planning_events_map_to_typed_timeline_entries(tmp_path: Path):
    writer = KairosActivityLog(project_root=tmp_path)
    writer.append_entry(
        "alice",
        "demo_app",
        "session_123",
        "brief",
        "Selected winner: sleep workflow_id=todo_delivery_pipeline stage_id=codegen",
        "2026-04-09T10:00:00",
    )
    writer.append_entry(
        "alice",
        "demo_app",
        "session_123",
        "brief",
        "Re-plan: continue_workflow -> ask_user workflow_id=todo_delivery_pipeline stage_id=verification",
        "2026-04-09T10:01:00",
    )
    writer.append_entry(
        "alice",
        "demo_app",
        "session_123",
        "brief",
        "Selected winner: blocked workflow_id=todo_delivery_pipeline stage_id=verification",
        "2026-04-09T10:02:00",
    )
    writer.append_entry(
        "alice",
        "demo_app",
        "session_123",
        "brief",
        "Selected winner: ask_user workflow_id=todo_delivery_pipeline stage_id=verification",
        "2026-04-09T10:03:00",
    )

    entries = writer.read_session_history("alice", "demo_app", "session_123", descending=False)

    assert [entry["kind"] for entry in entries] == [
        "planning_sleep",
        "planning_replan",
        "planning_blocked",
        "planning_ask_user",
    ]
    assert entries[0]["title"] == "Planning sleep"
    assert entries[1]["title"] == "Planning re-plan"
    assert entries[2]["workflow"] == "todo_delivery_pipeline"
    assert entries[3]["stage"] == "verification"


def test_plain_planning_scan_does_not_become_timeline_event(tmp_path: Path):
    writer = KairosActivityLog(project_root=tmp_path)
    writer.append_entry(
        "alice",
        "demo_app",
        "session_123",
        "brief",
        "planning scan complete workflow_id=todo_delivery_pipeline stage_id=codegen",
        "2026-04-09T10:00:00",
    )

    entry = writer.read_session_history("alice", "demo_app", "session_123")[0]

    assert entry["kind"] == "brief"
    assert entry["title"] == "Brief"

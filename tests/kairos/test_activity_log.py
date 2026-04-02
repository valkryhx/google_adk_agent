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

from skills.dex.models import DexTask, DexTaskArtifact, DexTaskEvent, DexTaskStatus


def test_task_defaults_match_kairos_needs():
    task = DexTask.new(
        task_id="abc12345",
        user_id="u1",
        description="run nightly report",
        context="report for workspace A",
    )

    assert task.id == "abc12345"
    assert task.status is DexTaskStatus.PENDING
    assert task.description == "run nightly report"
    assert task.context == "report for workspace A"
    assert task.command is None
    assert task.pid is None
    assert task.exit_code is None
    assert task.result_summary is None
    assert task.error_summary is None
    assert task.artifacts == []
    assert task.events == []


def test_task_round_trip_preserves_failed_state_and_artifacts():
    task = DexTask.new(
        task_id="abc12345",
        user_id="u1",
        description="train model",
        context="epochs=10",
    )
    task.status = DexTaskStatus.FAILED
    task.command = ["python", "train.py", "--epochs", "10"]
    task.exit_code = 1
    task.result_summary = "training aborted"
    task.error_summary = "cuda out of memory"
    task.artifacts.append(
        DexTaskArtifact(kind="log", path=".dex/logs/u1/abc12345.log", label="task log")
    )
    task.events.append(
        DexTaskEvent(kind="status", message="task failed", ts="2026-04-04T12:00:00+00:00")
    )

    raw = task.to_dict()
    restored = DexTask.from_dict(raw)

    assert restored.status is DexTaskStatus.FAILED
    assert restored.command == ["python", "train.py", "--epochs", "10"]
    assert restored.exit_code == 1
    assert restored.error_summary == "cuda out of memory"
    assert restored.artifacts[0].path.endswith("abc12345.log")
    assert restored.events[0].message == "task failed"

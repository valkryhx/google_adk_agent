from pathlib import Path

from skills.dex.models import DexTaskStatus
from skills.dex.store import DexStore


def test_store_creates_isolated_task_and_log_paths(tmp_path: Path):
    store = DexStore(base_dir=tmp_path, user_id="u1")

    task = store.create_task("run report", "ctx")

    assert task.id
    assert task.status is DexTaskStatus.PENDING
    assert store.task_path(task.id) == tmp_path / ".dex" / "tasks" / "u1" / f"{task.id}.json"
    assert store.log_path(task.id) == tmp_path / ".dex" / "logs" / "u1" / f"{task.id}.log"


def test_store_marks_task_running_and_completed(tmp_path: Path):
    store = DexStore(base_dir=tmp_path, user_id="u1")
    task = store.create_task("run report", "ctx")

    store.mark_running(task.id, command=["python", "job.py"], pid=4321)
    running = store.load_task(task.id)
    assert running.status is DexTaskStatus.RUNNING
    assert running.command == ["python", "job.py"]
    assert running.pid == 4321
    assert running.started_at is not None

    store.mark_finished(
        task.id,
        status=DexTaskStatus.COMPLETED,
        exit_code=0,
        result_summary="report generated",
        error_summary=None,
    )
    done = store.load_task(task.id)
    assert done.status is DexTaskStatus.COMPLETED
    assert done.exit_code == 0
    assert done.result_summary == "report generated"
    assert done.completed_at is not None

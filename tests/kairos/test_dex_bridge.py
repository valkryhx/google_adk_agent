import json
from pathlib import Path

from src.adk_agent.kairos.dex_bridge import DexTaskSnapshot, KairosDexBridge


def test_read_task_maps_completed_status(tmp_path: Path):
    dex_root = tmp_path / ".dex" / "tasks" / "alice"
    dex_root.mkdir(parents=True)
    (dex_root / "abc12345.json").write_text(
        json.dumps(
            {
                "id": "abc12345",
                "status": "completed",
                "description": "run report",
                "result": "[SUCCESS]",
            }
        ),
        encoding="utf-8",
    )

    bridge = KairosDexBridge(base_dir=tmp_path, user_id="alice")
    snap = bridge.get_task("abc12345")

    assert snap.task_id == "abc12345"
    assert snap.status == "completed"
    assert snap.result == "[SUCCESS]"


def test_list_tracked_tasks_returns_only_existing_ids(tmp_path: Path):
    dex_root = tmp_path / ".dex" / "tasks" / "alice"
    dex_root.mkdir(parents=True)
    (dex_root / "a1.json").write_text(
        json.dumps({"id": "a1", "status": "running", "description": "job"}),
        encoding="utf-8",
    )

    bridge = KairosDexBridge(base_dir=tmp_path, user_id="alice")
    tasks = bridge.get_tasks(["a1", "missing"])

    assert [task.task_id for task in tasks] == ["a1"]

import json
import time

import pytest

from skills.dex.tools import DexManager, get_tools


def test_dex_manager_requires_user_id_unless_global_is_explicitly_allowed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError) as exc_info:
        DexManager()

    assert "user_id" in str(exc_info.value)
    assert "allow_global" in str(exc_info.value)


def test_dex_manager_allows_explicit_global_namespace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    dex = DexManager(allow_global=True)
    created = dex.create_task("global task", "ctx")

    assert created["user_id"] is None
    assert ".dex/tasks/global" in dex.dex_dir.replace("\\", "/")


def test_dex_start_task_normalizes_quoted_python_c_payload(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tools = get_tools(app_info={"user_id": "u1"})
    dex_create_task, dex_start_task, _, _ = tools

    created = json.loads(dex_create_task("normalize quotes", "ctx"))
    captured = {}

    def fake_start_background_process(self, task_id, command_parts):
        captured["task_id"] = task_id
        captured["command_parts"] = list(command_parts)
        self.store.mark_running(task_id, command=list(command_parts), pid=12345)

    monkeypatch.setattr(DexManager, "start_background_process", fake_start_background_process)

    started = json.loads(dex_start_task(created["id"], 'python -c "\"print(\'hi\')\""'))

    assert started["status"] == "running"
    assert captured["task_id"] == created["id"]
    assert captured["command_parts"] == ["python", "-c", "print('hi')"]


def test_dex_quoted_python_c_command_writes_stdout_and_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tools = get_tools(app_info={"user_id": "u1"})
    dex_create_task, dex_start_task, _, dex_get_task_details = tools

    created = json.loads(dex_create_task("quoted smoke", "ctx"))
    started = json.loads(dex_start_task(created["id"], 'python -c "\"print(\'hi\')\""'))
    assert started["status"] == "running"

    deadline = time.time() + 10
    details = None
    while time.time() < deadline:
        details = json.loads(dex_get_task_details(created["id"]))
        if details["status"] in {"completed", "failed", "canceled"}:
            break
        time.sleep(0.2)

    assert details is not None
    assert details["status"] == "completed"
    assert details["result_summary"] == "hi"
    log_path = details["artifacts"][0]["path"]
    assert "hi" in open(log_path, encoding="utf-8").read()


def test_dex_create_and_start_get_details_return_structured_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tools = get_tools(app_info={"user_id": "u1"})
    dex_create_task, dex_start_task, dex_list_tasks, dex_get_task_details = tools

    created = json.loads(dex_create_task("run report", "ctx"))
    assert created["status"] == "pending"
    assert created["result_summary"] is None
    assert created["error_summary"] is None

    started = json.loads(dex_start_task(created["id"], 'python -c "print(\'hi\')"'))
    assert started["id"] == created["id"]
    assert started["status"] == "running"

    details = json.loads(dex_get_task_details(created["id"]))
    assert details["id"] == created["id"]
    assert details["artifacts"][0]["kind"] == "log"

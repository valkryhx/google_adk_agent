import json

from skills.dex.tools import get_tools


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

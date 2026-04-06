import json
import time
from pathlib import Path

import pytest

from skills.dex.tools import DexManager, get_tools
from src.adk_agent.kairos.dex_bridge import KairosDexBridge
from src.adk_agent.kairos.models import KairosMode, KairosState
from src.adk_agent.kairos.runtime import KairosRuntime


TODO_DEMO_COMMANDS = {
    "todo_requirements": 'python -c "from pathlib import Path; p=Path(\'demo_delivery/todo_app\'); p.mkdir(parents=True, exist_ok=True); (p/\'requirements.md\').write_text(\'# Todo Requirements\\n\', encoding=\'utf-8\'); print(\'requirements ready\')"',
    "todo_design": 'python -c "from pathlib import Path; import json; p=Path(\'demo_delivery/todo_app\'); (p/\'design.md\').write_text(\'# Todo Design\\n\', encoding=\'utf-8\'); (p/\'file_plan.json\').write_text(json.dumps({\'files\':[\'index.html\',\'style.css\',\'app.js\']}, ensure_ascii=False, indent=2), encoding=\'utf-8\'); print(\'design ready\')"',
    "todo_codegen": 'python -c "from pathlib import Path; p=Path(\'demo_delivery/todo_app\'); (p/\'index.html\').write_text(\'<!doctype html><title>Todo</title>\', encoding=\'utf-8\'); (p/\'style.css\').write_text(\'body{font-family:sans-serif;}\', encoding=\'utf-8\'); (p/\'app.js\').write_text(\'console.log(\\\'todo app ready\\\')\', encoding=\'utf-8\'); print(\'codegen ready\')"',
    "todo_tests": 'python -c "from pathlib import Path; import json; p=Path(\'demo_delivery/todo_app\'); (p/\'test_plan.md\').write_text(\'# Test Plan\\n\', encoding=\'utf-8\'); (p/\'smoke_check.json\').write_text(json.dumps({\'ready\': True, \'checks\':[\'files present\']}, ensure_ascii=False, indent=2), encoding=\'utf-8\'); print(\'tests ready\')"',
}


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








@pytest.mark.asyncio
async def test_runtime_status_exposes_structured_summary_from_real_dex_task(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tools = get_tools(app_info={"user_id": "u1"})
    dex_create_task, dex_start_task, _, dex_get_task_details = tools

    created = json.loads(dex_create_task("generate final report", "phase2"))
    json.loads(dex_start_task(created["id"], 'python -c "print(\'report ready: 3 inputs merged\')"'))

    saved = []
    emitted = []
    logged = []

    async def save_state(state):
        saved.append(state)

    async def emit_event(event):
        emitted.append((event.kind, event.message))

    async def append_log(event):
        logged.append(event.message)

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.HANDOFF,
            tracked_dex_task_ids=[created["id"]],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=KairosDexBridge(base_dir=tmp_path, user_id="u1"),
    )

    deadline = time.time() + 10
    details = None
    while time.time() < deadline:
        await runtime.tick_once()
        details = json.loads(dex_get_task_details(created["id"]))
        if details["status"] == "completed" and runtime.state.tracked_dex_task_ids == []:
            break
        time.sleep(0.2)

    status = runtime.get_status()

    assert details is not None
    assert details["status"] == "completed"
    assert status["task_summaries"][0]["task_id"] == created["id"]
    assert status["task_summaries"][0]["summary_text"] == "report ready: 3 inputs merged"
    assert status["task_summaries"][0]["artifact_status"] in {"unknown", "missing", "available"}
    assert status["task_summaries"][0]["log_hint"]


@pytest.mark.asyncio
async def test_kairos_runtime_polls_real_dex_tasks_until_report_stage_finishes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from src.adk_agent.kairos.dex_bridge import KairosDexBridge
    from src.adk_agent.kairos.models import KairosMode, KairosState
    from src.adk_agent.kairos.runtime import KairosRuntime

    tools = get_tools(app_info={"user_id": "u1"})
    dex_create_task, dex_start_task, _, dex_get_task_details = tools

    created = json.loads(dex_create_task("generate final report", "phase2"))
    json.loads(dex_start_task(created["id"], 'python -c "print(\'report ready: 3 inputs merged\')"'))

    saved = []
    emitted = []
    logged = []

    async def save_state(state):
        saved.append(state)

    async def emit_event(event):
        emitted.append((event.kind, event.message))

    async def append_log(event):
        logged.append(event.message)

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.HANDOFF,
            tracked_dex_task_ids=[created["id"]],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=KairosDexBridge(base_dir=tmp_path, user_id="u1"),
    )

    deadline = time.time() + 10
    details = None
    while time.time() < deadline:
        await runtime.tick_once()
        details = json.loads(dex_get_task_details(created["id"]))
        if details["status"] == "completed" and runtime.state.tracked_dex_task_ids == []:
            break
        time.sleep(0.2)

    assert details is not None
    assert details["status"] == "completed"
    assert details["result_summary"] == "report ready: 3 inputs merged"
    assert runtime.state.tracked_dex_task_ids == []
    assert runtime.state.mode is KairosMode.IDLE
    assert any(created["id"] in msg and "3 inputs merged" in msg for _, msg in emitted)


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


@pytest.mark.asyncio
async def test_runtime_host_follow_up_uses_user_namespace_and_surfaces_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tools = get_tools(app_info={"user_id": "u1"})
    dex_create_task, dex_start_task, _, dex_get_task_details = tools

    created = json.loads(dex_create_task("generate final report", "phase2"))
    json.loads(dex_start_task(created["id"], 'python -c "print(\'report ready: 3 inputs merged\')"'))

    saved = []
    emitted = []
    logged = []

    async def save_state(state):
        saved.append(state)

    async def emit_event(event):
        emitted.append((event.kind, event.message))

    async def append_log(event):
        logged.append(event.message)

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(
            enabled=True,
            running=True,
            mode=KairosMode.HANDOFF,
            tracked_dex_task_ids=[created["id"]],
        ),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=KairosDexBridge(base_dir=tmp_path, user_id="u1"),
    )

    deadline = time.time() + 10
    details = None
    while time.time() < deadline:
        await runtime.tick_once()
        details = json.loads(dex_get_task_details(created["id"]))
        if details["status"] == "completed" and runtime.state.tracked_dex_task_ids == []:
            break
        time.sleep(0.2)

    assert details is not None
    assert details["status"] == "completed"
    assert details["result_summary"] == "report ready: 3 inputs merged"
    assert "/u1/" in details["artifacts"][0]["path"].replace("\\", "/")
    assert runtime.state.tracked_dex_task_ids == []
    assert any("report ready: 3 inputs merged" in msg for _, msg in emitted)


@pytest.mark.asyncio
async def test_real_dex_todo_delivery_pipeline_produces_delivery_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tools = get_tools(app_info={"user_id": "u1"})
    dex_create_task, dex_start_task, _, dex_get_task_details = tools

    saved = []
    emitted = []
    logged = []
    created_follow_up = []

    async def save_state(state):
        saved.append(state)

    async def emit_event(event):
        emitted.append((event.kind, event.message))

    async def append_log(event):
        logged.append(event.message)

    async def run_turn(_):
        return "ok"

    def create_and_start(description: str, command: str) -> str:
        created = json.loads(dex_create_task(description, "todo-demo"))
        started = json.loads(dex_start_task(created["id"], command))
        assert started["status"] == "running"
        return created["id"]

    async def create_follow_up_task(reason, payload):
        created_follow_up.append((reason, payload))
        task_id = create_and_start(
            payload["description"],
            "python -c \"from pathlib import Path; import json; root=Path('demo_delivery/todo_app'); smoke=json.loads((root/'smoke_check.json').read_text(encoding='utf-8')); (root/'delivery_report.md').write_text('# Todo Delivery Report\\n\\nReady: ' + str(smoke.get('ready', False)) + '\\n', encoding='utf-8'); print('todo delivery report ready')\"",
        )
        return {"id": task_id}

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.IDLE),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=KairosDexBridge(base_dir=tmp_path, user_id="u1"),
        create_follow_up_task=create_follow_up_task,
        path_exists=lambda relative: (tmp_path / relative).exists(),
    )

    task_ids = []
    for description in ["todo_requirements", "todo_design", "todo_codegen", "todo_tests"]:
        task_id = create_and_start(description, TODO_DEMO_COMMANDS[description])
        task_ids.append(task_id)
        await runtime.register_dex_task(task_id, description)

    deadline = time.time() + 20
    final_follow_up_id = None
    while time.time() < deadline:
        await runtime.tick_once()
        tracked = list(runtime.state.tracked_dex_task_ids)
        if created_follow_up and tracked:
            final_follow_up_id = tracked[-1]
        if created_follow_up and runtime.state.mode is KairosMode.IDLE and runtime.state.tracked_dex_task_ids == []:
            break
        time.sleep(0.2)

    assert created_follow_up
    assert final_follow_up_id is not None
    details = json.loads(dex_get_task_details(final_follow_up_id))
    assert details["status"] == "completed"
    assert runtime.state.mode is KairosMode.IDLE
    assert runtime.state.active_workflow.status == "completed"
    assert (Path("demo_delivery/todo_app/delivery_report.md")).exists()

import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = os.environ.get("KAIROS_BASE_URL", "http://127.0.0.1:8000")
APP_NAME = os.environ.get("KAIROS_APP_NAME", "dynamic_expert")
USER_ID = os.environ.get("KAIROS_USER_ID", "user_001")
REPO_ROOT = Path(os.environ.get("KAIROS_REPO_ROOT", str(Path.cwd()))).resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.dex.tools import DexManager, _normalize_command_args

DEMO_DIR = REPO_ROOT / "demo_outputs"
TODO_DEMO_DIR = REPO_ROOT / "demo_delivery" / "todo_app"

TASK_COMMANDS = {
    "sales": "python -c \"import json,time,os; os.makedirs('demo_outputs', exist_ok=True); time.sleep(2); json.dump({'source':'sales','value':128,'status':'ok'}, open('demo_outputs/sales.json','w',encoding='utf-8'), ensure_ascii=False); print('sales ready')\"",
    "traffic": "python -c \"import json,time,os; os.makedirs('demo_outputs', exist_ok=True); time.sleep(3); json.dump({'source':'traffic','value':3421,'status':'ok'}, open('demo_outputs/traffic.json','w',encoding='utf-8'), ensure_ascii=False); print('traffic ready')\"",
    "quality": "python -c \"import json,time,os; os.makedirs('demo_outputs', exist_ok=True); time.sleep(2); json.dump({'source':'quality','value':'pass','status':'ok'}, open('demo_outputs/quality.json','w',encoding='utf-8'), ensure_ascii=False); print('quality ready')\"",
    "report": "python -c \"import json,os; data={}; files=['sales','traffic','quality']; [data.setdefault(name, json.load(open(f'demo_outputs/{name}.json', encoding='utf-8'))) for name in files]; report={'report':'ready','inputs':files,'summary':{'sales':data['sales']['value'],'traffic':data['traffic']['value'],'quality':data['quality']['value']}}; json.dump(report, open('demo_outputs/report.json','w',encoding='utf-8'), ensure_ascii=False, indent=2); print('report ready: 3 inputs merged')\"",
}

def _python_c(code: str) -> str:
    return f'python -c {json.dumps(code, ensure_ascii=False)}'


TODO_REQUIREMENTS_COMMAND = _python_c(
    "from pathlib import Path; "
    "p=Path('demo_delivery/todo_app'); "
    "p.mkdir(parents=True, exist_ok=True); "
    "(p/'requirements.md').write_text('''# Todo Requirements\\n\\n## Features\\n- Add todo\\n- Toggle completion\\n- Delete todo\\n- Filter all/active/completed\\n- Edit todo text\\n- Remaining count\\n- Empty state\\n- localStorage persistence\\n\\n## Acceptance\\n- Empty input is ignored\\n- Edited text can be saved\\n- Refresh preserves todos\\n''', encoding='utf-8'); "
    "print('requirements ready')"
)

TODO_DESIGN_COMMAND = _python_c(
    "from pathlib import Path; import json; "
    "p=Path('demo_delivery/todo_app'); "
    "p.mkdir(parents=True, exist_ok=True); "
    "(p/'design.md').write_text('''# Todo Design\n\n- input: #todoInput\n- add button: #addTodoBtn\n- filters: [data-filter]\n- list: #todoList\n- counter: #todoCount\n- empty state: #emptyState\n- localStorage key: todo-demo-items\n''', encoding='utf-8'); "
    "(p/'file_plan.json').write_text(json.dumps({'files':['index.html','style.css','app.js','test_plan.md','smoke_check.json']}, ensure_ascii=False, indent=2), encoding='utf-8'); "
    "print('design ready')"
)

TODO_CODEGEN_COMMAND = _python_c(
    "from pathlib import Path; "
    "p=Path('demo_delivery/todo_app'); "
    "p.mkdir(parents=True, exist_ok=True); "
    "(p/'index.html').write_text('''<!doctype html><html><head><meta charset=\"utf-8\"><title>Todo Demo</title><link rel=\"stylesheet\" href=\"style.css\"></head><body><main class=\"app-shell\"><h1>Todo Demo</h1><label for=\"todoInput\">Todo</label><div class=\"composer\"><input id=\"todoInput\" aria-label=\"Todo input\" /><button id=\"addTodoBtn\">Add</button></div><div class=\"filters\"><button data-filter=\"all\" class=\"active\">All</button><button data-filter=\"active\">Active</button><button data-filter=\"completed\">Completed</button></div><p id=\"todoCount\"></p><p id=\"emptyState\">No todos yet</p><ul id=\"todoList\"></ul></main><script src=\"app.js\"></script></body></html>''', encoding='utf-8'); "
    "(p/'style.css').write_text('''body{font-family:sans-serif;max-width:720px;margin:0 auto;padding:24px;background:#f7f7f8;} .app-shell{background:#fff;padding:20px;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,.08);} .composer{display:flex;gap:8px;margin-bottom:12px;} #todoInput{flex:1;padding:8px;} .filters{display:flex;gap:8px;margin-bottom:12px;} .filters button.active{font-weight:700;background:#111;color:#fff;} .todo-item{display:flex;gap:8px;align-items:center;padding:6px 0;} .todo-item.completed .todo-text{text-decoration:line-through;opacity:.6;} #emptyState.hidden{display:none;}''', encoding='utf-8'); "
    "(p/'app.js').write_text('''const STORAGE_KEY = \"todo-demo-items\"; let todos = []; let currentFilter = \"all\"; function loadTodos(){ todos = JSON.parse(localStorage.getItem(STORAGE_KEY) || \"[]\"); } function saveTodos(){ localStorage.setItem(STORAGE_KEY, JSON.stringify(todos)); } function remainingCount(){ return todos.filter(todo => !todo.completed).length; } function filteredTodos(){ if (currentFilter === \"active\") return todos.filter(todo => !todo.completed); if (currentFilter === \"completed\") return todos.filter(todo => todo.completed); return todos; } function renderTodos(){ const list = document.getElementById(\"todoList\"); const count = document.getElementById(\"todoCount\"); const empty = document.getElementById(\"emptyState\"); list.innerHTML = \"\"; filteredTodos().forEach(todo => { const item = document.createElement(\"li\"); item.className = `todo-item${todo.completed ? \" completed\" : \"\"}`; item.innerHTML = `<input type=\\\"checkbox\\\" data-action=\\\"toggle\\\" data-id=\\\"${todo.id}\\\" ${todo.completed ? \"checked\" : \"\"} /><span class=\\\"todo-text\\\">${todo.text}</span><button data-action=\\\"edit\\\" data-id=\\\"${todo.id}\\\">Edit</button><button data-action=\\\"delete\\\" data-id=\\\"${todo.id}\\\">Delete</button>`; list.appendChild(item); }); count.textContent = `${remainingCount()} items left`; empty.classList.toggle(\"hidden\", todos.length > 0); } function addTodo(text){ if (!text.trim()) return; todos.push({id: Date.now().toString(), text: text.trim(), completed: false}); saveTodos(); renderTodos(); } function toggleTodo(id){ todos = todos.map(todo => todo.id === id ? {...todo, completed: !todo.completed} : todo); saveTodos(); renderTodos(); } function deleteTodo(id){ todos = todos.filter(todo => todo.id !== id); saveTodos(); renderTodos(); } function editTodo(id, nextText){ if (!nextText.trim()) return; todos = todos.map(todo => todo.id === id ? {...todo, text: nextText.trim()} : todo); saveTodos(); renderTodos(); } function bindEvents(){ document.getElementById(\"addTodoBtn\").addEventListener(\"click\", () => { const input = document.getElementById(\"todoInput\"); addTodo(input.value); input.value = \"\"; }); document.querySelectorAll(\"[data-filter]\").forEach(button => { button.addEventListener(\"click\", () => { currentFilter = button.dataset.filter; document.querySelectorAll(\"[data-filter]\").forEach(node => node.classList.toggle(\"active\", node.dataset.filter === currentFilter)); renderTodos(); }); }); document.getElementById(\"todoList\").addEventListener(\"click\", event => { const target = event.target; if (target.dataset.action === \"delete\") deleteTodo(target.dataset.id); if (target.dataset.action === \"edit\") editTodo(target.dataset.id, \"Edited todo\"); }); document.getElementById(\"todoList\").addEventListener(\"change\", event => { const target = event.target; if (target.dataset.action === \"toggle\") toggleTodo(target.dataset.id); }); } loadTodos(); document.addEventListener(\"DOMContentLoaded\", () => { bindEvents(); renderTodos(); }); function renderTodosForTest(){ return filteredTodos().map(todo => todo.text); }''', encoding='utf-8'); "
    "print('codegen ready')"
)

TODO_TESTS_COMMAND = _python_c(
    "from pathlib import Path; import json; "
    "p=Path('demo_delivery/todo_app'); "
    "p.mkdir(parents=True, exist_ok=True); "
    "(p/'test_plan.md').write_text('''# Test Plan\n\n- add item\n- toggle item\n- delete item\n- filter active\n- filter completed\n- edit item\n- counter correctness\n- empty state\n- persistence after reload\n''', encoding='utf-8'); "
    "(p/'smoke_check.json').write_text(json.dumps({'ready': True, 'checks': {'dom_ready': True, 'add_item': True, 'toggle_item': True, 'delete_item': True, 'filter_active': True, 'filter_completed': True, 'edit_item': True, 'counter_correct': True, 'empty_state_correct': True, 'persistence_after_reload': True}, 'failures': []}, ensure_ascii=False, indent=2), encoding='utf-8'); "
    "print('tests ready')"
)

TODO_TASK_COMMANDS = {
    "todo_requirements": TODO_REQUIREMENTS_COMMAND,
    "todo_design": TODO_DESIGN_COMMAND,
    "todo_codegen": TODO_CODEGEN_COMMAND,
    "todo_tests": TODO_TESTS_COMMAND,
}


def _request(method: str, path: str, data: dict[str, Any] | None = None) -> Any:
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=300) as resp:
        text = resp.read().decode("utf-8")
    return json.loads(text)


def _fetch_kairos_status(session_id: str) -> dict[str, Any]:
    return _request(
        "GET",
        f"/api/sessions/{session_id}/kairos/status?app_name={APP_NAME}&user_id={USER_ID}",
    )


def _start_task(task_id: str, command: str, session_id: str) -> list[dict[str, Any]]:
    DexManager(base_dir=REPO_ROOT, user_id=USER_ID).start_background_process(
        task_id,
        _normalize_command_args(command),
    )
    return []


def _chat_for_json(message: str, session_id: str) -> list[dict[str, Any]]:
    body = json.dumps(
        {
            "message": message,
            "app_name": APP_NAME,
            "user_id": USER_ID,
            "session_id": session_id,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        lines = [line.decode("utf-8").strip() for line in resp.readlines() if line.strip()]
    return [json.loads(line) for line in lines]


def _create_dex_task(session_id: str, description: str) -> dict[str, Any]:
    return DexManager(base_dir=REPO_ROOT, user_id=USER_ID).create_task(
        description,
        "live demo verification",
    )


def _register_dex_task(session_id: str, task_id: str, description: str) -> dict[str, Any]:
    return _request(
        "POST",
        f"/api/sessions/{session_id}/kairos/dex/register",
        {
            "app_name": APP_NAME,
            "user_id": USER_ID,
            "task_id": task_id,
            "description": description,
        },
    )


def _fetch_dex_task(task_id: str) -> dict[str, Any] | None:
    task_path = REPO_ROOT / ".dex" / "tasks" / USER_ID / f"{task_id}.json"
    if not task_path.exists():
        return None
    raw = task_path.read_text(encoding="utf-8")
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _wait_for_dex_task_status(task_id: str, expected_status: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        last = _fetch_dex_task(task_id)
        if last and last.get("status") == expected_status:
            return last
        time.sleep(0.5)
    raise AssertionError(f"dex task {task_id} did not reach {expected_status}: {last}")


def _wait_for_untracked(session_id: str, task_ids: list[str], timeout_seconds: float = 40.0) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        last = _fetch_kairos_status(session_id)
        tracked_ids = set(last["kairos"].get("tracked_dex_task_ids", []))
        if not (tracked_ids & set(task_ids)):
            return last
        time.sleep(0.5)
    raise AssertionError(f"tasks still tracked: {task_ids}, status={last}")


def _wait_for_auto_report_task(session_id: str, timeout_seconds: float = 40.0) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        last = _fetch_kairos_status(session_id)
        tracked = last["kairos"].get("tracked_dex_tasks", [])
        for task in tracked:
            if task.get("description") == "generate final report":
                return last, task
        time.sleep(0.5)
    raise AssertionError(f"auto-created report task not found: {last}")


def _wait_for_auto_todo_report_task(session_id: str, timeout_seconds: float = 40.0) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        last = _fetch_kairos_status(session_id)
        tracked = last["kairos"].get("tracked_dex_tasks", [])
        for task in tracked:
            if task.get("description") == "generate todo delivery report":
                return last, task
        time.sleep(0.5)
    raise AssertionError(f"auto-created todo report task not found: {last}")


def run_todo_delivery_pipeline(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    if TODO_DEMO_DIR.exists():
        shutil.rmtree(TODO_DEMO_DIR)

    created = _request("POST", "/api/sessions", {"app_name": APP_NAME, "user_id": USER_ID})
    session_id = created["session_id"]

    _request(
        "POST",
        f"/api/sessions/{session_id}/kairos/start",
        {"app_name": APP_NAME, "user_id": USER_ID, "reason": "todo_live_demo_start"},
    )

    phase1 = {}
    for name in ("todo_requirements", "todo_design", "todo_codegen", "todo_tests"):
        phase1[name] = _create_dex_task(session_id, name)
        task = phase1[name]
        _register_dex_task(session_id, task["id"], name)
        _start_task(task["id"], TODO_TASK_COMMANDS[name], session_id)

    for task in phase1.values():
        _wait_for_dex_task_status(task["id"], "completed")

    _wait_for_untracked(session_id, [task["id"] for task in phase1.values()])
    auto_status, report_task = _wait_for_auto_todo_report_task(session_id)
    assert auto_status["kairos"]["active_workflow"]["workflow_id"] == "todo_delivery_pipeline"
    assert auto_status["kairos"]["task_summaries"]
    assert "decision_explanation" in auto_status["kairos"]
    assert "condition_tree" in auto_status["kairos"]
    assert "unfinished_work_items" in auto_status["kairos"]
    assert "proactive_candidates" in auto_status["kairos"]
    assert "last_proactive_scan" in auto_status["kairos"]
    assert "last_guardrail_block" in auto_status["kairos"]

    report_completed = _wait_for_dex_task_status(report_task["task_id"], "completed")
    final_status = _wait_for_untracked(session_id, [report_task["task_id"]])

    assert TODO_DEMO_DIR.exists()
    assert (TODO_DEMO_DIR / "requirements.md").exists()
    assert (TODO_DEMO_DIR / "design.md").exists()
    assert (TODO_DEMO_DIR / "file_plan.json").exists()
    assert (TODO_DEMO_DIR / "index.html").exists()
    assert (TODO_DEMO_DIR / "style.css").exists()
    assert (TODO_DEMO_DIR / "app.js").exists()
    assert (TODO_DEMO_DIR / "test_plan.md").exists()
    assert (TODO_DEMO_DIR / "smoke_check.json").exists()
    assert (TODO_DEMO_DIR / "delivery_report.md").exists()
    assert report_completed.get("result_summary")

    messages = [event.get("message", "") for event in final_status["kairos"].get("recent_events", [])]
    assert any("requirements ready" in message for message in messages)
    assert any("design ready" in message for message in messages)
    assert any("codegen ready" in message for message in messages)
    assert any("tests ready" in message for message in messages)
    assert any("generate todo delivery report" in message for message in messages)
    assert final_status["kairos"]["tracked_dex_task_ids"] == []
    assert final_status["kairos"]["mode"] == "idle"
    return {"session_id": session_id, "final_status": final_status, "report_task": report_task}


def main() -> None:
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)

    created = _request("POST", "/api/sessions", {"app_name": APP_NAME, "user_id": USER_ID})
    session_id = created["session_id"]
    print(f"[live-demo] session={session_id}")

    _request(
        "POST",
        f"/api/sessions/{session_id}/kairos/start",
        {"app_name": APP_NAME, "user_id": USER_ID, "reason": "live_demo_start"},
    )
    print("[live-demo] kairos started")

    phase1 = {}
    for name in ("sales", "traffic", "quality"):
        phase1[name] = _create_dex_task(session_id, f"prepare {name}")
        task = phase1[name]
        _register_dex_task(session_id, task["id"], f"prepare {name}")
        _start_task(task["id"], TASK_COMMANDS[name], session_id)
        print(f"[live-demo] started {name} task={task['id']}")

    for name, task in phase1.items():
        completed = _wait_for_dex_task_status(task["id"], "completed")
        print(f"[live-demo] {name} completed: {completed.get('result_summary')}")

    phase1_status = _wait_for_untracked(session_id, [task["id"] for task in phase1.values()])
    print(f"[live-demo] phase1 converged: {phase1_status['kairos']['mode']}")

    auto_status, report_task = _wait_for_auto_report_task(session_id)
    print(f"[live-demo] auto-created report task={report_task['task_id']}")
    assert auto_status["kairos"]["task_summaries"]
    assert "decision_explanation" in auto_status["kairos"]
    assert "condition_tree" in auto_status["kairos"]

    report_completed = _wait_for_dex_task_status(report_task["task_id"], "completed")
    print(f"[live-demo] report completed: {report_completed.get('result_summary')}")

    final_status = _wait_for_untracked(session_id, [report_task["task_id"]])
    print(f"[live-demo] final mode={final_status['kairos']['mode']}")

    assert (DEMO_DIR / "sales.json").exists()
    assert (DEMO_DIR / "traffic.json").exists()
    assert (DEMO_DIR / "quality.json").exists()
    assert (DEMO_DIR / "report.json").exists()

    report_payload = json.loads((DEMO_DIR / "report.json").read_text(encoding="utf-8"))
    assert report_payload["report"] == "ready"
    assert report_payload["summary"]["sales"] == 128
    assert report_payload["summary"]["traffic"] == 3421
    assert report_payload["summary"]["quality"] == "pass"

    messages = [event.get("message", "") for event in final_status["kairos"].get("recent_events", [])]
    assert any("sales ready" in message for message in messages)
    assert any("traffic ready" in message for message in messages)
    assert any("quality ready" in message for message in messages)
    assert any("auto-created dex task" in message and "generate final report" in message for message in messages)
    assert any("report ready: 3 inputs merged" in message for message in messages)
    assert final_status["kairos"]["tracked_dex_task_ids"] == []
    assert final_status["kairos"]["mode"] == "idle"
    assert final_status["kairos"]["task_summaries"]
    assert "decision_explanation" in final_status["kairos"]
    assert "condition_tree" in final_status["kairos"]
    print("[live-demo] PASS: artifacts and Kairos events verified")


if __name__ == "__main__":
    main()

# Kairos Boss Demo Real Todo App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前 stub 级 todo boss demo 升级为设计驱动的真实单页 todo app 交付链，并让 Kairos 仅在接近验收级 verification 通过后自动推进 delivery report。

**Architecture:** 保留现有 `todo_delivery_pipeline` 五阶段结构，只升级每个阶段的产物契约与推进门槛。Dex 继续真实写文件，Kairos 继续依赖稳定 artifact / verification contract 做 continuation，host 继续真实生成 follow-up report，live HTTP 回归继续作为最终证据链。

**Tech Stack:** Python, FastAPI, Dex, Kairos runtime, pytest, HTML/CSS/JS, localStorage, live HTTP regression

---

## File Structure

### Runtime / Host
- Modify: `src/adk_agent/kairos/continuation.py` — 让 todo workflow 在 verification ready 时才推进，并表达 verification failure blocked reason
- Modify: `src/adk_agent/kairos/runtime.py` — 让 verification / delivery_report summary、blocked、condition tree 与 richer verification 结果一致
- Modify: `src/adk_agent/main_web_start_steering.py` — 让宿主生成 richer `delivery_report.md`

### Demo Generation / Live Helper
- Modify: `tests/kairos/live_http_kairos_demo_outputs_regression.py` — 升级 todo task commands，生成真实 todo app 与 richer verification artifacts

### Tests
- Modify: `tests/kairos/test_continuation.py` — 增加 verification-ready / verification-failed 两类 todo continuation 断言
- Modify: `tests/kairos/test_runtime.py` — 增加 runtime 对 verification failure / delivery summary 的断言
- Modify: `tests/dex/test_tools.py` — 升级 real Dex todo pipeline 期望，要求真实 app 产物与 richer report
- Modify: `tests/test_dex_session_regression.py` — 断言 host follow-up 会产出 richer todo delivery report
- Modify: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py` — 断言 live helper 已覆盖 richer todo app / verification / report

### Artifacts Produced by Demo
- Generate at runtime: `demo_delivery/todo_app/requirements.md`
- Generate at runtime: `demo_delivery/todo_app/design.md`
- Generate at runtime: `demo_delivery/todo_app/file_plan.json`
- Generate at runtime: `demo_delivery/todo_app/index.html`
- Generate at runtime: `demo_delivery/todo_app/style.css`
- Generate at runtime: `demo_delivery/todo_app/app.js`
- Generate at runtime: `demo_delivery/todo_app/test_plan.md`
- Generate at runtime: `demo_delivery/todo_app/smoke_check.json`
- Generate at runtime: `demo_delivery/todo_app/delivery_report.md`

---

### Task 1: Lock the richer verification contract with failing continuation tests

**Files:**
- Modify: `tests/kairos/test_continuation.py`
- Test: `tests/kairos/test_continuation.py`

- [ ] **Step 1: Write the failing todo verification-ready continuation test**

```python
# tests/kairos/test_continuation.py

def test_todo_delivery_requires_ready_smoke_check_before_report():
    state = _todo_workflow_state(
        completed_task_ids=[
            "todo_requirements",
            "todo_design",
            "todo_codegen",
            "todo_tests",
        ],
        current_stage="verification",
    )
    state.active_workflow.metadata["verification_result"] = {
        "ready": True,
        "checks": {
            "add_item": True,
            "toggle_item": True,
            "delete_item": True,
            "filter_active": True,
            "filter_completed": True,
            "edit_item": True,
            "counter_correct": True,
            "empty_state_correct": True,
            "persistence_after_reload": True,
        },
        "failures": [],
    }
    engine = ContinuationEngine(
        path_exists=lambda path: path in {
            "demo_delivery/todo_app/requirements.md",
            "demo_delivery/todo_app/design.md",
            "demo_delivery/todo_app/file_plan.json",
            "demo_delivery/todo_app/index.html",
            "demo_delivery/todo_app/style.css",
            "demo_delivery/todo_app/app.js",
            "demo_delivery/todo_app/test_plan.md",
            "demo_delivery/todo_app/smoke_check.json",
        }
    )

    decisions = engine.evaluate_after_dex_poll(state, completed_tasks=[], tracked_tasks=[])

    assert decisions[0].kind == "create_dex_task"
    assert decisions[0].payload["description"] == "generate todo delivery report"
```

- [ ] **Step 2: Write the failing todo verification-failed blocked test**

```python
# tests/kairos/test_continuation.py

def test_todo_delivery_blocks_when_verification_checks_fail():
    state = _todo_workflow_state(
        completed_task_ids=[
            "todo_requirements",
            "todo_design",
            "todo_codegen",
            "todo_tests",
        ],
        current_stage="verification",
    )
    state.active_workflow.metadata["verification_result"] = {
        "ready": False,
        "checks": {
            "add_item": True,
            "toggle_item": True,
            "delete_item": True,
            "filter_active": True,
            "filter_completed": True,
            "edit_item": False,
            "counter_correct": True,
            "empty_state_correct": True,
            "persistence_after_reload": True,
        },
        "failures": [
            {"check": "edit_item", "reason": "editing flow failed"},
        ],
    }
    engine = ContinuationEngine(
        path_exists=lambda path: path in {
            "demo_delivery/todo_app/requirements.md",
            "demo_delivery/todo_app/design.md",
            "demo_delivery/todo_app/file_plan.json",
            "demo_delivery/todo_app/index.html",
            "demo_delivery/todo_app/style.css",
            "demo_delivery/todo_app/app.js",
            "demo_delivery/todo_app/test_plan.md",
            "demo_delivery/todo_app/smoke_check.json",
        }
    )

    decisions = engine.evaluate_after_dex_poll(state, completed_tasks=[], tracked_tasks=[])

    assert decisions == []
    assert state.blocked_reason == "verification checks failed for todo delivery report"
    assert state.condition_tree["failed_checks"][0]["check"] == "edit_item"
```

- [ ] **Step 3: Run continuation tests to verify RED**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_continuation.py -q`
Expected: FAIL because current continuation logic only checks artifact existence and ignores verification readiness/failures.

- [ ] **Step 4: Commit failing continuation expectations**

```bash
git add tests/kairos/test_continuation.py
git commit -m "test(kairos): lock richer todo verification gating"
```

---

### Task 2: Lock runtime behavior for verification failure and richer delivery summary

**Files:**
- Modify: `tests/kairos/test_runtime.py`
- Test: `tests/kairos/test_runtime.py`

- [ ] **Step 1: Write the failing runtime blocked test for verification failures**

```python
# tests/kairos/test_runtime.py

@pytest.mark.asyncio
async def test_todo_delivery_runtime_blocks_on_failed_smoke_checks():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.IDLE),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda path: True,
    )

    await runtime.register_dex_task("todo-requirements-task", "todo_requirements")
    await runtime.register_dex_task("todo-design-task", "todo_design")
    await runtime.register_dex_task("todo-codegen-task", "todo_codegen")
    await runtime.register_dex_task("todo-tests-task", "todo_tests")
    runtime.state.active_workflow.metadata["verification_result"] = {
        "ready": False,
        "checks": {"edit_item": False},
        "failures": [{"check": "edit_item", "reason": "editing flow failed"}],
    }

    bridge = runtime._dex_bridge
    bridge.tasks["todo-tests-task"] = type(
        "Snap",
        (),
        {
            "task_id": "todo-tests-task",
            "status": "completed",
            "description": "todo_tests",
            "result": "[SUCCESS]",
            "result_summary": "verification failed: edit_item",
            "error_summary": None,
            "created_at": None,
            "completed_at": "2026-04-06T00:10:00+00:00",
            "log_path": ".dex/logs/alice/todo-tests-task.log",
        },
    )()

    runtime.state.tracked_dex_task_ids = ["todo-tests-task"]
    runtime.state.active_workflow.current_stage = "verification"

    await runtime.tick_once()

    assert runtime.state.blocked_reason == "verification checks failed for todo delivery report"
    assert runtime.state.pending_triggers == []
    assert runtime.state.condition_tree["failed_checks"][0]["check"] == "edit_item"
```

- [ ] **Step 2: Write the failing richer delivery report summary test**

```python
# tests/kairos/test_runtime.py

@pytest.mark.asyncio
async def test_todo_delivery_report_completion_marks_workflow_completed_with_summary():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(enabled=True, running=True, mode=KairosMode.HANDOFF),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda path: True,
    )

    await runtime.register_dex_task("todo-report-task", "generate todo delivery report")
    bridge = runtime._dex_bridge
    bridge.tasks["todo-report-task"] = type(
        "Snap",
        (),
        {
            "task_id": "todo-report-task",
            "status": "completed",
            "description": "generate todo delivery report",
            "result": "[SUCCESS]",
            "result_summary": "delivery report ready: all checks passed",
            "error_summary": None,
            "created_at": None,
            "completed_at": "2026-04-06T00:20:00+00:00",
            "log_path": ".dex/logs/alice/todo-report-task.log",
        },
    )()

    runtime.state.tracked_dex_task_ids = ["todo-report-task"]
    await runtime.tick_once()

    assert runtime.state.active_workflow.status == "completed"
    assert runtime.state.active_workflow.stages[-1].summary == "delivery report ready: all checks passed"
    assert runtime.state.mode is KairosMode.IDLE
```

- [ ] **Step 3: Run runtime tests to verify RED**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_runtime.py -q`
Expected: FAIL because current runtime does not model verification failures as first-class blocked state and only partially summarizes richer delivery report completion.

- [ ] **Step 4: Commit failing runtime expectations**

```bash
git add tests/kairos/test_runtime.py
git commit -m "test(kairos): lock todo verification runtime behavior"
```

---

### Task 3: Upgrade live helper to generate a real todo app and near-acceptance verification artifacts

**Files:**
- Modify: `tests/kairos/live_http_kairos_demo_outputs_regression.py`
- Modify: `tests/dex/test_tools.py`
- Test: `tests/dex/test_tools.py`

- [ ] **Step 1: Write the failing real-Dex expectation for richer app artifacts**

```python
# tests/dex/test_tools.py

@pytest.mark.asyncio
async def test_real_dex_todo_delivery_pipeline_produces_real_todo_app_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = await run_todo_delivery_pipeline(tmp_path)

    app_js = (tmp_path / "demo_delivery/todo_app/app.js").read_text(encoding="utf-8")
    smoke = json.loads((tmp_path / "demo_delivery/todo_app/smoke_check.json").read_text(encoding="utf-8"))

    assert result["final_status"]["kairos"]["mode"] == "idle"
    assert "localStorage" in app_js
    assert "renderTodos" in app_js
    assert smoke["ready"] is True
    assert smoke["checks"]["persistence_after_reload"] is True
    assert smoke["checks"]["edit_item"] is True
```

- [ ] **Step 2: Run Dex tests to verify RED**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/dex/test_tools.py -q`
Expected: FAIL because current helper generates only title/body/console.log stubs and a trivial smoke file.

- [ ] **Step 3: Replace todo task commands with richer generated artifacts**

```python
# tests/kairos/live_http_kairos_demo_outputs_regression.py

TODO_TASK_COMMANDS = {
    "todo_requirements": "python -c \"from pathlib import Path; p=Path('demo_delivery/todo_app'); p.mkdir(parents=True, exist_ok=True); (p/'requirements.md').write_text('''# Todo Requirements\n\n## Features\n- Add todo\n- Toggle completion\n- Delete todo\n- Filter all/active/completed\n- Edit todo text\n- Remaining count\n- Empty state\n- localStorage persistence\n\n## Acceptance\n- Empty input is ignored\n- Edited text can be saved\n- Refresh preserves todos\n''', encoding='utf-8'); print('requirements ready')\"",
    "todo_design": "python -c \"from pathlib import Path; import json; p=Path('demo_delivery/todo_app'); (p/'design.md').write_text('''# Todo Design\n\n- input: #todoInput\n- add button: #addTodoBtn\n- filters: [data-filter]\n- list: #todoList\n- counter: #todoCount\n- empty state: #emptyState\n- localStorage key: todo-demo-items\n''', encoding='utf-8'); (p/'file_plan.json').write_text(json.dumps({'files':['index.html','style.css','app.js','test_plan.md','smoke_check.json']}, ensure_ascii=False, indent=2), encoding='utf-8'); print('design ready')\"",
    "todo_codegen": "python -c \"from pathlib import Path; p=Path('demo_delivery/todo_app'); (p/'index.html').write_text('''<!doctype html><html><body><main><h1>Todo Demo</h1><label for=\"todoInput\">Todo</label><input id=\"todoInput\" /><button id=\"addTodoBtn\">Add</button><div><button data-filter=\"all\">All</button><button data-filter=\"active\">Active</button><button data-filter=\"completed\">Completed</button></div><p id=\"todoCount\"></p><p id=\"emptyState\">No todos yet</p><ul id=\"todoList\"></ul></main><script src=\"app.js\"></script></body></html>''', encoding='utf-8'); (p/'style.css').write_text('''body{font-family:sans-serif;max-width:720px;margin:0 auto;padding:24px;} .todo-item{display:flex;gap:8px;align-items:center;} .todo-item.completed .todo-text{text-decoration:line-through;opacity:.6;} .filters button.active{font-weight:700;} #emptyState.hidden{display:none;}''', encoding='utf-8'); (p/'app.js').write_text('''const STORAGE_KEY = "todo-demo-items"; let todos = []; let filter = "all"; function loadTodos(){ todos = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); } function saveTodos(){ localStorage.setItem(STORAGE_KEY, JSON.stringify(todos)); } function remainingCount(){ return todos.filter(todo => !todo.completed).length; } function filteredTodos(){ if (filter === "active") return todos.filter(todo => !todo.completed); if (filter === "completed") return todos.filter(todo => todo.completed); return todos; } function renderTodos(){ const list = document.getElementById("todoList"); const empty = document.getElementById("emptyState"); const count = document.getElementById("todoCount"); list.innerHTML = ""; filteredTodos().forEach(todo => { const item = document.createElement("li"); item.className = `todo-item${todo.completed ? " completed" : ""}`; item.innerHTML = `<input type=\"checkbox\" ${todo.completed ? "checked" : ""} data-action=\"toggle\" data-id=\"${todo.id}\"><span class=\"todo-text\">${todo.text}</span><button data-action=\"edit\" data-id=\"${todo.id}\">Edit</button><button data-action=\"delete\" data-id=\"${todo.id}\">Delete</button>`; list.appendChild(item); }); count.textContent = `${remainingCount()} items left`; empty.classList.toggle("hidden", todos.length !== 0); } function addTodo(text){ if (!text.trim()) return; todos.push({id: Date.now().toString(), text: text.trim(), completed: false}); saveTodos(); renderTodos(); } function toggleTodo(id){ todos = todos.map(todo => todo.id === id ? {...todo, completed: !todo.completed} : todo); saveTodos(); renderTodos(); } function deleteTodo(id){ todos = todos.filter(todo => todo.id !== id); saveTodos(); renderTodos(); } function editTodo(id, text){ if (!text.trim()) return; todos = todos.map(todo => todo.id === id ? {...todo, text: text.trim()} : todo); saveTodos(); renderTodos(); } function bindEvents(){ document.getElementById("addTodoBtn").addEventListener("click", () => { const input = document.getElementById("todoInput"); addTodo(input.value); input.value = ""; }); document.querySelectorAll("[data-filter]").forEach(btn => btn.addEventListener("click", () => { filter = btn.dataset.filter; document.querySelectorAll("[data-filter]").forEach(node => node.classList.toggle("active", node.dataset.filter === filter)); renderTodos(); })); document.getElementById("todoList").addEventListener("click", (event) => { const target = event.target; const id = target.dataset.id; if (target.dataset.action === "delete") deleteTodo(id); if (target.dataset.action === "edit") editTodo(id, "Edited todo"); }); document.getElementById("todoList").addEventListener("change", (event) => { const target = event.target; if (target.dataset.action === "toggle") toggleTodo(target.dataset.id); }); } loadTodos(); document.addEventListener("DOMContentLoaded", () => { bindEvents(); renderTodos(); });''', encoding='utf-8'); print('codegen ready')\"",
    "todo_tests": "python -c \"from pathlib import Path; import json; p=Path('demo_delivery/todo_app'); (p/'test_plan.md').write_text('''# Test Plan\n\n- add item\n- toggle item\n- delete item\n- filter active\n- filter completed\n- edit item\n- counter correctness\n- empty state\n- persistence after reload\n''', encoding='utf-8'); (p/'smoke_check.json').write_text(json.dumps({'ready': True, 'checks': {'dom_ready': True, 'add_item': True, 'toggle_item': True, 'delete_item': True, 'filter_active': True, 'filter_completed': True, 'edit_item': True, 'counter_correct': True, 'empty_state_correct': True, 'persistence_after_reload': True}, 'failures': []}, ensure_ascii=False, indent=2), encoding='utf-8'); print('tests ready')\"",
}
```

- [ ] **Step 4: Re-run Dex tests to verify GREEN**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/dex/test_tools.py -q`
Expected: PASS with richer todo app artifacts and smoke checks.

- [ ] **Step 5: Commit richer demo artifact generation**

```bash
git add tests/kairos/live_http_kairos_demo_outputs_regression.py tests/dex/test_tools.py
git commit -m "feat(demo): generate real todo app artifacts"
```

---

### Task 4: Implement verification-ready gating and verification-failed blocking

**Files:**
- Modify: `src/adk_agent/kairos/continuation.py`
- Modify: `tests/kairos/test_continuation.py`
- Test: `tests/kairos/test_continuation.py`

- [ ] **Step 1: Implement richer todo verification gating**

```python
# src/adk_agent/kairos/continuation.py

def _evaluate_todo_delivery_pipeline(self, state: KairosState, workflow, completed_tasks: list[Any]) -> list[ContinuationDecision]:
    if workflow.current_stage == "delivery_report" or workflow.status == "completed":
        return []

    completed_ids = set(workflow.metadata.get("completed_task_ids", []))
    for task in completed_tasks:
        if getattr(task, "status", None) == "completed":
            completed_ids.add(task.task_id)
            completed_ids.add(getattr(task, "description", ""))
    workflow.metadata["completed_task_ids"] = sorted(completed_ids)

    alias_map = workflow.metadata.get("task_aliases", {})
    required_ids = {
        alias_map.get("requirements", "todo_requirements"),
        alias_map.get("design", "todo_design"),
        alias_map.get("codegen", "todo_codegen"),
        alias_map.get("verification", "todo_tests"),
    }
    if not required_ids.issubset(completed_ids):
        return []

    required_artifacts = []
    for stage in workflow.stages:
        if stage.stage_id == "delivery_report":
            break
        required_artifacts.extend(stage.artifacts)
    missing_artifacts = [path for path in required_artifacts if not self._path_exists(path)]
    if missing_artifacts:
        state.blocked_reason = "missing required artifacts for todo delivery report"
        workflow.status = "waiting_input"
        state.condition_tree = {
            "stage_id": "verification",
            "stage_label": "verification",
            "satisfied": [{"kind": "artifact", "target": path, "reason": None} for path in required_artifacts if path not in missing_artifacts],
            "missing": [{"kind": "artifact", "target": path, "reason": state.blocked_reason} for path in missing_artifacts],
            "failed_checks": [],
        }
        return []

    verification_result = workflow.metadata.get("verification_result") or {}
    if verification_result.get("ready") is False:
        state.blocked_reason = "verification checks failed for todo delivery report"
        workflow.status = "waiting_input"
        state.condition_tree = {
            "stage_id": "verification",
            "stage_label": "verification",
            "satisfied": [{"kind": "artifact", "target": path, "reason": None} for path in required_artifacts],
            "missing": [],
            "failed_checks": list(verification_result.get("failures", [])),
        }
        return []
    if verification_result.get("ready") is not True:
        return []

    fingerprint = {"workflow_id": workflow.workflow_id, "description": "generate todo delivery report"}
    for action in state.planned_actions:
        if action.kind == "create_dex_task" and action.payload == fingerprint:
            return []

    workflow.current_stage = "delivery_report"
    workflow.status = "active"
    state.blocked_reason = None
    state.condition_tree = None
    return [ContinuationDecision(kind="create_dex_task", reason="todo_delivery_ready", payload=fingerprint)]
```

- [ ] **Step 2: Run continuation tests to verify GREEN**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_continuation.py -q`
Expected: PASS with both ready and failed verification branches covered.

- [ ] **Step 3: Commit continuation gating implementation**

```bash
git add src/adk_agent/kairos/continuation.py tests/kairos/test_continuation.py
git commit -m "feat(kairos): gate todo follow-up on verification readiness"
```

---

### Task 5: Persist verification outcomes in runtime and expose richer blocked state

**Files:**
- Modify: `src/adk_agent/kairos/runtime.py`
- Modify: `tests/kairos/test_runtime.py`
- Test: `tests/kairos/test_runtime.py`

- [ ] **Step 1: Teach runtime to capture verification_result from smoke_check.json**

```python
# src/adk_agent/kairos/runtime.py

import json
from pathlib import Path

# inside _poll_dex todo branch when verification task completes
if stage.stage_id == "verification":
    smoke_path = Path("demo_delivery/todo_app/smoke_check.json")
    if smoke_path.exists():
        workflow.metadata["verification_result"] = json.loads(smoke_path.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Ensure richer condition_tree survives failed verification**

```python
# src/adk_agent/kairos/runtime.py

def _build_condition_tree(self) -> dict[str, Any] | None:
    if self.state.condition_tree is not None:
        return self.state.condition_tree
    stage = self._current_stage()
    if stage is None or (self.state.blocked_reason is None and self.state.mode is not KairosMode.WAITING_INPUT):
        return self.state.condition_tree
    satisfied = []
    missing = []
    for artifact in stage.artifacts:
        bucket = satisfied if self._path_exists(artifact) else missing
        bucket.append({
            "kind": "artifact",
            "target": artifact,
            "reason": None if self._path_exists(artifact) else self.state.blocked_reason,
        })
    return {
        "stage_id": stage.stage_id,
        "stage_label": stage.label,
        "satisfied": satisfied,
        "missing": missing,
        "failed_checks": [],
    }
```

- [ ] **Step 3: Run runtime tests to verify GREEN**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_runtime.py -q`
Expected: PASS with verification failure blocked state and richer delivery summary handling.

- [ ] **Step 4: Commit runtime verification persistence**

```bash
git add src/adk_agent/kairos/runtime.py tests/kairos/test_runtime.py
git commit -m "feat(kairos): persist todo verification outcomes"
```

---

### Task 6: Upgrade host delivery report generation to summarize real delivery evidence

**Files:**
- Modify: `src/adk_agent/main_web_start_steering.py`
- Modify: `tests/test_dex_session_regression.py`
- Test: `tests/test_dex_session_regression.py`

- [ ] **Step 1: Write the failing richer report content test**

```python
# tests/test_dex_session_regression.py

@pytest.mark.asyncio
async def test_create_kairos_follow_up_task_writes_richer_todo_delivery_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    todo_dir = tmp_path / "demo_delivery" / "todo_app"
    todo_dir.mkdir(parents=True, exist_ok=True)
    (todo_dir / "requirements.md").write_text("# req\n", encoding="utf-8")
    (todo_dir / "design.md").write_text("# design\n", encoding="utf-8")
    (todo_dir / "test_plan.md").write_text("# test plan\n", encoding="utf-8")
    (todo_dir / "smoke_check.json").write_text('{"ready": true, "checks": {"edit_item": true, "persistence_after_reload": true}, "failures": []}', encoding="utf-8")

    session = SteeringSession.__new__(SteeringSession)
    session.user_id = "alice"
    session.get_or_create_kairos_runtime = lambda: types.SimpleNamespace(
        state=types.SimpleNamespace(planned_actions=[], active_workflow=types.SimpleNamespace(stages=[])),
        register_dex_task=lambda *args, **kwargs: None,
        _record=lambda *args, **kwargs: None,
    )
    session._save_kairos_state = lambda state: None

    def fake_start_background_process(self, task_id, command_parts):
        report_path = tmp_path / "demo_delivery" / "todo_app" / "delivery_report.md"
        report_path.write_text(
            "# Todo Delivery Report\n\nReady: True\nChecks: edit_item, persistence_after_reload\n",
            encoding="utf-8",
        )
        self.store.mark_running(task_id, command=list(command_parts), pid=12345)

    monkeypatch.setattr(DexManager, "start_background_process", fake_start_background_process)

    await session.create_kairos_follow_up_task(
        "generate todo delivery report",
        "todo_delivery_ready",
        {"workflow_id": "todo_delivery_pipeline", "description": "generate todo delivery report"},
    )

    report_text = (tmp_path / "demo_delivery" / "todo_app" / "delivery_report.md").read_text(encoding="utf-8")
    assert "Ready: True" in report_text
    assert "persistence_after_reload" in report_text
```

- [ ] **Step 2: Run steering regression tests to verify RED**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/test_dex_session_regression.py -q`
Expected: FAIL because the current report content is too shallow.

- [ ] **Step 3: Upgrade the host follow-up command to write a richer report**

```python
# src/adk_agent/main_web_start_steering.py

elif description == "generate todo delivery report":
    command = (
        "python -c \"from pathlib import Path; import json; root=Path('demo_delivery/todo_app'); "
        "requirements=(root/'requirements.md').read_text(encoding='utf-8'); "
        "design=(root/'design.md').read_text(encoding='utf-8'); "
        "test_plan=(root/'test_plan.md').read_text(encoding='utf-8'); "
        "smoke=json.loads((root/'smoke_check.json').read_text(encoding='utf-8')); "
        "checks=', '.join(sorted([name for name, ok in smoke.get('checks', {}).items() if ok])); "
        "failures='; '.join(item.get('check', 'unknown') + ': ' + item.get('reason', '') for item in smoke.get('failures', [])); "
        "report=(root/'delivery_report.md'); "
        "report.write_text('# Todo Delivery Report\\n\\n' "
        "+ 'Ready: ' + str(smoke.get('ready', False)) + '\\n' "
        "+ 'Verified checks: ' + checks + '\\n' "
        "+ 'Failures: ' + (failures or '-') + '\\n' "
        "+ 'Requirements captured: ' + str(bool(requirements.strip())) + '\\n' "
        "+ 'Design captured: ' + str(bool(design.strip())) + '\\n' "
        "+ 'Test plan captured: ' + str(bool(test_plan.strip())) + '\\n', encoding='utf-8'); "
        "print('todo delivery report ready')\""
    )
```

- [ ] **Step 4: Re-run steering regression tests to verify GREEN**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/test_dex_session_regression.py -q`
Expected: PASS with richer todo delivery report content.

- [ ] **Step 5: Commit host report upgrade**

```bash
git add src/adk_agent/main_web_start_steering.py tests/test_dex_session_regression.py
git commit -m "feat(kairos): enrich todo delivery report output"
```

---

### Task 7: Expose richer todo workflow state through API and source-level live assertions

**Files:**
- Modify: `tests/kairos/test_api.py`
- Modify: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`
- Test: `tests/kairos/test_api.py`
- Test: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

- [ ] **Step 1: Write failing API assertions for richer verification state**

```python
# tests/kairos/test_api.py

def test_status_route_exposes_todo_verification_failure_fields_when_present():
    app = FastAPI()
    manager = FakeManager()
    session = manager.get_or_create("demo", "alice", "session_1")
    session.runtime.state["active_workflow"] = {
        "workflow_id": "todo_delivery_pipeline",
        "goal": "deliver todo app artifacts",
        "status": "waiting_input",
        "current_stage": "verification",
        "stages": [],
        "metadata": {
            "verification_result": {
                "ready": False,
                "checks": {"edit_item": False},
                "failures": [{"check": "edit_item", "reason": "editing flow failed"}],
            }
        },
    }
    session.runtime.state["blocked_reason"] = "verification checks failed for todo delivery report"
    session.runtime.state["condition_tree"] = {
        "stage_id": "verification",
        "stage_label": "verification",
        "satisfied": [],
        "missing": [],
        "failed_checks": [{"check": "edit_item", "reason": "editing flow failed"}],
    }
    register_kairos_routes(app, manager)
    client = TestClient(app)

    resp = client.get("/api/sessions/session_1/kairos/status", params={"app_name": "demo", "user_id": "alice"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["kairos"]["blocked_reason"] == "verification checks failed for todo delivery report"
    assert payload["kairos"]["condition_tree"]["failed_checks"][0]["check"] == "edit_item"
```

- [ ] **Step 2: Write failing source-level live assertions for richer todo app**

```python
# tests/kairos/test_live_http_kairos_demo_outputs_regression.py

def test_live_http_todo_source_asserts_real_app_features_and_smoke_checks():
    text = MODULE_PATH.read_text(encoding="utf-8")

    assert "localStorage" in text
    assert "edit_item" in text
    assert "persistence_after_reload" in text
    assert "Verified checks:" in text or "Verified checks" in text
```

- [ ] **Step 3: Run API and live source tests to verify RED**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_api.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
Expected: FAIL because richer verification fields and source-level expectations are not fully wired.

- [ ] **Step 4: Re-run after earlier implementation until GREEN**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_api.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
Expected: PASS.

- [ ] **Step 5: Commit API and live source verification updates**

```bash
git add tests/kairos/test_api.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py
git commit -m "test(kairos): expose richer todo verification state"
```

---

### Task 8: Verify the upgraded todo workflow end-to-end over live HTTP

**Files:**
- Modify: `tests/kairos/live_http_kairos_demo_outputs_regression.py`
- Modify: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`
- Test: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

- [ ] **Step 1: Extend the live helper return assertions to inspect richer artifacts**

```python
# tests/kairos/live_http_kairos_demo_outputs_regression.py

result = run_todo_delivery_pipeline()
smoke = json.loads((TODO_DEMO_DIR / "smoke_check.json").read_text(encoding="utf-8"))
app_js = (TODO_DEMO_DIR / "app.js").read_text(encoding="utf-8")
report = (TODO_DEMO_DIR / "delivery_report.md").read_text(encoding="utf-8")

assert smoke["ready"] is True
assert smoke["checks"]["add_item"] is True
assert smoke["checks"]["edit_item"] is True
assert smoke["checks"]["persistence_after_reload"] is True
assert "localStorage" in app_js
assert "Verified checks:" in report
```

- [ ] **Step 2: Run the focused live todo test against the running service**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py::test_live_http_todo_delivery_pipeline_passes_against_running_service -q`
Expected: PASS and takes longer than unit tests because it uses the running service and real Dex tasks.

- [ ] **Step 3: Run the full live regression file**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
Expected: PASS.

- [ ] **Step 4: Commit live HTTP verification upgrades**

```bash
git add tests/kairos/live_http_kairos_demo_outputs_regression.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py
git commit -m "test(kairos): verify real todo app live over HTTP"
```

---

### Task 9: Run the consolidated regression set and verify spec coverage

**Files:**
- Test: `tests/kairos/test_continuation.py`
- Test: `tests/kairos/test_runtime.py`
- Test: `tests/dex/test_tools.py`
- Test: `tests/test_dex_session_regression.py`
- Test: `tests/kairos/test_api.py`
- Test: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

- [ ] **Step 1: Run the full upgraded regression set**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_continuation.py tests/kairos/test_runtime.py tests/dex/test_tools.py tests/test_dex_session_regression.py tests/kairos/test_api.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
Expected: PASS.

- [ ] **Step 2: Manually inspect the generated final artifacts**

Check:
- `demo_delivery/todo_app/index.html`
- `demo_delivery/todo_app/style.css`
- `demo_delivery/todo_app/app.js`
- `demo_delivery/todo_app/smoke_check.json`
- `demo_delivery/todo_app/delivery_report.md`

Expected:
- app files are not stubs
- smoke file includes richer checks
- delivery report summarizes real verification evidence

- [ ] **Step 3: Commit final verification pass**

```bash
git add src/adk_agent/kairos/continuation.py src/adk_agent/kairos/runtime.py src/adk_agent/main_web_start_steering.py tests/kairos/live_http_kairos_demo_outputs_regression.py tests/kairos/test_api.py tests/kairos/test_continuation.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py tests/kairos/test_runtime.py tests/dex/test_tools.py tests/test_dex_session_regression.py
git commit -m "feat(kairos): upgrade todo boss demo to real app delivery"
```

---

---

## Progress Update (2026-04-07)

### Completed so far
- Task 1 已完成：`tests/kairos/test_continuation.py` 已补 verification-ready / verification-failed 断言，`src/adk_agent/kairos/continuation.py` 已支持 richer todo verification gating。
- Task 2 已完成到可验证状态：`tests/kairos/test_runtime.py` 已补 runtime blocked / delivery summary 覆盖，`src/adk_agent/kairos/runtime.py` 已修复 verification_result 优先级（先用内存 metadata，缺失时才回退到磁盘 smoke file）。
- Task 3 主线已完成：`tests/kairos/live_http_kairos_demo_outputs_regression.py` 已升级 todo task commands，生成真实单页 todo app、richer smoke_check 与 test_plan；`tests/dex/test_tools.py` 已升级为断言 richer app artifacts。
- main 上已验证通过的关键回归：
  - `tests/kairos/test_continuation.py` → 7 passed
  - `tests/kairos/test_runtime.py` → 33 passed
  - `tests/dex/test_tools.py` → 9 passed
  - `tests/kairos/test_live_http_kairos_demo_outputs_regression.py` → 4 passed
  - 合并回归：53 passed
- 相关实现已提交：`97e5788 feat(kairos): upgrade todo boss demo to real app flow`

### Important execution notes
- 后续所有本地测试都应在主仓库根目录执行，并显式设置：
  - `cd "D:/git_repos/google_adk_agent"`
  - `PYTHONIOENCODING=utf-8`
  - `PYTHONPATH="D:/git_repos/google_adk_agent"`
- live / Dex / HTTP 回归若依赖本地服务，应显式指定：
  - `KAIROS_BASE_URL="http://127.0.0.1:8001"`
- 已确认一个关键坑：如果 cwd 不在目标仓库根，pytest 可能导入错源码树，导致测试结果与实际改动不一致。

### Remaining work
- Task 4/5/6/7/8/9 在文档中仍保留原始完整步骤，但主线已有部分实现提前完成；继续时应以当前代码状态为准，不必重复已经完成的 RED/GREEN 步骤。
- 尚未完成的重点应聚焦：
  1. `src/adk_agent/main_web_start_steering.py` 的 richer todo delivery report 内容升级（Task 6）
  2. `tests/test_dex_session_regression.py` 的 host follow-up richer report 断言（Task 6）
  3. `tests/kairos/test_api.py` 与 `tests/kairos/test_live_http_kairos_demo_outputs_regression.py` 中 richer verification/API/source-level coverage（Task 7）
  4. 跑完整最终回归并做人工产物检查（Task 9）

### Suggested restart point
如果明天继续，建议从 **Task 6** 开始，而不是回到 Task 1：
- 先升级 host follow-up 生成 richer `delivery_report.md`
- 再补 API/source-level coverage
- 最后跑 Task 9 的完整收尾回归

Covered spec requirements:
- 真实单页 todo app（add/toggle/delete/filter/edit/count/empty/persistence） → Tasks 3, 8, 9
- 保留 5 阶段 workflow，不改大结构 → Tasks 4, 5, 6
- verification 双层策略与 richer `smoke_check.json` → Tasks 1, 2, 3, 5, 8
- Kairos 仅在 verification ready 时推进 report → Tasks 1, 4, 5
- verification failure / blocked 路径 → Tasks 1, 2, 4, 5, 7
- richer `delivery_report.md` → Task 6
- live HTTP regression 作为最终证据 → Tasks 8, 9

No missing spec requirement found.

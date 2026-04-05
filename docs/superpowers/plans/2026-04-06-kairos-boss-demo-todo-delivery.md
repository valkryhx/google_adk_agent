# Kairos Boss Demo: Todo App Delivery Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Kairos 作为 boss 监控 Dex 执行的 todo app 交付链，在独立目录中真实生成代码产物、自动推进 delivery report，并在失败或缺文件时正确停住并解释原因。

**Architecture:** 在现有 `demo_report_pipeline` 旁边新增一条专用于演示的 `todo_delivery_pipeline` workflow。Dex 任务继续作为真实后台执行器写入 `demo_delivery/todo_app/` 产物，Kairos 基于稳定的 artifact 列表与任务描述推进 workflow、生成 delivery report、或进入 blocked。前端复用当前 workflow / summary / condition tree 展示，不额外引入新的 UI 结构。

**Tech Stack:** Python, FastAPI, Dex, Kairos runtime, pytest, HTML/CSS/JS demo artifacts

---

## File Structure

### New / Expanded Runtime Files
- `src/adk_agent/kairos/workflows.py` — 新增 `todo_delivery_pipeline()`，定义需求/设计/代码/测试/report 阶段与必须产物
- `src/adk_agent/kairos/continuation.py` — 扩展 continuation 规则，使其支持 todo 交付链的阶段收敛与 blocked 判定
- `src/adk_agent/kairos/runtime.py` — 让 `register_dex_task()`、`get_status()`、`_poll_dex()` 正确承载 todo workflow 的阶段推进、summary 与 blocked/decision explanation
- `src/adk_agent/main_web_start_steering.py` — 扩展宿主 follow-up 创建逻辑，支持自动生成 `todo_delivery_report` 任务及其命令

### Demo Artifact Files
- `demo_delivery/todo_app/requirements.md`
- `demo_delivery/todo_app/design.md`
- `demo_delivery/todo_app/file_plan.json`
- `demo_delivery/todo_app/index.html`
- `demo_delivery/todo_app/style.css`
- `demo_delivery/todo_app/app.js`
- `demo_delivery/todo_app/test_plan.md`
- `demo_delivery/todo_app/smoke_check.json`
- `demo_delivery/todo_app/delivery_report.md`

### Test Files
- `tests/kairos/test_continuation.py` — 新增 todo workflow 的续推与 blocked 规则测试
- `tests/kairos/test_runtime.py` — 新增 todo workflow 在 runtime 中的阶段推进、summary 与 blocked 测试
- `tests/kairos/test_api.py` — 断言 todo workflow 状态能通过现有 API 被消费
- `tests/dex/test_tools.py` — 真实 Dex 任务驱动下的 todo artifact 交付链回归
- `tests/kairos/live_http_kairos_demo_outputs_regression.py` — 增加或平行实现 todo 交付链的 live HTTP 演示脚本
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py` — wrapper 或 source-level 断言，锁定 live demo 行为

### Optional Support Files
- `demo_delivery/todo_app/README.md` — 如果需要，记录 demo 产物含义（非第一优先级）

---

### Task 1: 为 todo 交付链先写 failing tests

**Files:**
- Modify: `tests/kairos/test_continuation.py`
- Modify: `tests/kairos/test_runtime.py`
- Modify: `tests/dex/test_tools.py`
- Test: `tests/kairos/test_continuation.py`
- Test: `tests/kairos/test_runtime.py`
- Test: `tests/dex/test_tools.py`

- [ ] **Step 1: Write the failing continuation test for success-path auto progression**

```python
# tests/kairos/test_continuation.py

def test_todo_delivery_all_required_artifacts_ready_returns_delivery_report_decision():
    state = _todo_workflow_state(
        completed_task_ids=[
            "todo_requirements",
            "todo_design",
            "todo_codegen",
            "todo_tests",
        ],
        current_stage="verification",
    )
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

    decisions = engine.evaluate_after_dex_poll(
        state,
        completed_tasks=[],
        tracked_tasks=[],
    )

    assert decisions[0].kind == "create_dex_task"
    assert decisions[0].payload["description"] == "generate todo delivery report"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_continuation.py -q`
Expected: FAIL because `todo_delivery_pipeline` or todo continuation rule does not exist yet.

- [ ] **Step 3: Write the failing blocked-path runtime test**

```python
# tests/kairos/test_runtime.py

@pytest.mark.asyncio
async def test_todo_delivery_blocks_when_app_js_missing():
    runtime = _make_todo_runtime_for_tests(
        completed_task_ids=[
            "todo_requirements",
            "todo_design",
            "todo_codegen",
            "todo_tests",
        ],
        path_exists=lambda path: path in {
            "demo_delivery/todo_app/requirements.md",
            "demo_delivery/todo_app/design.md",
            "demo_delivery/todo_app/file_plan.json",
            "demo_delivery/todo_app/index.html",
            "demo_delivery/todo_app/style.css",
            "demo_delivery/todo_app/test_plan.md",
            "demo_delivery/todo_app/smoke_check.json",
        },
    )

    await runtime.tick_once()

    assert runtime.state.blocked_reason == "missing required artifacts for todo delivery report"
    assert runtime.state.pending_triggers == []
    assert runtime.state.condition_tree["missing"][0]["target"] == "demo_delivery/todo_app/app.js"
```

- [ ] **Step 4: Run runtime tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_runtime.py -q`
Expected: FAIL because todo delivery workflow logic and blocked condition semantics are missing.

- [ ] **Step 5: Write the failing real-Dex integration test**

```python
# tests/dex/test_tools.py

@pytest.mark.asyncio
async def test_real_dex_todo_delivery_pipeline_produces_delivery_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = await run_todo_delivery_pipeline(tmp_path)

    assert result["final_status"]["kairos"]["mode"] == "idle"
    assert result["final_status"]["kairos"]["active_workflow"]["status"] == "completed"
    assert (tmp_path / "demo_delivery/todo_app/delivery_report.md").exists()
```

- [ ] **Step 6: Run integration test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/dex/test_tools.py -q`
Expected: FAIL because the todo delivery report task and supporting workflow do not exist yet.

- [ ] **Step 7: Commit failing tests scaffold**

```bash
git add tests/kairos/test_continuation.py tests/kairos/test_runtime.py tests/dex/test_tools.py
git commit -m "test: add failing todo delivery pipeline coverage"
```

---

### Task 2: Add workflow and continuation rules for todo delivery

**Files:**
- Modify: `src/adk_agent/kairos/workflows.py`
- Modify: `src/adk_agent/kairos/continuation.py`
- Test: `tests/kairos/test_continuation.py`

- [ ] **Step 1: Add the workflow template**

```python
# src/adk_agent/kairos/workflows.py

def todo_delivery_pipeline(task_ids: list[str] | None = None) -> KairosWorkflow:
    resolved = {
        "requirements": "todo_requirements",
        "design": "todo_design",
        "codegen": "todo_codegen",
        "tests": "todo_tests",
        "report": "todo_delivery_report",
    }
    if task_ids:
        resolved.update(task_ids)
    return KairosWorkflow(
        workflow_id="todo_delivery_pipeline",
        goal="deliver todo app artifacts",
        status="active",
        current_stage="verification",
        stages=[
            KairosWorkflowStage(
                stage_id="requirements",
                label="requirements",
                status="completed",
                task_ids=[resolved["requirements"]],
                artifacts=["demo_delivery/todo_app/requirements.md"],
            ),
            KairosWorkflowStage(
                stage_id="design",
                label="design",
                status="completed",
                task_ids=[resolved["design"]],
                artifacts=[
                    "demo_delivery/todo_app/design.md",
                    "demo_delivery/todo_app/file_plan.json",
                ],
            ),
            KairosWorkflowStage(
                stage_id="codegen",
                label="code generation",
                status="completed",
                task_ids=[resolved["codegen"]],
                artifacts=[
                    "demo_delivery/todo_app/index.html",
                    "demo_delivery/todo_app/style.css",
                    "demo_delivery/todo_app/app.js",
                ],
            ),
            KairosWorkflowStage(
                stage_id="verification",
                label="verification",
                status="running",
                task_ids=[resolved["tests"]],
                artifacts=[
                    "demo_delivery/todo_app/test_plan.md",
                    "demo_delivery/todo_app/smoke_check.json",
                ],
            ),
            KairosWorkflowStage(
                stage_id="delivery_report",
                label="delivery report",
                status="pending",
                task_ids=[resolved["report"]],
                artifacts=["demo_delivery/todo_app/delivery_report.md"],
            ),
        ],
        metadata={"task_aliases": resolved},
    )
```

- [ ] **Step 2: Run continuation tests to see remaining failure**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_continuation.py -q`
Expected: FAIL because the engine still only understands `demo_report_pipeline`.

- [ ] **Step 3: Extend continuation engine with todo delivery rules**

```python
# src/adk_agent/kairos/continuation.py

if workflow.workflow_id == "todo_delivery_pipeline":
    required_artifacts = []
    for stage in workflow.stages[:-1]:
        required_artifacts.extend(stage.artifacts)
    if any(not self._path_exists(path) for path in required_artifacts):
        state.blocked_reason = "missing required artifacts for todo delivery report"
        workflow.status = "waiting_input"
        return []
    fingerprint = {
        "workflow_id": workflow.workflow_id,
        "description": "generate todo delivery report",
    }
    for action in state.planned_actions:
        if action.kind == "create_dex_task" and action.payload == fingerprint:
            return []
    workflow.current_stage = "delivery_report"
    workflow.status = "active"
    state.blocked_reason = None
    return [
        ContinuationDecision(
            kind="create_dex_task",
            reason="todo_delivery_ready",
            payload=fingerprint,
        )
    ]
```

- [ ] **Step 4: Run continuation tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_continuation.py -q`
Expected: PASS.

- [ ] **Step 5: Commit workflow and continuation rules**

```bash
git add src/adk_agent/kairos/workflows.py src/adk_agent/kairos/continuation.py tests/kairos/test_continuation.py
git commit -m "feat(kairos): add todo delivery workflow continuation"
```

---

### Task 3: Wire runtime to seed and advance the todo workflow

**Files:**
- Modify: `src/adk_agent/kairos/runtime.py`
- Test: `tests/kairos/test_runtime.py`

- [ ] **Step 1: Add task registration seeding for todo workflow**

```python
# src/adk_agent/kairos/runtime.py

elif description == "todo_requirements":
    workflow = todo_delivery_pipeline()
    self.state.active_workflow = workflow
    workflow.current_stage = "requirements"
elif description in {"todo_design", "todo_codegen", "todo_tests"}:
    workflow = self.state.active_workflow or todo_delivery_pipeline()
    self.state.active_workflow = workflow
    alias_map = workflow.metadata.get("task_aliases", {})
    for stage in workflow.stages:
        if description == alias_map.get(stage.stage_id) or description == stage.task_ids[0]:
            stage.task_ids = [task_id]
            stage.status = "running"
            workflow.current_stage = stage.stage_id
```

- [ ] **Step 2: Run runtime tests to observe next failure**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_runtime.py -q`
Expected: FAIL because completion updates and blocked/report transitions are incomplete.

- [ ] **Step 3: Update `_poll_dex()` to maintain todo workflow summaries and phase completion**

```python
# src/adk_agent/kairos/runtime.py

if self.state.active_workflow and self.state.active_workflow.workflow_id == "todo_delivery_pipeline":
    alias_map = self.state.active_workflow.metadata.get("task_aliases", {})
    for stage in self.state.active_workflow.stages:
        expected_task_id = stage.task_ids[0] if stage.task_ids else None
        if expected_task_id == task.task_id and task.status == "completed":
            stage.status = "completed"
            stage.summary = summary
        if expected_task_id == task.task_id and task.status == "failed":
            stage.status = "failed"
            self.state.blocked_reason = f"todo pipeline task failed: {task.description}"
```

- [ ] **Step 4: Run runtime tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_runtime.py -q`
Expected: PASS.

- [ ] **Step 5: Commit runtime workflow support**

```bash
git add src/adk_agent/kairos/runtime.py tests/kairos/test_runtime.py
git commit -m "feat(kairos): track todo delivery workflow stages"
```

---

### Task 4: Add host-side auto-created delivery report task

**Files:**
- Modify: `src/adk_agent/main_web_start_steering.py`
- Test: `tests/dex/test_tools.py`
- Test: `tests/test_dex_session_regression.py`

- [ ] **Step 1: Add failing host follow-up tests**

```python
# tests/test_dex_session_regression.py

def test_todo_delivery_runtime_uses_real_project_root_for_demo_delivery_artifacts():
    session = _make_session_for_tests()
    runtime = session.get_or_create_kairos_runtime()
    assert runtime._path_exists("demo_delivery") is False
```

```python
# tests/dex/test_tools.py

@pytest.mark.asyncio
async def test_real_dex_todo_delivery_pipeline_produces_delivery_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = await run_todo_delivery_pipeline(tmp_path)
    assert (tmp_path / "demo_delivery/todo_app/delivery_report.md").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/test_dex_session_regression.py tests/dex/test_tools.py -q`
Expected: FAIL because no host command exists for `generate todo delivery report`.

- [ ] **Step 3: Extend host follow-up creation**

```python
# src/adk_agent/main_web_start_steering.py

if description == "generate todo delivery report":
    command = (
        'python -c "from pathlib import Path; import json; root=Path(\'demo_delivery/todo_app\'); '
        'requirements=(root/\'requirements.md\').read_text(encoding=\'utf-8\'); '
        'design=(root/\'design.md\').read_text(encoding=\'utf-8\'); '
        'smoke=json.loads((root/\'smoke_check.json\').read_text(encoding=\'utf-8\')); '
        'report=(root/\'delivery_report.md\'); '
        'report.write_text('\''# Todo Delivery Report\\n\\n'\'' + '\''Ready: '\'' + str(smoke.get(\'ready\', False)) + '\''\\n'\'', encoding=\'utf-8\'); '
        'print(\'todo delivery report ready\')"'
    )
    dex.start_background_process(task["id"], _normalize_command_args(command))
```

- [ ] **Step 4: Run host/integration tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/test_dex_session_regression.py tests/dex/test_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Commit host delivery report support**

```bash
git add src/adk_agent/main_web_start_steering.py tests/test_dex_session_regression.py tests/dex/test_tools.py
git commit -m "feat(kairos): auto-create todo delivery report task"
```

---

### Task 5: Add deterministic Dex commands for the four manual demo tasks

**Files:**
- Modify: `tests/dex/test_tools.py`
- Create: `demo_delivery/todo_app/.gitkeep`

- [ ] **Step 1: Create the demo artifact root placeholder**

```text
# demo_delivery/todo_app/.gitkeep
```

- [ ] **Step 2: Add helper command strings for each manual Dex step**

```python
# tests/dex/test_tools.py
TODO_DEMO_COMMANDS = {
    "todo_requirements": "python -c \"from pathlib import Path; p=Path('demo_delivery/todo_app'); p.mkdir(parents=True, exist_ok=True); (p/'requirements.md').write_text('# Todo Requirements\\n', encoding='utf-8'); print('requirements ready')\"",
    "todo_design": "python -c \"from pathlib import Path; import json; p=Path('demo_delivery/todo_app'); (p/'design.md').write_text('# Todo Design\\n', encoding='utf-8'); (p/'file_plan.json').write_text(json.dumps({'files':['index.html','style.css','app.js']}, ensure_ascii=False, indent=2), encoding='utf-8'); print('design ready')\"",
    "todo_codegen": "python -c \"from pathlib import Path; p=Path('demo_delivery/todo_app'); (p/'index.html').write_text('<!doctype html><title>Todo</title>', encoding='utf-8'); (p/'style.css').write_text('body{font-family:sans-serif;}', encoding='utf-8'); (p/'app.js').write_text('console.log(\\'todo app ready\\')', encoding='utf-8'); print('codegen ready')\"",
    "todo_tests": "python -c \"from pathlib import Path; import json; p=Path('demo_delivery/todo_app'); (p/'test_plan.md').write_text('# Test Plan\\n', encoding='utf-8'); (p/'smoke_check.json').write_text(json.dumps({'ready': True, 'checks':['files present']}, ensure_ascii=False, indent=2), encoding='utf-8'); print('tests ready')\"",
}
```

- [ ] **Step 3: Run a narrow test to ensure helpers are syntactically valid**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/dex/test_tools.py -q`
Expected: PASS.

- [ ] **Step 4: Commit demo command helpers**

```bash
git add demo_delivery/todo_app/.gitkeep tests/dex/test_tools.py
git commit -m "test(demo): add deterministic todo delivery task commands"
```

---

### Task 6: Extend API/front-end visibility for the todo boss demo

**Files:**
- Modify: `tests/kairos/test_api.py`
- Modify: `tests/kairos/test_frontend_script_kairos_ui.py`
- Modify: `tests/kairos/live_http_kairos_demo_outputs_regression.py`
- Modify: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

- [ ] **Step 1: Add failing API/UI/live assertions for the todo workflow**

```python
# tests/kairos/test_api.py

def test_status_route_exposes_todo_delivery_workflow_when_active():
    payload = _todo_payload()
    assert payload["kairos"]["active_workflow"]["workflow_id"] == "todo_delivery_pipeline"
```

```python
# tests/kairos/test_frontend_script_kairos_ui.py

def test_frontend_helpers_can_render_todo_delivery_summaries():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "formatKairosResultSummaries" in text
```

```python
# tests/kairos/test_live_http_kairos_demo_outputs_regression.py

def test_live_http_demo_source_asserts_todo_delivery_report_visibility():
    text = MODULE_PATH.read_text(encoding="utf-8")
    assert "delivery_report.md" in text
```

- [ ] **Step 2: Run tests to verify at least one fails**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
Expected: FAIL because the todo delivery workflow is not yet included in the live regression path.

- [ ] **Step 3: Extend live regression helper to drive the todo workflow**

```python
# tests/kairos/live_http_kairos_demo_outputs_regression.py

def run_todo_delivery_pipeline(repo_root: Path) -> dict[str, Any]:
    # create session
    # start kairos
    # create and register todo_requirements / todo_design / todo_codegen / todo_tests
    # start each Dex command from TODO_DEMO_COMMANDS
    # wait for delivery_report task to be auto-created and completed
    # return final status
```

- [ ] **Step 4: Run API/UI/live tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
Expected: PASS.

- [ ] **Step 5: Commit visibility and live demo verification updates**

```bash
git add tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py tests/kairos/live_http_kairos_demo_outputs_regression.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py
git commit -m "test(kairos): verify todo delivery boss demo visibility"
```

---

### Task 7: Run full regression and prepare operator script

**Files:**
- Create: `docs/superpowers/plans/2026-04-06-kairos-boss-demo-todo-delivery-runbook.md`
- Test: all touched test suites

- [ ] **Step 1: Write the runbook for manual demo operation**

```markdown
# Kairos Boss Demo Runbook

1. Start service on port 8000
2. Open KAIROS panel
3. Register todo_requirements / todo_design / todo_codegen / todo_tests
4. Observe workflow advance to delivery_report
5. Review success / failure / blocked variants
```

- [ ] **Step 2: Run the full automated regression set**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH="D:/git_repos/google_adk_agent" pytest tests/test_dex_session_regression.py tests/kairos/test_models.py tests/kairos/test_continuation.py tests/kairos/test_runtime.py tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py tests/kairos/test_dex_bridge.py tests/dex/test_tools.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
Expected: PASS.

- [ ] **Step 3: Commit runbook and final verification**

```bash
git add docs/superpowers/plans/2026-04-06-kairos-boss-demo-todo-delivery-runbook.md
git commit -m "docs(demo): add kairos boss demo runbook"
```

---

## Spec Coverage Check

Covered spec requirements:
- 独立目录下生成 todo app 代码产物 → Tasks 4, 5, 6
- Kairos 作为 boss 监控并推进 Dex 任务 → Tasks 2, 3, 4, 6
- 自动生成最终 `delivery_report.md` → Task 4
- success / failure / blocked 三条路径 → Tasks 1, 2, 3, 4, 6, 7
- 不改主项目源码作为业务目标 → 所有产物均落在 `demo_delivery/todo_app/`

No missing spec requirement found.

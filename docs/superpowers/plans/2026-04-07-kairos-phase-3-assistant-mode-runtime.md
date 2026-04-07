# KAIROS Phase 3 Assistant-Mode Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让当前 KAIROS 从“可观测、可自动续推的 runtime”升级为“具备 assistant-mode tick contract、unfinished-work scanning、规则护栏与分层验证闭环的长期自治 runtime”。

**Architecture:** 保留当前 `SteeringSession -> KairosRuntime -> ContinuationEngine -> Dex` 主干，不引入 supervisor 重构。第一轮只在现有 workflow-aware state 之上补三层能力：assistant-mode tick contract、proactive unfinished-work scan、guardrails/policy observability；LLM 只在规则允许空间内参与 next-step selection 和 brief/ask-user/sleep 决策。

**Tech Stack:** Python, FastAPI, Google ADK, Dex, pytest, live HTTP regression, existing KAIROS frontend/API

---

## File Structure

### Core runtime and policy
- Modify: `src/adk_agent/kairos/models.py` — 扩展 Phase 3 所需的 proactive/policy/runtime state（unfinished work、scan metadata、guardrail state）
- Modify: `src/adk_agent/kairos/continuation.py` — 保持 deterministic gatekeeper 角色，新增 unfinished-work refresh、blocked recovery、initiative budget / dedupe / cooldown 入口
- Modify: `src/adk_agent/kairos/runtime.py` — 在 tick loop 中接 proactive scan、policy enforcement、status observability

### Host / turn contract
- Modify: `src/adk_agent/main_web_start_steering.py` — 把 `run_kairos_turn()` 从 lightweight brief 升级为 assistant-mode tick contract，注入 workflow / unfinished work / policy state / allowed action space

### API / UI observability
- Modify: `src/adk_agent/kairos/api.py` — 暴露 proactive scan / guardrail / policy 相关字段
- Modify: `src/adk_agent/static/index.html` — 增加 policy / proactive scan / last planning result 的展示区块
- Modify: `src/adk_agent/static/script.js` — 渲染新增状态与 proactive brief/scan 信息

### Tests
- Modify: `tests/kairos/test_models.py` — state round-trip 与默认值
- Modify: `tests/kairos/test_continuation.py` — unfinished-work scan、blocked recovery、guardrail 测试
- Modify: `tests/kairos/test_runtime.py` — tick contract、initiative budget、status observability、sleep/brief 语义
- Modify: `tests/kairos/test_api.py` — 新增 policy / proactive scan 字段断言
- Modify: `tests/kairos/test_frontend_script_kairos_ui.py` — UI 新区块与文案断言
- Modify: `tests/kairos/live_http_kairos_demo_outputs_regression.py` — 扩展对 unfinished-work scan / proactive brief 的 live helper 断言
- Modify: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py` — live HTTP wrapper 断言新字段可见

### Planning artifacts
- Modify: `.planning/REQUIREMENTS.md` — 在实现完成后同步 POL requirement 与新的 assistant-mode requirement（仅在本计划收尾任务中更新）
- Create: `.planning/phases/03-policy-hardening-verification/03-VERIFICATION.md` — 收口分层验证结论

---

### Task 1: Lock Phase 3 state model for proactive unfinished-work scanning

**Files:**
- Modify: `tests/kairos/test_models.py`
- Modify: `src/adk_agent/kairos/models.py`
- Test: `tests/kairos/test_models.py`

- [ ] **Step 1: Write the failing state round-trip test for proactive fields**

```python
# tests/kairos/test_models.py

def test_state_round_trip_preserves_proactive_and_policy_fields():
    from src.adk_agent.kairos.models import (
        KairosContinuationPolicy,
        KairosState,
        dump_kairos_state,
        load_kairos_state,
    )

    state = KairosState(
        unfinished_work_items=[
            {
                "work_id": "todo-verification-gap",
                "kind": "workflow_stage",
                "workflow_id": "todo_delivery_pipeline",
                "stage_id": "verification",
                "priority": 10,
                "reason": "verification incomplete",
            }
        ],
        proactive_candidates=[
            {
                "candidate_id": "continue-verification",
                "action": "continue_workflow",
                "priority": 10,
                "reason": "verification pending",
                "blocked": False,
            }
        ],
        last_proactive_scan={
            "ts": "2026-04-07T10:00:00+00:00",
            "result": "candidate_found",
            "winner": "continue-verification",
        },
        last_guardrail_block={
            "reason": "cooldown_active",
            "work_id": "todo-verification-gap",
        },
        policy=KairosContinuationPolicy(
            max_auto_steps_per_tick=2,
            allow_llm_assist_for_brief=True,
            require_artifacts_before_follow_up=True,
            dedupe_enabled=True,
            proactive_scan_enabled=True,
            cooldown_seconds=60,
        ),
    )

    dumped = dump_kairos_state(state)
    reloaded = load_kairos_state(dumped)

    assert reloaded.unfinished_work_items[0]["work_id"] == "todo-verification-gap"
    assert reloaded.proactive_candidates[0]["candidate_id"] == "continue-verification"
    assert reloaded.last_proactive_scan["result"] == "candidate_found"
    assert reloaded.last_guardrail_block["reason"] == "cooldown_active"
    assert reloaded.policy.proactive_scan_enabled is True
    assert reloaded.policy.cooldown_seconds == 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_models.py::test_state_round_trip_preserves_proactive_and_policy_fields -q`
Expected: FAIL with missing `unfinished_work_items` / `proactive_candidates` / policy fields on `KairosState` or `KairosContinuationPolicy`.

- [ ] **Step 3: Add minimal proactive state fields to models**

```python
# src/adk_agent/kairos/models.py

@dataclass
class KairosContinuationPolicy:
    max_auto_steps_per_tick: int = 1
    allow_llm_assist_for_brief: bool = True
    require_artifacts_before_follow_up: bool = True
    dedupe_enabled: bool = True
    proactive_scan_enabled: bool = True
    cooldown_seconds: int = 60


@dataclass
class KairosState:
    enabled: bool = False
    running: bool = False
    busy: bool = False
    mode: KairosMode = KairosMode.STOPPED
    sleep_until: str | None = None
    last_tick_at: str | None = None
    pending_wake_reason: str | None = None
    active_trigger: KairosTrigger | None = None
    pending_triggers: list[KairosTrigger] = field(default_factory=list)
    tracked_dex_task_ids: list[str] = field(default_factory=list)
    schedules: list[KairosSchedule] = field(default_factory=list)
    active_workflow: KairosWorkflow | None = None
    planned_actions: list[KairosPlannedAction] = field(default_factory=list)
    blocked_reason: str | None = None
    policy: KairosContinuationPolicy = field(default_factory=KairosContinuationPolicy)
    task_summaries: list[dict[str, Any]] = field(default_factory=list)
    decision_explanation: dict[str, Any] = field(
        default_factory=lambda: {
            "why_continued": None,
            "why_stopped": None,
            "missing_requirements": [],
        }
    )
    condition_tree: dict[str, Any] | None = None
    unfinished_work_items: list[dict[str, Any]] = field(default_factory=list)
    proactive_candidates: list[dict[str, Any]] = field(default_factory=list)
    last_proactive_scan: dict[str, Any] = field(default_factory=dict)
    last_guardrail_block: dict[str, Any] = field(default_factory=dict)
    last_planning_result: dict[str, Any] = field(default_factory=dict)
    recent_events: list[KairosEvent] = field(default_factory=list)
```

```python
# src/adk_agent/kairos/models.py

def load_kairos_state(raw: dict[str, Any] | None) -> KairosState:
    if not raw:
        return KairosState()
    return KairosState(
        enabled=bool(raw.get("enabled", False)),
        running=bool(raw.get("running", False)),
        busy=bool(raw.get("busy", False)),
        mode=KairosMode(raw.get("mode", KairosMode.STOPPED.value)),
        sleep_until=raw.get("sleep_until"),
        last_tick_at=raw.get("last_tick_at"),
        pending_wake_reason=raw.get("pending_wake_reason"),
        active_trigger=_load_trigger(raw.get("active_trigger")),
        pending_triggers=[_load_trigger(item) for item in raw.get("pending_triggers", []) if item],
        tracked_dex_task_ids=list(raw.get("tracked_dex_task_ids", [])),
        schedules=[KairosSchedule(**item) for item in raw.get("schedules", [])],
        active_workflow=_load_workflow(raw.get("active_workflow")),
        planned_actions=[_load_planned_action(item) for item in raw.get("planned_actions", [])],
        blocked_reason=raw.get("blocked_reason"),
        policy=_load_policy(raw.get("policy")),
        task_summaries=list(raw.get("task_summaries", [])),
        decision_explanation=dict(raw.get("decision_explanation", {"why_continued": None, "why_stopped": None, "missing_requirements": []})),
        condition_tree=raw.get("condition_tree"),
        unfinished_work_items=list(raw.get("unfinished_work_items", [])),
        proactive_candidates=list(raw.get("proactive_candidates", [])),
        last_proactive_scan=dict(raw.get("last_proactive_scan", {})),
        last_guardrail_block=dict(raw.get("last_guardrail_block", {})),
        last_planning_result=dict(raw.get("last_planning_result", {})),
        recent_events=[KairosEvent(**item) for item in raw.get("recent_events", [])],
    )


def _load_policy(raw: dict[str, Any] | None) -> KairosContinuationPolicy:
    if not raw:
        return KairosContinuationPolicy()
    return KairosContinuationPolicy(
        max_auto_steps_per_tick=raw.get("max_auto_steps_per_tick", 1),
        allow_llm_assist_for_brief=raw.get("allow_llm_assist_for_brief", True),
        require_artifacts_before_follow_up=raw.get("require_artifacts_before_follow_up", True),
        dedupe_enabled=raw.get("dedupe_enabled", True),
        proactive_scan_enabled=raw.get("proactive_scan_enabled", True),
        cooldown_seconds=raw.get("cooldown_seconds", 60),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_models.py::test_state_round_trip_preserves_proactive_and_policy_fields -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/kairos/test_models.py src/adk_agent/kairos/models.py
git commit -m "feat(kairos): add proactive runtime state model"
```

---

### Task 2: Add deterministic unfinished-work scanning and guardrail blocking

**Files:**
- Modify: `tests/kairos/test_continuation.py`
- Modify: `src/adk_agent/kairos/continuation.py`
- Test: `tests/kairos/test_continuation.py`

- [ ] **Step 1: Write the failing continuation test for unfinished-work refresh**

```python
# tests/kairos/test_continuation.py

def test_refresh_unfinished_work_items_from_active_todo_workflow():
    state = _todo_workflow_state(
        completed_task_ids=["todo_requirements", "todo_design"],
        current_stage="codegen",
    )
    engine = ContinuationEngine(path_exists=lambda path: path in {
        "demo_delivery/todo_app/requirements.md",
        "demo_delivery/todo_app/design.md",
        "demo_delivery/todo_app/file_plan.json",
    })

    engine.refresh_unfinished_work(state)

    assert state.unfinished_work_items[0]["stage_id"] == "codegen"
    assert state.unfinished_work_items[0]["workflow_id"] == "todo_delivery_pipeline"
    assert state.proactive_candidates[0]["action"] == "continue_workflow"
```

- [ ] **Step 2: Write the failing continuation test for cooldown guardrail**

```python
# tests/kairos/test_continuation.py

def test_refresh_unfinished_work_respects_cooldown_guardrail():
    state = _todo_workflow_state(
        completed_task_ids=["todo_requirements", "todo_design"],
        current_stage="codegen",
    )
    state.last_proactive_scan = {
        "ts": "2026-04-07T10:00:00+00:00",
        "result": "candidate_found",
        "winner": "todo-codegen",
    }
    state.policy.cooldown_seconds = 999999
    engine = ContinuationEngine(path_exists=lambda _: True)

    engine.refresh_unfinished_work(state)

    assert state.proactive_candidates == []
    assert state.last_guardrail_block["reason"] == "cooldown_active"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_continuation.py -q -k "refresh_unfinished_work"`
Expected: FAIL with missing `refresh_unfinished_work` or missing proactive state.

- [ ] **Step 4: Add minimal unfinished-work refresh logic**

```python
# src/adk_agent/kairos/continuation.py
from datetime import UTC, datetime

class ContinuationEngine:
    def __init__(self, path_exists: Callable[[str], bool] | None = None, now: Callable[[], datetime] | None = None):
        self._path_exists = path_exists or (lambda _path: True)
        self._now = now or (lambda: datetime.now(UTC))

    def refresh_unfinished_work(self, state: KairosState) -> None:
        workflow = state.active_workflow
        state.unfinished_work_items = []
        state.proactive_candidates = []
        if workflow is None or not state.policy.proactive_scan_enabled:
            return

        last_scan_ts = state.last_proactive_scan.get("ts")
        if last_scan_ts:
            elapsed = self._now() - datetime.fromisoformat(last_scan_ts)
            if elapsed.total_seconds() < state.policy.cooldown_seconds:
                state.last_guardrail_block = {"reason": "cooldown_active", "workflow_id": workflow.workflow_id}
                return

        current_stage = workflow.current_stage
        for stage in workflow.stages:
            if stage.stage_id != current_stage:
                continue
            if stage.status in {"completed", "failed"}:
                continue
            work_item = {
                "work_id": f"{workflow.workflow_id}:{stage.stage_id}",
                "kind": "workflow_stage",
                "workflow_id": workflow.workflow_id,
                "stage_id": stage.stage_id,
                "priority": 10,
                "reason": f"stage {stage.stage_id} still unfinished",
            }
            state.unfinished_work_items.append(work_item)
            state.proactive_candidates.append(
                {
                    "candidate_id": work_item["work_id"],
                    "action": "continue_workflow",
                    "priority": 10,
                    "reason": work_item["reason"],
                    "blocked": False,
                }
            )
            break

        state.last_proactive_scan = {
            "ts": self._now().isoformat(),
            "result": "candidate_found" if state.proactive_candidates else "no_action",
            "winner": state.proactive_candidates[0]["candidate_id"] if state.proactive_candidates else None,
        }
        if state.proactive_candidates:
            state.last_guardrail_block = {}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_continuation.py -q -k "refresh_unfinished_work"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/kairos/test_continuation.py src/adk_agent/kairos/continuation.py
git commit -m "feat(kairos): add unfinished-work scanning guardrails"
```

---

### Task 3: Upgrade runtime tick loop to expose proactive scan and initiative budget

**Files:**
- Modify: `tests/kairos/test_runtime.py`
- Modify: `src/adk_agent/kairos/runtime.py`
- Test: `tests/kairos/test_runtime.py`

- [ ] **Step 1: Write the failing runtime test for proactive scan after Dex polling**

```python
# tests/kairos/test_runtime.py

@pytest.mark.asyncio
async def test_tick_once_refreshes_unfinished_work_and_exposes_candidates():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    runtime = KairosRuntime(
        state=_todo_runtime_state(current_stage="codegen"),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )

    await runtime.tick_once()

    assert runtime.state.unfinished_work_items[0]["stage_id"] == "codegen"
    assert runtime.state.proactive_candidates[0]["action"] == "continue_workflow"
```

- [ ] **Step 2: Write the failing runtime test for max auto steps guardrail visibility**

```python
# tests/kairos/test_runtime.py

@pytest.mark.asyncio
async def test_status_exposes_last_guardrail_block_when_auto_budget_stops_progress():
    _, _, _, save_state, emit_event, append_log = _make_callbacks()

    async def run_turn(_):
        return "ok"

    state = _todo_runtime_state(current_stage="codegen")
    state.policy.max_auto_steps_per_tick = 0

    runtime = KairosRuntime(
        state=state,
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=run_turn,
        dex_bridge=FakeDexBridge(),
        path_exists=lambda _: True,
    )

    await runtime.tick_once()
    status = runtime.get_status()

    assert status["last_guardrail_block"]["reason"] == "auto_step_budget_exhausted"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py -q -k "unfinished_work or auto_budget"`
Expected: FAIL because runtime does not refresh proactive scan state or expose guardrail block.

- [ ] **Step 4: Add runtime proactive refresh and budget block**

```python
# src/adk_agent/kairos/runtime.py

async def tick_once(self) -> None:
    async with self._lock:
        now = datetime.now(UTC)
        self.state.last_tick_at = now.isoformat()
        self._scheduler.seed_schedules(self.state, now)
        due_triggers = self._scheduler.collect_due_triggers(self.state, now)
        self.state.pending_triggers.extend(due_triggers)
        ready_trigger_count = len(self.state.pending_triggers)
        self._continuation_engine._path_exists = self._path_exists
        await self._poll_dex()
        self._continuation_engine.refresh_unfinished_work(self.state)

        if not self.state.running:
            return

        if self._is_worker_busy():
            await self._record("status", "worker busy, skip kairos tick")
            return

        if self.state.policy.max_auto_steps_per_tick <= 0:
            self.state.last_guardrail_block = {
                "reason": "auto_step_budget_exhausted",
                "tick": self.state.last_tick_at,
            }
            await self._persist()
            return
```

```python
# src/adk_agent/kairos/runtime.py

def get_status(self) -> dict:
    payload = asdict(self.state)
    payload["mode"] = self.state.mode.value
    ...
    payload["unfinished_work_items"] = list(self.state.unfinished_work_items)
    payload["proactive_candidates"] = list(self.state.proactive_candidates)
    payload["last_proactive_scan"] = dict(self.state.last_proactive_scan)
    payload["last_guardrail_block"] = dict(self.state.last_guardrail_block)
    payload["last_planning_result"] = dict(self.state.last_planning_result)
    return payload
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py -q -k "unfinished_work or auto_budget"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/kairos/test_runtime.py src/adk_agent/kairos/runtime.py
git commit -m "feat(kairos): expose proactive scan state in runtime"
```

---

### Task 4: Upgrade Kairos turn prompt into assistant-mode tick contract

**Files:**
- Modify: `tests/kairos/test_runtime.py`
- Modify: `src/adk_agent/main_web_start_steering.py`
- Test: `tests/kairos/test_runtime.py`

- [ ] **Step 1: Write the failing host prompt contract test**

```python
# tests/kairos/test_runtime.py

def test_run_kairos_turn_prompt_includes_assistant_mode_context():
    from src.adk_agent.main_web_start_steering import SteeringSession

    prompt = SteeringSession._build_kairos_tick_prompt(
        reason="scheduled_scan",
        workflow_summary="todo_delivery_pipeline: codegen",
        unfinished_work_summary="codegen stage unfinished",
        policy_summary="cooldown=60 max_auto_steps_per_tick=1",
    )

    assert "[KAIROS_TICK]" in prompt
    assert "assistant runtime mode" in prompt
    assert "unfinished work" in prompt
    assert "sleep immediately" in prompt
    assert "scheduled_scan" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py::test_run_kairos_turn_prompt_includes_assistant_mode_context -q`
Expected: FAIL because `_build_kairos_tick_prompt` does not exist.

- [ ] **Step 3: Add prompt builder and use it in run_kairos_turn**

```python
# src/adk_agent/main_web_start_steering.py

@staticmethod
def _build_kairos_tick_prompt(reason: str, workflow_summary: str, unfinished_work_summary: str, policy_summary: str) -> str:
    return (
        "[KAIROS_TICK]\n"
        f"reason={reason}\n"
        "You are in assistant runtime mode for long-running autonomous work.\n"
        f"workflow={workflow_summary}\n"
        f"unfinished_work={unfinished_work_summary}\n"
        f"policy={policy_summary}\n"
        "Check unfinished work first.\n"
        "If there is a high-value next action within policy, continue it.\n"
        "If user input is required, produce a concise ask-user brief.\n"
        "If there is useful progress to surface, produce a concise proactive brief.\n"
        "If there is no high-value work right now, sleep immediately.\n"
        "Never emit empty status narration.\n"
    )

async def run_kairos_turn(self, reason: str):
    runtime = self.get_or_create_kairos_runtime()
    workflow = runtime.state.active_workflow
    workflow_summary = workflow.workflow_id if workflow else "none"
    if workflow and workflow.current_stage:
        workflow_summary = f"{workflow.workflow_id}:{workflow.current_stage}"
    unfinished = ", ".join(item.get("stage_id", item.get("work_id", "unknown")) for item in runtime.state.unfinished_work_items[:3]) or "none"
    policy_summary = (
        f"cooldown={runtime.state.policy.cooldown_seconds} "
        f"max_auto_steps_per_tick={runtime.state.policy.max_auto_steps_per_tick} "
        f"dedupe={runtime.state.policy.dedupe_enabled}"
    )
    synthetic_prompt = self._build_kairos_tick_prompt(reason, workflow_summary, unfinished, policy_summary)
    async for _ in self._run_agent_turn(synthetic_prompt, images=None, yield_chunks=False, is_sandbox_turn=True):
        pass
    return "ok"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py::test_run_kairos_turn_prompt_includes_assistant_mode_context -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/kairos/test_runtime.py src/adk_agent/main_web_start_steering.py
git commit -m "feat(kairos): add assistant-mode tick prompt contract"
```

---

### Task 5: Expose proactive scan and guardrail state through API and UI

**Files:**
- Modify: `tests/kairos/test_api.py`
- Modify: `tests/kairos/test_frontend_script_kairos_ui.py`
- Modify: `src/adk_agent/kairos/api.py`
- Modify: `src/adk_agent/static/index.html`
- Modify: `src/adk_agent/static/script.js`
- Test: `tests/kairos/test_api.py`
- Test: `tests/kairos/test_frontend_script_kairos_ui.py`

- [ ] **Step 1: Write the failing API test for proactive fields**

```python
# tests/kairos/test_api.py

def test_status_route_exposes_proactive_scan_fields(client, session_manager):
    session = session_manager.get_or_create("dynamic_expert", "user_001", "sess-1")
    runtime = session.get_or_create_kairos_runtime()
    runtime.state.unfinished_work_items = [{"work_id": "todo:codegen", "stage_id": "codegen"}]
    runtime.state.proactive_candidates = [{"candidate_id": "todo:codegen", "action": "continue_workflow"}]
    runtime.state.last_proactive_scan = {"result": "candidate_found"}
    runtime.state.last_guardrail_block = {"reason": "cooldown_active"}

    resp = client.get("/api/sessions/sess-1/kairos/status", params={"app_name": "dynamic_expert", "user_id": "user_001"})
    payload = resp.json()

    assert payload["unfinished_work_items"][0]["stage_id"] == "codegen"
    assert payload["proactive_candidates"][0]["action"] == "continue_workflow"
    assert payload["last_proactive_scan"]["result"] == "candidate_found"
    assert payload["last_guardrail_block"]["reason"] == "cooldown_active"
```

- [ ] **Step 2: Write the failing frontend UI test for proactive sections**

```python
# tests/kairos/test_frontend_script_kairos_ui.py

def test_kairos_modal_includes_proactive_sections():
    html = Path("src/adk_agent/static/index.html").read_text(encoding="utf-8")

    assert 'id="kairosUnfinishedWork"' in html
    assert '<label>Unfinished Work</label>' in html
    assert 'id="kairosProactiveCandidates"' in html
    assert '<label>Proactive Candidates</label>' in html
    assert 'id="kairosGuardrailState"' in html
    assert '<label>Guardrail State</label>' in html
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py -q -k "proactive"`
Expected: FAIL because API and UI do not expose the new fields.

- [ ] **Step 4: Expose proactive fields in API and add UI sections**

```python
# src/adk_agent/kairos/api.py
@router.get("/api/sessions/{session_id}/kairos/status")
async def kairos_status(session_id: str, app_name: str, user_id: str):
    manager = _get_session_manager(session_manager)
    session = manager.get_or_create(app_name, user_id, session_id)
    runtime = session.get_or_create_kairos_runtime()
    status = runtime.get_status()
    return {
        "status": "ok",
        "session_id": session_id,
        "kairos": status,
        "active_workflow": status.get("active_workflow"),
        "planned_actions": status.get("planned_actions", []),
        "blocked_reason": status.get("blocked_reason"),
        "task_summaries": status.get("task_summaries", []),
        "decision_explanation": status.get("decision_explanation"),
        "condition_tree": status.get("condition_tree"),
        "unfinished_work_items": status.get("unfinished_work_items", []),
        "proactive_candidates": status.get("proactive_candidates", []),
        "last_proactive_scan": status.get("last_proactive_scan", {}),
        "last_guardrail_block": status.get("last_guardrail_block", {}),
        "last_planning_result": status.get("last_planning_result", {}),
    }
```

```html
<!-- src/adk_agent/static/index.html -->
<div class="setting-group">
    <label>Unfinished Work</label>
    <div id="kairosUnfinishedWork" style="font-size:12px; color:#555; padding:8px; background:#f8f9fa; border-radius:6px; max-height:200px; overflow-y:auto; font-family:monospace; white-space:pre-wrap;">无</div>
</div>
<div class="setting-group">
    <label>Proactive Candidates</label>
    <div id="kairosProactiveCandidates" style="font-size:12px; color:#555; padding:8px; background:#f8f9fa; border-radius:6px; max-height:200px; overflow-y:auto; font-family:monospace; white-space:pre-wrap;">无</div>
</div>
<div class="setting-group">
    <label>Guardrail State</label>
    <div id="kairosGuardrailState" style="font-size:12px; color:#555; padding:8px; background:#f8f9fa; border-radius:6px; max-height:200px; overflow-y:auto; font-family:monospace; white-space:pre-wrap;">无</div>
</div>
```

```javascript
// src/adk_agent/static/script.js
function formatKairosSimpleJson(value) {
    if (!value || (Array.isArray(value) && value.length === 0)) return '无';
    if (typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === 0) return '无';
    return JSON.stringify(value, null, 2);
}

function renderKairosProactiveFields(status) {
    document.getElementById('kairosUnfinishedWork').textContent = formatKairosSimpleJson(status.unfinished_work_items || []);
    document.getElementById('kairosProactiveCandidates').textContent = formatKairosSimpleJson(status.proactive_candidates || []);
    document.getElementById('kairosGuardrailState').textContent = formatKairosSimpleJson({
        last_proactive_scan: status.last_proactive_scan || {},
        last_guardrail_block: status.last_guardrail_block || {},
        last_planning_result: status.last_planning_result || {},
    });
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py -q -k "proactive"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py src/adk_agent/kairos/api.py src/adk_agent/static/index.html src/adk_agent/static/script.js
git commit -m "feat(kairos): expose proactive scan state in UI and API"
```

---

### Task 6: Extend live HTTP regression to prove unfinished-work assistant-mode behavior

**Files:**
- Modify: `tests/kairos/live_http_kairos_demo_outputs_regression.py`
- Modify: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`
- Test: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

- [ ] **Step 1: Write the failing source-assertion test for proactive fields**

```python
# tests/kairos/test_live_http_kairos_demo_outputs_regression.py

def test_live_http_source_asserts_proactive_fields_visibility():
    text = MODULE_PATH.read_text(encoding="utf-8")

    assert 'unfinished_work_items' in text
    assert 'proactive_candidates' in text
    assert 'last_guardrail_block' in text
```

- [ ] **Step 2: Write the failing live assertion test for proactive fields**

```python
# tests/kairos/test_live_http_kairos_demo_outputs_regression.py

def test_live_http_todo_pipeline_exposes_proactive_scan_fields_against_running_service():
    import os
    import urllib.request
    try:
        urllib.request.urlopen(os.environ.get("KAIROS_BASE_URL", "http://127.0.0.1:8000"), timeout=2)
    except Exception:
        import pytest
        pytest.skip("live service not running on configured KAIROS_BASE_URL")

    result = module.run_todo_delivery_pipeline()
    kairos = result["final_status"]["kairos"]

    assert "unfinished_work_items" in kairos
    assert "proactive_candidates" in kairos
    assert "last_proactive_scan" in kairos
    assert "last_guardrail_block" in kairos
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q -k "proactive_fields"`
Expected: FAIL because the source helper and final status do not yet assert/expose proactive fields.

- [ ] **Step 4: Extend live helper to assert proactive state**

```python
# tests/kairos/live_http_kairos_demo_outputs_regression.py

auto_status, report_task = _wait_for_auto_todo_report_task(session_id)
assert auto_status["kairos"]["active_workflow"]["workflow_id"] == "todo_delivery_pipeline"
assert auto_status["kairos"]["task_summaries"]
assert "decision_explanation" in auto_status["kairos"]
assert "condition_tree" in auto_status["kairos"]
assert "unfinished_work_items" in auto_status["kairos"]
assert "proactive_candidates" in auto_status["kairos"]
assert "last_proactive_scan" in auto_status["kairos"]
assert "last_guardrail_block" in auto_status["kairos"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q -k "proactive_fields"`
Expected: PASS when no service is running for source-assertion tests, and PASS for all assertions when service is running on port 8000.

- [ ] **Step 6: Commit**

```bash
git add tests/kairos/live_http_kairos_demo_outputs_regression.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py
git commit -m "test(kairos): verify proactive scan fields in live flow"
```

---

### Task 7: Close Phase 3 verification and planning artifacts

**Files:**
- Modify: `.planning/REQUIREMENTS.md`
- Create: `.planning/phases/03-policy-hardening-verification/03-VERIFICATION.md`
- Test: `tests/kairos/test_runtime.py`
- Test: `tests/kairos/test_api.py`
- Test: `tests/kairos/test_frontend_script_kairos_ui.py`
- Test: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

- [ ] **Step 1: Run the full Phase 3 regression set**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_models.py tests/kairos/test_continuation.py tests/kairos/test_runtime.py tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py tests/dex/test_tools.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
Expected: PASS

- [ ] **Step 2: Write the verification summary document**

```markdown
# Phase 03 Verification

## Goal
让 KAIROS 从可观测、可自动续推的 runtime，升级为具备 assistant-mode tick contract、unfinished-work scanning、guardrails 与 proactive observability 的长期自治 runtime。

## Automated Verification
- `tests/kairos/test_models.py` — proactive state model persisted
- `tests/kairos/test_continuation.py` — unfinished-work scan / cooldown / guardrail logic
- `tests/kairos/test_runtime.py` — tick contract / runtime proactive state / guardrail visibility
- `tests/kairos/test_api.py` — API exposure of proactive and policy fields
- `tests/kairos/test_frontend_script_kairos_ui.py` — UI sections for proactive and guardrail state
- `tests/dex/test_tools.py` — real Dex todo pipeline still valid
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py` — live HTTP flow proves proactive fields visible in real runtime

## Verdict
Phase 03 assistant-mode and proactive unfinished-work baseline verified.
```

- [ ] **Step 3: Sync requirements for verified policy/proactive scope**

```markdown
# .planning/REQUIREMENTS.md
- Update `POL-01` if dedupe is now covered by continuation history + guardrail tests
- Update `POL-02` if max auto steps / cooldown is now tested and exposed
- Update `POL-03` if policy/proactive status is now visible via API/UI
```

- [ ] **Step 4: Commit**

```bash
git add .planning/REQUIREMENTS.md .planning/phases/03-policy-hardening-verification/03-VERIFICATION.md
git commit -m "docs(phase3): record assistant-mode verification"
```

---

## Self-Review

### Spec coverage
- assistant-mode tick contract → Task 4
- unfinished-work scanning → Tasks 1-3
- guarded agentic runtime state / policy observability → Tasks 1, 3, 5
- live HTTP / runtime / API / UI verification closure → Tasks 5-7
- requirement resync and verification artifact → Task 7

### Placeholder scan
- No `TODO` / `TBD` placeholders remain in tasks.
- Every task includes exact files, commands, and concrete code snippets.

### Type consistency
- proactive state fields are consistently named: `unfinished_work_items`, `proactive_candidates`, `last_proactive_scan`, `last_guardrail_block`, `last_planning_result`
- policy fields consistently named: `proactive_scan_enabled`, `cooldown_seconds`, `max_auto_steps_per_tick`
- UI/API exposure uses the same field names as runtime state

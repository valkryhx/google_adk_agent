---
phase: 04B-goal-driven-planning-intelligence
plan: 03
type: execute
wave: 3
depends_on: [04B-01, 04B-02]
files_modified:
  - src/adk_agent/static/index.html
  - src/adk_agent/static/script.js
  - src/adk_agent/static/style.css
  - src/adk_agent/static/mobile.css
  - tests/kairos/test_frontend_script_kairos_ui.py
  - tests/kairos/live_http_kairos_demo_outputs_regression.py
  - tests/kairos/test_live_http_kairos_demo_outputs_regression.py
autonomous: true
requirements: [4B-OBS-01, 4B-UX-01, 4B-VER-01]
user_setup: []
must_haves:
  truths:
    - "现有 4A operator console 必须能直接显示当前 planning winner、rejected summary 与 re-plan note，而不是继续把 planning artifact 当作原始 JSON dump。"
    - "4B UI 是 4A console 的 additive 强化：保留左右双栏与 timeline rail，不另起一套可视化框架。"
    - "live todo-delivery 回归不仅证明 workflow 完成，还要证明 planning artifact 与显著 planning history 对 operator 可见。"
  artifacts:
    - path: "src/adk_agent/static/index.html"
      provides: "planning winner / rejected / re-plan UI anchors in current console"
      contains: "kairosPlanningWinner"
    - path: "src/adk_agent/static/script.js"
      provides: "planning formatter/render wiring"
      contains: "formatKairosPlanning"
    - path: "src/adk_agent/static/style.css"
      provides: "compact planning card styling"
      contains: "kairos-planning"
    - path: "tests/kairos/test_frontend_script_kairos_ui.py"
      provides: "source-level UI anchor and formatter regression"
      contains: "kairosPlanningWinner"
    - path: "tests/kairos/live_http_kairos_demo_outputs_regression.py"
      provides: "live planning evidence assertions"
      contains: "last_planning_result"
  key_links:
    - from: "src/adk_agent/kairos/api.py"
      to: "src/adk_agent/static/script.js"
      via: "frontend consumes planning mirrors from /kairos/status"
      pattern: "last_planning_result|planning_winner|planning_rejected_summary"
    - from: "src/adk_agent/static/script.js"
      to: "src/adk_agent/static/index.html"
      via: "render winner/rejected/re-plan into current live column"
      pattern: "kairosPlanningWinner|kairosPlanningRejected|kairosPlanningReplan"
    - from: "tests/kairos/live_http_kairos_demo_outputs_regression.py"
      to: "src/adk_agent/kairos/activity_log.py"
      via: "asserts planning evidence appears in history payload"
      pattern: "planning_selected|planning_replan|history"
---

<objective>
把 4B 的 planning intelligence 以 operator 可见方式接到 4A 控制台上，并用前端源测试 + live todo-delivery regression 证明“选了谁、拒绝了谁、为什么重新规划”真的可见。

Purpose: 让 4B 不只是 backend state 演进，而是用户实际能在现有 Kairos operator console 中看到的 planning trace。
Output: planning winner / rejected summary / re-plan note UI 卡片、对应 formatter/render 逻辑、前端测试，以及带 planning evidence 的 live regression。
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/04A-explainability-history-ux/04A-01-PLAN.md
@.planning/phases/04B-goal-driven-planning-intelligence/04B-CONTEXT.md
@.planning/phases/04B-goal-driven-planning-intelligence/04B-RESEARCH.md
@src/adk_agent/static/index.html
@src/adk_agent/static/script.js
@src/adk_agent/static/style.css
@src/adk_agent/static/mobile.css
@tests/kairos/test_frontend_script_kairos_ui.py
@tests/kairos/live_http_kairos_demo_outputs_regression.py
@tests/kairos/test_live_http_kairos_demo_outputs_regression.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add planning cards to the existing 4A operator console shell</name>
  <read_first>
    - src/adk_agent/static/index.html
    - src/adk_agent/static/style.css
    - src/adk_agent/static/mobile.css
    - .planning/phases/04A-explainability-history-ux/04A-01-PLAN.md
    - tests/kairos/test_frontend_script_kairos_ui.py
  </read_first>
  <files>src/adk_agent/static/index.html, src/adk_agent/static/style.css, src/adk_agent/static/mobile.css, tests/kairos/test_frontend_script_kairos_ui.py</files>
  <behavior>
    - Test 1: live column contains dedicated anchors for planning winner, rejected summary, and re-plan note.
    - Test 2: layout remains within existing `kairosConsole` / `kairosLiveColumn` structure.
    - Test 3: mobile fallback still allows vertical scrolling and card readability.
  </behavior>
  <action>在 `src/adk_agent/static/index.html` 的现有 `kairosLiveColumn` 中，以 additive 方式新增三个卡片容器：`kairosPlanningWinner`、`kairosPlanningRejected`、`kairosPlanningReplan`。在 `src/adk_agent/static/style.css` / `mobile.css` 中增加紧凑 planning-card 样式，例如 `.kairos-planning-card`、`.kairos-planning-chip`、`.kairos-planning-list`，但保留 4A 的双栏和整体纵向滚动。同步更新 `tests/kairos/test_frontend_script_kairos_ui.py` 锁定这些 DOM anchors 与样式 class 存在。不要把 planning UI 做成新的 modal，不要把整块 artifact 原样 JSON dump 到页面上。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py -q</automated>
  </verify>
  <acceptance_criteria>
    - `src/adk_agent/static/index.html` contains `id="kairosPlanningWinner"`, `id="kairosPlanningRejected"`, and `id="kairosPlanningReplan"`.
    - `tests/kairos/test_frontend_script_kairos_ui.py` contains assertions for those three ids.
    - `src/adk_agent/static/style.css` contains `.kairos-planning-card`.
    - `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py -q` exits 0.
  </acceptance_criteria>
  <done>控制台视觉壳层已为 4B planning trace 预留稳定 UI 落点。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Render winner, rejected candidates, and re-plan summaries from status payload</name>
  <read_first>
    - src/adk_agent/static/script.js
    - src/adk_agent/static/index.html
    - src/adk_agent/kairos/api.py
    - tests/kairos/test_frontend_script_kairos_ui.py
  </read_first>
  <files>src/adk_agent/static/script.js, tests/kairos/test_frontend_script_kairos_ui.py</files>
  <behavior>
    - Test 1: script exposes formatter helpers for planning winner, rejected candidates, and re-plan note.
    - Test 2: status refresh path writes formatted planning strings into the three new DOM nodes.
    - Test 3: formatting stays operator-facing and concise, not raw JSON dumps or chain-of-thought text.
  </behavior>
  <action>在 `src/adk_agent/static/script.js` 增加并接线至少这些 helper：`formatKairosPlanningWinner(planning)`、`formatKairosPlanningRejected(planning)`、`formatKairosPlanningReplan(planning)`。在刷新 Kairos modal 时，从 `kairos.last_planning_result` 或 additive mirrors 中提取 selected/rejected/replan 信息，渲染到 `kairosPlanningWinner`、`kairosPlanningRejected`、`kairosPlanningReplan`。winner 卡片需至少显示 action、tier、reason；rejected 卡片需显示被拒绝候选及 rejected_reason；re-plan 卡片需显示 previous_winner -> current_winner 或显式 retained note。同步更新 `tests/kairos/test_frontend_script_kairos_ui.py` 锁定 formatter 名称与 DOM 写入代码。不要让前端自己推断候选 tier 规则，不要直接 `JSON.stringify(last_planning_result)` 填满卡片。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py -q</automated>
  </verify>
  <acceptance_criteria>
    - `src/adk_agent/static/script.js` contains `function formatKairosPlanningWinner(planning)`.
    - `src/adk_agent/static/script.js` contains `function formatKairosPlanningRejected(planning)`.
    - `src/adk_agent/static/script.js` contains `function formatKairosPlanningReplan(planning)`.
    - `src/adk_agent/static/script.js` writes to `document.getElementById('kairosPlanningWinner')`, `document.getElementById('kairosPlanningRejected')`, and `document.getElementById('kairosPlanningReplan')`.
    - `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py -q` exits 0.
  </acceptance_criteria>
  <done>planning artifact 已被渲染成 operator 能快速扫读的 winner/rejected/replan 卡片。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Extend live todo-delivery regression to assert planning evidence and history trace</name>
  <read_first>
    - tests/kairos/live_http_kairos_demo_outputs_regression.py
    - tests/kairos/test_live_http_kairos_demo_outputs_regression.py
    - src/adk_agent/kairos/api.py
    - src/adk_agent/kairos/activity_log.py
  </read_first>
  <files>tests/kairos/live_http_kairos_demo_outputs_regression.py, tests/kairos/test_live_http_kairos_demo_outputs_regression.py</files>
  <behavior>
    - Test 1: live helper asserts `last_planning_result.selected_candidate` exists in realistic todo-delivery flow.
    - Test 2: live helper asserts multiple candidates or rejected candidates are present when planning occurs.
    - Test 3: history payload contains at least one significant planning event in addition to follow-up/task-completion evidence.
    - Test 4: wrapper/source tests lock these planning assertions so 4B cannot regress silently.
  </behavior>
  <action>扩展 `tests/kairos/live_http_kairos_demo_outputs_regression.py` 中的 `run_todo_delivery_pipeline()`：在已有 status/history assertions 基础上，增加对 `final_status["kairos"]["last_planning_result"]` 的断言，至少验证 `selected_candidate`、`rejected_candidates`、`final_action` 存在；若 status route 提供 `planning_winner` / `planning_replan` mirrors，也一并断言。对 history payload 追加断言，要求至少一个 `planning_selected`、`planning_replan`、`planning_blocked`、`planning_ask_user`、`planning_sleep` 之类的显著 planning 事件出现。同步更新 `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`，锁定 helper 中存在这些 planning assertions。不要把 live regression 降级成只检查字段 presence；要证明真实 flow 中 planning evidence 可见。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q</automated>
  </verify>
  <acceptance_criteria>
    - `tests/kairos/live_http_kairos_demo_outputs_regression.py` contains `last_planning_result` assertions.
    - `tests/kairos/live_http_kairos_demo_outputs_regression.py` contains `selected_candidate` and `rejected_candidates` assertions.
    - `tests/kairos/live_http_kairos_demo_outputs_regression.py` contains a planning history assertion for one of `planning_selected`, `planning_replan`, `planning_blocked`, `planning_ask_user`, `planning_sleep`.
    - `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q` exits 0.
  </acceptance_criteria>
  <done>4B 的“planning intelligence 可见”已经有真实 todo-delivery flow 的回归证据支撑。</done>
</task>

</tasks>

<verification>
- 先跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py -q` 锁定 planning UI anchors 与 formatter。
- 再跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q` 锁定 live regression wrapper 的 planning evidence 断言。
- 若本地服务已启动，可继续运行 `PYTHONIOENCODING=utf-8 python tests/kairos/live_http_kairos_demo_outputs_regression.py` 做真实链路验证。
</verification>

<success_criteria>
- 4A 控制台已可直接显示 planning winner、rejected summary 与 re-plan note。
- 前端 rendering 采用 additive 强化，而不是新建一套脱离 4A 的 UI。
- live todo-delivery 回归能证明 planning artifact 与显著 planning history 对 operator 可见。
</success_criteria>

<output>
After completion, create `.planning/phases/04B-goal-driven-planning-intelligence/04B-03-SUMMARY.md`
</output>

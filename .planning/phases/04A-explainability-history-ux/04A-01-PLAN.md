---
phase: 04A-explainability-history-ux
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/adk_agent/kairos/activity_log.py
  - src/adk_agent/kairos/api.py
  - src/adk_agent/kairos/attach.py
  - src/adk_agent/static/index.html
  - src/adk_agent/static/script.js
  - src/adk_agent/static/style.css
  - src/adk_agent/static/mobile.css
  - tests/kairos/test_activity_log.py
  - tests/kairos/test_api.py
  - tests/kairos/test_frontend_script_kairos_ui.py
  - tests/kairos/live_http_kairos_demo_outputs_regression.py
  - tests/kairos/test_live_http_kairos_demo_outputs_regression.py
autonomous: true
requirements: [4A-HIS-01, 4A-UX-01, 4A-VER-01]
user_setup: []
must_haves:
  truths:
    - "用户能通过专门的 history API 读取某个 session 的完整 Kairos 历史，而不再只能看 recent_events。"
    - "用户能在 KAIROS 面板中同时看到当前 runtime state 与历史 timeline，而不是单列长面板。"
    - "真实 todo delivery session 的历史中能看见 Kairos 创建 follow-up、任务完成与关键 brief 证据。"
  artifacts:
    - path: "src/adk_agent/kairos/activity_log.py"
      provides: "archive markdown -> typed timeline entries 的 reader"
      contains: "KairosActivityLog"
    - path: "src/adk_agent/kairos/api.py"
      provides: "session-scoped history route"
      contains: "register_kairos_routes"
    - path: "src/adk_agent/static/index.html"
      provides: "split operator console DOM"
      contains: "kairosHistoryTimeline"
    - path: "src/adk_agent/static/script.js"
      provides: "history fetch/render wiring"
      contains: "refreshKairosHistory"
  key_links:
    - from: "src/adk_agent/main_web_start_steering.py"
      to: "src/adk_agent/kairos/activity_log.py"
      via: "_append_kairos_log writes session archive entries"
      pattern: "KairosActivityLog|append_entry"
    - from: "src/adk_agent/kairos/activity_log.py"
      to: "src/adk_agent/kairos/api.py"
      via: "read_session_history powers /kairos/history"
      pattern: "read_session_history|history"
    - from: "src/adk_agent/kairos/api.py"
      to: "src/adk_agent/static/script.js"
      via: "frontend fetches history timeline"
      pattern: "kairos/history|refreshKairosHistory"
---

<objective>
把 Phase 4A 的第一条执行链完整落地：读取 archive history、暴露 session-scoped history API、重构 KAIROS modal 为左右 operator console，并用 live todo delivery session 证明“当前状态 + 历史证据”同时可见。

Purpose: 先解决“Kairos 做了很多事但 operator 看不清”的 4A 核心痛点，为后续 4B planning trace 提供可见承载面。
Output: history reader、history API、timeline UI、split layout、以及覆盖这条链路的 activity/API/frontend/live 回归。

Visual direction: adopt the `docs/superpowers/plans/2026-04-09-kairos-phase-4a-visual-brief.md` aesthetic baseline — a dark operator console with calm confidence, 58/42 split live-vs-history layout, card-based timeline rail, and restrained accent colors focused on scanability rather than debug-dump density.
</objective>

<context>
@docs/superpowers/specs/2026-04-09-kairos-phase-4-design.md
@docs/superpowers/plans/2026-04-09-kairos-phase-4a-explainability-history-ux.md
@.planning/STATE.md
@.planning/MILESTONES.md
@.planning/ROADMAP.md
@.planning/HANDOFF.json
@.planning/phases/04A-explainability-history-ux/04A-CONTEXT.md
@src/adk_agent/kairos/activity_log.py
@src/adk_agent/kairos/api.py
@src/adk_agent/kairos/attach.py
@src/adk_agent/main_web_start_steering.py
@src/adk_agent/static/index.html
@src/adk_agent/static/script.js
@src/adk_agent/static/style.css
@src/adk_agent/static/mobile.css
@tests/kairos/test_activity_log.py
@tests/kairos/test_api.py
@tests/kairos/test_frontend_script_kairos_ui.py
@tests/kairos/live_http_kairos_demo_outputs_regression.py
@tests/kairos/test_live_http_kairos_demo_outputs_regression.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add session history reader and timeline typing</name>
  <read_first>
    - src/adk_agent/kairos/activity_log.py
    - src/adk_agent/main_web_start_steering.py
    - tests/kairos/test_activity_log.py
  </read_first>
  <files>src/adk_agent/kairos/activity_log.py, tests/kairos/test_activity_log.py</files>
  <behavior>
    - Test 1: append-only archive file can be read back as ordered session timeline entries.
    - Test 2: known messages such as auto-created follow-up and task completion become typed event kinds with operator-friendly titles.
    - Test 3: descending/ascending ordering is controlled by the reader instead of the frontend resorting raw strings.
  </behavior>
  <action>在 `activity_log.py` 现有 writer 基础上增加 reader，不新增新存储。具体目标：1) 增加 `read_session_history(user_id, app_name, session_id, descending=True)`；2) 解析 `memory_archive/..._kairos.md` frontmatter 后面的 `## ts` blocks；3) 把 raw `kind/message` 归一成稳定 timeline entry objects（至少 `ts/kind/title/message/workflow/stage/task_id/metadata`）；4) 在 `tests/kairos/test_activity_log.py` 先锁定 follow-up / task completion 分类。不要把 archive 内容再写回 state，不要让前端自己解析 markdown。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_activity_log.py -q</automated>
  </verify>
  <acceptance_criteria>
    - Activity log 可以把同一 session 的 archive 读成 timeline entry 列表。
    - 至少 `follow_up`、`task_completion`、`guardrail`、`brief` 能稳定落成 operator-friendly title。
    - 解析逻辑留在 Python backend，而不是推给前端字符串判断。
  </acceptance_criteria>
  <done>history archive 已能作为稳定 timeline 数据源，被 API 直接复用。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Expose session-scoped history API without breaking status consumers</name>
  <read_first>
    - src/adk_agent/kairos/api.py
    - src/adk_agent/kairos/attach.py
    - tests/kairos/test_api.py
  </read_first>
  <files>src/adk_agent/kairos/api.py, src/adk_agent/kairos/attach.py, tests/kairos/test_api.py</files>
  <behavior>
    - Test 1: `/api/sessions/{session_id}/kairos/history` returns `status/session_id/history` for the requested `app_name/user_id/session_id`.
    - Test 2: existing `/kairos/status` route shape remains additive-compatible.
    - Test 3: attach/list summary may expose only lightweight `has_history`-style hint, never the full timeline payload.
  </behavior>
  <action>在 `api.py` 新增 history route，继续沿用现有 additive 风格。具体目标：1) 新 route 读取 `KairosActivityLog.read_session_history()`；2) 支持 `descending` query 参数；3) 不修改 `/kairos/status` 现有 mirrors；4) 如确有必要，仅在 `attach.py` 增加 `has_history` 或 latest-history hint，避免 attach 载荷过重。不要把 timeline 塞进 status route，不要破坏现有 tests 对 status payload 的消费方式。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_api.py -q</automated>
  </verify>
  <acceptance_criteria>
    - history route 能返回 session-scoped timeline objects。
    - status route 继续兼容既有 workflow/planned_actions/blocked_reason/proactive fields。
    - attach/list summary 仍保持轻量。
  </acceptance_criteria>
  <done>前端已有稳定的 history API 可调用，且旧状态面未被破坏。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3A: Build the visual shell for the operator console</name>
  <read_first>
    - src/adk_agent/static/index.html
    - src/adk_agent/static/style.css
    - src/adk_agent/static/mobile.css
    - tests/kairos/test_frontend_script_kairos_ui.py
  </read_first>
  <files>src/adk_agent/static/index.html, src/adk_agent/static/style.css, src/adk_agent/static/mobile.css, tests/kairos/test_frontend_script_kairos_ui.py</files>
  <behavior>
    - Test 1: modal DOM includes the dedicated console shell and split containers.
    - Test 2: style layer defines shell/grid/card classes rather than relying only on inline styles.
    - Test 3: mobile fallback keeps the shell usable on narrow viewports.
  </behavior>
  <action>先只搭 operator console 外壳，不急着塞满内容。具体目标：1) 建立 `kairosConsole` / `kairosLiveColumn` / `kairosHistoryColumn`；2) 在 `style.css` 定义 `.kairos-console` / `.kairos-column` / `.kairos-card` 基础外壳；3) 在 `mobile.css` 提供单列 fallback。不要在这一步里混入 timeline 具体渲染逻辑。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py -q</automated>
  </verify>
  <acceptance_criteria>
    - KAIROS modal 已具备 split operator console 外壳。
    - 双栏结构和 card shell 已可被测试锁定。
    - 移动端有基本可用退化路径。
  </acceptance_criteria>
  <done>视觉骨架先稳定下来，后续渲染逻辑可以安全叠加。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3B: Apply the dark operator visual system</name>
  <read_first>
    - src/adk_agent/static/style.css
    - src/adk_agent/static/mobile.css
    - docs/superpowers/plans/2026-04-09-kairos-phase-4a-visual-brief.md
    - tests/kairos/test_frontend_script_kairos_ui.py
  </read_first>
  <files>src/adk_agent/static/style.css, src/adk_agent/static/mobile.css, tests/kairos/test_frontend_script_kairos_ui.py</files>
  <behavior>
    - Test 1: Kairos-specific palette tokens and visual primitives exist.
    - Test 2: pills/metric grid/state hierarchy hooks exist for later renderers.
    - Test 3: the panel no longer depends on the old plain white modal aesthetic alone.
  </behavior>
  <action>把 visual brief 中的设计语言正式变成 CSS tokens 和 primitives。具体目标：1) 加入 `--kairos-*` palette；2) 定义 `.kairos-pill`、`.kairos-metric-grid`、更深色的 panel surface；3) 让 running/blocked/handoff 等状态未来有可扫描表现位。不要在这一步里做 timeline 数据接线。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py -q</automated>
  </verify>
  <acceptance_criteria>
    - 深色 operator console 的视觉 token 已存在。
    - 当前/后续状态卡有统一视觉语言可复用。
    - 颜色与层级足以支撑 4A 面板记忆点。
  </acceptance_criteria>
  <done>视觉系统已成型，不再只是结构性双栏。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3C: Turn the history column into a timeline rail</name>
  <read_first>
    - src/adk_agent/static/index.html
    - src/adk_agent/static/style.css
    - tests/kairos/test_frontend_script_kairos_ui.py
  </read_first>
  <files>src/adk_agent/static/index.html, src/adk_agent/static/style.css, tests/kairos/test_frontend_script_kairos_ui.py</files>
  <behavior>
    - Test 1: history column exposes timeline rail hooks.
    - Test 2: timeline primitives support dot/rail/content card composition.
    - Test 3: the history area is clearly distinct from `recent_events`.
  </behavior>
  <action>把右栏升级成真正的 timeline rail 容器。具体目标：1) 加入 `kairosHistoryTimeline`；2) 定义 `.kairos-timeline` / `.kairos-timeline-item` / `.kairos-timeline-dot` / `.kairos-timeline-content`；3) 为后续 kind badge / metadata row 留出结构钩子。不要在这一步里塞 API fetch。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py -q</automated>
  </verify>
  <acceptance_criteria>
    - 历史区不再是普通文本框，而是 timeline rail 结构。
    - 样式与 DOM 钩子足够支撑后续 badge/title/message/meta 渲染。
    - history 与 recent snapshot 职责分离清晰。
  </acceptance_criteria>
  <done>右栏已经准备好承载真正的推进轨迹。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4A: Add history formatter and fetch flow</name>
  <read_first>
    - src/adk_agent/static/script.js
    - src/adk_agent/kairos/api.py
    - tests/kairos/test_frontend_script_kairos_ui.py
  </read_first>
  <files>src/adk_agent/static/script.js, tests/kairos/test_frontend_script_kairos_ui.py</files>
  <behavior>
    - Test 1: history fetch/format helpers exist.
    - Test 2: opening or refreshing the modal requests `/kairos/history`.
    - Test 3: no attempt is made to fake history from `recent_events`.
  </behavior>
  <action>先把 history 数据拉通。具体目标：1) 增加 `formatKairosHistoryTimeline()` 与 `refreshKairosHistory()`；2) modal 打开/刷新时同时刷新 history；3) timeline 数据源只走 `/kairos/history`。不要在这一步追求最终 DOM card 细节，先保证数据链路正确。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py -q</automated>
  </verify>
  <acceptance_criteria>
    - 前端能真实拉取并显示 history payload。
    - `recent_events` 仍然只服务 recent snapshot。
    - history 数据链路已经 ready。
  </acceptance_criteria>
  <done>timeline 已经不再是静态容器，而是活的数据面板。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4B: Upgrade live-state rendering from dump to cockpit cards</name>
  <read_first>
    - src/adk_agent/static/index.html
    - src/adk_agent/static/script.js
    - docs/superpowers/plans/2026-04-09-kairos-phase-4a-visual-brief.md
    - tests/kairos/test_frontend_script_kairos_ui.py
  </read_first>
  <files>src/adk_agent/static/index.html, src/adk_agent/static/script.js, tests/kairos/test_frontend_script_kairos_ui.py</files>
  <behavior>
    - Test 1: overview/controls render hooks exist.
    - Test 2: current-state renderer has a dedicated overview helper.
    - Test 3: status rendering can evolve away from a single plain text dump.
  </behavior>
  <action>把左栏逐步从纯文本 status dump 推向 cockpit cards。具体目标：1) 新增 `kairosOverviewCard` / `kairosControlsCard` 等容器；2) 增加 `formatKairosOverview(kairos)`；3) 为 pills/metrics/stage summary 的更细渲染留挂点。不要一次性推翻所有旧 formatter，先让新 overview path 可叠加。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py -q</automated>
  </verify>
  <acceptance_criteria>
    - 左栏已有 overview render hook，可承载 pills + metrics。
    - 旧 formatter 仍可作为兼容 fallback。
    - live snapshot 正朝“驾驶舱”而不是“文本 dump”演进。
  </acceptance_criteria>
  <done>左栏 current-state 体验被拆出清晰演进路径，便于后续细化。</done>
</task>


<task type="auto" tdd="true">
  <name>Task 5: Prove the surface with real todo-delivery history evidence</name>
  <read_first>
    - tests/kairos/live_http_kairos_demo_outputs_regression.py
    - tests/kairos/test_live_http_kairos_demo_outputs_regression.py
    - docs/superpowers/specs/2026-04-09-kairos-phase-4-design.md
  </read_first>
  <files>tests/kairos/live_http_kairos_demo_outputs_regression.py, tests/kairos/test_live_http_kairos_demo_outputs_regression.py</files>
  <behavior>
    - Test 1: live helper fetches both current status and history payload for a todo delivery session.
    - Test 2: history contains evidence of follow-up creation and task completion, not just status existence.
    - Test 3: source-level wrapper tests assert that history/timeline expectations remain in the regression helper.
  </behavior>
  <action>扩展现有 todo delivery live regression，使其在 final status 之外再 fetch `/kairos/history`，并断言 history entries 能证明 Kairos 真正推进过 workflow。具体目标：1) 添加 `_fetch_kairos_history()` helper；2) 在 `run_todo_delivery_pipeline()` 中断言 history 至少包含 `follow_up` 或 `task_completion` evidence，且能看到 todo delivery report 相关消息；3) 更新 wrapper tests 锁定这些断言存在。不要把 live regression 改成只验证字段 presence，要验证“历史能证明 Kairos 做过工作”。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q</automated>
  </verify>
  <acceptance_criteria>
    - live regression 同时覆盖 current status 与 history timeline。
    - history 中能看到 follow-up/task-completion 这类工作证据。
    - wrapper tests 锁住 history surface，不让 4A 之后回退成只有 status 没有 timeline。
  </acceptance_criteria>
  <done>4A 的“证据可见性”已经有 live todo delivery session 的真实回归支撑。</done>
</task>

</tasks>

<verification>
- 先跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_activity_log.py tests/kairos/test_api.py -q` 锁定 backend history reader + API。
- 再跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py -q` 锁定 split layout 与 timeline wiring。
- 最后跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`；若服务已启动，再执行 live helper 完整回归。
</verification>

<success_criteria>
- session-scoped history API 可稳定返回 timeline entries。
- KAIROS modal 能同时展示 current state 与 history timeline。
- 真实 todo delivery session 能证明 Kairos 创建 follow-up、完成任务与发出关键 brief 的历史证据对 operator 可见。
</success_criteria>

<output>
After completion, create `.planning/phases/04A-explainability-history-ux/04A-01-SUMMARY.md`
</output>

# Phase 04B: Goal-Driven Planning Intelligence - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4B 的目标是在 4A 已完成的可见性与 operator UX 基础上，把 Kairos 从“规则驱动续推 + 有限主动性”升级为“可见地比较候选动作、选择赢家、记录 rejected reasons，并在条件变化时显式 re-plan 的 planning runtime”。

本 phase 聚焦的是 planning intelligence 的状态模型、planning artifact、re-plan 触发与 operator-facing trace，不重新打开 Phase 3 的自治边界争论，也不把系统推向完全自由的 LLM orchestration。

</domain>

<decisions>
## Implementation Decisions

### 候选模型
- **D-01:** 4B 最小可落地版本采用**固定小集合候选动作**，不做开放式或可无限扩展的 planner。
- **D-02:** 最小候选集合先收敛为：`continue_workflow`、`create_follow_up`、`emit_brief`、`ask_user`、`sleep`、`blocked`。
- **D-03:** 候选动作采用用户最终确认的**三层等级**：高=`ask_user` / `blocked`；中=`create_follow_up` / `continue_workflow`；低=`emit_brief` / `sleep`。
- **D-04:** 新候选只有在**明确高一个等级**时，才允许推翻当前 winner；4B 不采用纯 numeric priority 驱动的频繁抖动式切换。

### 规划产物
- **D-05:** `last_planning_result` 在 4B 中必须从占位字段升级为真实 planning artifact，并至少包含：`ts`、`goal`、`workflow_id`、`stage_id`、`candidates_considered`、`selected_candidate`、`rejected_candidates`、`final_action`、`policy_note`。
- **D-06:** rejected candidates 采用**中等粒度**记录：不仅保留 rejected reason，还保留类似 `priority` / `blocked` / `policy_note` 这类足以解释“为什么没选”的字段。
- **D-07:** 4B 不要求保存完整 deliberation transcript；planning artifact 应可解释、可测试、可在 UI/API 中稳定展示，但不能演变成大段内部思维流原文。

### Re-Plan 触发
- **D-08:** 最小版 re-plan 不只覆盖 cooldown / artifact / verification / blocked 等硬触发，还允许在**出现更高价值候选**时显式触发 re-plan。
- **D-09:** “更高价值候选”采用离散等级跃迁语义，而不是连续分数比较；只有明确跨等级时才触发 winner 切换。
- **D-10:** re-plan 必须成为显式状态转移和可观察事件，而不是仅让 operator 从结果倒推“系统可能重新想过了”。

### Operator 可见 trace
- **D-11:** 4B 的 operator-facing 决策语气偏**较完整轨迹**：要让用户能看到考虑了什么、选了什么、为什么没选别的、为什么停住/睡眠/ask_user，但不暴露完整 chain-of-thought。
- **D-12:** planning trace 采用**双面都强**的展示策略：当前状态/API 中展示当前 planning result 与当前 winner；history timeline 中记录显著 planning / re-plan 事件，形成可回放轨迹。
- **D-13:** history timeline 只记录**显著 planning 事件**，至少包括：选出新 winner、winner 被更高等级候选推翻、进入 `ask_user` / `blocked` / `sleep`、发生显式 re-plan；不记录每次 scan / 每次 planning 评估。

### Claude's Discretion
- 候选对象的精确字段名与 JSON 组织方式
- `policy_note`、`rejected_reason`、`selected_reason` 的具体文案模板
- 当前状态面板里 planning artifact、winner、rejected 摘要的卡片编排顺序
- history timeline 中 planning 事件 title/message 的精确措辞
- 在不违背三层等级规则前提下，如何把现有 `priority` 字段保留为辅助排序信息

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Approved phase direction
- `docs/superpowers/specs/2026-04-09-kairos-phase-4-design.md` — Phase 4 的权威设计文档，定义 4A/4B split、4B deliverables、acceptance criteria 与 scope boundaries
- `.planning/ROADMAP.md` — 当前 phase 列表与 4A/4B 的高层路线定义
- `.planning/STATE.md` — 当前主线状态，确认 4A-01 已完成、当前自然下一步是进入 4B planning

### Project constraints and requirements baseline
- `.planning/PROJECT.md` — 核心价值、当前 active requirement、guardrail 原则与“不做完全自由 LLM orchestration”的项目级边界
- `.planning/REQUIREMENTS.md` — 既有 v1/v2 requirement 基线；4B 规划应在现有自治与可观测性能力上继续增强，而不是改写旧 requirement 历史

### Prior phase decisions that carry forward
- `.planning/phases/03-policy-hardening-verification/03-CONTEXT.md` — 已锁定“智能 + 规则协同”“unfinished-work scan”“assistant-mode contract”“last_planning_result 可作为独立持久化对象”的方向
- `.planning/phases/04A-explainability-history-ux/04A-CONTEXT.md` — 已锁定 history archive / status state 分层、operator console 双栏、timeline rail 与 additive API/UI 扩展方式，4B 必须复用这些观测面
- `.planning/phases/02-artifact-aware-reporting-visibility/02-CONTEXT.md` — 已锁定 API/UI additive 扩展与 recent events / summary / blocked reason 的职责边界

### Source-of-truth code anchors
- `src/adk_agent/kairos/models.py` — 当前 `KairosState` 已包含 `proactive_candidates`、`last_proactive_scan`、`last_guardrail_block`、`last_planning_result` 等 4B 关键状态锚点
- `src/adk_agent/kairos/continuation.py` — 当前 unfinished-work refresh、候选构造、cooldown guardrail 与 `planned_actions` 生成逻辑，是 4B candidate / re-plan 演进主入口
- `src/adk_agent/kairos/runtime.py` — 当前 `get_status()` 输出 planning-related state，是 4B API/UI 暴露 planning artifact 的运行时锚点
- `src/adk_agent/kairos/api.py` — 当前 `/kairos/status` additive mirrors 的 API 锚点
- `src/adk_agent/static/script.js` — 当前 operator console 已渲染 `planned_actions`、`proactive_candidates`、`last_planning_result`、history timeline，是 4B trace UI 的直接前端接线点
- `src/adk_agent/main_web_start_steering.py` — 当前 Kairos turn prompt 与宿主边界，4B planning intelligence 仍需保持 host callback / orchestrator 结构

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/adk_agent/kairos/models.py` 已经在 `KairosState` 中预留 `proactive_candidates`、`last_proactive_scan`、`last_guardrail_block`、`last_planning_result`，4B 可以升级这些字段而不必新开平行状态面。
- `src/adk_agent/kairos/continuation.py::refresh_unfinished_work()` 已会构造最小 `proactive_candidates` 和 `last_proactive_scan`，适合作为多候选与 winner-selection 的第一落点。
- `src/adk_agent/kairos/runtime.py::get_status()` 已把 planning-related 字段暴露给 status payload，适合继续增强为真实 planning artifact 输出面。
- `src/adk_agent/static/script.js` 已有 `formatKairosPlannedActions()`、`formatKairosGuardrailState()`、`formatKairosHistoryTimeline()`，并在 modal 打开时并行拉取 status + history，说明 4A 已为 4B trace 可视化铺好 UI 接线。

### Established Patterns
- Kairos 当前状态继续走 `session.state["kairos"]` 的 state-only persistence；历史轨迹继续走 archive + history API 分层，4B 不能把 planning history 再塞回 state 作为无限增长日志。
- 项目已经明确采用 rule guardrails + agent intelligence 协同路线，4B 要增强 planning intelligence，但不能退化为完全自由的 unconstrained planner。
- 前端当前是 additive console 强化路径：保留现有 DOM / formatter / API 契约，按卡片和 timeline 增量升级，不做前端架构迁移。
- 4A 已经把当前状态面和历史时间线面拆开，因此 4B 最适合采用“当前 planning result + 显著 planning history 事件”双面展示，而不是让单一面板承担全部语义。

### Integration Points
- `src/adk_agent/kairos/continuation.py` 需要把当前最小 `proactive_candidates` 升级为固定小集合候选动作、winner selection、rejected candidates 与显式 re-plan 逻辑。
- `src/adk_agent/kairos/models.py` 需要把 `last_planning_result` 从空 dict 升级为稳定、可测试的 artifact shape。
- `src/adk_agent/kairos/runtime.py` / `src/adk_agent/kairos/api.py` 需要把新的 planning artifact 通过 status/API mirrors 暴露给 operator console。
- `src/adk_agent/kairos/activity_log.py` 与 history route/formatter 需要承接“显著 planning 事件”写入与 timeline 展示，但保持只记录显著事件而非每次 scan。
- `src/adk_agent/static/script.js` / `index.html` / `style.css` 需要把 planning artifact、winner、rejected summary、re-plan trace 融入现有 4A console，而不是另起一套可视化体系。

</code_context>

<specifics>
## Specific Ideas

- 4B 最小版的核心不是“更会想”，而是“明确留下：考虑了什么、选了什么、为什么没选、为什么重规划”。
- 用户明确偏好从**最小可落地版本**起步：先把小集合候选动作、真实 planning artifact、显著 re-plan 事件、UI/history trace 打通，再考虑后续泛化。
- 用户明确接受“更高价值候选出现时触发 re-plan”，但要求只有**明确高一个等级**时才能推翻当前 winner，避免系统像分数抖动器。
- 用户明确要求 planning trace 在**当前状态**与**历史时间线**两面都要强，而不是只在 status 或 history 其中一个面可见。
- 用户明确要求 operator-facing 风格偏**较完整轨迹**，但不接受完整思维流直出。

</specifics>

<deferred>
## Deferred Ideas

- 开放式或无限可扩展的 candidate taxonomy / 通用 planner
- 每次 planning scan 都写入 timeline 的高噪声 trace 模式
- 纯 numeric score 驱动的 winner 抖动式切换机制
- 完整 deliberation transcript / chain-of-thought 持久化与展示
- generalized repo-wide autonomous work discovery、supervisor/worker 重构、external notifications 等已在更早 phase 中明确延后能力

</deferred>

---

*Phase: 04B-goal-driven-planning-intelligence*
*Context gathered: 2026-04-10*

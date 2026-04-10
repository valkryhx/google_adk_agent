# Phase 4A: Explainability, History & Operator UX - Context

**Gathered:** 2026-04-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4A 的目标不是继续增强“Kairos 是否会自动推进”，而是把已经存在的自治行为变成 operator 可见、可解释、可回放的历史与当前状态体验。这个 phase 聚焦三件事：把 `memory_archive/..._kairos.md` 暴露成 session-scoped history API；把 history 归一成前端可直接消费的 timeline 结构；把当前单列、过长的 KAIROS modal 重构成左右并列的 operator console。

4A 不负责引入更强的多候选 planning intelligence，也不重新打开 Phase 3 的 continuation/policy 语义争论。它是 visibility-first phase，要为 4B 的 planning trace 打可观测基础。

</domain>

<decisions>
## Implementation Decisions

### 历史与当前状态的职责分离
- **D-01:** 4A 明确区分 current runtime state 与 archived history：`/kairos/status` 继续负责“现在发生什么”，新 history API 负责“之前发生了什么”。
- **D-02:** history API 必须直接读取 `memory_archive/..._kairos.md`，而不是复用 `recent_events` 作为伪历史来源。
- **D-03:** `recent_events` 仍保留 lightweight recent snapshot 角色；完整 timeline 来自 archive reader，不与 `recent_events` 混用。

### Timeline 语义模型
- **D-04:** timeline entry 要成为前端直接消费的结构化对象，至少包含 `ts`、`kind`、`title`、`message`，并允许附带 workflow/stage/task linkage metadata。
- **D-05:** history reader 要负责把 archive markdown 中的原始 entry 转成稳定的 typed event kinds（如 `status`、`brief`、`follow_up`、`task_completion`、`guardrail`），不要把分类逻辑丢给前端字符串猜测。
- **D-06:** timeline 默认服务“证明 Kairos 做过什么工作”，所以 title/summary 必须偏 operator 可扫描表达，而不是原样回放整段日志。

### API 设计
- **D-07:** 新增 history route 采用 additive 策略：保留现有 `/api/sessions/{session_id}/kairos/status` 合约，再增加 session-scoped history endpoint，避免打破现有前端与 live 验证路径。
- **D-08:** history API 最小查询维度为 `session_id + app_name + user_id`，并支持前端切换升序/降序读取。
- **D-09:** attach/list summary 只做轻量扩展；完整 timeline 仍通过专门 history endpoint 拉取，避免 attach payload 过重。

### Operator UX / 前端布局
- **D-10:** 当前 KAIROS modal 从单列长表单重构为左右两列：左侧 live snapshot，右侧 timeline/history，同时保留 start/stop/wake/refresh 等 controls。
- **D-11:** UI 视觉方向是 dense operator console，而不是 debug dump：更强卡片分组、更清晰层级、更可扫描的 timeline，但不引入新前端框架。
- **D-12:** 前端仍沿用 `index.html + script.js + style.css` 现有模式；本 phase 通过 DOM 结构、formatter、样式增强完成，不做前端架构迁移。

### 测试与证据
- **D-13:** 4A 必须同时补 API 契约测试与前端 source-level 结构测试，锁定 history route、timeline formatter、split-layout DOM。
- **D-14:** live / semi-live regression 至少要证明一个真实 todo delivery session 能同时暴露 current state + timeline evidence，而不是只验证字段存在。
- **D-15:** `private_key.yaml` 仍视为 local-only drift，任何 4A 相关提交或计划都不能把它纳入 staged files。

### Claude's Discretion
- history markdown parser 的实现形态（在 `activity_log.py` 中扩展还是增加 reader helper）
- timeline entry title 的精确生成规则
- 左右布局里各卡片的摆放顺序与视觉分组
- history API 的具体字段名（只要保持稳定、可测试且前后端一致）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Approved Phase 4 direction
- `docs/superpowers/specs/2026-04-09-kairos-phase-4-design.md` — 4A/4B split、scope、acceptance criteria 的权威设计文档
- `.planning/HANDOFF.json` — 当前主线已经切到 4A，且明确要求从 `main` 出发，不重开旧 Phase 3 worktree 流程
- `.planning/phases/03-policy-hardening-verification/.continue-here.md` — 为什么当前工作重点已经从“做完 Phase 3”转向“让 Kairos visibly explain itself”

### Current project planning state
- `.planning/STATE.md` — 当前 focus、session continuity 与 local drift 注意事项
- `.planning/MILESTONES.md` — milestone 已切到 v1.1 Kairos Phase 4
- `.planning/ROADMAP.md` — 4A/4B phase 定义与高层成功标准
- `.planning/REQUIREMENTS.md` — 现有 requirement 基线；4A 可在实现完成后补充新的 explainability/history traceability requirement

### Existing baseline and relevant prior phase context
- `.planning/phases/02-artifact-aware-reporting-visibility/02-CONTEXT.md` — Phase 2 已锁定“current summary / blocked reason / recent events”语义边界，4A 需要在此之上扩历史与 operator UX
- `.planning/phases/03-policy-hardening-verification/03-CONTEXT.md` — Phase 3 已锁定 proactive/policy state 与 assistant-mode 观测面，4A 不能推翻这些状态语义

### Source-of-truth code anchors
- `src/adk_agent/kairos/activity_log.py` — 当前 archive 写入格式与 `memory_archive` 路径约定
- `src/adk_agent/main_web_start_steering.py` — 当前 `_append_kairos_log()` 调用入口，说明 archive 记录何时写入
- `src/adk_agent/kairos/api.py` — 当前 `/kairos/status`、attach/list routes 与 additive API 扩展落点
- `src/adk_agent/kairos/runtime.py` — 当前 runtime status payload 生成位置
- `src/adk_agent/kairos/attach.py` — session summary 轻量输出基线
- `src/adk_agent/static/index.html` — 当前单列 modal 结构
- `src/adk_agent/static/script.js` — 当前 formatter / refreshKairosStatus 流程
- `src/adk_agent/static/style.css` — modal / panel 样式基线
- `tests/kairos/test_activity_log.py` — 当前 archive writer 测试基线
- `tests/kairos/test_api.py` — 当前 KAIROS API route 测试基线
- `tests/kairos/test_frontend_script_kairos_ui.py` — 当前前端 source-level KAIROS UI 测试基线
- `tests/kairos/live_http_kairos_demo_outputs_regression.py` — todo delivery live evidence 基线

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `KairosActivityLog.append_entry()` 已经稳定把事件写入 `memory_archive/<user>/<YYYY-MM>/<date>_<app>_<session>_kairos.md`，frontmatter 中已包含 `user_id` / `app_name` / `session_id`，适合作为 history reader 的直接数据源。
- `main_web_start_steering.py::_append_kairos_log()` 已在每次 event emission 时同步写 archive，说明真实运行 session 已经有可用历史证据，不需要额外补采集链路。
- `runtime.py::get_status()` 已暴露 workflow / planned actions / blocked reason / task summaries / proactive fields，可作为左侧 live snapshot 数据底座。
- `api.py` 当前采用 additive mirror 风格，适合继续新增 history endpoint 而不破坏 `/kairos/status`。
- `script.js` 已有集中式 `refreshKairosStatus()` 与 formatter helpers，适合补 timeline fetch/render 与 split layout 更新。
- `style.css` 已有 modal 基础样式，但当前 `.modal-content` 和 `.modal-body` 仍是窄宽度单列布局，确实支撑不了 dense operator console。

### Established Patterns
- KAIROS 状态与 archive 分离：state 走 `session.state["kairos"]`，history 走 `memory_archive` append-only 文件；4A 应延续这种“当前状态 vs 历史”分层，而不是把 archive 再塞回 state。
- 前端 KAIROS 面板目前依赖 source-level DOM id + formatter tests；4A 的布局重构应继续走可 grep / 可断言的静态结构，而不是引入隐式模板系统。
- API / UI 回归通常采用“source-level + live helper”双证据链；4A 也应保留这种可快速回归的模式。

### Integration Points
- `activity_log.py` 需要新增 history reader / parser，使 archive markdown 能转成 timeline entry objects。
- `api.py` 需要新增 history route，并可能轻量扩充 attach summary，让 session 列表或面板入口知道 history 是否可用。
- `script.js` 需要在现有 refresh 路径外增加 history fetch，并在 modal 打开或状态刷新后同步渲染右侧 timeline。
- `index.html` / `style.css` 需要一起完成 modal 双列布局，保证 controls、snapshot cards、timeline cards 能在常规 viewport 下同时可读。
- `tests/kairos/test_activity_log.py`、`test_api.py`、`test_frontend_script_kairos_ui.py`、`test_live_http_kairos_demo_outputs_regression.py` 是 4A 最关键的 regression anchors。

</code_context>

<specifics>
## Specific Ideas

- timeline 里应优先显式展示“registered Dex task / completed Dex task / auto-created follow-up / guardrail block / waiting_input transition / brief emission”等真正证明 Kairos 做过工作的事件。
- 右侧 timeline 不应只是 `recent_events` 的扩容，而应来自 archive reader 的 session history。
- 左侧 current snapshot 至少保留：运行状态、active workflow、planned actions、blocked/guardrail、unfinished/proactive 状态、result summary/decision explanation。
- 两列 layout 在桌面端应同时可见；在更窄 viewport 下可以退化为纵向堆叠，但不能让主要信息彻底掉到 fold below。
- 4B 相关的 multi-candidate planning result 只需要为未来 UI 留承载位置，不在 4A 里预实现 planning logic。

</specifics>

<deferred>
## Deferred Ideas

- richer candidate model / selected vs rejected candidate trace
- real `last_planning_result` 结构升级与 re-plan triggers
- attach continuity / supervisor-worker 架构改造
- generalized repo-wide autonomous work discovery
- external notifications / webhook / memory distill

</deferred>

---
*Phase: 04A-explainability-history-ux*
*Context gathered: 2026-04-09*

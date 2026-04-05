# Phase 2: Artifact-Aware Reporting & Visibility - Context

**Gathered:** 2026-04-06
**Status:** Ready for planning

<domain>
## Phase Boundary

让 KAIROS 不只知道 task 完成，还能解释结果、展示 workflow 与下一步，并把 blocked reason 对用户可见化。这个 phase 聚焦 artifact-aware reporting 与可视化增强，不新增 push/channel/webhook 等新能力，也不扩展到完整 policy hardening。

</domain>

<decisions>
## Implementation Decisions

### 结果摘要
- **D-01:** Phase 2 采用结构化结果摘要，但字段比最小版更丰富；不能只停留在 `completed/failed` 文本。
- **D-02:** 每条任务摘要应至少包含扩展字段集合：任务状态、`result_summary` / `error_summary`、artifact 相关信息、必要的日志定位提示；允许比四要素摘要更丰富，但不直接塞入大段原始日志。
- **D-03:** 失败任务默认展示“错误摘要 + 去哪里看日志/产物”的排查指引，而不是原样回显长错误栈。

### ��塞与可解释性
- **D-04:** blocked / waiting_input 采用三段式可解释表达：为什么继续、为什么停住、还缺什么。
- **D-05:** 当进入 blocked / waiting_input 时，要把缺失条件展示到完整条件树级别，而不是只给一句 blocked reason。
- **D-06:** 继续沿用 Phase 1 的 rule-based continuation 边界；可解释性增强是把已有决策显性化，不引入新的自由规划能力。

### 前端可视化
- **D-07:** 保留现有 `Active Workflow`、`Planned Actions`、`Blocked Reason` 三个区块，并新增或补强专门的结果摘要区，而不是把全部自治信息揉成单一总览区。
- **D-08:** `recent_events` 保持时间线角色；结果摘要区负责当前结果总览，避免时间线与摘要区重复堆相同内容。
- **D-09:** 前端应继续优先服务调试与 live 验证，确保用户无需翻 `.dex/tasks/*.json` 就能理解当前自治状态与最近产出。

### API 扩展
- **D-10:** 状态 API 采用兼容增强策略：保留现有 `kairos` payload 和顶层 mirrors，同时新增更明确的摘要/决策字段，便于前端渐进接入。
- **D-11:** 新增 API 字段应优先表达“当前结果摘要”“当前决策解释”“当前缺失条件”，而不是单纯镜像更多内部状态。
- **D-12:** API 输出与 UI 展示要共用同一套语义模型，避免 recent events、summary 区、status 字段各说各话。

### Claude's Discretion
- 结果摘要对象的精确字段名与嵌套结构
- 前端摘要区的具体摆放顺序、文案和视觉层次
- 完整条件树在 API 中的编码形式（数组 / 对象 / 分组结构）
- recent events 与摘要区之间的去重细节

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone roadmap and acceptance
- `.planning/ROADMAP.md` — Phase 2 goal、scope 与 plan 列表的权威定义
- `.planning/REQUIREMENTS.md` — `RPT-01`、`RPT-02`、`RPT-03` 对应的验收要求与 traceability
- `docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-roadmap-与验收标准.md` §3 — 3B milestone 的 scope、验收标准、主要风险与建议改动范围

### Existing baseline and verification evidence
- `.planning/phases/01-autonomous-continuation-mvp/01-CONTEXT.md` — Phase 1 已锁定的 continuation、可视化与宿主边界决策
- `.planning/phases/01-autonomous-continuation-mvp/01-UAT.md` — Phase 1 已验证通过的用户可见行为基线
- `docs/实现phase-2的kairos/KAIROS-phase-2-实现进度.md` — phase-2 既有 runtime / attach / handoff / UI 基线能力
- `docs/实现phase-2的kairos/2026-04-05-KAIROS-测试设计说明.md` — 分层测试证据链与 live demo 验证方式

### Source-of-truth code anchors
- `src/adk_agent/kairos/runtime.py` — 当前 runtime status、tracked task snapshot 与 recent events 生成位置
- `src/adk_agent/kairos/api.py` — 当前 `/kairos/status` 响应形状与顶层 mirrors
- `src/adk_agent/static/index.html` — 当前 KAIROS 面板区块结构
- `src/adk_agent/static/script.js` — 当前 workflow / planned actions / blocked reason / recent events 渲染逻辑

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/adk_agent/kairos/runtime.py` — 已经把 `tracked_dex_tasks` 暴露为带 `result_summary` / `error_summary` 的快照，可直接作为 artifact-aware summary 的数据底座。
- `src/adk_agent/kairos/api.py` — 已有 `kairos` payload + `active_workflow` / `planned_actions` / `blocked_reason` 顶层镜像，适合走兼容增强。
- `src/adk_agent/static/script.js` — 已有 `formatKairosTrackedTasks()`、`formatKairosWorkflow()`、`formatKairosPlannedActions()`、`formatKairosEvents()`，可在现有 formatter 基础上扩结果摘要与解释展示。
- `src/adk_agent/static/index.html` — 已有 KAIROS modal 的自治状态展示骨架，可在不推翻布局的前提下增加摘要区。

### Established Patterns
- KAIROS 状态仍通过 `session.state["kairos"]` 持久化，新增 reporting/visibility 字段应继续遵守 state-only persistence 路径。
- 当前前端采用“独立文本区块 + formatter”模式渲染自治状态，因此新增摘要/解释更适合复用 formatter 扩展，而不是引入全新交互范式。
- recent events 已承担时间线职责；Phase 2 明确继续保留该角色，不把它改造成结果详情面板。

### Integration Points
- `src/adk_agent/kairos/runtime.py` 的 `get_status()`、`_poll_dex()` 与事件记录逻辑是引入 richer summary / blocked explanations 的主入口。
- `src/adk_agent/kairos/dex_bridge.py` 是扩充 artifact 信息与日志定位信息的桥接点。
- `src/adk_agent/kairos/api.py` 的 status route 是新增兼容字段与 summary mirrors 的输出面。
- `src/adk_agent/static/script.js` / `index.html` 是前端继续沿用三区 + 摘要区布局的主要接线点。

</code_context>

<specifics>
## Specific Ideas

- 用户明确希望结果摘要是“结构化但字段更丰富”的版本，而不是极简四要素卡片。
- 用户明确希望 `recent_events` 继续做时间线，摘要区单独承担“当前结果总览”。
- 用户明确希望 blocked / waiting_input 展示到完整条件树粒度，而不是一句话原因。
- 用户明确希望 API 扩展保持兼容，不要推翻当前 `kairos` payload + top-level mirrors 的消费方式。

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---
*Phase: 02-artifact-aware-reporting-visibility*
*Context gathered: 2026-04-06*

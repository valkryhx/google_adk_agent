# Phase 1: Autonomous Continuation MVP - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

让 KAIROS 在 staged workflow 的输入任务完成后，能够自动发现下一步并自动创建/接管 report follow-up Dex task。这个 phase 的目标是完成最小自治闭环，不做完整 supervisor 重构，也不把所有 follow-up 规划都交给 LLM。

</domain>

<decisions>
## Implementation Decisions

### 自治策略
- **D-01:** Phase 1 采用**混合模式**：规则引擎负责自治边界与是否允许继续；LLM 可以参与解释与部分 follow-up 判断，但不能绕过规则护栏。
- **D-02:** 规则护栏至少包括：触发条件明确、重复续推去重、自动步数上限、缺条件即 blocked/waiting_input、关键决策可解释。
- **D-03:** LLM 在 Phase 1 中不主导自由规划；它主要负责 brief、解释、总结，以及在规则允许的范围内参与 continuation reasoning。

### 状态模型
- **D-04:** Phase 1 采用**最小模型**，显式引入：`active_workflow`、`stages`、`planned_actions`、`blocked_reason`、`policy`。
- **D-05:** Phase 1 不要求一开始就做完整 workflow memory / continuation history / retry orchestration；这些属于后续 phase。
- **D-06:** workflow 状态必须足以表达当前处于哪个 stage、为什么继续、为什么停住，以及下一步 planned action 是什么。

### 执行入口
- **D-07:** 自动创建 report follow-up 的执行入口由 **SteeringSession 宿主回调** 提供；runtime/continuation engine 不应直接散乱 import DexManager 自己执行。
- **D-08:** follow-up 创建后应由宿主层统一完成 Dex task 创建与 handoff 注册，保持执行边界清晰并避免宿主污染。

### 可视化与可观测性
- **D-09:** Phase 1 就要做**完整展示**：至少在 status/API 和前端面板上显示 workflow、planned actions、blocked reason。
- **D-10:** 当前 phase 不接受“只在后端可见、前端后置”的策略，因为 Phase 1 需要直接支撑调试与 live 验证。
- **D-11:** `recent_events` 不再只承担状态回显，还应配合 workflow/planned actions 呈现为什么继续、为什么停住。

### Claude's Discretion
- continuation engine 的内部类名、函数名与文件拆分细节
- workflow template 的具体表示形式（dataclass / dict）
- 前端具体布局、字段排版与文本格式
- LLM 参与 continuation reasoning 的 prompt 细节

</decisions>

<specifics>
## Specific Ideas

- 规则护栏的直觉定义：LLM 决定“怎么表达”和“怎么总结”，规则决定“什么时候能继续、什么时候必须停、什么时候不能重复做”。
- 当前 phase 最关键的成功信号：在 live HTTP demo 中，不再由人手工注册 report task，而是 KAIROS 自己发现 phase-1 已收敛，并自动推进 report 阶段。
- staged workflow 仍以现有 `sales/traffic/quality -> report` 作为第一闭环，不在本 phase 扩展更多 workflow template。

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase-3 vision and roadmap
- `docs/实现phase-3的kairos/INDEX.md` — 本轮 phase-3 文档索引与统一结论
- `docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-演进思考.md` — 为什么 phase-3 的核心是 continuation，而不是继续做观察
- `docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-roadmap-与验收标准.md` — 3A/3B/3C 路线与 milestone acceptance
- `docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-下一步行动清单.md` — 第一轮开工建议

### Implementation shape
- `docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-实施计划-第一版.md` — Runtime orchestration + rule-based Continuation Engine + workflow-aware state
- `docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-精确代码改造清单.md` — Phase 1 需要新增/修改的精确文件清单
- `docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-测试矩阵.md` — runtime / integration / live-http / frontend 四层验证建议

### Existing phase-2 baseline
- `docs/实现phase-2的kairos/2026-04-04-kairos-live-demo-design.md` — 当前 staged workflow demo 语义
- `docs/实现phase-2的kairos/2026-04-05-KAIROS-测试设计说明.md` — 现有分层验证策略
- `docs/实现phase-2的kairos/KAIROS-phase-2-实现进度.md` — 当前 phase-2 已落地能力与边界

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/adk_agent/kairos/runtime.py` — 已有 tick/schedule/handoff/poll 主循环，是 continuation 接入的主锚点
- `src/adk_agent/kairos/models.py` — 已有 KairosState / KairosTrigger / KairosSchedule，可在此基础上扩 phase-3 状态模型
- `src/adk_agent/main_web_start_steering.py` — `run_kairos_turn()` 与 `get_or_create_kairos_runtime()` 是宿主层接线点
- `skills/dex/tools.py` — 已有 DexManager、dex_create/start/list/get_details，可作为 follow-up 执行基础能力
- `tests/kairos/test_runtime.py` — 已有 staged workflow convergence 语义测试，可扩成 auto-follow-up 回归

### Established Patterns
- KAIROS state 通过 `session.state["kairos"]` 持久化，且必须走 state-only 路径
- KAIROS turn 通过 sandbox turn 执行，不污染用户 history
- Dex 真实任务与 live HTTP regression 已经存在，适合直接升级为 phase-3 闭环证据

### Integration Points
- `runtime.py::_poll_dex()` 后适合接 continuation evaluation
- `main_web_start_steering.py::run_kairos_turn()` 适合注入 workflow/planned action 上下文
- `main_web_start_steering.py::get_or_create_kairos_runtime()` 适合挂 continuation engine 与宿主 callback
- `script.js` 与 `api.py` 适合作为 workflow / planned actions / blocked reason 的观测面

</code_context>

<deferred>
## Deferred Ideas

- 完整 supervisor / worker 多进程重构
- webhook / GitHub / channels / push notification 驱动的 continuation
- 多 workflow template 并行支持
- nightly memory distill / dream
- 完整 workflow memory / continuation history / retry orchestration

</deferred>

---
*Phase: 01-autonomous-continuation-mvp*
*Context gathered: 2026-04-05*

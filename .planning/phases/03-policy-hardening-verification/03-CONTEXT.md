# Phase 3: Policy Hardening & Verification - Context

**Gathered:** 2026-04-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 不应再被狭义理解为“给 continuation 补几个 policy 选项”，而应被正式定义为：让当前 KAIROS 从“可观测、可自动续推的 runtime”，演进为“在规则护栏约束下，能够持续扫描未完成工作、主动选择下一步、主动 brief/ask-user/sleep，并长期推进复杂任务的 autonomous assistant mode runtime”。

这意味着 Phase 3 的目标已经不只是验证一次自动续推闭环，而是把前两个 phase 的 runtime、workflow、reporting 与验证基座，推进成更接近 Claude Code KAIROS assistant mode 的长期自治执行层。

当前 phase 的重点包括：
- 让主动性从 event-driven continuation 升级为 unfinished-work scanning
- 让 tick/wake/sleep 形成正式的 assistant-mode 合约
- 让 agent intelligence 在规则护栏内参与 next-step selection，而不是只做 lightweight brief
- 让去重、限步、blocked/waiting_input、policy state 成为一等可观测对象

</domain>

<decisions>
## Implementation Decisions

### 总体方向
- **D-01:** Phase 3 采用 **智能 + 规则协同** 路线，而不是二选一。规则负责 guardrails 与可验证边界，agent intelligence 负责主动发现未完成工作、判断下一步、决定 brief / ask-user / sleep。
- **D-02:** 当前 phase 不把 deterministic continuation 视为最终目标，而视为长期自治 runtime 的起步跑道。
- **D-03:** 当前 phase 仍不引入完整 supervisor / worker 多进程重构；优先在现有 `SteeringSession` + `KairosRuntime` 基础上完成 assistant-mode 语义增强。

### 主动性定义
- **D-04:** Kairos 的 proactive 不应被定义为“主动干完所有事情”，而应被定义为：**持续读取 unfinished work，并在规则允许时主动推动下一步。**
- **D-05:** 第一轮 proactive scan 先聚焦当前 `active_workflow` 的 unfinished stages，并尽快扩展到 blocked but recoverable work items；暂不直接扫描全仓库任意任务。
- **D-06:** tick 的职责不再只是检查 Dex task 是否完成，而应包括：unfinished-work scan、blocked recovery scan、next-step selection、brief necessity check、sleep decision。

### LLM 与规则边界
- **D-07:** 规则层负责：dedupe、cooldown、max auto steps、blocked/waiting_input、artifact/verification gating、policy observability。
- **D-08:** LLM/agent intelligence 负责：解释当前状态、发现值得推进的 unfinished work、在允许空间内选择下一步、决定何时 ask-user / brief / sleep。
- **D-09:** 当前 phase 不允许“让 LLM 自由规划全部后续动作”；任何 agentic planning 都必须在规则护栏与 workflow context 内进行。

### Assistant Mode Contract
- **D-10:** `run_kairos_turn()` 应从 lightweight brief prompt 升级为 assistant-mode tick contract，明确：当前处于长期自治模式、应优先检查 unfinished work、无高价值动作则 sleep、禁止空转状态播报。
- **D-11:** Brief 不是附属输出，而是长期自治的用户契约。Phase 3 必须明确何时主动 brief：阶段推进、关键产物完成、blocked 超阈值、需要用户决策、连续未推进等。
- **D-12:** 当前 phase 的成功信号不再只是一条 follow-up 是否自动创建，而是：Kairos 是否开始表现出“无需新用户 prompt 也会持续检查并推进未完成工作”的 assistant-mode 行为。

### Claude's Discretion
- unfinished-work item 的精确数据结构
- proactive candidate ranking 的编码形式
- brief 类型的具体分类与阈值
- LLM planning result 是否单独持久化为 `last_planning_result`
- policy state 在 status/API/UI 中的字段设计

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### New phase-3 direction
- `docs/实现phase-3的kairos/INDEX.md` — 已同步 2026-04-07 新结论后的总索引与统一结论
- `docs/实现phase-3的kairos/2026-04-07-KAIROS-phase-3-基于-ClaudeCode-源码分析的再定位与推进结论.md` — 当前最重要的方向校准文档
- `docs/探讨claudecode/KAIROS-特性源码分析报告.md` — Claude Code 中 KAIROS 的 assistant mode / tick / brief / daemon / bridge 定位证据

### Prior phase-3 docs (still useful, but must be reinterpreted through the new direction)
- `docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-演进思考.md`
- `docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-实施计划-第一版.md`
- `docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-精确代码改造清单.md`
- `docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-测试矩阵.md`
- `docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-roadmap-与验收标准.md`
- `docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-下一步行动清单.md`

### Current planning and evidence
- `.planning/PROJECT.md` — 项目核心价值与当前 active requirements
- `.planning/REQUIREMENTS.md` — 需重新解释的 v1/v2 requirement 状态
- `.planning/STATE.md` — 当前主线状态与 live HTTP 补验证事实
- `.planning/phases/03-policy-hardening-verification/.continue-here.md` — 当前恢复点与 recent evidence
- `docs/superpowers/plans/2026-04-06-kairos-boss-demo-real-todo-app.md` — richer todo app flow 的实现计划与剩余尾项

### Existing evidence chain already landed on main
- `src/adk_agent/kairos/continuation.py` — 当前 deterministic continuation / gating 入口
- `src/adk_agent/kairos/runtime.py` — tick loop、internal trigger、status、task_summaries、condition_tree、decision_explanation
- `src/adk_agent/main_web_start_steering.py` — host callback、follow-up 执行入口、当前 lightweight kairos turn prompt
- `tests/kairos/test_continuation.py` — continuation 规则层回归
- `tests/kairos/test_runtime.py` — runtime 行为回归
- `tests/dex/test_tools.py` — real Dex todo pipeline 证据
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py` — live HTTP regression；当前仓库已在 8000 端口服务下实测 `4 passed`
- `tests/kairos/live_http_kairos_demo_outputs_regression.py` — current live helper and todo delivery pipeline scenario

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/adk_agent/kairos/runtime.py` 已具备 tick / wake / schedule / handoff / internal trigger 主循环，是 assistant-mode contract 与 proactive scan 的核心落点。
- `src/adk_agent/kairos/continuation.py` 已经承担 deterministic gatekeeper 角色，适合作为后续 guardrail 层继续扩展，而不是推翻重写。
- `src/adk_agent/main_web_start_steering.py::run_kairos_turn()` 已有独立 Kairos turn 通道，可升级为更像 Claude Code assistant-mode 的 tick prompt。
- `src/adk_agent/main_web_start_steering.py::create_kairos_follow_up_task()` 已证明 host callback 模式有效，可继续作为受控执行入口。
- `src/adk_agent/kairos/api.py` 已暴露 `active_workflow`、`planned_actions`、`blocked_reason`、`task_summaries`、`decision_explanation`、`condition_tree`，适合继续扩 policy/proactive observability。
- richer todo app live pipeline 已具备真实产物链、verification gating、blocked-state evidence 和 live HTTP 4-pass 基线，是当前最强 phase-3 验证跑道。

### Established Patterns
- KAIROS state 必须继续走 `session.state["kairos"]` 的 state-only persistence 路径，避免 history duplication 回归。
- long-running work 应继续交给 Dex，Kairos 保持协调者与 orchestrator 身份，而不是自己被阻塞命令拖死。
- 当前 deterministic workflow / gating / live regression 已存在，因此 Phase 3 的下一步不是扩更多 demo，而是让 tick loop 逐步具备主动扫描与主动推进未完成工作的能力。
- current todo pipeline 已经证明：最小自主闭环可以落地；后续重点应从“能否自动 report”转向“能否持续管理 unfinished work”。

### Integration Points
- `runtime.py::tick_once()` 应成为 proactive scan、initiative budget、policy enforcement 的统一节拍入口。
- `runtime.py::_poll_dex()` 之后除了 continuation evaluation，还应逐步接入 unfinished-work refresh / blocked recovery evaluation。
- `main_web_start_steering.py::run_kairos_turn()` 应注入 workflow goal、unfinished work、blocked state、planned actions、policy state、allowed action space。
- `api.py` / frontend 应成为 policy state、proactive scan result、last planning result、last guardrail block 的观测面。

</code_context>

<specifics>
## Specific Ideas

- Kairos 的主动性应先从 `active_workflow` 的 unfinished stages 开始扫描，而不是一开始就读取全仓库所有潜在任务。
- 第一阶段更像“持续工作的执行经理”：不断检查未完成阶段、blocked 项、验证结果与后续动作，而不是自由探索所有可能机会。
- 之后可以再逐步扩展到 blocked but recoverable items、规划文档里的 pending work、甚至更开放的 work queue。
- Brief 应被正式分型，例如：progress brief、blocked brief、decision-needed brief、completion brief、stalled brief。
- 长期自治不等于不停发言；真正的 assistant-mode 语义是：有高价值动作就行动，有高价值信息就 brief，否则 sleep。

</specifics>

<deferred>
## Deferred Ideas

- 完整 supervisor / worker 多进程重构
- remote bridge / attach continuity 的高保真复刻
- GitHub webhook / channels / push notification 接入
- nightly dream / memory distill
- 一开始就扫描全仓库所有潜在任务或让 LLM 自由规划所有 follow-up

</deferred>

---
*Phase: 03-policy-hardening-verification*
*Context gathered: 2026-04-07*

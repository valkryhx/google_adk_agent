# Roadmap: google_adk_agent

## Overview

这个 milestone 聚焦 KAIROS 从“观察 Dex 后台任务状态”向“主动发现下一步并自动续推 workflow”的跃迁。路线分为三个 phase：先做 Autonomous Continuation MVP，证明系统能在 staged workflow 中自动创建 report follow-up；再做 artifact-aware proactive reporting 与前端/API 可视化；最后做 policy hardening 与分层验证，确保自治能力可解释、可测试、不失控。

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Autonomous Continuation MVP** - 引入 workflow-aware state 与 continuation engine，打通自动创建 report follow-up 的最小自治闭环
- [ ] **Phase 2: Artifact-Aware Reporting & Visibility** - 增强结果摘要、blocked reason 与 workflow/planned actions 可视化
- [ ] **Phase 3: Policy Hardening & Verification** - 增加去重、限步、策略观测与完整回归验证，稳固自治能力

## Phase Details

### Phase 1: Autonomous Continuation MVP
**Goal**: 让 KAIROS 在 staged workflow 的输入任务完成后，能够自动发现下一步并自动创建/接管 report follow-up Dex task。
**Depends on**: Nothing (first phase)
**Requirements**: [KAI-01, KAI-02, KAI-03, KAI-04, VER-01, VER-02, VER-03]
**Success Criteria** (what must be TRUE):
  1. 用户不必手工注册每个后续 task，KAIROS 在 phase-1 输入满足时会自动发现并生成下一步动作
  2. staged workflow 中 `sales/traffic/quality` 全部完成后，KAIROS 会自动创建并接管 report follow-up Dex task
  3. follow-up 条件不满足时，KAIROS 会进入 blocked 或 waiting_input，而不是盲目继续或空转
  4. runtime / real Dex integration / live HTTP regression 三层测试证明 report task 已不再依赖人工手工注册
**Plans**: 3 plans

Plans:
- [x] 01-01: 扩展 Kairos 状态模型，加入 workflow / planned actions / blocked reason / policy
- [x] 01-02: 新增 continuation engine 与 workflow template，并接入 runtime 主循环
- [x] 01-03: 接通宿主层 follow-up 执行入口，完成真实 Dex + live HTTP 自动 report 闭环

### Phase 2: Artifact-Aware Reporting & Visibility
**Goal**: 让 KAIROS 不只知道 task 完成，还能解释结果、展示 workflow 与下一步，并把 blocked reason 对用户可见化。
**Depends on**: Phase 1
**Requirements**: [RPT-01, RPT-02, RPT-03]
**Success Criteria** (what must be TRUE):
  1. 用户可以从 KAIROS recent events / status 中看到 task 完成后的结果摘要，而不只是 completed/failed 状态
  2. 用户可以看到 KAIROS 为什么继续、为什么停住，以及当前 blocked reason
  3. 前端面板可以展示 workflow、planned actions、blocked reason 等自治状态
**Plans**: 2 plans

Plans:
- [ ] 02-01: 增强 Dex snapshot/result/log 摘要消费与 artifact-aware proactive brief
- [ ] 02-02: 扩展 API 与前端面板，展示 workflow / planned actions / blocked reason

### Phase 3: Policy Hardening & Verification
**Goal**: 让 phase-3 的自治续推具备去重、限步、策略可观测与稳定回归保障，避免重复续推和失控。
**Depends on**: Phase 2
**Requirements**: [POL-01, POL-02, POL-03]
**Success Criteria** (what must be TRUE):
  1. KAIROS 不会对同一个 workflow 重复创建相同的 follow-up Dex task
  2. KAIROS 的自动续推步数受到策略限制，不会出现无限循环或 runaway autonomy
  3. 开发者可以通过 API 或 status 观察 KAIROS 的关键自治策略状态与决策结果
  4. 分层回归测试能够稳定覆盖去重、限步、blocked/waiting_input 与 live HTTP 自动续推闭环
**Plans**: 2 plans

Plans:
- [ ] 03-01: 实现 continuation history、dedupe、cooldown / max auto steps 等策略护栏
- [ ] 03-02: 补齐 runtime / integration / live-http / frontend 回归矩阵并固化状态观测输出

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Autonomous Continuation MVP | 0/3 | Not started | - |
| 2. Artifact-Aware Reporting & Visibility | 0/2 | Not started | - |
| 3. Policy Hardening & Verification | 0/2 | Not started | - |

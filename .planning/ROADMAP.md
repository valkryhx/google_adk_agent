# Roadmap: google_adk_agent

## Overview

这个 milestone 聚焦 KAIROS 从“观察 Dex 后台任务状态”向“主动发现下一步并自动续推 workflow”的跃迁。路线分为三个 phase：先做 Autonomous Continuation MVP，证明系统能在 staged workflow 中自动创建 report follow-up；再做 artifact-aware proactive reporting 与前端/API 可视化；最后做 policy hardening 与分层验证，确保自治能力可解释、可测试、不失控。

当前 v1.0 路线已经完成。下一步将进入 v1.1，拆成两个连续 phase：先做 `4A`（Explainability, History & Operator UX），解决 Kairos 做了很多事但前端看不清的问题；再做 `4B`（Goal-Driven Planning Intelligence），让 Kairos 在可见、可解释的基础上，显式比较候选动作、留下 planning 痕迹并做更强的目标驱动推进。

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Autonomous Continuation MVP** - 引入 workflow-aware state 与 continuation engine，打通自动创建 report follow-up 的最小自治闭环
- [x] **Phase 2: Artifact-Aware Reporting & Visibility** - 增强结果摘要、blocked reason 与 workflow/planned actions 可视化
- [x] **Phase 3: Policy Hardening & Verification** - 增加去重、限步、策略观测与完整回归验证，稳固自治能力
- [ ] **Phase 4A: Explainability, History & Operator UX** - 让 Kairos 的当前状态与完整推进历史在前端/API 中同时可见，并重构操作面板为高密度可用的左右布局
- [ ] **Phase 4B: Goal-Driven Planning Intelligence** - 在 4A 的可见性基础上，引入多候选 next-step selection、真实 planning result 与可解释的 re-plan 痕迹

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
- [x] 02-01: 增强 Dex snapshot/result/log 摘要消费与 artifact-aware proactive brief
- [x] 02-02: 扩展 API 与前端面板，展示 workflow / planned actions / blocked reason

### Phase 4: Explainability & Planning Intelligence

### Phase 4A: Explainability, History & Operator UX
**Goal**: 让 Kairos 的当前状态与完整推进历史在前端/API 中同时可见，并重构操作面板为高密度可用的左右布局。
**Depends on**: Phase 3
**Requirements**: [4A-HIS-01, 4A-UX-01, 4A-VER-01]
**Success Criteria** (what must be TRUE):
  1. 用户可以通过 session-scoped history API 读取完整 Kairos 历史，而不再只能依赖 `recent_events`
  2. KAIROS 面板可以同时展示 current runtime state 与 history timeline
  3. 历史 timeline 能显示 follow-up 创建、任务完成、guardrail 等工作证据，而不只是状态存在
  4. live todo delivery regression 能同时验证 current status 与 history evidence
**Plans**: 1 plan

Plans:
- [x] 04A-01: 落地 history reader / history API / operator console shell / timeline rail / live history evidence

### Phase 4B: Goal-Driven Planning Intelligence

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Autonomous Continuation MVP | 3/3 | Complete | 2026-04-06 |
| 2. Artifact-Aware Reporting & Visibility | 2/2 | Complete | 2026-04-06 |
| 3. Policy Hardening & Verification | 2/2 | Complete | 2026-04-07 |
| 4A. Explainability, History & Operator UX | 1/1 | In progress | - |
| 4B. Goal-Driven Planning Intelligence | 0/? | Not started | - |

---
*Last updated: 2026-04-10 after completing Phase 4A plan 01 history/operator UX execution*

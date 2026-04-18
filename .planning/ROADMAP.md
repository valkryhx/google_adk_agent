# Roadmap: google_adk_agent

## Overview

这个 milestone 聚焦 KAIROS 从“观察 Dex 后台任务状态”向“主动发现下一步并自动续推 workflow”的跃迁。路线分为三个 phase：先做 Autonomous Continuation MVP，证明系统能在 staged workflow 中自动创建 report follow-up；再做 artifact-aware proactive reporting 与前端/API 可视化；最后做 policy hardening 与分层验证，确保自治能力可解释、可测试、不失控。

当前 v1.0 路线中的 Phase 1-5 已完成。当前推进点为 `6`（Markdown-First Skill-Using Autonomy）：在保留安全边界的前提下，把 Kairos 从 document-aware continuation 推进到 markdown-first、skill-using、LLM-core 的长期自治运行时。

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Autonomous Continuation MVP** - 引入 workflow-aware state 与 continuation engine，打通自动创建 report follow-up 的最小自治闭环
- [x] **Phase 2: Artifact-Aware Reporting & Visibility** - 增强结果摘要、blocked reason 与 workflow/planned actions 可视化
- [x] **Phase 3: Policy Hardening & Verification** - 增加去重、限步、策略观测与完整回归验证，稳固自治能力
- [x] **Phase 4A: Explainability, History & Operator UX** - 让 Kairos 的当前状态与完整推进历史在前端/API 中同时可见，并重构操作面板为高密度可用的左右布局
- [x] **Phase 4B: Goal-Driven Planning Intelligence** - 在 4A 的可见性基础上，引入多候选 next-step selection、真实 planning result 与可解释的 re-plan 痕迹
- [x] **Phase 5: Document-Driven Continuation** - 让 Kairos 从硬编码 workflow 续推器升级为通过提示词协议生成、阅读、更新工作文档的后台常驻 assistant，能够从需求和工作文档中发现、规划、推进未完成任务与新任务
- [ ] **Phase 6: Markdown-First Skill-Using Autonomy** - 把 Kairos 升级为以 markdown 工件为工作记忆、以 LLM 为核心智能、以 skills 为执行能力层的最小可用长期自治体

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

### Phase 3: Policy Hardening & Verification
**Goal**: 在自治能力初步可用后补齐策略护栏与分层验证，确保 Kairos 的自动推进可解释、可测试、不过度执行。
**Depends on**: Phase 2
**Requirements**: [POL-01, POL-02, POL-03, VER-04]
**Success Criteria** (what must be TRUE):
  1. continuation 不会重复派发同类动作造成循环推进
  2. 有明确的限步、blocked/waiting_input 等停止条件
  3. runtime / integration / live-http 三层验证能覆盖关键自治路径
  4. phase-2 到 phase-3 的行为变更有稳定回归证据
**Plans**: 2 plans

Plans:
- [x] 03-01: 策略护栏加固（去重、限步、blocked/waiting_input）
- [x] 03-02: 分层验证收敛（runtime / integration / live-http）

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
**Goal**: 在 4A 的可见性基础上，让 Kairos 具备真实 planning artifact、固定候选动作选择、显式 re-plan 事件以及 operator 可见 planning trace。
**Depends on**: Phase 4A
**Requirements**: [4B-PLN-01, 4B-PLN-02, 4B-OBS-01, 4B-UX-01, 4B-VER-01]
**Success Criteria** (what must be TRUE):
  1. `last_planning_result` 成为稳定 planning artifact，而不是占位字段
  2. planner 只从固定候选动作集合中选 winner，并遵守 tier-based supersession
  3. runtime / API / history / operator console 都能看到 planning winner、rejected summary 与 re-plan trace
  4. live HTTP flow 能证明 planning evidence 在真实运行链路中可见
**Plans**: 3 plans

Plans:
- [x] 04B-01: 落地稳定 planning artifact、fixed candidate planner 与 final_action bridge
- [x] 04B-02: 接通 runtime re-plan、API mirrors 与 sparse planning history timeline
- [x] 04B-03: 接通 operator console planning cards、timeline polish 与 live planning evidence

### Phase 5: Document-Driven Continuation
**Goal**: 让 Kairos 从硬编码 workflow 续推器升级为通过提示词协议生成、阅读、更新工作文档的后台常驻 assistant，能够从需求和工作文档中发现、规划、推进未完成任务与新任务。
**Depends on**: Phase 4B
**Requirements**: [DOC-01, DOC-02, DOC-03, DOC-04, DOC-05, DOC-VER-01, DOC-VER-02, DOC-VER-03]
**Success Criteria** (what must be TRUE):
  1. Kairos 能通过提示词协议把需求与工作状态沉淀为规范化文档，而不再只依赖 `demo_report_pipeline` / `todo_delivery_pipeline`
  2. 用户需求可以先落为 spec/plan/work item 文档，再进入 Kairos 的持续推进链路
  3. 自动唤醒时，Kairos 能通过阅读文档和工件状态发现 unfinished work 和新派生任务，并在安全边界内持续推进
  4. planning winner / rejected / re-plan / history / UI trace 继续成立，但对象变为 document-backed work items
**Plans**: 3 plans

Plans:
- [x] 05-IMPLEMENTATION: document-backed executable progression first wave（bridge）
- [x] 05A: 文档协议与阅读/写入底座
- [x] 05B: 需求落盘与工作草案生成
- [x] 05C: 自主发现新任务与持续编排

### Phase 6: Markdown-First Skill-Using Autonomy
**Goal**: 把 Kairos 从“document-aware continuation”推进到“markdown-first + LLM-core + skill-using”的长期自治执行体。
**Depends on**: Phase 5
**Requirements**: [A6-MD-01, A6-SKILL-01, A6-VERIFY-01]
**Success Criteria** (what must be TRUE):
  1. requirement/design/codegen/verification 至少两类阶段以 markdown 工件为主要输出
  2. planner 在 live 路径不因 strict JSON 约束而整体回退
  3. Kairos 能在受控边界内自主加载/调用现有 skills 推进任务
  4. verification/replan 能驱动真实后续动作，而不是只写状态
**Plans**: 1 plan

Plans:
- [ ] 06-IMPLEMENTATION: LLM-first autonomous task intelligence（markdown-first skill bridge + replan loop，wave-1: attention/respond + llm-only follow-up 已落地，见 `06-01-SUMMARY.md`）

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4A → 4B → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Autonomous Continuation MVP | 3/3 | Complete | 2026-04-06 |
| 2. Artifact-Aware Reporting & Visibility | 2/2 | Complete | 2026-04-06 |
| 3. Policy Hardening & Verification | 2/2 | Complete | 2026-04-07 |
| 4A. Explainability, History & Operator UX | 1/1 | Complete | 2026-04-10 |
| 4B. Goal-Driven Planning Intelligence | 3/3 | Complete | 2026-04-11 |
| 5. Document-Driven Continuation | 4/4 | Complete | 2026-04-12 |
| 6. Markdown-First Skill-Using Autonomy | 0/1 | In Progress (wave-1 delivered) | — |

---
*Last updated: 2026-04-18 after formalizing Phase 6 as active phase*

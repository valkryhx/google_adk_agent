# Requirements: google_adk_agent

**Defined:** 2026-04-05
**Core Value:** 把普通的一次一答式 agent 运行时，演进成一个可扩展、可观测、可长期运行、能自主推进工作的现代 Agent Operating System。

## v1 Requirements

### Kairos Continuation

- [x] **KAI-01**: 用户可以让 KAIROS 在已跟踪的阶段性任务完成后自动发现下一步 workflow 动作，而不必手工注册每个后续 task
- [x] **KAI-02**: 用户可以看到 KAIROS 当前正在推进的 workflow、当前阶段和下一步 planned actions
- [x] **KAI-03**: 当 staged workflow 的 phase-1 输入全部满足时，KAIROS 可以自动创建并接管 report follow-up Dex task
- [x] **KAI-04**: KAIROS 在 follow-up 条件不满足时会进入 blocked 或 waiting_input，而不是盲目继续或空转

### Kairos Reporting

- [x] **RPT-01**: 用户可以从 KAIROS recent events / status 中看到 task 完成后的结果摘要，而不只是 completed/failed 状态
- [x] **RPT-02**: 用户可以看到 KAIROS 为什么继续、为什么停住、以及当前的 blocked reason
- [x] **RPT-03**: 用户可以在前端面板查看 workflow、planned actions、blocked reason 等自治状态

### Kairos Safety & Policy

- [x] **POL-01**: KAIROS 不会对同一个 workflow 重复创建相同的 follow-up Dex task
- [x] **POL-02**: KAIROS 的自动续推步数受到策略限制，避免无限循环或 runaway autonomy
- [x] **POL-03**: 开发者可以通过 API 或 status 输出观察 KAIROS 的自治策略状态与关键决策结果

### Verification

- [x] **VER-01**: phase-3 的 continuation 行为具备 runtime 层回归测试
- [x] **VER-02**: phase-3 的自动 follow-up 行为具备真实 Dex 集成测试
- [x] **VER-03**: phase-3 的自动续推闭环具备 live HTTP regression，并证明 report task 不再需要人工手工注册

## v2 Requirements

### Extended Autonomy

- **AUTO-01**: KAIROS 支持多个 workflow template，而不只限于当前 demo_report_pipeline
- **AUTO-02**: KAIROS 支持 webhook / external event 驱动的自动 workflow continuation
- **AUTO-03**: KAIROS 支持更丰富的 policy 管理与策略配置 UI

### Long-Term Runtime

- **LTR-01**: KAIROS 具备完整 supervisor / worker 多进程架构
- **LTR-02**: KAIROS 具备高保真 remote bridge / attach continuity
- **LTR-03**: KAIROS 具备 nightly memory distill / dream 体系

## Out of Scope

| Feature | Reason |
|---------|--------|
| 完整 supervisor / worker 多进程重构 | 当前 milestone 先验证最小自治跃迁，不做大架构迁移 |
| GitHub webhook / channels / push notification | 属于后续外部事件与通知能力，不属于当前最短闭环 |
| nightly dream / memory distill | 当前 milestone 聚焦 workflow continuation，不升级长期记忆体系 |
| 让 LLM 自由规划全部后续动作 | 第一阶段优先 rule-based continuation，确保稳定与可测 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| KAI-01 | Phase 1 | Complete |
| KAI-02 | Phase 1 | Complete |
| KAI-03 | Phase 1 | Complete |
| KAI-04 | Phase 1 | Complete |
| RPT-01 | Phase 2 | Complete |
| RPT-02 | Phase 2 | Complete |
| RPT-03 | Phase 2 | Complete |
| POL-01 | Phase 3 | Complete |
| POL-02 | Phase 3 | Complete |
| POL-03 | Phase 3 | Complete |
| VER-01 | Phase 1 | Complete |
| VER-02 | Phase 1 | Complete |
| VER-03 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-05*
*Last updated: 2026-04-07 after Phase 3 assistant-mode proactive runtime verification*

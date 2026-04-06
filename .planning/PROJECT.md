# google_adk_agent

## What This Is

google_adk_agent（Ciri）是一个基于 Google ADK 从零构建的现代 AI Agent 系统，面向希望体验和研究多智能体、动态技能、长时上下文与后台自治能力的开发者。当前代码库已经具备多租户 SteeringSession 宿主、动态技能懒加载、Dex 异步执行与 KAIROS phase-2 runtime，正在朝更自主的 long-term running agent 方向演进。

## Core Value

把普通的一次一答式 agent 运行时，演进成一个可扩展、可观测、可长期运行、能自主推进工作的现代 Agent Operating System。

## Requirements

### Validated

- ✓ 基于 `SteeringSession` 的多会话 agent 宿主已可运行 — pre-milestone brownfield baseline
- ✓ 技能系统支持按需发现与延迟加载工具 — pre-milestone brownfield baseline
- ✓ Dex 可执行真实后台任务并返回结构化状态/摘要 — pre-milestone brownfield baseline
- ✓ KAIROS phase-2 已支持 start/stop/wake/schedule/handoff/tracked tasks/status API — pre-milestone brownfield baseline
- ✓ KAIROS live demo 已能完成 phase-1 并行任务 + 手工 report 阶段验证 — pre-milestone brownfield baseline
- ✓ KAIROS 已能在 todo boss demo 中自动创建并接管 `generate todo delivery report` follow-up task — validated 2026-04-06 via real host + Dex + live HTTP verification
- ✓ KAIROS 已能在独立目录 `demo_delivery/todo_app/` 中完成 requirements/design/codegen/tests/report 多阶段真实产物交付 — validated 2026-04-06 via live HTTP verification

### Active

- [ ] KAIROS 能在任务完成后主动发现下一步并自动续推 workflow
- [ ] KAIROS 具备 workflow / planned actions / blocked reason 等自治状态建模
- [ ] KAIROS 能输出 artifact-aware proactive summary，而不只是状态事件
- [ ] KAIROS 具备去重、限步、blocked/waiting_input 等自治策略护栏

### Out of Scope

- 完整 supervisor / worker 多进程体系 — 当前 milestone 先验证最小自治跃迁，不做大架构迁移
- 高保真 remote bridge / attach continuity 复刻 — 当前 focus 是 continuation，不是 bridge protocol
- GitHub webhook / channels / push notification — 属于后续能力扩展，不属于当前最短闭环
- nightly dream / memory distill — 当前不做长期记忆体系升级
- 让 LLM 自由规划所有 follow-up — 第一里程碑优先 rule-based continuation，保证可测性与稳定性

## Context

当前仓库已是一个 brownfield agent codebase：主宿主为 `src/adk_agent/main_web_start_steering.py`，动态技能系统由 `SkillManager` 管理，Dex 负责长任务后台执行，KAIROS phase-2 已经落出 runtime/scheduler/api/attach/dex_bridge/frontend 展示与 live HTTP 回归。当前最重要的下一步不是继续增强“观察后台任务”，而是让 KAIROS 从 poller/handoff tracker 升级为能够主动发现下一步并自动推进 workflow 的自治 runtime。

## Constraints

- **Tech stack**: 必须继续基于现有 Python + FastAPI + Google ADK + SQLite + Dex 架构推进 — 避免无必要技术迁移
- **Architecture**: 当前 milestone 不引入完整 supervisor 重构 — 优先在现有 `SteeringSession` + `KairosRuntime` 上完成最小自治闭环
- **Verification**: 必须保留并扩展现有 runtime / integration / live-http 分层测试证据链 — phase-3 不能只靠叙事证明
- **Windows**: 任何输出中文/emoji 的 Python 命令仍需遵循 UTF-8 环境变量约束 — 避免现有 Windows 编码问题回归
- **Safety**: 只改 state 的路径必须继续走 state-only persistence — 避免 history duplication 类问题复发

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| KAIROS phase-3 先做 continuation engine，而不是 supervisor 重构 | 先验证“自动续推 workflow”这个最关键能力跃迁，成本最低、证据最强 | — Pending |
| Phase-3 第一里程��以 `sales/traffic/quality -> report` 自动续推闭环为主 | 当前已有 live demo、真实 Dex 子进程与回归链路，最适合证明跳出 REPL 主导模式 | — Pending |
| 第一版采用 rule-based continuation，而不是把自治全交给 LLM | 便于测试、去重、限步与风险控制 | — Pending |

## Current Milestone: v1.0 Kairos phase-3

**Goal:** 让 KAIROS 从观察 Dex 后台任务，升级为能主动发现下一步并自动续推 workflow。

**Target features:**
- Continuation Engine + internal trigger
- workflow / planned actions / blocked reason 状态与可视化
- staged workflow 中自动创建并接管 report follow-up
- artifact-aware proactive reporting 与 policy hardening

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-05 after starting milestone v1.0 Kairos phase-3*

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

- [x] KAIROS 能在任务完成后主动发现下一步并自动续推 workflow
- [x] KAIROS 具备 workflow / planned actions / blocked reason 等自治状态建模
- [x] KAIROS 能输出 artifact-aware proactive summary，而不只是状态事件
- [x] KAIROS 具备去重、限步、blocked/waiting_input 等自治策略护栏

### Next

- [ ] KAIROS 能通过提示词协议生成规范化工作文档，而不只是回复建议
- [ ] KAIROS 能通过提示词协议阅读和更新工作文档，把文档作为工作事实来源
- [ ] KAIROS 能把用户需求与系统发现的问题统一转成可续推工作项
- [ ] KAIROS 支持从“需求 -> 文档 -> 执行推进 -> 派生工作 -> 再推进”的下一阶段自治跃迁

### Out of Scope

- 完整 supervisor / worker 多进程体系 — 当前 milestone 先验证最小自治跃迁，不做大架构迁移
- 高保真 remote bridge / attach continuity 复刻 — 当前 focus 是 continuation，不是 bridge protocol
- GitHub webhook / channels / push notification — 属于后续能力扩展，不属于当前最短闭环
- nightly dream / memory distill — 当前不做长期记忆体系升级
- 让 LLM 自由规划所有 follow-up — 第一里程碑优先 rule-based continuation，保证可测性与稳定性

## Context

当前仓库已是一个 brownfield agent codebase：主宿主为 `src/adk_agent/main_web_start_steering.py`，动态技能系统由 `SkillManager` 管理，Dex 负责长任务后台执行。Phase 4 已完成：4A 解决了 history/operator UX，可在前端/API 中看到 current state + history timeline；4B 进一步完成了 planning artifact、固定候选动作选择、runtime re-plan、API/history/UI planning trace 与 live HTTP planning evidence。当前最重要的下一步，不再是继续补 Phase 4 可见性，而是让 KAIROS 从“预定义 workflow 的续推器”升级为“根据需求动态生成 workflow / task 的自主编排器”。

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

## Current Milestone: v1.1 Kairos phase-4 complete

**Goal achieved:** 让 KAIROS 从观察 Dex 后台任务，升级为能主动发现下一步、留下 planning 痕迹、并把 planning trace 暴露给 operator。

**Delivered features:**
- Continuation Engine + internal trigger
- workflow / planned actions / blocked reason 状态与可视化
- staged workflow 中自动创建并接管 report follow-up
- artifact-aware proactive reporting 与 policy hardening
- planning artifact / fixed candidate taxonomy / final_action
- runtime re-plan + API/history/operator console planning trace

## Next Milestone Candidate

**Direction:** 从“预定义 workflow 续推”升级为“需求驱动 workflow / task 生成”。

### Phase 5 draft

建议命名：`Prompt-Governed Document-Driven Continuation`

建议总目标：
- 让 Kairos 从依赖硬编码 pipeline 的续推器，升级为通过提示词协议生成、阅读、更新工作文档的后台常驻 assistant
- 既能接管用户需求并落为工作文档，也能在自动唤醒时通过阅读文档和工件状态发现未完成任务与新派生任务
- 用 LLM 负责文档理解与文档生成，用代码负责目录白名单、安全边界、审计与少量关键约束校验

建议阶段拆分：
- **5A：文档协议与阅读/写入底座** — 定义文档语义锚点与三类核心提示词（生成/阅读/更新）
- **5B：需求落盘与工作草案生成** — `/api/chat` 需求转文档化 work item，而不是只回复文本
- **5C：自主发现新任务与持续编排** — 从 progress/verification/artifacts/history 中发现新工作并写回文档

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

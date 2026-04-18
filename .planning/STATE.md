# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-06)

Core Value: 把普通的一次一答式 agent 运行时，演进成可扩展、可观测、可长期运行、能自主推进工作的 Agent Operating System。
Current Focus: Phase 6 — Markdown-First Skill-Using Autonomy

## Current Position

Current Phase: 6
Current Phase Name: Markdown-First Skill-Using Autonomy
Total Phases: 7
Current Plan: 1
Total Plans in Phase: 1
Status: In progress
Last Activity: 2026-04-18
Last Activity Description: 已完成 Phase 6 wave-1（attention/respond + 回复写入 work.md + llm-only follow-up）并同步阶段文档；下一步实现 Kairos 专属 work/register 入口。
Progress: 97%

## Decisions Made

| Phase | Summary | Rationale |
|-------|---------|-----------|
| 5 | `/api/chat` 不再作为 Kairos 任务注册入口 | 避免普通对话路径和自治任务路径耦合，保持宿主职责清晰 |
| 6 | Phase 6 采用 markdown-first + skill boundary，而非 strict JSON-first | 提升 live 稳定性并保留安全边界 |
| 6 | `ask_user` 保持轻量：用户回复直接写入 work.md，再由 LLM 读取推进 | 避免复杂人工分支拖垮自治主链，保持 document-first 智能循环 |
| 6 | `llm_only_decision_enabled` 开启时，Dex follow-up 决策只由 LLM 产出 | 保证 Phase-6 “LLM 作为唯一驱动”的主方向 |

## Blockers

- `private_key.yaml` 仍为 tracked 且本地修改，后续提交必须显式排除。
- 工作区存在大量非 Phase 6 相关未跟踪文件，提交前必须精确 `git add`。

## Session

Last Date: 2026-04-18T23:20:00+08:00
Stopped At: 已同步 06 phase 文档（含 06-01-SUMMARY）；下一步落地 Kairos 专用 work/register 入口并完成端到端验证
Resume File: None

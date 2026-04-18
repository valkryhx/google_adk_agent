---
phase: 06-markdown-first-skill-using-autonomy
plan: 06-IMPLEMENTATION
slice: wave-1
status: partial
completed_at: 2026-04-18
tags:
  - kairos
  - llm-only
  - attention
  - markdown-first
---

# 06-01 Summary (Wave 1)

## Outcome

Phase 6 第一波已完成：Kairos 具备了“轻量人工介入 + LLM-only 后续决策”的可运行闭环，且不会因单任务 ask_user 阻塞而停掉整个会话推进。

## Delivered

- 新增 attention 回复入口：`POST /api/sessions/{session_id}/kairos/attention/respond`
- 新增 attention 状态模型与 UI 入口（Need Your Input）
- 用户回复会写入 `work.md` 的 `Replan Notes`，作为后续 LLM 规划输入
- runtime 增加 `llm_only_decision_enabled`：
  - 开启时 follow-up 决策仅接受 LLM 输出
  - planner 不可用时转 blocked，而非 silently 规则回退
- continuation 增强为“仅暂停阻塞任务”，其余可执行任务继续推进

## Verification Evidence

已执行并通过以下回归集合（历史执行记录）：

- `tests/kairos/test_models.py`
- `tests/kairos/test_document_protocol.py`
- `tests/kairos/test_continuation.py`
- `tests/kairos/test_api.py`
- `tests/kairos/test_frontend_script_kairos_ui.py`
- `tests/kairos/test_runtime.py`

结果：`124 passed`

## Open Gap

Phase 6 关键缺口仍在入口侧：Kairos 任务注册需要从 Kairos 专属面板/API 进入，不能复用或依赖普通 `/api/chat` 路径。

## Next Step

实现并验证 `POST /api/sessions/{session_id}/kairos/work/register`，并打通“专属入口 -> markdown 工件 -> LLM 规划与推进 -> verification/replan”的端到端自治链路。

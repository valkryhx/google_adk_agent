---
phase: 06-markdown-first-skill-using-autonomy
plan: 06-IMPLEMENTATION
slice: wave-2
status: partial
completed_at: 2026-04-19
tags:
  - kairos
  - work-register
  - markdown-first
  - panel-entry
---

# 06-02 Summary (Wave 2)

## Outcome

已落地 Kairos 专属任务注册入口，用户可直接从 Kairos 面板/API 注册 requirement，不再依赖普通 `/api/chat` 路径。

## Delivered

- 后端 API：
  - 新增 `POST /api/sessions/{session_id}/kairos/work/register`
- runtime：
  - 新增 `register_work_item(requirement, session_id, source_label)`
  - 自动生成并写入 `requirements/<session_id>/work.md`
  - 更新 `document_work_items` 并 enqueue `work_registered:*` 触发
- 前端：
  - Kairos 面板新增“注册 Kairos Work”输入框与按钮
  - 接线到 `/kairos/work/register` 调用
- LLM 执行链（新增）：
  - `llm_planner` 允许 `agent_execute` 动作
  - `runtime` 新增 `agent_execute` 分支：读取 `required_skills/execution_prompt`，先 `skill_load`，再触发 `agent_execute::*` turn
  - `runtime` 增加 `allowed_skills` 约束与异常阻断（无 loader/非法技能/加载失败进入 `WAITING_INPUT` + attention）
  - `SteeringSession` 在创建 runtime 时注入 `skill_load` 回调，复用用户侧技能加载生态
  - 后续最小优化：
    - `required_skills` 中非 skill 名称（tool hint）改为 skip，不阻塞 `agent_execute`
    - 若计划 step 已含 `required_skills/execution_prompt`，runtime 直接构造 payload 执行，避免二次 payload LLM 漏派发
    - document protocol 改为仅提取显式问句，移除默认 storage 问题自动阻塞
    - `WAITING_INPUT` 状态下暂停普通 trigger，避免 ask_user 后继续野蛮执行

## Verification Evidence

- 新增用例通过：
  - `tests/kairos/test_api.py::test_register_work_route_creates_document_work_item`
  - `tests/kairos/test_runtime.py::test_register_work_item_writes_work_doc_and_enqueues_manual_trigger`
  - `tests/kairos/test_frontend_script_kairos_ui.py::test_kairos_modal_includes_work_register_controls`
- 核心回归集通过：
  - `tests/kairos/test_models.py`
  - `tests/kairos/test_document_protocol.py`
  - `tests/kairos/test_continuation.py`
  - `tests/kairos/test_api.py`
  - `tests/kairos/test_frontend_script_kairos_ui.py`
  - `tests/kairos/test_runtime.py`
  - 结果：`127 passed`
- `agent_execute` 专项回归（新增）：
  - `tests/kairos/test_runtime.py::test_dispatch_agent_execute_loads_skills_and_runs_turn`
  - `tests/kairos/test_runtime.py::test_dispatch_agent_execute_blocks_when_skill_not_allowed`
  - `tests/kairos/test_runtime.py::test_dispatch_agent_execute_blocks_when_loader_missing`
  - `tests/kairos/test_llm_planner.py::test_allowed_action_kinds_include_agent_execute`
  - `tests/kairos/test_llm_planner.py::test_sanitize_action_payload_keeps_agent_execute_args`
  - 回归命令：`pytest tests/kairos/test_llm_planner.py tests/kairos/test_runtime.py tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py -q`
  - 结果：`98 passed`
 - 新增回归（ask_user 降噪 + plan-step 直派发）：
   - `tests/kairos/test_runtime.py::test_tick_once_dispatches_agent_execute_from_plan_step_without_payload_llm`
   - `tests/kairos/test_runtime.py::test_dispatch_agent_execute_skips_unknown_skill_hints_without_blocking`
   - `tests/kairos/test_runtime.py::test_dispatch_agent_execute_skips_loading_when_loader_missing`
   - `tests/kairos/test_runtime.py::test_tick_waiting_input_keeps_manual_trigger_queued_and_skips_run_turn`
   - `tests/kairos/test_document_protocol.py::test_build_requirement_work_item_defaults_to_autonomous_when_no_explicit_question`
   - 综合回归：`107 passed`

## Live Evidence (Round 5)

- 会话：`session_1776518351935_6bdb2a53`
- 入口：`POST /api/sessions/{session_id}/kairos/work/register`
- 观测：
  - `current_execution_plan.steps=4`
  - 首步 `action_kind=agent_execute`
  - 首步包含 `required_skills=["file_read","text_parse"]`
  - history 含 `agent execute queued ...` 与 `kairos turn started: manual:work_registered...`
- live HTTP 验证（Kairos 专属入口）：
  - 使用 `POST /api/sessions/{session_id}/kairos/work/register` 注册 requirement
  - `requirements/<session_id>/work.md` 成功生成，且包含 `## Goal` / `## Replan Notes`
  - 观测到 runtime turn 启停事件（`kairos turn started/finished`）
  - 通过最小修复消除了 planner 的 `NoneType is not a mapping` 异常（`extra_body` 传参修复）
  - 通过超时归一化修复避免 planner 调用长期挂起（兼容毫秒配置并限时）
  - 二次修复后，`current_understanding.goal` 可见，且空计划会显式 `record_blocked`（`blocked_reason=llm planner failed for document work: ValueError`），不再静默空跑
  - 三次复验后，已观测到非空执行计划（示例会话：`current_execution_plan.steps=4`）
  - 目前剩余缺口：planning trace（`final_action`）与实际执行状态仍有一致性改进空间，需要继续收敛

## Next Step

在已拿到非空 steps 的基础上，继续验证 ask_user/skill/replan 的连续推进，并收敛 planning trace 与实际执行状态的一致性。

# Phase 1 Research: Autonomous Continuation MVP

**Date:** 2026-04-05
**Phase:** 1 — Autonomous Continuation MVP
**Goal:** 让 KAIROS 在 staged workflow 的输入任务完成后，能够自动发现下一步并自动创建/接管 report follow-up Dex task。

## 1. 最小实现路径

### 推荐路线
采用 **rule-based continuation engine + 宿主受控执行入口 + 现有 runtime orchestration 复用**。

原因：
- 当前 `src/adk_agent/kairos/runtime.py` 已经具备 tick / trigger / handoff / dex polling 的主循环能力，最短路径不是重做 runtime，而是在 `_poll_dex()` 后接 continuation evaluation。
- `src/adk_agent/main_web_start_steering.py:450-500` 已经是 KAIROS turn 与 runtime 宿主接线点，适合扩成受控 follow-up 执行入口。
- `tests/kairos/test_runtime.py:831-922` 已经验证 staged workflow 的收敛语义，说明 Phase 1 可以沿着现有 `sales/traffic/quality -> report` 闭环继续往前推，而不是设计新的 demo。

### 建议的最小步骤
1. **先扩状态模型**
   - 在 `src/adk_agent/kairos/models.py` 增加 workflow / planned action / blocked reason / policy 的最小结构。
2. **新增 continuation engine**
   - 新文件建议：`src/adk_agent/kairos/continuation.py`
   - 输入：当前 state + 刚完成的 Dex snapshots
   - 输出：continuation decisions / internal trigger / planned action
3. **接入 runtime**
   - 在 `src/adk_agent/kairos/runtime.py::_poll_dex()` 后追加 continuation evaluation
   - 当检测到 phase-1 inputs 全部完成且产物存在时，生成 follow-up decision
4. **宿主层执行 follow-up**
   - 在 `SteeringSession` 暴露 callback，统一完成：
     - 创建 Dex task
     - 启动/注册 handoff
     - 更新 recent events / state
5. **扩 live demo regression**
   - 把当前手工注册 report task 的步骤改成“等待 KAIROS 自动创建并推进 report”

---

## 2. 最小状态建模

### 推荐原则
采用 **最小显式模型**，不要一开始就上完整 workflow memory / retry orchestration / long-term autonomy ledger。

### 建议新增对象

#### `KairosWorkflowStage`
表示当前 workflow 的阶段。

建议字段：
- `stage_id`
- `label`
- `status` (`pending/running/completed/failed/blocked`)
- `task_ids`
- `artifacts`
- `summary`

#### `KairosWorkflow`
表示当前被 KAIROS 推进的 workflow。

建议字段：
- `workflow_id`
- `goal`
- `status` (`active/waiting_input/completed/failed/paused`)
- `current_stage`
- `stages`
- `metadata`

#### `KairosPlannedAction`
表示 runtime 认为下一步应该做的动作。

建议字段：
- `action_id`
- `kind` (`create_dex_task`, `emit_brief`, `wait_for_input`, `verify_artifact`)
- `reason`
- `payload`
- `status`
- `created_at`

#### `KairosContinuationPolicy`
最小护栏配置。

建议字段：
- `max_auto_steps_per_tick`
- `allow_llm_assist_for_brief`
- `require_artifacts_before_follow_up`
- `dedupe_enabled`

### 在 `KairosState` 中建议新增
- `active_workflow`
- `planned_actions`
- `blocked_reason`
- `policy`

### 为什么不建议第一版上完整 history
当前 milestone 的目标是“自动续推最小闭环”，而不是“完整长期自治记忆系统”。

如果一开始就加入：
- continuation history
- retry ledger
- failure clustering
- workflow memory distill

会把实现复杂度拉高，而且对当前最关键的 success criteria 没有直接帮助。

---

## 3. 宿主回调如何安全创建 Dex task 并 handoff

### 推荐位置
放在 `src/adk_agent/main_web_start_steering.py` 对应的 `SteeringSession` 上。

当前已有关键锚点：
- `_save_kairos_state()` — 持久化 runtime state
- `_emit_kairos_event()` — 向 UI / SSE 推送事件
- `_append_kairos_log()` — 记录 activity log
- `run_kairos_turn()` — 执行 sandbox autonomous turn
- `get_or_create_kairos_runtime()` — runtime 构造与依赖注入

### 推荐方式
不要让 `runtime.py` 直接 import `DexManager` 并自己调起 follow-up。更稳妥方式是：

#### 在 `SteeringSession` 上增加受控 callback
例如概念上提供：
- `create_kairos_follow_up_task(...)`
- `register_kairos_follow_up_handoff(...)`

由这个 callback 负责：
1. 使用当前 `user_id` 创建 Dex task
2. 确保不落到 global namespace
3. 启动或注册 handoff
4. 更新 KAIROS state 与 recent events
5. 仍然走 state-only persistence

#### runtime / continuation engine 只表达“意图”
也就是：
- runtime 判断应该创建 report
- 它发出 `planned_action` / `decision`
- 宿主回调真正执行

### 为什么这比 runtime 直调更安全
1. **避免 user_id / namespace 出错**
   - `skills/dex/tools.py` 明确要求 `DexManager(user_id=...)`，否则会进入 global 或报错。
2. **避免宿主污染**
   - 现有 KAIROS 已经明确区分 history 与 state-only persistence，宿主层更容易遵守这个边界。
3. **统一事件记录**
   - 宿主层已经有 `_emit_kairos_event()` / `_append_kairos_log()`，复用最自然。
4. **测试更清晰**
   - runtime 测试关注 decision
   - integration/live 测试关注宿主回调是否真实创建 follow-up task

---

## 4. 分层测试补齐建议

继续沿用 phase-2 已证明有效的四层测试结构。

### 4.1 Runtime 层
目标：锁定自治语义。

建议扩展：
- `tests/kairos/test_models.py`
- `tests/kairos/test_runtime.py`
- 新增 `tests/kairos/test_continuation.py`

建议新增测试：
- `test_state_round_trip_preserves_workflow_and_planned_actions`
- `test_completed_inputs_enqueue_internal_continuation_trigger`
- `test_runtime_auto_creates_report_follow_up_when_all_inputs_ready`
- `test_runtime_enters_waiting_input_when_artifact_missing`
- `test_runtime_does_not_duplicate_follow_up_task_creation`

### 4.2 Integration 层
目标：确认不是 fake continuation。

建议扩展：
- `tests/dex/test_tools.py`
- `tests/kairos/test_dex_bridge.py`

建议新增测试：
- `test_kairos_runtime_auto_registers_report_task_against_real_dex`
- `test_auto_created_follow_up_task_uses_user_namespace`
- `test_follow_up_task_summary_surfaces_into_runtime_events`

### 4.3 Live HTTP 层
目标：这是当前最重要证据。

建议修改：
- `tests/kairos/live_http_kairos_demo_outputs_regression.py`
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

关键变化：
- phase-1 tasks 仍由脚本创建并注册
- **report task 不再手工注册**
- 等待 KAIROS 自动创建并推进 report

新增断言：
- 存在 auto-created report 事件
- 最终 `report.json` 落盘
- 最终 `tracked_dex_task_ids == []`
- 最终 `mode == idle`

### 4.4 Frontend 层
目标：Phase 1 就要能看见自治状态。

建议扩展：
- `tests/kairos/test_frontend_script_kairos_ui.py`

建议新增测试：
- `test_script_exposes_workflow_and_planned_actions_helpers`
- `test_kairos_modal_renders_workflow_and_blocked_reason_panels`

---

## 5. 结论

如果只说一句最重要的实现建议：

> **Phase 1 应该在现有 runtime 主循环上，新增一个最小的 rule-based continuation engine，并通过 SteeringSession 的宿主回调安全创建 report follow-up task。**

这样可以最小成本实现：
- 自动发现下一步
- 自动创建并接管 report
- 不污染 history
- 不绕开现有 Dex/user_id 边界
- 还能直接复用现有 live HTTP regression 升级成最强证据链

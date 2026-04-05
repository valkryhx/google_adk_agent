# KAIROS Phase 3 测试矩阵

> 日期：2026-04-05
> 目标：为 phase-3 的 proactive KAIROS 建立可执行、可回归、可分层定位问题的测试矩阵。
> 原则：延续 phase-2 已经证明有效的四层验证思路，不把所有信心都压到最重的 live 测试上。

---

## 1. 测试目标

phase-3 要验证的，不再只是：

- Dex task 能不能完成
- KAIROS 能不能看到 completed/failed

而是要验证：

1. KAIROS 能否在任务完成后**自动识别 workflow 已推进**
2. KAIROS 能否**自己生成 internal continuation trigger**
3. KAIROS 能否**自动创建 follow-up Dex task**
4. KAIROS 能否避免**重复续推 / 重复创建任务**
5. KAIROS 能否在缺失输入时进入 **WAITING_INPUT / blocked**
6. KAIROS 能否输出更强的 **artifact-aware summary**
7. 上述行为在 runtime / integration / live-http / frontend 四层都能被证据化

---

## 2. 四层测试结构

## 2.1 Runtime 层

### 作用
验证：
- 状态机
- continuation decision 接入主循环后的行为语义
- internal trigger / planned action / waiting_input 的纯运行时逻辑

### 推荐文件
- 修改：`tests/kairos/test_models.py`
- 修改：`tests/kairos/test_runtime.py`
- 新增：`tests/kairos/test_continuation.py`
- 可选新增：`tests/kairos/test_workflows.py`

### 推荐新增测试

#### `tests/kairos/test_models.py`
- `test_state_round_trip_preserves_workflow_and_planned_actions`
- `test_load_legacy_state_fills_phase3_defaults`
- `test_policy_defaults_are_stable`

#### `tests/kairos/test_continuation.py`
- `test_all_inputs_ready_returns_create_report_decision`
- `test_missing_artifact_returns_blocked_decision`
- `test_duplicate_follow_up_is_suppressed_by_fingerprint`
- `test_policy_can_disable_auto_continue`

#### `tests/kairos/test_runtime.py`
- `test_completed_inputs_enqueue_internal_continuation_trigger`
- `test_runtime_auto_creates_report_follow_up_when_all_inputs_ready`
- `test_runtime_does_not_duplicate_follow_up_task_creation`
- `test_runtime_enters_waiting_input_when_required_artifact_missing`
- `test_runtime_respects_max_auto_steps_per_tick`
- `test_runtime_status_exposes_workflow_and_planned_actions`

### 关注点
- **internal continuation trigger 是否进入 `pending_triggers`**
- **同一 workflow 是否会重复派生 follow-up**
- **当 follow-up 缺条件时是否进入 blocked / waiting_input**
- **`get_status()` 是否暴露新字段**

### 为什么要单独做这一层
因为 phase-3 的核心变化首先是“决策语义变化”，必须先在最快、最稳定的一层被锁住。

---

## 2.2 Integration 层

### 作用
验证：
- 真实 DexManager
- 真实 `.dex/tasks/<user>/*.json`
- 真实 KairosDexBridge
- 真实 KairosRuntime

确保不是 fake snapshot 驱动出来的“假自治”。

### 推荐文件
- 修改：`tests/dex/test_tools.py`
- 修改：`tests/kairos/test_dex_bridge.py`
- 可选新增：`tests/kairos/test_continuation_integration.py`

### 推荐新增测试

#### `tests/dex/test_tools.py`
- `test_kairos_runtime_auto_registers_report_task_against_real_dex`
- `test_auto_created_follow_up_task_produces_expected_summary`
- `test_failed_follow_up_task_records_blocked_reason`

#### `tests/kairos/test_dex_bridge.py`
- `test_bridge_exposes_result_summary_and_error_summary_for_continuation`
- `test_bridge_snapshot_contains_artifact_info_needed_by_follow_up_logic`

### 关注点
- KAIROS 是否真的在 **real Dex task completed** 后续推
- 自动生成的 report task 是否真实存在于 `.dex/tasks/user_xxx/`
- `result_summary / error_summary / log_path` 是否足够支撑 continuation decision

### 为什么必须做这一层
phase-3 的“更 proactive”必须建立在真实 Dex 边界上，否则很容易出现：

- runtime 测试看起来都对
- 但真实 Dex 任务文件、结果摘要、产物验证一接上就失真

---

## 2.3 Live HTTP 层

### 作用
验证：
- 服务已启动
- session / kairos API / runtime 宿主接线正常
- 从真实服务入口看，KAIROS 是否已经从“被动跟踪”升级成“自动续推”

### 推荐文件
- 修改：`tests/kairos/live_http_kairos_demo_outputs_regression.py`
- 修改：`tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

### 当前 phase-2 状态
当前脚本是：
- 手工注册 phase-1 tasks
- 手工注册 report task
- 验证最终产物

### phase-3 的关键升级
把脚本改成：
- phase-1 tasks 仍由测试脚本创建并注册
- **report task 不再手工注册**
- 等待 KAIROS 自动创建 report task
- 验证：
  - `recent_events` 中出现 auto-created follow-up
  - `report.json` 最终落盘
  - `mode` 最终收敛为 `idle`

### 推荐新增断言
- 存在类似 `phase-1 converged, auto-created report task`
- `planned_actions` 不重复残留
- `active_workflow` 最终变为 completed / idle compatible state
- `tracked_dex_task_ids` 最终清空

### 推荐新增 live 用例名
- `test_live_http_kairos_auto_progresses_from_inputs_to_report`
- `test_live_http_kairos_does_not_duplicate_report_follow_up`

### 为什么这是 phase-3 最重要的证据
因为这条测试一旦成立，就意味着：

> **KAIROS 第一次在真实服务链路里，完成了“任务完成 -> 自己发现下一步 -> 自己推进”的闭环。**

这正是你想要的“跳出 REPL”。

---

## 2.4 Frontend 层

### 作用
验证：
- phase-3 新状态是否在前端可见
- workflow / planned actions / blocked reason 是否能展示
- 多行文本 / 可读性不退化

### 推荐文件
- 修改：`tests/kairos/test_frontend_script_kairos_ui.py`
- 如需要，可新增更细的 DOM 字符串测试

### 推荐新增测试
- `test_script_exposes_workflow_and_planned_actions_helpers`
- `test_kairos_modal_renders_workflow_and_blocked_reason_panels`
- `test_status_refresh_updates_workflow_and_planned_actions_sections`

### 关注点
- 是否新增：
  - `formatKairosWorkflow(...)`
  - `formatKairosPlannedActions(...)`
- `index.html` 中是否存在：
  - `id="kairosWorkflow"`
  - `id="kairosPlannedActions"`
  - `id="kairosBlockedReason"`
- `white-space: pre-wrap` 等多行渲染属性是否保留

### 为什么这一层不能省
phase-3 一旦变得更主动，就必须让人类看见：
- 为什么继续
- 下一步准备做什么
- 为什么停住

否则调试和演示都会变得非常困难。

---

## 3. 推荐测试执行顺序

## 3.1 改状态模型 / continuation 规则时
先跑：

```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/kairos/test_models.py \
  tests/kairos/test_continuation.py \
  tests/kairos/test_runtime.py -q
```

### 目的
先锁住 phase-3 的“决策语义”和状态契约。

---

## 3.2 改 Dex follow-up 创建 / bridge 字段时
再跑：

```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/dex/test_tools.py \
  tests/kairos/test_dex_bridge.py -q
```

### 目的
确认真实 Dex 边界没有被破坏。

---

## 3.3 改宿主接线 / 真正自动续推时
再跑：

```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q
```

### 目的
确认真实服务链路已完成从“观察”到“自动续推”的跃迁。

---

## 3.4 改前端展示时
最后跑：

```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/kairos/test_frontend_script_kairos_ui.py -q
```

### 并建议补一次手动验证
- 打开 KAIROS 面板
- 查看 workflow / planned actions / blocked reason 区块是否易读

---

## 4. 特别需要覆盖的风险点

## 4.1 重复续推
必须有测试保证：
- phase-1 收敛后不会每个 tick 都再创建一个 report task

建议用例：
- `test_runtime_does_not_duplicate_follow_up_task_creation`
- `test_live_http_kairos_does_not_duplicate_report_follow_up`

---

## 4.2 artifact 不满足时的等待策略
必须有测试保证：
- 任务 completed 但缺产物时，不是瞎推进，而是进入 blocked / waiting_input

建议用例：
- `test_missing_artifact_returns_blocked_decision`
- `test_runtime_enters_waiting_input_when_required_artifact_missing`

---

## 4.3 自动步数失控
必须有测试保证：
- 一个 tick 内不会无穷续推

建议用例：
- `test_runtime_respects_max_auto_steps_per_tick`

---

## 4.4 摘要质量退化
必须有测试保证：
- recent_events 不再只是“task completed”，而是包含足够的 result / error summary

建议用例：
- `test_auto_created_follow_up_task_produces_expected_summary`
- `test_bridge_exposes_result_summary_and_error_summary_for_continuation`

---

## 5. 一句话总结

phase-3 的测试矩阵应该证明的，不是“又多了几个状态字段”，而是：

> **KAIROS 能在真实服务链路和真实 Dex 边界上，自主发现并继续推进下一步工作，同时不重复、不失控、可解释。**

因此最关键的测试升级是：

1. **runtime 层验证 internal continuation trigger**
2. **integration 层验证自动创建 follow-up Dex task**
3. **live-http 层验证 report 任务不再由人手动注册，而是由 KAIROS 自动推进**
4. **frontend 层验证 workflow / planned actions / blocked reason 可见**

# KAIROS Phase 3 精确代码改造清单

> 日期：2026-04-05
> 目标：把 phase-3 的“更 proactive、能自动续推”进一步收敛为精确的代码改造清单，便于后续直接进入实现或继续拆为详细 plan。
> 说明：本清单严格基于当前仓库现有实现整理，不是假设一个全新系统。

---

## 1. 新增文件

## 1.1 `src/adk_agent/kairos/continuation.py`

### 建议职责
负责 phase-3 最关键的新能力：**Continuation Engine**。

输入：
- `KairosState`
- 已完成/失败的 Dex snapshots
- 当前 workflow 状态
- recent events
- policy

输出：
- continuation decisions
- internal triggers
- planned actions
- blocked / waiting_input 决策

### 为什么必须新建
当前 `src/adk_agent/kairos/runtime.py` 已经承担：
- tick orchestration
- schedule collection
- dex polling
- state persistence
- event recording

如果再把“如何决定下一步”直接塞进去，`runtime.py` 会同时承担 orchestration + policy + semantic interpretation，后续会迅速失控。

### 建议核心对象
- `ContinuationDecision`
- `ContinuationEngine`

### 建议最小接口
```python
class ContinuationEngine:
    def evaluate_after_dex_poll(self, state, completed_tasks, tracked_tasks):
        ...

    def evaluate_before_turn(self, state):
        ...
```

---

## 1.2 `src/adk_agent/kairos/workflows.py`

### 建议职责
把当前隐含在 demo / 测试里的 staged workflow，提升为显式 workflow template。

### 为什么必须新建
现在 workflow 语义主要分散在：
- `tests/kairos/test_runtime.py:831-922`
- `tests/kairos/live_http_kairos_demo_outputs_regression.py:149-191`
- `docs/实现phase-2的kairos/2026-04-04-kairos-live-demo-design.md`

也就是：
- phase-1 三个输入任务
- phase-2 report 汇总任务

这些规则目前没有在运行时代码中变成一等结构，因此 KAIROS 只能“看到任务完成”，却无法“理解 workflow 已推进到下一阶段”。

### 建议最小内容
先支持一个模板：
- `demo_report_pipeline`

显式描述：
- stages
- required tasks
- required artifacts
- convergence rule
- follow-up action

---

## 1.3 `tests/kairos/test_continuation.py`

### 建议职责
专门测试 continuation rules，不和 runtime orchestration 混在一起。

### 为什么建议新增
当前 `tests/kairos/test_runtime.py` 已经很适合做 runtime 状态机测试，但 phase-3 一旦引入“续推动作决策”，如果全部塞回 runtime tests，会让失败定位变差。

### 建议覆盖
- all inputs ready -> create follow-up decision
- artifact missing -> blocked/waiting_input
- duplicate follow-up prevention
- continuation policy limits

---

## 1.4 可选新增：`tests/kairos/test_workflows.py`

### 建议职责
测试 workflow template 与 stage progression 规则。

### 何时新增
如果 phase-3 第一版只做一个 `demo_report_pipeline`，也可以先不单独拆；
如果 workflow 规则变多，建议尽早抽出来。

---

## 2. 必须修改的文件

## 2.1 `src/adk_agent/kairos/models.py`

### 当前职责
当前已经定义：
- `KairosMode`
- `TriggerKind`
- `KairosEvent`
- `KairosTrigger`
- `KairosSchedule`
- `KairosState`
- `load_kairos_state()`
- `dump_kairos_state()`

### phase-3 必须新增/修改

#### A. 新增 workflow 相关模型
建议新增：
- `KairosWorkflowStage`
- `KairosWorkflow`
- `KairosPlannedAction`
- `KairosContinuationPolicy`

#### B. 扩展 `KairosState`
建议新增字段：
- `active_workflow`
- `planned_actions`
- `blocked_reason`
- `continuation_history`
- `policy`

#### C. 更新序列化
必须同步修改：
- `load_kairos_state()`
- `dump_kairos_state()`

### 为什么必须改
phase-2 的状态模型足够表达 runtime，但不足以表达：
- 当前目标
- workflow stage
- 下一步 planned action
- 为什么停住

如果不先扩模型，phase-3 的自主续推会沦为零散字段拼接。

---

## 2.2 `src/adk_agent/kairos/runtime.py`

### 当前职责
当前是 KAIROS runtime 核心编排器：
- `start()` / `stop()`
- `enqueue_trigger()` / `wake()`
- `add_schedule()` / `delete_schedule()`
- `register_dex_task()`
- `tick_once()`
- `_poll_dex()`
- `_record()` / `_persist()`
- `get_status()`

### phase-3 必须修改的点

#### A. 在 `_poll_dex()` 后接 continuation evaluation
当前 `src/adk_agent/kairos/runtime.py:219-240` 的逻辑是：
- task completed/failed -> 记录事件 -> untrack

phase-3 需要变成：
- task completed/failed -> richer summary
- 更新 workflow stage
- 调用 `ContinuationEngine`
- 生成 `internal trigger` 或 `planned action`
- 如满足规则则自动创建 follow-up Dex task

#### B. 在 `tick_once()` 中处理 internal continuation trigger
当前 `TriggerKind.INTERNAL` 虽然存在于 `models.py:17-21`，但未真正形成 phase-3 主循环的一部分。

需要增强：
- `pending_triggers` 中的 internal trigger 执行路径
- 让 runtime 能区分：
  - manual wake
  - schedule wake
  - continuation wake

#### C. 增加去重与最大自动步数限制
建议在 runtime 内增加：
- `max_auto_steps_per_tick`
- follow-up fingerprint 去重
- 同一 workflow follow-up 不重复注册

#### D. 扩展 `get_status()`
返回更多 phase-3 调试信息：
- `active_workflow`
- `planned_actions`
- `blocked_reason`
- `continuation_history`（可裁剪）

### 为什么必须改
phase-3 的“主动续推”最终必须落到 runtime 主循环里，否则就只是一个旁路工具。

---

## 2.3 `src/adk_agent/main_web_start_steering.py`

### 当前职责（与 KAIROS 直接相关部分）
- `SteeringSession._persist_session_state()`
- `SteeringSession._save_kairos_state()`
- `SteeringSession._emit_kairos_event()`
- `SteeringSession._append_kairos_log()`
- `SteeringSession.run_kairos_turn()`
- `SteeringSession.get_or_create_kairos_runtime()`
- route registration: `register_kairos_routes(...)`

### phase-3 必须修改的点

#### A. 升级 `run_kairos_turn()`
当前位置：
- `src/adk_agent/main_web_start_steering.py:450-477`

当前 synthetic prompt 只够 phase-2：
- 看状态
- 看 dex 完成
- 决定是否 sleep

phase-3 需要让它带入更多上下文：
- 当前 workflow
- 当前 trigger
- 已完成任务摘要
- planned actions
- blocked reason
- autonomy policy

#### B. 给 runtime 提供安全的 follow-up 执行回调
如果 phase-3 要让 KAIROS 自动创建 Dex task，建议不要在 `runtime.py` 里直接散乱 import 业务执行逻辑。

更稳妥的方式：
- 在 `SteeringSession` 中提供受控 callback
- runtime / continuation engine 通过 callback 发起 Dex task 创建与 handoff 注册

#### C. `get_or_create_kairos_runtime()` 接线 continuation engine
当前位置：
- `src/adk_agent/main_web_start_steering.py:479-500`

这里需要把：
- `ContinuationEngine`
- workflow policy
- 受控 follow-up callback

一起挂入 runtime。

### 为什么必须改
KAIROS 不是独立 daemon，当前是挂在 `SteeringSession` 内的 runtime；phase-3 要落地，宿主必须参与接线。

---

## 2.4 `src/adk_agent/kairos/api.py`

### 当前职责
当前已暴露：
- start / stop / wake / status
- schedules CRUD
- dex register
- attach / list

### phase-3 必须修改的点

#### A. 扩展 `status`
返回：
- `active_workflow`
- `planned_actions`
- `blocked_reason`
- 可能还可加 `continuation_policy`

#### B. 新增调试接口（建议）
- `GET /api/sessions/{session_id}/kairos/workflow`
- `GET /api/sessions/{session_id}/kairos/planned-actions`
- `POST /api/sessions/{session_id}/kairos/policy`

### 为什么必须改
phase-3 一旦增强自治，若 API 仍只暴露 tracked tasks，开发者无法解释“KAIROS 为什么继续 / 为什么停住”。

---

## 2.5 `src/adk_agent/static/script.js`

### 当前职责
phase-2 已实现：
- `formatKairosTrackedTasks()`
- `formatKairosEvents()`
- `formatKairosStatus()`
- `refreshKairosStatus()`
- `registerDexHandoff()`

### phase-3 必须修改的点

#### A. 新增 workflow 与 planned actions 展示
建议新增 helper：
- `formatKairosWorkflow(workflow)`
- `formatKairosPlannedActions(actions)`

#### B. 新增 blocked / waiting_input 展示
让 UI 能显示：
- 当前被什么阻塞
- 是否在等待人类输入

#### C. `refreshKairosStatus()` 同步渲染新字段
例如渲染：
- `#kairosWorkflow`
- `#kairosPlannedActions`
- `#kairosBlockedReason`

### 为什么必须改
phase-2 UI 解决了“跟踪什么 task”；
phase-3 UI 要解决“为什么继续、下一步是什么、为什么停住”。

---

## 2.6 `src/adk_agent/kairos/__init__.py`

### 当前职责
统一导出 phase-2 模型。

### phase-3 必须修改
导出新增的：
- workflow types
- planned action types
- continuation types

### 为什么必须改
避免测试与调用层 import 路径过于分散。

---

## 2.7 可选修改：`src/adk_agent/kairos/dex_bridge.py`

### 当前职责
把 Dex 任务转换成 `DexTaskSnapshot`。

### phase-3 可能需要增强的点
如果 phase-3 要做更强的 artifact-aware continuation，可考虑增加：
- 更多 artifact metadata
- 更明确的 result/log tail access 辅助

### 是否必须立即修改
不一定。若第一版 continuation 只依赖：
- `status`
- `description`
- `result_summary`
- `error_summary`
- `log_path`

则可以先不动。

---

## 3. 对应测试文件扩展清单

## 3.1 `tests/kairos/test_models.py`

### 必须扩展
新增覆盖：
- workflow / planned action / policy 的 round-trip 序列化
- legacy state 兼容
- 新字段默认值

### 建议新增测试名
- `test_state_round_trip_preserves_workflow_and_planned_actions`
- `test_load_legacy_state_fills_phase3_defaults`
- `test_policy_defaults_are_stable`

---

## 3.2 `tests/kairos/test_runtime.py`

### 必须扩展
这是 phase-3 的核心 runtime 回归文件。

### 建议新增测试名
- `test_completed_inputs_enqueue_internal_continuation_trigger`
- `test_runtime_auto_creates_report_follow_up_when_all_inputs_ready`
- `test_runtime_does_not_duplicate_follow_up_task_creation`
- `test_runtime_enters_waiting_input_when_required_artifact_missing`
- `test_runtime_respects_max_auto_steps_per_tick`
- `test_runtime_status_exposes_workflow_and_planned_actions`

### 说明
当前该文件已经覆盖：
- handoff lifecycle
- multi-stage workflow convergence

phase-3 应继续把“主动续推”作为 runtime 层第一证据源。

---

## 3.3 新增 `tests/kairos/test_continuation.py`

### 建议覆盖
- 规则引擎判断 all inputs ready
- artifact missing -> blocked reason
- follow-up 去重
- policy 对决策的影响

### 为什么建议新增
把纯决策逻辑从 runtime 状态机测试中拆出来，失败定位更清晰。

---

## 3.4 `tests/dex/test_tools.py`

### 建议扩展
在现有真实 Dex 子进程测试基础上，增加：
- runtime 自动创建 follow-up Dex task 的真实集成验证
- 跟踪 report auto-created 场景

### 建议新增测试名
- `test_kairos_runtime_auto_registers_report_task_against_real_dex`
- `test_auto_created_follow_up_task_produces_expected_summary`

---

## 3.5 `tests/kairos/live_http_kairos_demo_outputs_regression.py`

### 必须扩展
这是最关键的 live 证据链。

### 当前 phase-2 行为
- 手工创建并注册 phase-1 tasks
- 手工创建并注册 report task

### phase-3 目标
改成：
- phase-1 tasks 仍可手工注册
- **不再手工注册 report**
- 等待 KAIROS 自动创建 report task
- 验证 `recent_events` 中出现 auto-created follow-up 的描述

### 建议新增断言
- 存在 `auto-created report task`
- 最终 `report.json` 落盘
- 最终 `mode == idle`
- `planned_actions` 没有重复残留

---

## 3.6 `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

### 必须同步扩展
保持 pytest 包装层与 live 主脚本一致。

---

## 3.7 `tests/kairos/test_frontend_script_kairos_ui.py`

### 必须扩展
新增校验：
- workflow helper 暴露
- planned actions helper 暴露
- 新 panel 的 DOM id 存在
- multiline text 渲染仍然成立

### 建议新增测试名
- `test_script_exposes_workflow_and_planned_actions_helpers`
- `test_kairos_modal_renders_workflow_and_blocked_reason_panels`

---

## 4. 推荐的实现顺序

### Step 1
先改：
- `src/adk_agent/kairos/models.py`
- `src/adk_agent/kairos/__init__.py`
- `tests/kairos/test_models.py`

### Step 2
新增：
- `src/adk_agent/kairos/continuation.py`
- `src/adk_agent/kairos/workflows.py`
- `tests/kairos/test_continuation.py`

### Step 3
改：
- `src/adk_agent/kairos/runtime.py`
- `tests/kairos/test_runtime.py`
- `tests/dex/test_tools.py`

### Step 4
改：
- `src/adk_agent/main_web_start_steering.py`
- `src/adk_agent/kairos/api.py`

### Step 5
改：
- `src/adk_agent/static/script.js`
- `tests/kairos/test_frontend_script_kairos_ui.py`
- `tests/kairos/live_http_kairos_demo_outputs_regression.py`
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

---

## 5. 一句话总结

phase-3 真正需要新增的，不是“更多 tracked task 字段”，而是：

> **一层独立的 continuation 规则与 workflow 语义，让当前 runtime 能在任务完成后主动决定并执行下一步。**

所以代码层面的最关键动作是：

1. **新增 `continuation.py`**
2. **新增 `workflows.py`**
3. **扩 `models.py` 与 `runtime.py`**
4. **把 live HTTP 回归升级到“report task 由 KAIROS 自动创建”**

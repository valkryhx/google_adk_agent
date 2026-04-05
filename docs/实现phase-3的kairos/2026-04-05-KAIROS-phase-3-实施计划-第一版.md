# KAIROS Phase 3 实施计划（第一版）

> 日期：2026-04-05
> 关联文档：`docs/实现phase-3的kairos/2026-04-05-KAIROS-phase-3-演进思考.md`
> 目标：把“phase-3 演进思考”进一步收敛成一个对当前仓库可直接执行的实施计划，明确模块改造点、状态模型演进、测试策略与落地顺序。

---

## 1. 实施目标

phase-3 第一阶段不追求完整 supervisor，也不追求一步到位复刻 Claude Code 内部 assistant daemon。

这一阶段的唯一核心目标是：

> **让当前 KAIROS 从“能观察 Dex 后台任务完成”升级为“能在任务完成后主动发现下一步并自动续推 workflow”。**

在当前代码里，这意味着：

1. 引入比 `tracked_dex_task_ids` 更高一层的 workflow / planned action 结构
2. 在 `Dex completed/failed` 之后，不只写 brief，还能生成 internal continuation trigger
3. 让 `run_kairos_turn()` 带着更明确的 goal / next-action 上下文运行
4. 至少打通一个真正的自主闭环：
   - `sales + traffic + quality 全部完成`
   - `KAIROS 自动创建 report Dex task`
   - `自动注册 handoff`
   - `最终收敛并汇报`

---

## 2. 总体方案

我建议 phase-3 第一版采用：

> **Runtime orchestration + rule-based Continuation Engine + workflow-aware state**

而不是：

- 直接把自治全交给 LLM
- 或继续把所有逻辑堆进 `runtime.py`

### 这样拆的原因

当前代码边界其实已经很清楚：

- `runtime.py` 负责 tick / wake / schedule / handoff / persistence
- `scheduler.py` 负责 cron -> trigger
- `dex_bridge.py` 负责读 Dex task snapshot
- `main_web_start_steering.py` 负责宿主、turn 执行、事件输出

phase-3 要做的是在这之上补一层：

- **continuation decision**
- **planned action generation**
- **workflow stage progression**

所以最合理的新增模块不是 supervisor，而是：

- `continuation.py`
- `workflows.py`

---

## 3. 代码改造清单

## 3.1 建议新增文件

### 3.1.1 `src/adk_agent/kairos/continuation.py`

**职责：**
- 输入当前 runtime state、Dex completed snapshots、recent events、workflow state
- 输出 continuation decision
- 决定是否：
  - 生成 internal trigger
  - 生成 planned action
  - 自动创建 follow-up Dex task
  - 进入 waiting_input / blocked

**建议先实现为规则引擎，不直接做 LLM planner。**

建议核心接口：

```python
class ContinuationEngine:
    def evaluate_after_dex_poll(self, state, completed_tasks, tracked_tasks) -> list[ContinuationDecision]:
        ...

    def evaluate_before_turn(self, state) -> list[ContinuationDecision]:
        ...
```

---

### 3.1.2 `src/adk_agent/kairos/workflows.py`

**职责：**
- 定义 workflow template
- 把当前演示与未来自动续推逻辑从“测试里的隐式约定”提升为显式配置

建议先支持一个模板：

- `demo_report_pipeline`

模板里显式定义：
- phase-1 input tasks: `sales`, `traffic`, `quality`
- convergence rule: all inputs completed and artifacts exist
- phase-2 follow-up: create `report`

---

## 3.2 必须修改的文件

### 3.2.1 `src/adk_agent/kairos/models.py`

**需要新增的状态结构：**

#### `KairosWorkflowStage`
字段建议：
- `stage_id`
- `label`
- `status` (`pending/running/completed/failed/blocked`)
- `task_ids`
- `artifacts`
- `summary`

#### `KairosWorkflow`
字段建议：
- `workflow_id`
- `goal`
- `status` (`active/waiting_input/completed/failed/paused`)
- `current_stage`
- `stages`
- `metadata`

#### `KairosPlannedAction`
字段建议：
- `action_id`
- `kind`
- `reason`
- `payload`
- `status`
- `created_at`

#### `KairosContinuationPolicy`
字段建议：
- `auto_continue_on_all_inputs_ready`
- `auto_verify_artifacts`
- `auto_summarize_completed_task`
- `max_auto_steps_per_tick`
- `dedupe_window_seconds`

#### 在 `KairosState` 中新增
- `active_workflow`
- `planned_actions`
- `blocked_reason`
- `continuation_history`
- `policy`

**目的：**
让状态从“只知道 tracked tasks”升级为“知道我在推进什么目标、下一步准备做什么”。

---

### 3.2.2 `src/adk_agent/kairos/runtime.py`

这是 phase-3 第一阶段最核心的改造文件。

#### 需要增强的地方

**A. 在 `_poll_dex()` 之后做 continuation evaluation**

当前位置：
- `src/adk_agent/kairos/runtime.py:219-240`

当前行为：
- 任务完成 -> 记录事件 -> 从 tracked 列表移除

需要增强为：
- 任务完成 -> richer summary
- 更新 workflow stage
- 调用 `ContinuationEngine`
- 若有决策，则：
  - 生成 `TriggerKind.INTERNAL`
  - 或生成 `planned_actions`
  - 或直接自动创建 follow-up Dex task

**B. 在 `tick_once()` 中增加 internal continuation trigger 执行路径**

当前位置：
- `src/adk_agent/kairos/runtime.py:116-180`

新增逻辑：
- `pending_triggers` 中若是 `INTERNAL`
- 让 turn 带着更明确的 continuation context 执行
- 或先执行 deterministic planned action，再决定是否需要 LLM brief

**C. 增加自动续推步数限制**

建议增加：
- `auto_steps_executed_this_tick`
- 达到上限后停止自动推进，避免 runaway autonomy

**D. 增加去重机制**

避免：
- 同一个 phase-1 收敛被多次识别
- 同一个 report task 被重复创建

---

### 3.2.3 `src/adk_agent/main_web_start_steering.py`

#### 需要改的点

**A. 升级 `run_kairos_turn()` 的 synthetic prompt**

当前位置：
- `src/adk_agent/main_web_start_steering.py:450-477`

当前 prompt 太轻，只适合 phase-2。

phase-3 应补：
- 当前 workflow 摘要
- 当前 trigger 类型与 reason
- 最近完成的任务摘要
- planned actions / blocked reason
- autonomy 约束：
  - 若存在无需用户介入的下一步，优先自动推进
  - 若缺信息，则明确提出 ask-user brief
  - 若没有高价值动作，sleep

**B. 为 KAIROS turn 注入更明确的 state summary**

现在只传 `reason`。
phase-3 应把关键上下文摘要串进去。

**C. 如需要自动创建 Dex task，可在宿主层提供安全��行入口**

例如：
- runtime 不直接 import dex create/start 逻辑乱调
- 由 `SteeringSession` 暴露一个更受控的 callback 给 runtime/continuation engine 使用

---

### 3.2.4 `src/adk_agent/kairos/api.py`

建议新增/增强：

- `GET /api/sessions/{session_id}/kairos/workflow`
- `GET /api/sessions/{session_id}/kairos/planned-actions`
- `POST /api/sessions/{session_id}/kairos/policy`
- 在现有 `status` 里返回：
  - `active_workflow`
  - `planned_actions`
  - `blocked_reason`

**目的：**
让 phase-3 的自治状态可调试、可观测，而不是黑盒。

---

### 3.2.5 `src/adk_agent/static/script.js`

建议 UI 增强区块：

- `Current Workflow`
- `Planned Next Actions`
- `Blocked / Waiting Input`
- `Autonomy Decisions`

**目标：**
phase-2 UI 解决“看 tracked task”；
phase-3 UI 要解决“看为什么继续、下一步是什么、为什么停住”。

---

### 3.2.6 `src/adk_agent/kairos/__init__.py`

需要导出新增模型和 continuation 相关类型，避免测试与调用层 import 散乱。

---

## 4. 最小落地闭环（建议 phase-3 第一里程碑）

我建议优先做下面这条闭环，不要一开始发散：

### 4.1 闭环目标

在现有 demo workflow 中，当：

- `sales`
- `traffic`
- `quality`

三个输入任务全部完成，且对应产物存在时，KAIROS 自动：

1. 判断 phase-1 已收敛
2. 生成一个 internal continuation decision
3. 自动创建 report Dex task
4. 自动 register dex handoff
5. recent_events 写入：
   - `phase-1 converged, auto-created report task`
6. report 完成后自动汇报摘要并收敛到 `idle`

### 4.2 为什么优先做这条

因为当前仓库已经有：
- 完整的 demo story
- 真实 Dex 子进程
- 真实产物落盘
- 现成 live regression

所以这是最容易把“更 proactive”变成可见事实的地方。

也就是说，phase-3 最有说服力的第一步不是再讲概念，而是把：

> `manual report registration`

替换成：

> `Kairos auto-created report task`

---

## 5. 测试计划

phase-3 继续沿用 phase-2 已经建立的分层验证策略。

## 5.1 Runtime 层

修改/新增：
- `tests/kairos/test_models.py`
- `tests/kairos/test_runtime.py`

建议新增测试名：

- `test_state_round_trip_preserves_workflow_and_planned_actions`
- `test_completed_inputs_enqueue_internal_continuation_trigger`
- `test_continuation_engine_auto_creates_report_task_when_all_inputs_ready`
- `test_runtime_does_not_duplicate_follow_up_task_creation`
- `test_runtime_enters_waiting_input_when_follow_up_requires_user_data`
- `test_runtime_respects_max_auto_steps_per_tick`

### 关注点
- 新状态模型序列化
- internal trigger 生成
- planned action 去重
- waiting_input / blocked 语义

---

## 5.2 Integration 层

修改/新增：
- `tests/dex/test_tools.py`
- 可新增 `tests/kairos/test_continuation_engine.py`

建议新增测试名：

- `test_kairos_runtime_auto_registers_follow_up_report_task_against_real_dex`
- `test_continuation_engine_verifies_artifact_presence_before_follow_up`
- `test_failed_follow_up_task_records_blocked_reason`

### 关注点
- 真实 Dex task 文件
- 真实子进程完成后，KAIROS 是否自动续推
- 结果摘要与 artifact-aware 判断

---

## 5.3 Live HTTP 层

修改：
- `tests/kairos/live_http_kairos_demo_outputs_regression.py`
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

### 当前 phase-2 行为
- 手工注册 phase-1 tasks
- 手工注册 report task

### phase-3 目标
改为：
- 手工注册 phase-1 tasks
- **不手工注册 report**
- 等待 KAIROS 自动创建并推进 report
- 最终验证 `report.json` 与 recent events

建议新增 live 断言：
- `recent_events` 中出现 `auto-created report task`
- `planned_actions` 不重复
- 最终 mode 收敛为 `idle`

---

## 5.4 Frontend 层

修改/新增：
- `tests/kairos/test_frontend_script_kairos_ui.py`

建议新增测试名：
- `test_script_exposes_workflow_and_planned_actions_helpers`
- `test_kairos_modal_renders_blocked_reason_and_workflow_panels`

### 关注点
- 前端是否展示 workflow / planned action / blocked reason
- 多行文本渲染是否保留

---

## 6. 建议的落地顺序

### Step 1：先扩状态模型
先改：
- `models.py`
- `__init__.py`
- `test_models.py`

目标：把 workflow / planned action / policy 这些结构定住。

### Step 2：引入 continuation engine（规则版）
新增：
- `continuation.py`
- `workflows.py`
- 对应测试

目标：先把“如何决定下一步”独立出来。

### Step 3：接入 runtime
修改：
- `runtime.py`
- 补 internal trigger / planned action execution / 去重

目标：让 continuation decision 真正进入主循环。

### Step 4：接入宿主与 Dex follow-up 创建入口
修改：
- `main_web_start_steering.py`
- 如有需要的 Dex callback 封装

目标：打通自动创建 report task 的真实闭环。

### Step 5：扩 API / UI / live regression
修改：
- `api.py`
- `script.js`
- `live_http_kairos_demo_outputs_regression.py`

目标：让 phase-3 的自治行为真正可见、可调试、可验证。

---

## 7. 风险控制要求

phase-3 必须从第一版就加上这些保护：

### 7.1 去重
避免重复创建同一个 follow-up task。

### 7.2 最大自动步数限制
避免一个 tick 内无限续推。

### 7.3 blocked / waiting_input 语义
缺输入时不要空转。

### 7.4 可观察性
任何自动决策都要能在 API / recent_events / UI 里看到原因。

---

## 8. 最终建议

如果只保留一个最小、最能体现价值的 phase-3 目标，我建议明确写成：

> **让 KAIROS 在现有 staged workflow 中，自动从 phase-1 输入收敛推进到 report 阶段，而不再需要人类手动注册 report task。**

这是最小、最真实、最能说明“已经开始跳出 REPL 主导模式”的标志。

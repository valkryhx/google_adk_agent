# Phase 05 Implementation Plan: Document-Backed Executable Progression

## Goal

把当前 document-backed work 从“planning-visible but execution-dead”推进到“至少能自主产生一步 executable progression”。

这份计划明确约束：
- 不围绕 Flask/SQLite/HTML 示例做特化
- 目标是通用的 document-backed autonomous task progression
- 保留现有 4B planning/history/API 可见性资产
- 通过最小改造补上 execution bridge，而不是回到硬编码 workflow template 扩张

---

## Problem Statement

当前仓库已经具备：
- `/api/chat` requirement drafting -> `requirements/<session>/work.md`
- `document_work_items` / `pending_requirements` runtime & API visibility
- document-backed planning winner
- spawned work write-back 的最小 host bridge

但仍缺少：
- document-backed winner -> executable next step
- step progression
- gate-aware orchestration
- 最小 attempt persistence / dedupe

当前真实断点是：
- document-backed `continue_workflow` 最终物化为 `continue_workflow_scan`
- document-backed `create_follow_up` 被硬编码阻断
- `apply_decisions()` 只会为 `create_dex_task` 创建 internal trigger

因此系统当前是 **document-aware**，但还不是 **document-orchestrating**。

---

## First-Wave Scope

第一波只做最小闭环，不做大重构：

1. 新增 progression contract
2. 让 document-backed `continue_workflow` winner 物化为 executable action
3. 让 executable action 进入 runtime/internal trigger/host callback
4. 增加最小 `StepAttempt` persistence
5. 用测试锁定“新 document-backed requirement 至少能产生一步 executable progression”

明确不做：
- 不做完整通用 workflow DSL
- 不做复杂 DAG / work graph scheduler
- 不做 LLM 直接决定自由执行命令
- 不做项目类型特化模板
- 不做 fully autonomous ship / PR loop

---

## First-Wave Target Files

### 1. `src/adk_agent/kairos/continuation.py`

#### Required changes
- 保留当前 candidate taxonomy，不推翻 4B winner/rejected 结构
- 修改 `_build_final_action()`：
  - 对旧 workflow 保持现状
  - 对 document-backed `continue_workflow`，不再返回 `continue_workflow_scan`
  - 改为调用 orchestration materializer，返回：
    - `run_dex_task`
    - `ask_user`
    - `record_blocked`
    - `sleep_until_signal`
- 扩展 `apply_decisions()`：
  - 新增 `run_dex_task` -> `planned_actions` + `TriggerKind.INTERNAL`
  - 新增 `ask_user` -> `blocked_reason` / planning-visible outcome
  - 新增 `record_blocked` -> blocked runtime outcome
  - 允许 `sleep_until_signal` 成为显式 no-op final action
- 给 document-backed candidate 增加足够 payload，便于 materializer 找到对应 `DocumentReadResult`
- 可新增辅助函数：
  - `_is_document_candidate()`
  - `_build_document_final_action()`

#### Expected result
- document-backed winner 不再默认落成 `continue_workflow_scan`
- continuation 层第一次具备 document-backed executable decision 物化能力

---

### 2. `src/adk_agent/kairos/orchestration.py` (new)

#### Required changes
新增一个最小 orchestration 层，负责把 document-backed state 转成执行原语。

#### Required functions
- `build_progress_snapshot(item: DocumentReadResult) -> WorkProgressSnapshot`
- `evaluate_document_gates(snapshot, runtime_state, path_exists) -> GateEvaluation`
- `materialize_document_action(snapshot, gates, runtime_state) -> ExecutableAction`

#### Required contract objects
- `WorkProgressSnapshot`
  - `work_id`
  - `goal`
  - `current_step`
  - `status`
  - `next_actions`
  - `blockers`
  - `open_questions`
  - `expected_artifacts`
  - `verification_needs`
  - `source_docs`
- `GateEvaluation`
  - `passed`
  - `requires_human`
  - `reason`
  - `missing_artifacts`
  - `questions`
  - `verification_pending`
- `ExecutableAction`
  - `kind`
  - `reason`
  - `payload`

#### Allowed action kinds
- `run_dex_task`
- `ask_user`
- `record_blocked`
- `spawn_child_work`
- `request_replan`
- `sleep_until_signal`

#### First-wave rules
- 有 `open_questions` / `human_input_required` -> `ask_user`
- 有 `blockers` -> `record_blocked`
- `next_actions` 非空且 gates 通过 -> `run_dex_task`
- 否则 -> `sleep_until_signal`

#### Expected result
- document-backed path 不再只是“被解释”，而是能被 materialize 为受控执行原语

---

### 3. `src/adk_agent/main_web_start_steering.py`

#### Required changes
主要修改 `create_kairos_follow_up_task()`。

#### Expand payload contract
统一接受并消费：
- `work_id`
- `step_id`
- `description`
- `source_doc`
- `current_step`
- `goal`
- `expected_artifacts`
- `next_actions`
- `open_questions`
- `human_input_required`

#### Change follow-up write-back behavior
- 优先使用 `step_id` 更新 `DocumentReadResult.current_step`
- 不再让 document-backed follow-up 默认永远写成 `follow_up`
- 对 document-backed payload 的 planned action 去重键改为：
  - `work_id + step_id + description`
  而不只是 `workflow_id + description`
- 继续复用现有：
  - Dex task 创建
  - `append_spawned_work_update()`
  - `document_work_items` 更新
  - sparse activity evidence

#### Expected result
- runtime 生成的 INTERNAL trigger metadata 能被 host bridge 直接消费
- 新 follow-up 创建后，document-backed item 的 `current_step` 至少推进一格

---

### 4. `src/adk_agent/kairos/models.py`

#### Required changes
新增最小 execution-fact persistence。

#### Add dataclass
`StepAttempt`
- `attempt_id`
- `work_id`
- `step_id`
- `action_kind`
- `status`
- `doc_fingerprint`
- `created_at`
- `completed_at`
- `result_summary`

#### Extend `KairosState`
新增：
- `step_attempts: list[StepAttempt] = field(default_factory=list)`

#### Update state serialization
- `load_kairos_state()` 读取 `step_attempts`
- `dump_kairos_state()` round-trip 保持稳定

#### Expected result
- 系统具备最小 attempt-level persistence
- 为 dedupe / retry / audit 打底

---

### 5. `tests/kairos/test_continuation.py`

#### Required new tests
1. `document_backed_continue_workflow_materializes_run_dex_task`
   - 给一个 document-backed requirement item
   - 断言 winner 仍可为 `continue_workflow`
   - 但 `final_action.kind` 不再是 `continue_workflow_scan`
   - 应变成 `run_dex_task`

2. `document_backed_open_questions_materialize_ask_user`
   - 有 `open_questions` / `human_input_required`
   - 断言 `final_action.kind == ask_user`

3. `document_backed_blocker_materializes_record_blocked`
   - 有 blocker
   - 断言 `final_action.kind == record_blocked` 或其他显式 blocked executable outcome

4. `apply_decisions_creates_internal_trigger_for_run_dex_task`
   - 构造 `ContinuationDecision(kind="run_dex_task")`
   - 断言：
     - `TriggerKind.INTERNAL`
     - `planned_actions` 正确记录
     - payload 保持一致

#### Expected result
- 先锁住最关键的桥接缺口
- 防止改完后仍只是 planning-visible

---

## Second-Wave Files (after first wave)

这些不是第一波必须，但第一波完成后应继续补：

- `src/adk_agent/kairos/runtime.py`
  - 补 document-backed executable action 的状态投影 / mode / condition tree 兼容
- `src/adk_agent/kairos/document_protocol.py`
  - 增加最小 step write-back helper
- `tests/kairos/test_runtime.py`
  - document-backed INTERNAL trigger -> host callback 回归
- `tests/test_dex_session_regression.py`
  - step progression / attempt persistence 回归
- `tests/kairos/test_api.py`
  - API 暴露 executable final_action / attempts / gate state
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`
  - 新增 generic software-task live progression scenario

---

## TDD Order

1. 先写/改 `tests/kairos/test_continuation.py`，让 document-backed path 必须产出 executable final action
2. 新建 `src/adk_agent/kairos/orchestration.py`
3. 修改 `src/adk_agent/kairos/continuation.py`
4. 修改 `src/adk_agent/main_web_start_steering.py`
5. 修改 `src/adk_agent/kairos/models.py`
6. 再补 runtime/api/dex/live tests

---

## Acceptance Criteria for First Wave

第一波完成后，必须同时满足：

1. 新 document-backed requirement 不再默认停在 `continue_workflow_scan`
2. 至少能物化出一个 executable action：
   - `run_dex_task` / `ask_user` / `record_blocked` / `sleep_until_signal`
3. `run_dex_task` 能经由 `apply_decisions()` 进入 `TriggerKind.INTERNAL`
4. host bridge 能消费 document-backed payload 并创建 follow-up
5. `document_work_items` 至少出现一次真实 progression（如 `current_step` 改变）
6. 测试明确证明：document-backed work 已从 visible 变成 executable

---

## Guardrails

- 不要针对 Flask 示例写分支或模板
- 不要回退到新的 hardcoded workflow template 扩张
- 不要让 LLM 直接生成自由执行命令并落地执行
- 不要把 spawned work 只保存在 runtime memory
- 不要把 verification 继续当成 prose advisory；后续应升级为 gate

---

## Suggested Follow-Up After First Wave

第一波落地后，下一步应继续：
- 扩 runtime/API/history 对 executable document progression 的可见性
- 把 verification 从 prose 提升为显式 gate
- 增加 generic live HTTP regression，证明“需求 -> 文档 -> 推进 -> 派生工作 -> 再推进”

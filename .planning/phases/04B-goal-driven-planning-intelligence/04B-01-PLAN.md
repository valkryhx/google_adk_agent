---
phase: 04B-goal-driven-planning-intelligence
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/adk_agent/kairos/models.py
  - src/adk_agent/kairos/continuation.py
  - tests/kairos/test_models.py
  - tests/kairos/test_continuation.py
autonomous: true
requirements: [4B-PLN-01, 4B-PLN-02]
user_setup: []
must_haves:
  truths:
    - "Kairos 每次 proactive planning 都基于固定小集合候选动作构造真实 planning artifact，而不是只留下 winner id 或空 dict。"
    - "winner 只有在出现明确更高等级候选时才允许切换；同等级候选只能用辅助 priority 排序，不能抖动式推翻当前 winner。"
    - "last_planning_result 必须稳定包含 candidates_considered、selected_candidate、rejected_candidates、final_action 与 policy_note，且不会持久化 chain-of-thought。"
  artifacts:
    - path: "src/adk_agent/kairos/models.py"
      provides: "KairosState planning artifact shape and round-trip persistence"
      contains: "last_planning_result"
    - path: "src/adk_agent/kairos/continuation.py"
      provides: "fixed candidate-set builder, tiered winner selection, rejected-candidate reasoning"
      contains: "refresh_unfinished_work"
    - path: "tests/kairos/test_models.py"
      provides: "planning artifact serialization tests"
      contains: "test_last_planning_result"
    - path: "tests/kairos/test_continuation.py"
      provides: "candidate ranking / supersession / blocked-state planning tests"
      contains: "test_refresh_unfinished_work"
  key_links:
    - from: "src/adk_agent/kairos/continuation.py"
      to: "src/adk_agent/kairos/models.py"
      via: "writes stable planning artifact into KairosState.last_planning_result"
      pattern: "last_planning_result"
    - from: "src/adk_agent/kairos/continuation.py"
      to: "tests/kairos/test_continuation.py"
      via: "candidate selection and winner supersession regression coverage"
      pattern: "selected_candidate|rejected_candidates|policy_note"
---

<objective>
把 4B 的 planning 内核落到现有 Kairos continuation 主入口中：用固定候选动作集合、三层等级 winner selection、稳定 planning artifact 与 rejected reasons，替换当前过于轻量的 proactive candidate snapshot。

Purpose: 让后续 runtime/API/history/UI 暴露的 planning 信息有真实后端语义来源，而不是在 4A 控制台上展示占位字段。
Output: 稳定的 `last_planning_result` 契约、固定 candidate taxonomy、winner retention / supersession 规则，以及覆盖这些规则的模型/continuation 测试。
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/phases/04B-goal-driven-planning-intelligence/04B-CONTEXT.md
@.planning/phases/04B-goal-driven-planning-intelligence/04B-RESEARCH.md
@docs/superpowers/specs/2026-04-09-kairos-phase-4-design.md
@src/adk_agent/kairos/models.py
@src/adk_agent/kairos/continuation.py
@tests/kairos/test_models.py
@tests/kairos/test_continuation.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Formalize the 4B planning artifact contract in Kairos state</name>
  <read_first>
    - src/adk_agent/kairos/models.py
    - .planning/phases/04B-goal-driven-planning-intelligence/04B-CONTEXT.md
    - .planning/phases/04B-goal-driven-planning-intelligence/04B-RESEARCH.md
    - tests/kairos/test_models.py
  </read_first>
  <files>src/adk_agent/kairos/models.py, tests/kairos/test_models.py</files>
  <behavior>
    - Test 1: `KairosState.last_planning_result` round-trip preserves `ts`, `goal`, `workflow_id`, `stage_id`, `candidates_considered`, `selected_candidate`, `rejected_candidates`, `final_action`, and `policy_note`.
    - Test 2: candidate entries preserve `action`, `tier`, `priority`, `blocked`, `selected`, and concise reason fields after `dump_kairos_state()` + `load_kairos_state()`.
    - Test 3: no test fixture or implementation stores fields named `deliberation`, `chain_of_thought`, or `cot` inside `last_planning_result`.
  </behavior>
  <action>在 `src/adk_agent/kairos/models.py` 保持 `last_planning_result` 为 dict 以兼容现有 state-only persistence，但把 4B 最小稳定 shape 明确固化到默认值与测试夹具中：`ts`、`goal`、`workflow_id`、`stage_id`、`candidates_considered`、`selected_candidate`、`rejected_candidates`、`final_action`、`policy_note`。同时在 `tests/kairos/test_models.py` 新增 round-trip 测试，使用至少 3 个候选（`continue_workflow`、`create_follow_up`、`sleep`）覆盖 selected/rejected 数据不会在序列化后丢失。不要新增平行 persistence 字段，不要引入完整 planner transcript 存储。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_models.py -q</automated>
  </verify>
  <acceptance_criteria>
    - `tests/kairos/test_models.py` contains `test_last_planning_result_round_trip_preserves_selected_and_rejected_candidates`.
    - `tests/kairos/test_models.py` contains the strings `candidates_considered`, `selected_candidate`, `rejected_candidates`, and `policy_note`.
    - `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_models.py -q` exits 0.
    - `src/adk_agent/kairos/models.py` does not contain `chain_of_thought`.
  </acceptance_criteria>
  <done>`KairosState.last_planning_result` 已成为稳定、可测试的 planning artifact 容器。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Upgrade proactive scan into a fixed candidate-set planner</name>
  <read_first>
    - src/adk_agent/kairos/continuation.py
    - src/adk_agent/kairos/models.py
    - .planning/phases/04B-goal-driven-planning-intelligence/04B-CONTEXT.md
    - .planning/phases/04B-goal-driven-planning-intelligence/04B-RESEARCH.md
    - tests/kairos/test_continuation.py
  </read_first>
  <files>src/adk_agent/kairos/continuation.py, tests/kairos/test_continuation.py</files>
  <behavior>
    - Test 1: `refresh_unfinished_work()` always evaluates only this fixed action taxonomy: `continue_workflow`, `create_follow_up`, `emit_brief`, `ask_user`, `sleep`, `blocked`.
    - Test 2: candidates are annotated with discrete `tier` values (`high`, `medium`, `low`) and auxiliary `priority`.
    - Test 3: when a current winner exists, same-tier candidates do not supersede it; only a newly eligible higher-tier candidate can replace it.
    - Test 4: blocked and waiting-input scenarios produce planning results whose selected action is `blocked` or `ask_user` instead of pretending autonomous progress is still available.
  </behavior>
  <action>在 `src/adk_agent/kairos/continuation.py` 内扩展现有 `refresh_unfinished_work()`，不要新开第二套 planner。具体要做：1) 基于当前 workflow/stage、artifact readiness、verification result、cooldown 与 blocked context 构造固定候选集合 `continue_workflow` / `create_follow_up` / `emit_brief` / `ask_user` / `sleep` / `blocked`；2) 给每个候选写入 `candidate_id`、`action`、`tier`、`priority`、`reason`、`blocked`、`policy_note`、必要的 `workflow_id` / `stage_id`；3) 生成 `selected_candidate` 与 `rejected_candidates`，并将 winner retention 规则固定为“只有更高 tier 候选可以推翻当前 winner”；4) 让 `last_proactive_scan.winner` 与 `last_planning_result.selected_candidate.candidate_id` 对齐；5) 在 `tests/kairos/test_continuation.py` 增加同 tier 不抖动、higher-tier supersession、cooldown fallback、verification failed -> blocked/ask_user 的回归测试。不要把 candidate taxonomy 做成无限扩展框架，不要让 numeric priority 单独决定跨 tier 推翻。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_continuation.py -q</automated>
  </verify>
  <acceptance_criteria>
    - `src/adk_agent/kairos/continuation.py` contains all six action strings: `continue_workflow`, `create_follow_up`, `emit_brief`, `ask_user`, `sleep`, `blocked`.
    - `tests/kairos/test_continuation.py` contains `test_same_tier_candidate_does_not_supersede_current_winner`.
    - `tests/kairos/test_continuation.py` contains `test_higher_tier_candidate_supersedes_current_winner`.
    - `tests/kairos/test_continuation.py` contains either `test_verification_failure_selects_blocked_or_ask_user_candidate` or equivalent exact coverage of that scenario.
    - `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_continuation.py -q` exits 0.
  </acceptance_criteria>
  <done>当前 proactive scan 已升级成真正的固定候选 planning 内核，而不是单一 continue 候选快照。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Bridge selected planning winner into final_action and decision application</name>
  <read_first>
    - src/adk_agent/kairos/continuation.py
    - src/adk_agent/kairos/models.py
    - tests/kairos/test_continuation.py
  </read_first>
  <files>src/adk_agent/kairos/continuation.py, tests/kairos/test_continuation.py</files>
  <behavior>
    - Test 1: `last_planning_result.final_action` matches the eventual `ContinuationDecision` / `planned_actions` payload for follow-up creation scenarios.
    - Test 2: `create_follow_up` and `continue_workflow` winners produce concrete executor-facing payloads instead of opaque summaries.
    - Test 3: `sleep`, `blocked`, and `ask_user` winners leave explicit `final_action.kind` values that downstream runtime/UI can surface without guessing.
  </behavior>
  <action>把 planning artifact 与执行入口接通：在 `src/adk_agent/kairos/continuation.py` 中让 `last_planning_result.final_action` 显式描述最终动作，例如 `create_dex_task`、`continue_workflow_scan`、`emit_brief_only`、`ask_user`, `blocked`, `sleep`。当 `_evaluate_demo_report_pipeline()` 或 `_evaluate_todo_delivery_pipeline()` 已确定 follow-up 条件满足时，要把该 follow-up 映射成 `create_follow_up` 候选与 `final_action.kind=create_dex_task`。当只是等待条件变化时，要把 winner 保持为 `continue_workflow` 或 `sleep`，而不是伪造 follow-up。同步补充 `tests/kairos/test_continuation.py`，断言 `final_action`、`selected_candidate.action` 与 `apply_decisions()` 产出的 planned action payload 一致。不要新增 LLM-based planner callback，不要把 final_action 写成无法执行的自然语言段落。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_continuation.py tests/kairos/test_models.py -q</automated>
  </verify>
  <acceptance_criteria>
    - `src/adk_agent/kairos/continuation.py` contains `final_action`.
    - `tests/kairos/test_continuation.py` contains `test_final_action_matches_follow_up_decision_payload`.
    - `tests/kairos/test_continuation.py` contains the exact string `create_dex_task` in planning assertions.
    - `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_continuation.py tests/kairos/test_models.py -q` exits 0.
  </acceptance_criteria>
  <done>planning artifact 已和执行层 payload 对齐，后续 runtime/API/UI 可以直接消费 `final_action`。</done>
</task>

</tasks>

<verification>
- 先跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_models.py -q` 锁定 artifact shape round-trip。
- 再跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_continuation.py -q` 锁定固定 candidate taxonomy、tier 规则与 supersession 行为。
- 最后跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_models.py tests/kairos/test_continuation.py -q` 证明模型与 continuation 联动回归通过。
</verification>

<success_criteria>
- `last_planning_result` 已具备稳定、无 chain-of-thought 的结构化 planning artifact。
- proactive planning 只从固定六类候选中选 winner，且遵守三层等级 supersession 规则。
- selected/rejected/final_action 三件套可以被 runtime、API 与 UI 直接消费，而无需猜测 planner 语义。
</success_criteria>

<output>
After completion, create `.planning/phases/04B-goal-driven-planning-intelligence/04B-01-SUMMARY.md`
</output>

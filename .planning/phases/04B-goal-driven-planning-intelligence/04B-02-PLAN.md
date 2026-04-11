---
phase: 04B-goal-driven-planning-intelligence
plan: 02
type: execute
wave: 2
depends_on: [04B-01]
files_modified:
  - src/adk_agent/kairos/runtime.py
  - src/adk_agent/kairos/api.py
  - src/adk_agent/kairos/activity_log.py
  - src/adk_agent/kairos/attach.py
  - tests/kairos/test_runtime.py
  - tests/kairos/test_api.py
  - tests/kairos/test_activity_log.py
autonomous: true
requirements: [4B-PLN-02, 4B-OBS-01, 4B-VER-01]
user_setup: []
must_haves:
  truths:
    - "Kairos 的 re-plan 是显式、可观察的状态变化，而不是 operator 只能从最终结果倒推系统可能重新想过。"
    - "history timeline 只记录显著 planning 事件：新 winner、winner 被更高等级候选推翻、进入 ask_user/blocked/sleep、显式 re-plan。"
    - "`/kairos/status` 与 attach summary 以 additive 方式暴露 planning artifact，不破坏 4A 已有 status/history 消费者。"
  artifacts:
    - path: "src/adk_agent/kairos/runtime.py"
      provides: "re-plan trigger evaluation, significant planning-event recording, status mirrors"
      contains: "get_status"
    - path: "src/adk_agent/kairos/api.py"
      provides: "status route planning mirrors"
      contains: "last_planning_result"
    - path: "src/adk_agent/kairos/activity_log.py"
      provides: "planning event -> typed timeline entry mapping"
      contains: "_to_timeline_entry"
    - path: "tests/kairos/test_runtime.py"
      provides: "re-plan and runtime status regression"
      contains: "test_"
    - path: "tests/kairos/test_api.py"
      provides: "API mirror regression for planning fields"
      contains: "test_status_route"
    - path: "tests/kairos/test_activity_log.py"
      provides: "planning timeline event classification"
      contains: "test_"
  key_links:
    - from: "src/adk_agent/kairos/runtime.py"
      to: "src/adk_agent/kairos/activity_log.py"
      via: "records significant planning events into history"
      pattern: "winner_replaced|ask_user|blocked|sleep"
    - from: "src/adk_agent/kairos/runtime.py"
      to: "src/adk_agent/kairos/api.py"
      via: "status payload mirrors planning artifact"
      pattern: "last_planning_result|planning_winner|planning_rejected_summary"
    - from: "src/adk_agent/kairos/attach.py"
      to: "src/adk_agent/kairos/api.py"
      via: "attach summary remains lightweight while hinting planning/history availability"
      pattern: "has_history"
---

<objective>
在 04B-01 的 planning artifact 基础上，把 re-plan 触发、显著 planning 事件写入 history、以及 additive status/API mirrors 全部打通，让 operator 真正能观察“为什么系统重规划、选了谁、为什么没选别的”。

Purpose: 把 planning intelligence 从内部状态升级成 runtime 可观察行为，同时保持 4A 已有 status/history surface 稳定。
Output: 显式 re-plan 触发与事件记录、稀疏但可解释的 planning timeline、以及 `/kairos/status` / attach 层的 planning mirrors 与测试。
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
@src/adk_agent/kairos/runtime.py
@src/adk_agent/kairos/api.py
@src/adk_agent/kairos/activity_log.py
@src/adk_agent/kairos/attach.py
@tests/kairos/test_runtime.py
@tests/kairos/test_api.py
@tests/kairos/test_activity_log.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add explicit re-plan trigger handling and winner diffing in runtime</name>
  <read_first>
    - src/adk_agent/kairos/runtime.py
    - src/adk_agent/kairos/continuation.py
    - .planning/phases/04B-goal-driven-planning-intelligence/04B-CONTEXT.md
    - .planning/phases/04B-goal-driven-planning-intelligence/04B-RESEARCH.md
    - tests/kairos/test_runtime.py
  </read_first>
  <files>src/adk_agent/kairos/runtime.py, tests/kairos/test_runtime.py</files>
  <behavior>
    - Test 1: runtime compares previous and current planning winners after dex poll / unfinished-work refresh.
    - Test 2: same-tier reordering does not emit a winner-replaced event.
    - Test 3: when a higher-tier candidate becomes available, runtime records explicit re-plan metadata with previous winner info.
    - Test 4: entering `ask_user`, `blocked`, or `sleep` through planning result produces distinct runtime-visible planning state.
  </behavior>
  <action>在 `src/adk_agent/kairos/runtime.py` 的 `tick_once()` 流程里，在 `_poll_dex()` 和 `refresh_unfinished_work()` 前后保留 planning snapshot，比较 `last_planning_result.selected_candidate.candidate_id` 与 `replan` 字段，识别至少这些显式 re-plan 触发：dex task complete / failed、artifact ready / missing、verification failed、cooldown entered / expired、tracked task set changed、winner 被更高 tier 候选取代。把 re-plan 结果保留在当前 planning artifact 中，同时只在“winner 新建/替换或进入 ask_user/blocked/sleep”时生成显著 runtime 事件。不要为每次 scan 都写 history，不要在 runtime 再实现第二套 candidate ranking。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py -q</automated>
  </verify>
  <acceptance_criteria>
    - `tests/kairos/test_runtime.py` contains `test_runtime_records_replan_when_higher_tier_candidate_replaces_winner`.
    - `tests/kairos/test_runtime.py` contains `test_runtime_does_not_emit_replan_for_same_tier_reordering`.
    - `src/adk_agent/kairos/runtime.py` contains `previous_winner` or equivalent explicit old-winner comparison state.
    - `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py -q` exits 0.
  </acceptance_criteria>
  <done>runtime 已能显式感知 re-plan，而不是只被动输出当前 snapshot。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Surface planning artifact and summaries through additive API mirrors</name>
  <read_first>
    - src/adk_agent/kairos/api.py
    - src/adk_agent/kairos/attach.py
    - src/adk_agent/kairos/runtime.py
    - tests/kairos/test_api.py
  </read_first>
  <files>src/adk_agent/kairos/api.py, src/adk_agent/kairos/attach.py, tests/kairos/test_api.py</files>
  <behavior>
    - Test 1: `/api/sessions/{session_id}/kairos/status` returns `last_planning_result` plus lightweight mirrors like winner/rejected summary if added.
    - Test 2: history route shape remains unchanged.
    - Test 3: attach summary stays lightweight and does not inline entire planning artifact or full history payload.
  </behavior>
  <action>扩展 `src/adk_agent/kairos/api.py` 的 status route，继续走 additive 方式暴露 planning fields：至少保留 `last_planning_result`，并可新增 `planning_winner`、`planning_rejected_summary`、`planning_replan` 这类轻量 mirror，前提是不破坏现有 route shape。同步审视 `src/adk_agent/kairos/attach.py`，确保 attach summary 最多给出 `has_history`、当前 mode、以及必要的 planning availability hint，而不要内嵌完整 planning artifact。更新 `tests/kairos/test_api.py` 锁定 status route 中 planning mirrors 存在、history route 不变、attach 载荷不膨胀。不要新开 `/kairos/planning` 独立 route。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_api.py -q</automated>
  </verify>
  <acceptance_criteria>
    - `tests/kairos/test_api.py` contains `last_planning_result` assertions for status route.
    - `tests/kairos/test_api.py` contains an assertion that attach payload does not include a full `history` array.
    - `src/adk_agent/kairos/api.py` still contains `/api/sessions/{session_id}/kairos/history` unchanged as the dedicated history route.
    - `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_api.py -q` exits 0.
  </acceptance_criteria>
  <done>operator 与前端已有稳定 API surface 可读取 planning artifact，而不需要猜字段含义。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Classify significant planning events into sparse history timeline entries</name>
  <read_first>
    - src/adk_agent/kairos/activity_log.py
    - src/adk_agent/kairos/runtime.py
    - tests/kairos/test_activity_log.py
  </read_first>
  <files>src/adk_agent/kairos/activity_log.py, tests/kairos/test_activity_log.py</files>
  <behavior>
    - Test 1: planning event messages map to typed timeline kinds for selected winner, winner replaced, blocked, ask_user, and sleep.
    - Test 2: generic scan/no-op planning messages do not become first-class timeline entries.
    - Test 3: timeline entry title/message remain operator-facing and do not leak chain-of-thought text.
  </behavior>
  <action>在 `src/adk_agent/kairos/activity_log.py` 扩展 `_to_timeline_entry()`，识别 4B planning 事件并映射成稳定 timeline kinds，例如 `planning_selected`、`planning_replan`、`planning_blocked`、`planning_ask_user`、`planning_sleep`。运行时记录这些事件时，要使用简洁 message/title，比如“Selected winner: create_follow_up”“Re-plan: sleep -> blocked”，而不是长篇 deliberation。同步在 `tests/kairos/test_activity_log.py` 增加 planning event 解析与“普通 planning scan 不入 timeline”的测试。不要把所有 planner candidate 列表写入 history，不要让 raw internal rationale 原文暴露给 timeline。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_activity_log.py -q</automated>
  </verify>
  <acceptance_criteria>
    - `tests/kairos/test_activity_log.py` contains `planning_selected` or equivalent typed planning kind assertions.
    - `tests/kairos/test_activity_log.py` contains coverage for `blocked`, `ask_user`, and `sleep` planning entries.
    - `src/adk_agent/kairos/activity_log.py` does not classify a plain `planning scan` string as a timeline event.
    - `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_activity_log.py -q` exits 0.
  </acceptance_criteria>
  <done>history timeline 已能稀疏但清晰地讲述 Kairos planning / re-plan 轨迹。</done>
</task>

</tasks>

<verification>
- 先跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py -q` 锁定显式 re-plan 行为。
- 再跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_api.py tests/kairos/test_activity_log.py -q` 锁定 status/API/history surface。
- 最后跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py tests/kairos/test_api.py tests/kairos/test_activity_log.py -q` 证明 runtime→API→history 链路通过。
</verification>

<success_criteria>
- re-plan 触发、winner 替换与特殊停驻状态已成为显式 runtime 行为。
- `/kairos/status` 与 attach 以 additive、轻量方式暴露 planning 信息，不破坏 4A surface。
- history timeline 只记录显著 planning 事件，避免 scan 噪声淹没 operator 视图。
</success_criteria>

<output>
After completion, create `.planning/phases/04B-goal-driven-planning-intelligence/04B-02-SUMMARY.md`
</output>

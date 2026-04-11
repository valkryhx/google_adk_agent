---
phase: 05-document-driven-continuation
plan: 03
type: execute
wave: 3
depends_on: [05A, 05B]
files_modified:
  - src/adk_agent/kairos/runtime.py
  - src/adk_agent/kairos/activity_log.py
  - src/adk_agent/kairos/api.py
  - tests/kairos/test_runtime.py
  - tests/kairos/test_activity_log.py
  - tests/kairos/test_api.py
  - tests/kairos/live_http_kairos_demo_outputs_regression.py
autonomous: true
requirements: [DOC-03, DOC-05, DOC-VER-02, DOC-VER-03]
user_setup: []
must_haves:
  truths:
    - "Kairos 不只要推进已有文档工作，还要能把新发现的问题和派生工作写回文档。"
    - "派生工作只有回写文档后才算真实存在，避免幽灵任务。"
    - "document-backed re-plan / spawned work 仍需保留 4B 的 history/API/UI 可见性。"
  artifacts:
    - path: "src/adk_agent/kairos/runtime.py"
      provides: "new work discovery and document-backed replan events"
      contains: "tick_once"
    - path: "src/adk_agent/kairos/activity_log.py"
      provides: "history classification for document-backed planning events"
      contains: "planning_"
    - path: "src/adk_agent/kairos/api.py"
      provides: "document-backed status mirrors"
      contains: "planning_winner|planning_replan"
  key_links:
    - from: "src/adk_agent/kairos/runtime.py"
      to: "src/adk_agent/kairos/activity_log.py"
      via: "records spawned work / replan events into timeline"
      pattern: "planning_selected|planning_replan"
---

<objective>
让 Kairos 在自动唤醒时，不仅能推进现有文档任务，还能发现新派生工作、把它们文档化，并继续通过 planning/history/API/UI 暴露这些变化。

Purpose: 实现真正持续的 document-driven orchestration，而不是一次性起草后停住。
Output: spawned work persistence、document-backed re-plan events、API/history/UI 回归与 live evidence。
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/05-document-driven-continuation/05-CONTEXT.md
@.planning/phases/05-document-driven-continuation/05-RESEARCH.md
@src/adk_agent/kairos/runtime.py
@src/adk_agent/kairos/activity_log.py
@src/adk_agent/kairos/api.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add failing tests for spawned work and document-backed re-plan</name>
  <read_first>
    - tests/kairos/test_runtime.py
    - tests/kairos/test_activity_log.py
    - tests/kairos/test_api.py
  </read_first>
  <files>tests/kairos/test_runtime.py, tests/kairos/test_activity_log.py, tests/kairos/test_api.py</files>
  <behavior>
    - Test 1: runtime can surface spawned work discovered during wakeup.
    - Test 2: history/API expose significant document-backed planning/re-plan events.
    - Test 3: new work only becomes real after it is written back to documents.
  </behavior>
  <action>先写失败测试，锁定 5C 的核心：spawned work 文档化、document-backed re-plan 可见、history/API/UI 继续保持解释性。不要把这一步退化成只在 memory 里塞一个数组。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py tests/kairos/test_activity_log.py tests/kairos/test_api.py -q</automated>
  </verify>
  <acceptance_criteria>
    - runtime/activity/api tests contain spawned work / replan assertions.
    - 现有 4B planning visibility assertions保持可用。
    - test command exits 0 after implementation.
  </acceptance_criteria>
  <done>5C 的外部可见行为先被测试锁定。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement document-backed spawned work persistence and visibility</name>
  <read_first>
    - src/adk_agent/kairos/runtime.py
    - src/adk_agent/kairos/activity_log.py
    - src/adk_agent/kairos/api.py
  </read_first>
  <files>src/adk_agent/kairos/runtime.py, src/adk_agent/kairos/activity_log.py, src/adk_agent/kairos/api.py</files>
  <behavior>
    - Test 1: spawned work discovered at runtime is persisted as document fact.
    - Test 2: runtime emits significant document-backed planning/re-plan events only.
    - Test 3: API mirrors keep showing planning winner/replan in additive form.
  </behavior>
  <action>在 runtime 中把新发现工作接入文档回写与事件记录路径；在 activity log 和 API 中继续以 additive 方式暴露这��变化。不要引入第二套 planning trace 模型，不要把每次 scan 都写成 timeline 噪声。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py tests/kairos/test_activity_log.py tests/kairos/test_api.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q</automated>
  </verify>
  <acceptance_criteria>
    - spawned work 有持久化事实来源。
    - history/API 保持稀疏且可解释。
    - live/source regressions remain green.
  </acceptance_criteria>
  <done>Phase 5C 完成后，Kairos 已具备 document-driven 持续编排的雏形。</done>
</task>

</tasks>

<verification>
- 先跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py tests/kairos/test_activity_log.py tests/kairos/test_api.py -q`
- 再跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py tests/kairos/test_activity_log.py tests/kairos/test_api.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
</verification>

<success_criteria>
- 新派生工作不再只是内存现象，而是文档事实。
- document-backed re-plan 继续具备 history/API/UI 可见性。
- Kairos 开始接近真正长期持续编排 assistant。
</success_criteria>

<output>
After completion, create `.planning/phases/05-document-driven-continuation/05C-SUMMARY.md`
</output>

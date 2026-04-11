---
phase: 05-document-driven-continuation
plan: 02
type: execute
wave: 2
depends_on: [05A]
files_modified:
  - src/adk_agent/main_web_start_steering.py
  - src/adk_agent/kairos/runtime.py
  - src/adk_agent/kairos/document_protocol.py
  - tests/kairos/test_runtime.py
  - tests/kairos/test_live_http_kairos_demo_outputs_regression.py
  - tests/kairos/live_http_kairos_demo_outputs_regression.py
autonomous: true
requirements: [DOC-04, DOC-VER-01, DOC-VER-03]
user_setup: []
must_haves:
  truths:
    - "用户需求进入 Kairos 后，不应只得到文本回复；Phase 5B 要让需求先落盘成工作文档。"
    - "需求不完整时，Kairos 应输出 open questions / ask_user，而不是伪造可执行计划。"
    - "文档一旦落盘，应进入 Kairos 的 wakeup/continuation 链路。"
  artifacts:
    - path: "src/adk_agent/main_web_start_steering.py"
      provides: "需求落盘入口与 host integration"
      contains: "chat -> work doc draft"
    - path: "src/adk_agent/kairos/runtime.py"
      provides: "new document-backed work discovery after user request"
      contains: "tick_once"
    - path: "tests/kairos/live_http_kairos_demo_outputs_regression.py"
      provides: "user requirement -> document -> continuation live helper"
      contains: "run_user_requirement_"
  key_links:
    - from: "src/adk_agent/main_web_start_steering.py"
      to: "src/adk_agent/kairos/runtime.py"
      via: "new work doc becomes observable to Kairos wakeup loop"
      pattern: "work doc|ask_user|pending work"
---

<objective>
让用户通过 `/api/chat` 输入需求后，Kairos 能先把需求转成规范化工作文档，再将该文档纳入持续推进链路，而不只是停留在自然语言回复层。

Purpose: 打通“用户需求 -> 文档工作项 -> Kairos 续推”的最小闭环。
Output: 需求落盘入口、缺失信息 ask-user 行为、以及 live/source 测试。
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
@src/adk_agent/main_web_start_steering.py
@src/adk_agent/kairos/runtime.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add failing tests for user requirement -> work doc drafting</name>
  <read_first>
    - tests/kairos/test_live_http_kairos_demo_outputs_regression.py
    - tests/kairos/live_http_kairos_demo_outputs_regression.py
  </read_first>
  <files>tests/kairos/test_live_http_kairos_demo_outputs_regression.py, tests/kairos/live_http_kairos_demo_outputs_regression.py</files>
  <behavior>
    - Test 1: source tests lock that user requirements can produce a documented work draft, not just a textual conclusion.
    - Test 2: if the requirement is underspecified, the draft includes open questions / ask-user semantics.
    - Test 3: live helper verifies the new work doc becomes visible in Kairos status or related output.
  </behavior>
  <action>先写失败测试，锁定 5B 的最小闭环：用户通过 `/api/chat` 输入受支持需求，系统会落盘工作文档并让 Kairos 后续可见。不要一开始要求 fully autonomous codegen；先验证“需求能成为文档事实”。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q</automated>
  </verify>
  <acceptance_criteria>
    - source tests contains assertions for requirement -> work doc behavior.
    - live helper mentions open questions / ask_user handling.
    - test command exits 0 after implementation.
  </acceptance_criteria>
  <done>Phase 5B 有了清晰的测试驱动目标。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire user requirement drafting into the host/runtime path</name>
  <read_first>
    - src/adk_agent/main_web_start_steering.py
    - src/adk_agent/kairos/runtime.py
    - src/adk_agent/kairos/document_protocol.py
  </read_first>
  <files>src/adk_agent/main_web_start_steering.py, src/adk_agent/kairos/runtime.py, src/adk_agent/kairos/document_protocol.py</files>
  <behavior>
    - Test 1: supported user requirement produces a work doc draft.
    - Test 2: missing info yields ask-user/open-questions output instead of fake completion.
    - Test 3: the new document-backed work item enters Kairos continuation visibility.
  </behavior>
  <action>在宿主层增加最小接线：当某类受支持需求进入聊天接口时，先触发 work doc draft 生成，再让 runtime 能发现该文档工作项。注意仍保持安全边界，不把这一步做成“用户一句话直接全自动执行代码”。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q</automated>
  </verify>
  <acceptance_criteria>
    - runtime/status 能感知新文档工作项。
    - 缺信息时进入 ask_user 路径。
    - 不破坏现有 4B live regression。
  </acceptance_criteria>
  <done>用户需求正式进入 Kairos 的 document-driven loop。</done>
</task>

</tasks>

<verification>
- 先跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
- 再跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
</verification>

<success_criteria>
- 用户需求能落盘为工作文档。
- 文档工作项能被 Kairos status/runtime 看见。
- 不完整需求会 ask_user，而不会伪造执行闭环。
</success_criteria>

<output>
After completion, create `.planning/phases/05-document-driven-continuation/05B-SUMMARY.md`
</output>

---
phase: 05-document-driven-continuation
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/adk_agent/kairos/document_protocol.py
  - src/adk_agent/kairos/document_reader.py
  - src/adk_agent/kairos/models.py
  - src/adk_agent/kairos/continuation.py
  - tests/kairos/test_document_protocol.py
  - tests/kairos/test_document_reader.py
  - tests/kairos/test_continuation.py
autonomous: true
requirements: [DOC-01, DOC-02, DOC-VER-01]
user_setup: []
must_haves:
  truths:
    - "Phase 5A 的主目标不是写死新的 workflow schema，而是建立 Kairos 的第一版提示词约束文档协议。"
    - "文档可以是 Markdown，但必须包含稳定语义锚点，供 Kairos 后续读取与更新。"
    - "代码只做薄护栏和最小中间态，不应把文档语义重新硬编码成 rigid workflow 模板。"
  artifacts:
    - path: "src/adk_agent/kairos/document_protocol.py"
      provides: "Prompt-governed doc protocol helpers / anchors"
      contains: "Goal|Current Status|Current Step"
    - path: "src/adk_agent/kairos/document_reader.py"
      provides: "LLM-facing document reading contract and normalized read result"
      contains: "read_work_document"
    - path: "src/adk_agent/kairos/continuation.py"
      provides: "document-backed unfinished work evaluation entry"
      contains: "refresh_unfinished_work"
    - path: "tests/kairos/test_document_protocol.py"
      provides: "document protocol generation/update contract tests"
      contains: "test_"
    - path: "tests/kairos/test_document_reader.py"
      provides: "document reading normalization tests"
      contains: "test_"
  key_links:
    - from: "src/adk_agent/kairos/document_reader.py"
      to: "src/adk_agent/kairos/continuation.py"
      via: "normalized document work state feeds proactive planning"
      pattern: "current_step|blockers|next_actions"
    - from: "src/adk_agent/kairos/document_protocol.py"
      to: "tests/kairos/test_document_protocol.py"
      via: "prompt-governed anchor expectations"
      pattern: "Goal|Current Status|Expected Artifacts"
---

<objective>
建立 Phase 5 的第一块底座：定义 Kairos 的提示词约束文档协议，并让 continuation engine 能开始面向 document-backed work item 而不是只面向硬编码 workflow stage 思考下一步。

Purpose: 为后续“需求落盘”和“自主发现新任务”提供统一文档事实来源。
Output: 文档协议锚点、文档读取结果中间态、最小 document-backed continuation 接线，以及对应测试。
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
@.planning/phases/05-document-driven-continuation/05-CONTEXT.md
@.planning/phases/05-document-driven-continuation/05-RESEARCH.md
@src/adk_agent/kairos/models.py
@src/adk_agent/kairos/continuation.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Define the prompt-governed document protocol anchors</name>
  <read_first>
    - .planning/phases/05-document-driven-continuation/05-CONTEXT.md
    - .planning/phases/05-document-driven-continuation/05-RESEARCH.md
    - src/adk_agent/kairos/models.py
  </read_first>
  <files>src/adk_agent/kairos/document_protocol.py, tests/kairos/test_document_protocol.py</files>
  <behavior>
    - Test 1: protocol helper exposes the required semantic anchors (`Goal`, `Current Status`, `Current Step`, `Steps`, `Expected Artifacts`, `Blockers`, `Verification`, `Replan Notes`, `Spawned Work`).
    - Test 2: generation/update prompts require normalized-but-human-readable markdown instead of JSON-only payloads.
    - Test 3: missing-key-info cases are represented as open questions rather than silently omitted.
  </behavior>
  <action>新增 `src/adk_agent/kairos/document_protocol.py`，集中存放 Phase 5A 的文档协议锚点和提示词辅助文本；在 `tests/kairos/test_document_protocol.py` 写失败测试锁定这些锚点存在，且协议强调 Markdown 文书 + 语义块，而不是 rigid schema。不要把整个协议做成数据库 schema 或 pydantic-only 模型。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_document_protocol.py -q</automated>
  </verify>
  <acceptance_criteria>
    - `tests/kairos/test_document_protocol.py` contains the anchor strings listed above.
    - `src/adk_agent/kairos/document_protocol.py` contains prompt contract helpers rather than workflow-specific template code.
    - `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_document_protocol.py -q` exits 0.
  </acceptance_criteria>
  <done>Kairos 的第一版文档协议锚点已被明确写成可测试资产。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add normalized document-reading results for continuation</name>
  <read_first>
    - src/adk_agent/kairos/continuation.py
    - .planning/phases/05-document-driven-continuation/05-RESEARCH.md
  </read_first>
  <files>src/adk_agent/kairos/document_reader.py, src/adk_agent/kairos/models.py, tests/kairos/test_document_reader.py</files>
  <behavior>
    - Test 1: reading result includes `work_id`, `goal`, `status`, `current_step`, `next_actions`, `blockers`, and `expected_artifacts`.
    - Test 2: document-reading result is an intermediate runtime shape, not a rigid requirement on markdown formatting.
    - Test 3: missing info can be surfaced as `open_questions` / `human_input_required`.
  </behavior>
  <action>新增 `src/adk_agent/kairos/document_reader.py` 和必要的最小 models 扩展，定义 Phase 5A 的“LLM reading result”中间态。它的职责是承接提示词输出结果，供 runtime/continuation 使用。不要让它直接替代全部 Kairos state，也不要在这一步接入真实 LLM 调用。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_document_reader.py tests/kairos/test_models.py -q</automated>
  </verify>
  <acceptance_criteria>
    - `tests/kairos/test_document_reader.py` contains stable field assertions for the normalized read result.
    - Missing info can be represented without crashing continuation.
    - `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_document_reader.py tests/kairos/test_models.py -q` exits 0.
  </acceptance_criteria>
  <done>Kairos 拥有了文档阅读结果的最小中间态，而不是只能消费硬编码 workflow。</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Let continuation evaluate document-backed unfinished work</name>
  <read_first>
    - src/adk_agent/kairos/continuation.py
    - src/adk_agent/kairos/document_reader.py
    - tests/kairos/test_continuation.py
  </read_first>
  <files>src/adk_agent/kairos/continuation.py, tests/kairos/test_continuation.py</files>
  <behavior>
    - Test 1: `refresh_unfinished_work()` can consume at least one document-backed work item and generate candidates without a hardcoded workflow template.
    - Test 2: blocked/open-question document states lead to `ask_user` or `blocked` outcomes.
    - Test 3: expected artifact readiness can still influence `continue_workflow` vs `sleep` vs follow-up selection.
  </behavior>
  <action>在 `src/adk_agent/kairos/continuation.py` 增加 document-backed unfinished work 的最小接线：允许 state 中存在由文档读取结果归一出来的 work item，然后沿用 4B 的 candidate taxonomy / winner / re-plan 输出。不要删除现有 demo/todo workflow 分支；只做增量式文档 work 支持。</action>
  <verify>
    <automated>PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_continuation.py tests/kairos/test_document_protocol.py tests/kairos/test_document_reader.py -q</automated>
  </verify>
  <acceptance_criteria>
    - `tests/kairos/test_continuation.py` contains document-backed continuation coverage.
    - 现有 4B continuation tests remain green.
    - `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_continuation.py tests/kairos/test_document_protocol.py tests/kairos/test_document_reader.py -q` exits 0.
  </acceptance_criteria>
  <done>Phase 5A 完成后，Kairos 已能对 document-backed work item 进行最小续推。</done>
</task>

</tasks>

<verification>
- 先跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_document_protocol.py -q`
- 再跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_document_reader.py tests/kairos/test_models.py -q`
- 最后跑 `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_continuation.py tests/kairos/test_document_protocol.py tests/kairos/test_document_reader.py -q`
</verification>

<success_criteria>
- Kairos 拥有第一版提示词约束文档协议。
- runtime/continuation 拥有最小 document-backed work item 输入面。
- 没有把文档协议重新硬编码成 rigid workflow parser。
</success_criteria>

<output>
After completion, create `.planning/phases/05-document-driven-continuation/05A-SUMMARY.md`
</output>

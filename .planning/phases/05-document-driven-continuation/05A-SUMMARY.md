---
phase: 05-document-driven-continuation
plan: 01
subsystem: kairos
tags: [kairos, documents, continuation, planning, markdown]
requires:
  - phase: 04B-goal-driven-planning-intelligence
    provides: fixed candidate taxonomy, final_action bridge, planning trace surfaces
provides:
  - prompt-governed document protocol anchors for Kairos work docs
  - normalized DocumentReadResult runtime handoff for document-backed work
  - document-backed unfinished work evaluation in continuation
  - focused regression coverage for protocol, reader, models, and continuation
affects: [05B, 05C, runtime, planning, tests]
tech-stack:
  added: []
  patterns: [prompt-governed markdown protocol, minimal normalized runtime read result, additive document-backed continuation]
key-files:
  created: [src/adk_agent/kairos/document_protocol.py, src/adk_agent/kairos/document_reader.py]
  modified: [src/adk_agent/kairos/continuation.py, src/adk_agent/kairos/models.py, tests/kairos/test_document_protocol.py, tests/kairos/test_document_reader.py, tests/kairos/test_continuation.py, tests/kairos/test_models.py]
key-decisions:
  - "Keep Phase 5 document semantics prompt-governed and markdown-first instead of parser-first."
  - "Use DocumentReadResult as a minimal runtime intermediate shape, not a rigid work-document schema."
  - "Reuse the 4B candidate taxonomy and final_action pipeline for document-backed continuation."
patterns-established:
  - "Document protocol pattern: require stable semantic anchors while keeping the document human-readable."
  - "Runtime handoff pattern: normalize only the reader output consumed by continuation."
  - "Migration pattern: add document-backed work support without removing existing workflow branches."
requirements-completed: [DOC-01, DOC-02, DOC-VER-01]
duration: unknown
completed: 2026-04-12
---

# Phase 05A: 文档协议与阅读/写入底座 Summary

**Kairos 现在具备提示词约束的工作文档协议、最小文档读取中间态，以及可消费 document-backed work item 的 continuation 输入面。**

## Performance

- **Duration:** 跨两次会话完成
- **Started:** 2026-04-11T16:46:21Z
- **Completed:** 2026-04-12T03:33:28Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- 为 Phase 5 建立了 prompt-governed、markdown-first 的文档协议锚点，而不是再引入 rigid parser-first schema。
- 为 runtime 增加了 `DocumentReadResult` 这一最小归一化读取结果，使文档工作项可以稳定进入 Kairos 状态。
- 让 `refresh_unfinished_work()` 能在保留既有 workflow 路径的同时，评估 document-backed unfinished work 并复用 4B planning/final_action 管线。

## Task Commits

Each task was committed atomically:

1. **Task 1: Define the prompt-governed document protocol anchors** - `32fed15` (feat)
2. **Task 2: Add normalized document-reading results for continuation** - `32fed15` (feat)
3. **Task 3: Let continuation evaluate document-backed unfinished work** - `32fed15` (feat)

**Plan metadata:** `a657e28` (docs: draft phase 5 planning and execution plans)

## Files Created/Modified
- `src/adk_agent/kairos/document_protocol.py` - 定义文档协议语义锚点与生成/更新提示词辅助文本
- `src/adk_agent/kairos/document_reader.py` - 提供 `read_work_document()` 与最小 normalized 读取结果
- `src/adk_agent/kairos/models.py` - 扩展 `DocumentReadResult` / `document_work_items` 的状态模型承载
- `src/adk_agent/kairos/continuation.py` - 让 continuation 能评估 document-backed unfinished work 并生成候选动作
- `tests/kairos/test_document_protocol.py` - 锁定协议锚点、markdown-first 与 open questions 约束
- `tests/kairos/test_document_reader.py` - 验证 normalized 读取结果字段与 human-input/open-questions 行为
- `tests/kairos/test_continuation.py` - 覆盖 document-backed continuation、blocked/ask_user 路径与候选动作选择
- `tests/kairos/test_models.py` - 验证 `DocumentReadResult` 在状态 round-trip 中保真

## Decisions Made
- 保持文档协议是提示词约束的 soft protocol，而不是把文档语义重新硬编码为 rigid schema。
- 只把 reader 输出归一为 `DocumentReadResult` 供 runtime 消费，避免在 5A 过早引入完整文档数据库/解析器设计。
- document-backed continuation 直接复用 4B 的 candidate taxonomy、winner 选择与 `final_action` 输出，减少并行分叉路径。

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Focused pytest 通过，但运行时出现 `pytest_asyncio` 关于 `asyncio_default_fixture_loop_scope` 未配置的弃用告警；当前不影响 05A 验证结论。

## Verification
- `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_document_protocol.py tests/kairos/test_document_reader.py tests/kairos/test_models.py tests/kairos/test_continuation.py -q`
- Result: `39 passed in 0.26s`

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- 05A 的代码与 focused verification 已完成，适合进入 05B：把用户需求落盘为 work doc 并接入 runtime/host 可见链路。
- 继续推进时应保持 document-driven、markdown-first 方向，不要回退到 parser-first 或重新打开 05A 底层协议设计。
- `private_key.yaml` 仍为本地敏感改动，后续任何提交都必须显式排除。

---
*Phase: 05-document-driven-continuation*
*Completed: 2026-04-12*

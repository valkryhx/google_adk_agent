---
phase: 05-document-driven-continuation
plan: 03
subsystem: kairos
tags: [kairos, documents, continuation, planning, spawned-work]
requires:
  - phase: 05-document-driven-continuation
    provides: requirement drafting, document-backed pending work visibility
provides:
  - document-backed spawned work persistence for Kairos follow-up creation
  - requirement-doc write-back for replan notes and spawned work facts
  - focused regression coverage for spawned work persistence and helper visibility
affects: [05-completion, runtime, host-session, document-protocol, tests]
tech-stack:
  added: []
  patterns: [document-fact persistence, additive planning visibility, markdown section append]
key-files:
  created: [.planning/phases/05-document-driven-continuation/05C-SUMMARY.md]
  modified: [src/adk_agent/kairos/document_protocol.py, src/adk_agent/main_web_start_steering.py, tests/test_dex_session_regression.py, tests/kairos/test_document_protocol.py, tests/kairos/test_live_http_kairos_demo_outputs_regression.py]
key-decisions:
  - "Spawned work only becomes real after it is written back into the requirement document."
  - "Preserve 4B additive planning/history/API visibility instead of introducing a second planning trace model."
  - "Fix the /api/chat requirement drafting path by returning both work_item and doc_path from draft_user_requirement_work_item()."
patterns-established:
  - "Requirement doc write-back pattern: append sparse entries into Replan Notes and Spawned Work instead of rewriting the whole document."
  - "Host follow-up bridge pattern: create Dex task, persist document fact, refresh runtime visibility, then emit sparse activity log evidence."
requirements-completed: [DOC-03, DOC-05, DOC-VER-02, DOC-VER-03]
duration: unknown
completed: 2026-04-12
---

# Phase 05C: 自主发现新任务与持续编排 Summary

**Kairos 现在不仅能暴露 document-backed work item，还能在 follow-up 创建时把 spawned work 回写为 requirement document 中的真实事实，并继续通过 runtime/history/API 回路保持可见。**

## Performance

- **Duration:** 跨多次会话完成
- **Completed:** 2026-04-12
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- 为 requirement work doc 增加了最小的 spawned-work 写回能力：`Replan Notes` 和 `Spawned Work` section 会追加稀疏、可读的事实条目，而不是只在 runtime 内存里插数组。
- 在 `SteeringSession.create_kairos_follow_up_task()` 中把 Dex follow-up 创建、文档回写、`DocumentReadResult` 注入 runtime、`refresh_unfinished_work()` 刷新、以及 sparse activity log 记录接成一条最小闭环。
- 修复了 `/api/chat` requirement drafting 分支的返回值缺口：`draft_user_requirement_work_item()` 现在返回 `(work_item, doc_path)`，与 `RequirementDraft(*await ...)` 调用保持一致。
- 继续保持 4B 的 additive explainability 方向：planning/history/API 仍使用现有字段体系，只补 document-backed spawned work 的事实来源与测试锁定。
- 修复了 live helper 回归中的结构性损坏，补上 `main` 导出断言，避免 source-string 通过但模块实际不可执行的假绿状态。

## Files Created/Modified

- `src/adk_agent/kairos/document_protocol.py` - 新增 `append_spawned_work_update()` 与 section append helper，把 follow-up 持久化为文档事实。
- `src/adk_agent/main_web_start_steering.py` - 在 host follow-up bridge 中接入文档回写、runtime document_work_items 更新、sparse spawned-work log，并修复 requirement drafting 返回值。
- `tests/test_dex_session_regression.py` - 新增回归测试，锁定 spawned work 必须写回 `requirements/<session_id>/work.md`，并进入 runtime `document_work_items`。
- `tests/kairos/test_document_protocol.py` - 锁定 spawned-work 文档 helper 的 source evidence。
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py` / `tests/kairos/live_http_kairos_demo_outputs_regression.py` - 保持 live/source regression helper 结构与 document-work visibility 断言有效。

## Decisions Made

- 不新增第二套 planning trace 或 document event schema；直接复用 4B 已有的 runtime/history/API surfaces。
- spawned work 的“真实性”以 requirement markdown 文档回写为准，而不是把 follow-up 仅保存在运行时状态中。
- 文档更新采用 section append，而不是全文重写，减少对人类可编辑文档的破坏性。

## Deviations from Plan

### Auto-fixed Issues

1. [Rule 3 - Blocking issue] `draft_user_requirement_work_item()` 无返回值，但 `/api/chat` 直接解包结果
- **Found during:** 05C gap review
- **Issue:** `RequirementDraft(*await session.draft_user_requirement_work_item(...))` 与函数实现不匹配，存在运行时结构缺陷。
- **Fix:** 让 `draft_user_requirement_work_item()` 返回 `(work_item, doc_path)`。
- **Files modified:** `src/adk_agent/main_web_start_steering.py`

2. [Rule 3 - Blocking issue] live helper 被误改坏导致 `main()` 导出丢失
- **Found during:** 05C verification tightening
- **Issue:** source-string assertions 仍能通过，但 live helper 模块结构已损坏。
- **Fix:** 恢复 helper 与 `main()` 分离，并新增 `test_live_http_module_exports_main_entrypoint()` 锁定模块导出。
- **Files modified:** `tests/kairos/live_http_kairos_demo_outputs_regression.py`, `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

3. [Rule 3 - Blocking issue] `_build_kairos_tick_prompt()` 在实现时临时变成实例方法，打破既有静态调用测试
- **Found during:** focused Phase 5C verification
- **Issue:** `tests/kairos/test_runtime.py::test_run_kairos_turn_prompt_includes_assistant_mode_context` 失败。
- **Fix:** 恢复 `@staticmethod` 语义。
- **Files modified:** `src/adk_agent/main_web_start_steering.py`

## Verification

- `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/test_dex_session_regression.py tests/kairos/test_document_protocol.py -q`
  - 结果：8 passed
- `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py tests/kairos/test_activity_log.py tests/kairos/test_api.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py tests/test_dex_session_regression.py tests/kairos/test_document_protocol.py -q`
  - 结果：78 passed, 3 skipped

## Full Phase 5 Verification

- `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_document_protocol.py tests/kairos/test_document_reader.py tests/kairos/test_models.py tests/kairos/test_continuation.py tests/kairos/test_runtime.py tests/kairos/test_activity_log.py tests/kairos/test_api.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py tests/test_dex_session_regression.py -q`
  - 结果：115 passed, 3 skipped

## Known Issues / Follow-ups

- 当前 spawned-work 持久化闭环是 host-side 最小实现，仍以 payload 提供的 `source_doc` / `work_id` / `goal` 为主，后续若做更强自治，需要把 document-discovery 与 richer document update strategy 接入 runtime/continuation 内核。
- focused verification 仍带 `pytest_asyncio` loop scope 与 FastAPI `on_event` deprecation warnings；这些不是 05C 阻塞项，但后续应在基础设施层统一清理。
- `private_key.yaml` 仍为本地敏感改动，后续提交必须显式排除。

## Next Phase Readiness

- Phase 5 的三个执行计划现在均已实现并有 summary 支撑，适合进入 phase-level verification / closure。
- 继续推进时应验证 05A/05B/05C 组合后的端到端体验，而不是再把 05C 回退成 runtime-only visibility patch。

---
*Phase: 05-document-driven-continuation*
*Completed: 2026-04-12*

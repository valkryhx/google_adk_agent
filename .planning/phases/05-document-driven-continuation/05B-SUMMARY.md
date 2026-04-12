---
phase: 05-document-driven-continuation
plan: 02
subsystem: kairos
completed_at: 2026-04-12
commits:
  - 98b7abc
  - 113429b
tags:
  - kairos
  - document-driven
  - requirements
  - runtime
requirements:
  - DOC-04
  - DOC-VER-01
  - DOC-VER-03
---

# Phase 05 Plan 02: Requirement drafting into document-backed Kairos work summary

最小闭环已打通：当受支持的用户需求进入 `/api/chat` 时，宿主层会先把需求落盘成 `requirements/<session_id>/work.md` 工作文档，并把该文档对应的 work item 注入 Kairos runtime/status，使 ask_user/open_questions 语义在运行态可见。

## Completed Work

- 在 `D:/git_repos/google_adk_agent/src/adk_agent/kairos/document_protocol.py` 中新增 requirement work item 生成、open question 推断、markdown work document 渲染与写盘逻辑。
- 在 `D:/git_repos/google_adk_agent/src/adk_agent/main_web_start_steering.py` 中为 `/api/chat` 增加最小 requirement drafting 分流：受支持需求直接生成工作文档并返回 ask-user 风格文本块，而不是仅停留在自然语言回复。
- 在 `D:/git_repos/google_adk_agent/src/adk_agent/kairos/runtime.py` 中扩展 status 输出，暴露 `document_work_items` 与 `pending_requirements`，使新文档工作项进入 Kairos continuation visibility。
- 更新 `D:/git_repos/google_adk_agent/tests/kairos/test_runtime.py` 与 `D:/git_repos/google_adk_agent/tests/kairos/test_live_http_kairos_demo_outputs_regression.py`，锁定 source/runtime 回归；更新 live helper `D:/git_repos/google_adk_agent/tests/kairos/live_http_kairos_demo_outputs_regression.py`，验证工作文档与 status 可见性。

## Tests Run

- `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
  - 结果：6 passed, 3 skipped
- `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
  - 结果：46 passed, 3 skipped

## Deviations from Plan

### Auto-fixed Issues

1. [Rule 3 - Blocking issue] runtime status 缺少 document-backed requirement 可见字段
- **Found during:** Task 2
- **Issue:** 新增 runtime 测试需要 `pending_requirements`，但 `KairosRuntime.get_status()` 之前只暴露 generic unfinished work。
- **Fix:** 增加 `document_work_items` 与 `pending_requirements` 投影，保留原有字段同时补充 05B 所需可见性。
- **Files modified:** `D:/git_repos/google_adk_agent/src/adk_agent/kairos/runtime.py`
- **Commit:** `113429b`

2. [Rule 3 - Blocking issue] live helper 仍停留在 boundary-check 语义
- **Found during:** Task 1 / Task 2
- **Issue:** 现有 helper 名称与断言都描述“不能推进”，无法表达 05B 的 document-first 最小闭环。
- **Fix:** 将 helper 调整为 `run_user_requirement_document_flow`，并补充文档落盘与 status 可见性断言。
- **Files modified:** `D:/git_repos/google_adk_agent/tests/kairos/live_http_kairos_demo_outputs_regression.py`, `D:/git_repos/google_adk_agent/tests/kairos/test_live_http_kairos_demo_outputs_regression.py`
- **Commit:** `98b7abc`, `113429b`

## Decisions Made

- 05B 继续保持 document-first，而不是让 `/api/chat` 直接触发代码执行或复杂 workflow parser。
- open questions 通过最小启发式补齐到 work item，并通过 `blocked` / `pending_requirements` 状态暴露 ask_user 语义。
- status 输出采用 additive 扩展，保留 4B 的 planning/runtime/history 字段不变。

## Known Stubs

- `D:/git_repos/google_adk_agent/src/adk_agent/kairos/document_protocol.py:109` `_extract_open_questions()` 目前仍是最小启发式，而非真正基于提示词的 rich requirement understanding。该 stub 不阻塞 05B 目标，但 05C 若要做更强自治编排，应升级为更真实的 requirement interpretation。

## Deferred Issues

- `requirements mark-complete` 工具未在 `D:/git_repos/google_adk_agent/.planning/REQUIREMENTS.md` 中找到 `DOC-04` / `DOC-VER-01` / `DOC-VER-03`，说明当前要求编号与文档中的 Phase 5 section 没有被该工具识别；需要 05C 或后续文档维护时修正 requirements tooling/format。

## Self-Check: PASSED

- Verified file exists: `D:/git_repos/google_adk_agent/.planning/phases/05-document-driven-continuation/05B-SUMMARY.md`
- Verified commits exist: `98b7abc`, `113429b`

# Phase 03 Verification

## Goal
让 KAIROS 从可观测、可自动续推的 runtime，升级为具备 assistant-mode tick contract、unfinished-work scanning、guardrails 与 proactive observability 的长期自治 runtime。

## Automated Verification
- `tests/kairos/test_models.py` — proactive state model persisted
- `tests/kairos/test_continuation.py` — unfinished-work scan / cooldown / guardrail logic
- `tests/kairos/test_runtime.py` — tick contract / runtime proactive state / guardrail visibility
- `tests/kairos/test_api.py` — API exposure of proactive and policy fields
- `tests/kairos/test_frontend_script_kairos_ui.py` — UI sections for proactive and guardrail state
- `tests/dex/test_tools.py` — real Dex todo pipeline still valid
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py` — live HTTP flow proves proactive fields visible in real runtime

## Regression Command
`PYTHONIOENCODING=utf-8 PYTHONPATH=. KAIROS_BASE_URL=http://127.0.0.1:8011 pytest tests/kairos/test_models.py tests/kairos/test_continuation.py tests/kairos/test_runtime.py tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py tests/dex/test_tools.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`

## Result
- Full regression: `95 passed`
- Warnings: 4 FastAPI `on_event` deprecation warnings (non-blocking, pre-existing framework warning)

## Requirement Closure
- `POL-01` complete — duplicate follow-up suppression covered by continuation tests
- `POL-02` complete — cooldown and auto-step budget guardrails verified in continuation/runtime tests
- `POL-03` complete — policy/proactive status visible via API, UI, and live HTTP regression

## Root-Cause Note for Live HTTP Verification
Task 6 的 live HTTP 初次失败并非 Phase 3 代码缺失，而是运行中的 `8000/8011` 服务仍是旧版本进程，返回的 status payload 不含 proactive 字段。重启 worktree 的 `8011` 服务后，payload 与 live regression 全部通过。

## Verdict
Phase 03 assistant-mode and proactive unfinished-work baseline verified.

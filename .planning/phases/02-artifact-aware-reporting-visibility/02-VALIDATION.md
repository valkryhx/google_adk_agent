---
phase: 02
slug: artifact-aware-reporting-visibility
status: draft
nyquist_compliant: false
wave_0_complete: true
created: 2026-04-06
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none — existing repo pytest defaults |
| **Quick run command** | `PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest tests/kairos/test_runtime.py tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py -q` |
| **Full suite command** | `PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest tests/kairos/test_runtime.py tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py tests/dex/test_tools.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q` |
| **Estimated runtime** | ~90 seconds |

---

## Sampling Rate

- **After every task commit:** Run `PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest tests/kairos/test_runtime.py tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py -q`
- **After every plan wave:** Run `PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest tests/kairos/test_runtime.py tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py tests/dex/test_tools.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | RPT-01 | runtime/api | `PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest tests/kairos/test_runtime.py tests/kairos/test_api.py -q` | ✅ | ⬜ pending |
| 02-01-02 | 01 | 1 | RPT-02 | runtime/api | `PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest tests/kairos/test_runtime.py tests/kairos/test_api.py -q` | ✅ | ⬜ pending |
| 02-02-01 | 02 | 1 | RPT-03 | frontend | `PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest tests/kairos/test_frontend_script_kairos_ui.py -q` | ✅ | ⬜ pending |
| 02-02-02 | 02 | 1 | RPT-01, RPT-02, RPT-03 | integration/live | `PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest tests/dex/test_tools.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| KAIROS 面板中的摘要区与时间线可读性 | RPT-03 | 自动测试能锁 DOM/formatter，但不能完全代表人类阅读体验 | 启动服务，打开 KAIROS 面板，确认 recent events 仍是时间线，而结果摘要区显示结构化摘要与 blocked 条件树 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

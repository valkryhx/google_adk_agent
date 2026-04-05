# Phase 2: Artifact-Aware Reporting & Visibility - Research

**Date:** 2026-04-06  
**Phase:** 02-artifact-aware-reporting-visibility  
**Requirements:** RPT-01, RPT-02, RPT-03

## Executive Summary

Phase 1 already delivers the core runtime/data path needed for Phase 2: `KairosRuntime.get_status()` exposes tracked Dex task snapshots with `result_summary`, `error_summary`, timestamps, and `log_path`; the API already returns a stable `kairos` payload plus top-level mirrors for `active_workflow`, `planned_actions`, and `blocked_reason`; and the frontend already renders independent multiline panels via formatter helpers. Phase 2 should therefore be planned as an additive refinement of three existing surfaces rather than a new subsystem:

1. **Runtime/domain layer** — add richer summary and condition-tree fields to the Kairos state/status payload.
2. **API layer** — expose those new fields compatibly, preserving existing shape while adding explicit mirrors/helpers.
3. **Frontend layer** — keep `recent_events` as timeline, add/expand a dedicated summary panel, and render condition trees/readable explanations from the new payload.

The planning risk is not missing primitives; it is letting runtime, API, and UI drift into three different representations. Plans should enforce a single shared reporting model.

## What Already Exists

### Runtime/Dex data available today
- `src/adk_agent/kairos/runtime.py:194-218` — `get_status()` already emits:
  - `tracked_dex_tasks[]`
  - per-task `status`, `description`, `result`, `result_summary`, `error_summary`, `created_at`, `completed_at`, `log_path`
  - `active_workflow`, `planned_actions`, `blocked_reason`
- `src/adk_agent/kairos/runtime.py:293-312` — `_poll_dex()` already synthesizes human-readable brief messages from task completion/failure using `result_summary` / `error_summary`, and already updates workflow completion state.
- `src/adk_agent/kairos/dex_bridge.py:10-47` — `DexTaskSnapshot` already maps the Dex task file into a runtime snapshot with `result_summary`, `error_summary`, and extracted `log_path`.
- `src/adk_agent/kairos/continuation.py:37-39` — missing-artifact blocking already exists, but only as a flat `blocked_reason` string.

### API/output shape available today
- `src/adk_agent/kairos/api.py:63-76` — `/api/sessions/{session_id}/kairos/status` already returns:
  - `kairos` full payload
  - top-level mirrors for `active_workflow`, `planned_actions`, `blocked_reason`
- Start/stop/wake/register routes all already return `runtime.get_status()` directly (`src/adk_agent/kairos/api.py:39-61`, `80-111`).

### Frontend baseline available today
- `src/adk_agent/static/index.html:220-243` — modal already has independent blocks for:
  - Active Workflow
  - Planned Actions
  - Blocked Reason
  - Tracked Dex Tasks
  - 最近事件
- `src/adk_agent/static/script.js:1916-1983` — existing formatter model is text-first / multiline-preformatted, not componentized.
- `src/adk_agent/static/script.js:2083-2090` — refresh path already populates each block independently.

### Test baseline available today
- `tests/kairos/test_runtime.py` already covers:
  - task result/error summaries in polling behavior
  - workflow/planned_actions/blocked_reason state transitions
  - multi-stage workflow convergence
- `tests/kairos/test_api.py` already validates status-route shape.
- `tests/kairos/test_frontend_script_kairos_ui.py` currently validates formatter/helper existence and panel IDs.
- `tests/kairos/live_http_kairos_demo_outputs_regression.py` already proves real end-to-end Dex/report convergence and event visibility.

## Planning Implications

### 1. Runtime should introduce a shared reporting model, not ad-hoc strings
Current state is split across:
- `recent_events` (timeline strings)
- `tracked_dex_tasks` (raw-ish snapshot data)
- `blocked_reason` (flat string)
- `active_workflow` / `planned_actions` (workflow state)

For Phase 2, planning should create a **single additive reporting model** inside runtime status, for example conceptually:
- task summary objects (for the summary panel/API)
- decision explanation object (`why_continued`, `why_stopped`, `missing_requirements`)
- condition tree object for blocked/waiting_input

This should be generated in runtime from the existing Dex/workflow data, then reused by API and frontend. Avoid deriving one representation in runtime and a different one in `script.js`.

### 2. API evolution can stay additive and low-risk
Because the frontend already reads `data.kairos` first and uses top-level mirrors only for a few fields (`script.js:2088-2090`), the safest Phase 2 API plan is:
- keep existing `kairos` payload unchanged for compatibility
- add new nested fields inside `kairos` for summary + explanation + condition tree
- optionally mirror only the highest-value new fields at top level for easy adoption if needed

Best planning posture:
- **primary source of truth** remains `kairos.*`
- top-level mirrors should exist only for convenience, not to duplicate the whole model
- route tests should lock this additive behavior

### 3. Frontend should extend current panel architecture, not re-architect UI
The current UI is not component-driven; it is formatter-driven text blocks with `white-space: pre-wrap`. That means the least-risk Phase 2 path is:
- add a new summary block in `index.html`
- add new formatter helper(s) in `script.js`
- keep `recent_events` as timeline only
- keep workflow/planned-actions/blocked-reason blocks, but make blocked reason render richer condition content instead of a flat string where appropriate

Because the user explicitly chose “现有三区+摘要” and “events = timeline”, plans should avoid any redesign into a single dashboard/overview widget.

### 4. Blocked / waiting_input needs a tree-shaped model, not just better copy
Current blocking support is only:
- workflow artifact requirement logic in continuation
- a flat `blocked_reason` string

To satisfy RPT-02 with the user’s explicit “完整条件树” decision, plans should introduce a structured representation that can answer:
- what stage we are evaluating
- which conditions are satisfied
- which conditions are missing
- which artifact/input/trigger each missing condition depends on

This likely belongs in runtime/model territory, not only frontend formatting, because both API and UI need the same semantics.

Important planning constraint: keep it inspectable without over-modeling every future policy feature. Phase 2 should capture only the condition-tree shape needed for reporting/visibility; policy history/dedupe/max-steps belongs to Phase 3.

### 5. Summary quality should come from deterministic composition first
The repo’s current summaries (`result_summary`, `error_summary`) are deterministic and testable. The roadmap also explicitly warns against letting summary quality depend on free-form LLM output.

Planning implication:
- Phase 2 should compose richer summaries from existing deterministic sources first:
  - Dex result/error summaries
  - workflow stage/artifact expectations
  - artifact existence/availability checks
  - log path presence
- If any prose generation is added, it should be tightly bounded and not become the only source of meaning

This is the safest route to satisfy RPT-01 while keeping runtime/integration/live tests stable.

## Validation Architecture

Phase 2 should keep the same layered pytest strategy used in Phase 1, but tighten it around reporting visibility rather than only workflow convergence.

### Test Infrastructure
- **Framework:** `pytest`
- **Quick run command:** `PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest tests/kairos/test_runtime.py tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py -q`
- **Integration command:** `PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest tests/dex/test_tools.py -q`
- **Live verification command:** `PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`
- **Full suite command:** `PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest tests/kairos/test_runtime.py tests/kairos/test_api.py tests/kairos/test_frontend_script_kairos_ui.py tests/dex/test_tools.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q`

### Requirement-to-Test Strategy
- **RPT-01 (artifact-aware result summaries):** cover in `tests/kairos/test_runtime.py` and `tests/dex/test_tools.py` by asserting richer summary payloads are built from `result_summary`, `error_summary`, artifact availability, and log guidance.
- **RPT-02 (why continued / why stopped / blocked reason visibility):** cover in `tests/kairos/test_runtime.py` and `tests/kairos/test_api.py` by asserting additive explanation fields and condition-tree payloads for blocked / waiting_input cases.
- **RPT-03 (frontend visibility):** cover in `tests/kairos/test_frontend_script_kairos_ui.py` and the live HTTP regression by asserting the new summary panel, richer blocked display, and compatible refresh/render behavior.

### Sampling Guidance
- After each runtime/API task: run the quick command.
- After Dex/integration changes: run the integration command.
- After frontend rendering changes: rerun the quick command plus frontend test file.
- Before phase verification: full suite must be green.

### Wave-0 Expectations
- No new framework is needed; existing pytest coverage is sufficient.
- Phase 2 should add missing regression cases rather than invent a separate validation harness.
- The only likely new fixture burden is deterministic blocked/waiting_input test data for condition-tree assertions.


The cleanest plan decomposition appears to be **two plans in one wave or two tightly-sequenced waves**:

### Candidate Plan A — Runtime/API reporting model
Focus:
- enrich runtime status with task summary objects
- add decision explanation model
- add blocked/waiting_input condition tree
- expose fields compatibly through API
- add runtime + API tests

### Candidate Plan B — Frontend visibility + regression proof
Focus:
- add summary panel / richer blocked display in UI
- preserve timeline role of recent events
- add frontend tests for new panel/formatters
- extend live/integration verification to assert new fields/visibility

A possible third micro-plan only makes sense if planning finds verification breadth too large; otherwise keep verification work attached to the runtime/API and frontend plans.

## Recommended Test Strategy

### Runtime tests
Extend `tests/kairos/test_runtime.py` to cover:
- `get_status()` includes new summary structures and explanation fields
- blocked/waiting_input yields a condition tree, not only `blocked_reason`
- summary objects are populated from `result_summary` / `error_summary` / artifacts/log presence
- recent_events remain timeline entries and are not overloaded with duplicate structured payloads

### API tests
Extend `tests/kairos/test_api.py` to cover:
- new additive fields appear in `kairos`
- existing fields remain present
- top-level mirrors (if any added) are stable and aligned with `kairos`

### Frontend tests
Extend `tests/kairos/test_frontend_script_kairos_ui.py` to cover:
- new summary panel DOM ID exists in `index.html`
- new formatter helper(s) exist in `script.js`
- refresh logic populates summary panel and richer blocked display
- current workflow/planned-actions/events blocks remain intact

### Integration / Dex tests
Extend Dex/Kairos integration tests to prove:
- real Dex task files with artifacts/logs are converted into richer summary payloads
- failure tasks surface error summary + log guidance

### Live HTTP / regression tests
Extend live HTTP regression to assert not just convergence but visibility:
- status payload contains richer summary fields after task completion
- blocked/waiting_input path (or a deterministic synthetic case) exposes inspectable missing-condition data
- final UI/API state remains human-readable without manual `.dex/tasks/*.json` inspection

## Risks To Plan Around

### Risk 1 — Duplicate semantics across runtime/API/UI
If runtime emits one shape, API mirrors another, and frontend builds a third, the phase will “work” but be brittle. Plans should define the reporting model once and test that UI/API consume it, not reinvent it.

### Risk 2 — Overloading recent_events
The user explicitly wants `recent_events` to stay a timeline. Plans should avoid turning events into the primary structured reporting channel.

### Risk 3 — Condition tree scope creep into full policy engine
A blocked condition tree is needed now, but dedupe/cooldown/max-auto-steps/policy observability belong to Phase 3. Plans should stop at reporting the current condition state.

### Risk 4 — Frontend redesign churn
The current UI pattern is stable enough for additive expansion. Replanning the modal into a richer app-like experience would create unnecessary scope and fragile tests.

## Concrete Recommendations For The Planner

1. **Treat runtime as the source of truth** for summary/explanation/condition-tree structures.
2. **Keep API additive**: extend `kairos`, add only minimal mirrors if needed.
3. **Add a dedicated summary panel** in the existing modal; do not merge all panels.
4. **Keep recent_events as a timeline** and ensure summary panel data does not depend on parsing event strings.
5. **Model blocked/waiting_input as structured conditions** with enough detail for UI + API, but not as a full future policy framework.
6. **Anchor every plan to RPT-01/02/03 explicitly** so requirements coverage gate passes cleanly.
7. **Include live/integration verification in the plans**, because this phase is about user-visible observability, not only internal state.

## Suggested Files Likely In Scope

Primary implementation files:
- `src/adk_agent/kairos/runtime.py`
- `src/adk_agent/kairos/models.py`
- `src/adk_agent/kairos/dex_bridge.py`
- `src/adk_agent/kairos/api.py`
- `src/adk_agent/static/index.html`
- `src/adk_agent/static/script.js`

Primary verification files:
- `tests/kairos/test_runtime.py`
- `tests/kairos/test_api.py`
- `tests/kairos/test_frontend_script_kairos_ui.py`
- `tests/dex/test_tools.py`
- `tests/kairos/live_http_kairos_demo_outputs_regression.py`
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

## Research Verdict

**Research complete.** The codebase already contains the necessary primitives; Phase 2 planning should focus on structuring and exposing them coherently rather than inventing a new subsystem.

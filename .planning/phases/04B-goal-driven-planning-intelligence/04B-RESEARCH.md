# Phase 4B: Goal-Driven Planning Intelligence - Research

**Researched:** 2026-04-10  
**Domain:** Kairos goal-driven planning runtime, planning artifact, re-plan trace, operator-visible decisioning  
**Confidence:** HIGH

## Summary

Phase 4B should extend the existing Kairos backbone rather than introduce a new planner subsystem. The repo already has the right anchors in place: `KairosState` already reserves `proactive_candidates`, `last_proactive_scan`, `last_guardrail_block`, and `last_planning_result`; `ContinuationEngine.refresh_unfinished_work()` already constructs a minimal candidate; `runtime.get_status()` and `/kairos/status` already mirror planning-related fields; and 4A already established the dual-surface model of “current state in status/API” plus “significant history in timeline”.

The most important design decision is to keep 4B as a constrained, inspectable planning layer, not a free-form LLM planner. The current code is deterministic and stage-driven; 4B should make that determinism legible by explicitly constructing a fixed candidate set, selecting a winner, recording rejected candidates with concise rationale, and emitting significant re-plan events when the winner changes or the system transitions into `ask_user` / `blocked` / `sleep`. The right mental model is “policy-backed planner with explicit artifacts”, not “open-ended orchestration”.

**Primary recommendation:** implement 4B by upgrading `refresh_unfinished_work()` into a fixed candidate evaluation pipeline that produces a stable `last_planning_result`, with discrete priority tiers and explicit re-plan events written to history only for significant winner/phase changes.

---

## 1. Implementation approach/options

### Recommended approach: state-first, fixed action-space planner
Use the existing continuation scan path as the single source of planning truth:

1. Build a fixed candidate set every planning cycle:
   - `continue_workflow`
   - `create_follow_up`
   - `emit_brief`
   - `ask_user`
   - `sleep`
   - `blocked`

2. Annotate each candidate with:
   - action type
   - workflow/stage context
   - tier (`high` / `medium` / `low`)
   - auxiliary `priority`
   - eligibility / blocked flags
   - concise reason fields

3. Select one winner with discrete rules:
   - High tier: `ask_user`, `blocked`
   - Medium tier: `create_follow_up`, `continue_workflow`
   - Low tier: `emit_brief`, `sleep`
   - A new candidate may replace the current winner only when it is clearly one tier higher.

4. Persist the full planning artifact into `last_planning_result`.

5. Emit a history event only when the planning outcome is significant:
   - new winner selected
   - winner replaced by a higher-tier candidate
   - transition into `ask_user`
   - transition into `blocked`
   - transition into `sleep`
   - explicit re-plan occurred

This fits the repo’s current additive style and preserves testability.

### Why this is the best fit for current code
- `ContinuationEngine.refresh_unfinished_work()` already owns unfinished-work and candidate generation.
- `evaluate_after_dex_poll()` already reacts to changing execution conditions; it can become a re-plan input rather than a separate planner.
- `KairosState` is already the persistent state surface; no new persistence layer is necessary.
- `activity_log.py` already supports append-only, typed history entries and 4A already consumes history in timeline form.

### Alternative 1: separate planning module/class
A new `planner.py` could hold candidate building + winner selection.

**Tradeoff:** cleaner separation, but probably premature for this repo size. It would add indirection before the artifact shape and trigger semantics are stable.

### Alternative 2: runtime-owned planning logic
Move planning decisions into `KairosRuntime.tick_once()`.

**Tradeoff:** easiest to patch quickly, but it would blur runtime loop concerns with candidate semantics and make unit testing weaker than continuation-owned logic.

### Recommendation
Keep planning semantics inside `src/adk_agent/kairos/continuation.py`, with `runtime.py` responsible for:
- invoking planning at the right times
- detecting significant re-plan transitions
- recording events
- exposing current planning artifact through status/API

---

## 2. Recommended artifact shape for `last_planning_result`

Use a stable, compact, operator-readable artifact. Do not store chain-of-thought. Keep one authoritative latest artifact only.

### Recommended JSON shape

```json
{
  "ts": "2026-04-10T08:30:00+00:00",
  "goal": "advance todo delivery pipeline toward shippable report",
  "workflow_id": "todo_delivery_pipeline",
  "stage_id": "verification",
  "planning_version": "4b.v1",
  "trigger": {
    "kind": "dex_poll",
    "reason": "todo_tests completed"
  },
  "replan": {
    "occurred": true,
    "kind": "winner_replaced",
    "reason": "higher_tier_candidate_available",
    "previous_winner": "sleep",
    "previous_tier": "low"
  },
  "candidates_considered": [
    {
      "candidate_id": "todo_delivery_pipeline:verification:continue",
      "action": "continue_workflow",
      "tier": "medium",
      "priority": 50,
      "workflow_id": "todo_delivery_pipeline",
      "stage_id": "verification",
      "reason": "verification stage still unfinished",
      "blocked": false,
      "selected": false,
      "policy_note": "eligible but follow-up is higher leverage"
    },
    {
      "candidate_id": "todo_delivery_pipeline:delivery_report:create_follow_up",
      "action": "create_follow_up",
      "tier": "medium",
      "priority": 60,
      "workflow_id": "todo_delivery_pipeline",
      "stage_id": "delivery_report",
      "reason": "all prerequisite tasks and artifacts are satisfied",
      "blocked": false,
      "selected": true,
      "policy_note": "allowed by continuation policy"
    },
    {
      "candidate_id": "todo_delivery_pipeline:sleep",
      "action": "sleep",
      "tier": "low",
      "priority": 10,
      "reason": "no stronger action available",
      "blocked": false,
      "selected": false,
      "policy_note": "fallback only"
    }
  ],
  "selected_candidate": {
    "candidate_id": "todo_delivery_pipeline:delivery_report:create_follow_up",
    "action": "create_follow_up",
    "tier": "medium",
    "priority": 60,
    "reason": "all prerequisite tasks and artifacts are satisfied",
    "selected_reason": "best eligible candidate in current tier ordering"
  },
  "rejected_candidates": [
    {
      "candidate_id": "todo_delivery_pipeline:verification:continue",
      "action": "continue_workflow",
      "tier": "medium",
      "priority": 50,
      "blocked": false,
      "rejected_reason": "same tier but lower auxiliary priority",
      "policy_note": "follow-up unlocks more value"
    },
    {
      "candidate_id": "todo_delivery_pipeline:sleep",
      "action": "sleep",
      "tier": "low",
      "priority": 10,
      "blocked": false,
      "rejected_reason": "lower tier than selected winner",
      "policy_note": "only valid as fallback"
    }
  ],
  "final_action": {
    "kind": "create_dex_task",
    "reason": "todo_delivery_ready",
    "payload": {
      "workflow_id": "todo_delivery_pipeline",
      "description": "generate todo delivery report"
    }
  },
  "policy_note": "winner chosen under tiered-action policy; no unrestricted planning used"
}
```

### Field guidance
- `ts`, `goal`, `workflow_id`, `stage_id`: required and stable.
- `candidates_considered`: full evaluated set for current cycle.
- `selected_candidate`: exact winner snapshot.
- `rejected_candidates`: only rejected items, with concise rationale.
- `final_action`: bridge from planner output to runtime/execution action.
- `policy_note`: short, operator-facing explanation of why the planner was allowed or constrained.

### What not to include
- raw internal deliberation transcript
- long prose reasoning
- token-heavy diagnostic blobs
- duplicated copies of full workflow state

---

## 3. Recommended re-plan trigger model

### Recommended model: hard triggers + tier-jump override
A re-plan should occur when either:
1. a hard execution condition changes, or
2. a clearly higher-tier candidate becomes available.

### Hard triggers
These should force a new planning artifact:
- Dex task completed
- Dex task failed
- required artifact became available
- required artifact disappeared / remains missing
- verification result changed
- cooldown became active
- cooldown expired
- workflow entered blocked/waiting state
- internal follow-up action succeeded or failed
- tracked task set changed from non-empty to empty, or vice versa

### Tier-jump override trigger
If the current winner exists, replace it only when a newly eligible candidate is exactly higher by tier:
- low → medium: re-plan and replace
- medium → high: re-plan and replace
- low → high: re-plan and replace
- same-tier competitor: do not thrash winner; only reorder internally using auxiliary `priority`
- lower-tier candidate appearing: do not replace winner

### Winner retention rule
If the current winner is still valid and no higher-tier candidate appears, retain it.

This is the key anti-flapping rule and directly matches the locked 4B decision.

### State distinctions to preserve
The planner should explicitly distinguish:
- `sleep`: nothing valuable enough to do now
- `blocked`: meaningful action exists but policy/runtime prevents action
- `ask_user`: meaningful action exists but human input is required
- `continue_workflow` / `create_follow_up`: actionable autonomous work exists
- `emit_brief`: useful operator-visible output exists, but not stronger than execution actions

### Suggested re-plan classification values
Use a small enum-like string set in artifact/history:
- `initial_plan`
- `input_changed`
- `cooldown_entered`
- `cooldown_expired`
- `task_failed`
- `artifact_ready`
- `artifact_missing`
- `verification_failed`
- `winner_replaced`
- `winner_retained`

---

## 4. Integration points by file

## Backend state and planning core

### `src/adk_agent/kairos/models.py`
**Role:** canonical state schema

**Recommended changes:**
- keep `last_planning_result` as dict for backward compatibility, but formalize its shape in code comments/tests
- optionally introduce lightweight dataclasses later only if shape stabilizes
- consider adding `current_winner_candidate_id` only if needed for cleaner diffing; otherwise derive from `last_planning_result.selected_candidate`

---

### `src/adk_agent/kairos/continuation.py`
**Role:** best home for 4B planning intelligence

**Recommended changes:**
- upgrade `refresh_unfinished_work()` from “build one minimal candidate” to:
  - build fixed candidate set
  - annotate tiers and auxiliary priority
  - compute selected winner
  - compute rejected candidates
  - write `proactive_candidates`
  - write `last_proactive_scan`
  - write `last_guardrail_block`
  - write `last_planning_result`
- preserve existing workflow-specific continuation checks in `_evaluate_demo_report_pipeline()` and `_evaluate_todo_delivery_pipeline()`
- use existing follow-up fingerprints to bridge planning outcome into `apply_decisions()`

---

### `src/adk_agent/kairos/runtime.py`
**Role:** runtime loop, event emission, status exposure

**Recommended changes:**
- invoke planning after dex poll and after state changes that can affect winner selection
- compare previous vs new planning result to detect significant re-plan events
- write only significant planning events to history via `_record()`
- expose richer planning artifact through `get_status()`
- keep `planned_actions` as execution-facing queue; do not make it the authoritative planning artifact

---

### `src/adk_agent/kairos/activity_log.py`
**Role:** append-only operator-facing history

**Recommended changes:**
- extend `_to_timeline_entry()` to recognize planning event kinds/messages
- add typed mapping for:
  - planning selected winner
  - re-plan winner replacement
  - entered ask_user
  - entered blocked
  - entered sleep
- keep history sparse; do not log every scan

---

### `src/adk_agent/kairos/api.py`
**Role:** additive mirror of status/history

**Recommended changes:**
- continue mirroring `last_planning_result` from status payload
- consider additive mirrors for:
  - `planning_winner`
  - `planning_replan`
  - `planning_rejected_summary`
  only if frontend benefits materially
- do not create a separate planning API yet; `/kairos/status` is sufficient

## Frontend operator console

### `src/adk_agent/static/script.js`
**Role:** formatter/rendering for Kairos console

**Recommended changes:**
- add formatter helpers:
  - `formatKairosPlanningResult(planning)`
  - `formatKairosPlanningWinner(planning)`
  - `formatKairosRejectedCandidates(planning)`
- update refresh path to render:
  - winner summary
  - rejected summary
  - re-plan note
- reuse existing history rendering path for planning events rather than inventing new fetch logic

### `src/adk_agent/static/index.html`
**Role:** current operator console DOM anchors

**Recommended changes:**
- add cards in current live column for:
  - Planning Winner
  - Last Planning Result
  - Rejected Candidates Summary
- keep history column unchanged structurally except for timeline content becoming richer

### `src/adk_agent/static/style.css`
**Role:** visual density and card hierarchy

**Recommended changes:**
- add compact styling for planning cards
- ensure rejected candidate section remains scan-friendly and not over-tall
- preserve current vertical scrolling behavior in modal body/columns

### `src/adk_agent/main_web_start_steering.py`
**Role:** host/runtime boundary and prompt plumbing

**Recommended changes:**
- likely minimal or none for MVP
- only touch if planning turns need extra structured prompt context
- avoid making 4B prompt-led unless deterministic planner signals prove insufficient

---

## 5. Verification/test strategy

### Test philosophy
Do not validate 4B only by “workflow still completes”. Validate the planning evidence itself:
- which candidates existed
- which one won
- why others were rejected
- when re-plan occurred
- what operator-visible history was emitted

### Unit tests: planning core
Target file: expand tests around `continuation.py`.

**Must cover:**
1. fixed candidate set is constructed from current state
2. tier ordering works
3. same-tier candidates do not flap winner
4. higher-tier candidate replaces current winner
5. cooldown yields `sleep` or `blocked` according to policy semantics
6. verification failure yields `blocked` or `ask_user` distinctly
7. `last_planning_result` shape is fully populated

### Runtime/API tests
Extend runtime and API tests.

**Must cover:**
- `/kairos/status` returns populated `last_planning_result`
- selected/rejected candidate fields are present
- planning artifact survives through runtime state
- re-plan relevant status fields are mirrored correctly

### Activity log / timeline tests
Extend activity-log tests.

**Must cover:**
- planning events are parsed into typed timeline entries
- winner replacement becomes a distinct timeline event
- blocked / ask_user / sleep planning transitions classify correctly
- non-significant scans do not create noisy history

### Frontend source-level tests
Extend Kairos frontend script tests.

**Must cover:**
- formatter helpers for planning result exist
- DOM contains planning cards
- rejected candidates and winner card anchors exist
- current 4A layout remains intact

### Live/semi-live regression
Use the existing todo delivery flow as the anchor.

**Must add assertions for:**
- `last_planning_result.selected_candidate` exists during a realistic flow
- at least one realistic run shows multiple candidates in state
- at least one failure/stall scenario shows explicit re-plan
- history contains significant planning evidence, not just task completion evidence

### Suggested phase gate
A credible 4B phase gate should require:
1. unit tests green for planner selection/re-plan rules
2. API tests green for artifact exposure
3. activity-log tests green for planning timeline semantics
4. frontend source tests green for operator console anchors
5. one realistic runtime flow demonstrating planning artifact + history evidence

---

## 6. Risks/guardrails

### Risk 1: planning artifact duplicates too much state
**Guardrail:** keep artifact focused on candidate evaluation and final action only.

### Risk 2: winner flapping within same tier
**Guardrail:** only allow replacement on clear tier jump; use auxiliary `priority` only for initial selection or stable same-tier ordering.

### Risk 3: history becomes spammy
**Guardrail:** log only significant planning events:
- new winner
- replaced winner
- blocked / ask_user / sleep entry
- explicit re-plan

### Risk 4: `planned_actions` and `last_planning_result` drift semantically
**Guardrail:** define them clearly:
- `last_planning_result` = latest planning artifact
- `planned_actions` = executable follow-through items

### Risk 5: introducing too much LLM dependence
**Guardrail:** keep 4B deterministic and policy-backed first. Only enrich prompt context later if necessary.

### Risk 6: local repo drift pollutes planning/verification
**Guardrails from repo context:**
- never commit `private_key.yaml`
- when running Python commands that may emit Chinese/emoji on Windows, use `PYTHONIOENCODING=utf-8`

---

## 7. Proposed plan split (1-3 plans max)

## Plan 04B-01: Planning state model and candidate selection core
**Goal:** turn minimal proactive scan into a fixed-action candidate planner with stable artifact output.

**Scope:**
- formalize candidate taxonomy and tier model
- upgrade `refresh_unfinished_work()`
- generate `last_planning_result`
- keep `apply_decisions()` aligned with selected winner
- add planner-focused unit tests

## Plan 04B-02: Runtime re-plan events, API mirrors, and history trace
**Goal:** make re-plan explicit and operator-observable without history spam.

**Scope:**
- runtime diffing of previous/new winner
- significant re-plan event emission
- status/API exposure of richer planning artifact
- activity log classification/parsing for planning events
- API and history tests

## Plan 04B-03: Operator console surfacing and live regression evidence
**Goal:** present winner/rejected/re-plan trace clearly in the 4A console and prove it in realistic flow.

**Scope:**
- add planning cards to current state column
- render selected/rejected/re-plan summaries
- preserve dense 4A layout
- extend source-level frontend tests
- extend live todo-delivery regression to assert planning evidence

---

## Recommended planning notes for the planner

- Do not split candidate taxonomy into a broad extensibility framework yet.
- Do not create a separate planning persistence channel.
- Do not emit every planning scan into history.
- Prefer upgrading existing fields over adding parallel ones.
- Use the todo-delivery pipeline as the primary realistic verification story, because it already exercises workflow progression, verification gating, follow-up creation, and history surfaces.

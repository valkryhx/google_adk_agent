# Kairos Phase 4 Design — Explainability, History UX, and Goal-Driven Planning Intelligence

**Date:** 2026-04-09
**Status:** Proposed
**Scope:** Post-Phase-3 continuation design for the next milestone
**Authoring context:** Phase 3 is already complete, pushed, and verified on `main` / `origin/main`; this spec defines what should come next rather than reopening Phase 3 work.

---

## 1. Executive Summary

Phase 3 proved that Kairos can autonomously continue deterministic workflows under rule guardrails, create follow-up Dex tasks, and survive a realistic verification pipeline. However, the current system still has a major gap between **actual autonomy** and **perceived autonomy**:

1. **Kairos often looks less intelligent than it really is** because its full history is not visible in the frontend. Users see a thin slice of current runtime state and `recent_events`, while the true progression is archived elsewhere (`memory_archive/..._kairos.md`).
2. **Kairos is still only partially goal-driven**. Much of its continuation behavior is deterministic and workflow-template driven. It can advance work, but it does not yet leave behind strong evidence that it compared alternatives, selected a winner, or explicitly re-planned when conditions changed.
3. **The frontend operator experience is not yet suitable for dense, real-time autonomy observability.** The current vertically stacked Kairos modal becomes too tall, pushes important content toward browser edges, and makes it difficult to simultaneously understand current state and prior progression.

The Phase 4 proposal therefore splits the next milestone into two sequential phases:

- **Phase 4A — Explainability, History & Operator UX**
- **Phase 4B — Goal-Driven Planning Intelligence**

This split is intentional. 4A ensures that existing and future autonomy becomes fully visible, navigable, and interpretable. 4B then strengthens Kairos’s actual planning intelligence on top of that observability foundation.

In short:

- **Phase 4A makes Kairos’s autonomy visible and inspectable**
- **Phase 4B makes Kairos more explicitly intelligent and planful**

---

## 2. Why Phase 4 Is Needed

### 2.1 What Phase 3 solved

Phase 3 delivered the following high-value capabilities:

- assistant-mode runtime state
- proactive unfinished-work scanning
- cooldown / dedupe / guardrail semantics
- richer API/UI visibility of current runtime status
- live HTTP verification that Kairos can continue work and auto-create follow-up tasks
- push/sync/cleanup and GSD closeout

The current project state already confirms:

- `main` and `origin/main` are aligned
- full Phase 3 regression passed (`96 passed`)
- temporary worktrees and stale branches were cleaned up
- the current baseline should be treated as stable and authoritative

### 2.2 What still feels insufficient

Even though Kairos truly performed real continuation work, the observed user experience revealed a meaningful problem:

> Kairos looked like it “wasn’t really doing much” because the UI did not surface enough history or reasoning.

The underlying autonomy existed, but the operator-facing evidence did not.

Separately, the current intelligence layer remains constrained:

- `ContinuationEngine` still relies heavily on deterministic workflow rules
- unfinished work scanning is currently narrow and mostly stage-local
- `last_planning_result` is not yet a rich, authoritative planning artifact
- selection among competing next actions is not yet sufficiently explicit or user-visible

As a result, Kairos today is best described as:

- **rule-guided, LLM-assisted autonomy**
- not yet **strongly goal-driven, visibly deliberative agentic planning**

### 2.3 Why not skip directly to “more intelligence”

Jumping directly into stronger planning without first solving observability would make the system harder to reason about and much harder to validate.

If Kairos begins to:

- consider multiple candidates,
- emit re-plans,
- change directions dynamically,
- defer, ask, or sleep based on richer internal reasoning,

but the operator still cannot clearly see why, then every bug investigation becomes more difficult, and user trust will fall rather than rise.

Therefore the sequence matters:

1. **First make current and future autonomy legible (4A)**
2. **Then make it stronger (4B)**

---

## 3. Guiding Principles for Phase 4

1. **Do not reopen Phase 3.** Phase 3 is already complete. Phase 4 must build on its verified baseline, not rewrite or relitigate it.
2. **Keep main as the only authoritative baseline.** Do not reintroduce old worktree-centric implementation flow for this line of work.
3. **Separate visibility from capability.** Make autonomy visible before making it more ambitious.
4. **Retain rule guardrails.** Goal-driven planning should become richer, but not collapse into unconstrained free-form LLM orchestration.
5. **Improve the operator experience as a first-class product.** If humans cannot understand what Kairos is doing, the system will not feel trustworthy, regardless of its actual competence.
6. **Preserve testability.** Any new planning intelligence must leave behind structured state that can be asserted in tests.
7. **Prefer explicit state over implied behavior.** If Kairos considers candidates or rejects one path in favor of another, that should be represented in inspectable state.

---

## 4. Proposed Milestone Structure

## Phase 4A — Explainability, History & Operator UX

### Goal

Make Kairos’s existing autonomy fully visible, interpretable, and navigable from the frontend and API so that users can clearly see:

- what Kairos is doing now,
- what it did previously,
- why it moved forward,
- why it stopped,
- what follow-up tasks it created,
- and what internal runtime conditions influenced those decisions.

### Why this phase comes first

The recent user observation is the strongest evidence for 4A:

- Kairos did real work,
- but the user could not confidently see that from the frontend,
- so the perceived intelligence level remained low.

Fixing that gap is the fastest way to increase trust and also lays the foundation for validating 4B later.

### 4A Core Deliverables

#### 4A-1. Kairos History API

Add an explicit API layer for reading session-scoped Kairos history from the archival record, not just current runtime state.

This should unify two currently separate surfaces:

- **current runtime state** (what `kairos/status` returns now)
- **archived historical activity** (what is persisted under `memory_archive/..._kairos.md`)

The history API should support at minimum:

- lookup by `session_id`, `app_name`, `user_id`
- a stable response shape for frontend consumption
- ordering by timestamp ascending/descending
- event kind typing (`status`, `brief`, `guardrail`, `follow_up`, `task_completion`, etc.)
- a small summary form suitable for timeline display

#### 4A-2. Operator-Friendly Timeline Model

Convert archived Kairos history into a timeline-oriented structure the UI can render directly.

Each timeline entry should ideally include:

- timestamp
- entry kind
- short title
- detailed message
- optional workflow/stage context
- optional task linkage (`task_id`, `description`)
- optional decision metadata if known

This should let the frontend answer questions like:

- “When did Kairos decide the workflow was ready to continue?”
- “When did it create the follow-up Dex task?”
- “What completed before that happened?”
- “Was it blocked, cooling down, or sleeping at some point?”

#### 4A-3. Kairos Modal Layout Redesign

Redesign the current Kairos modal from a long single-column vertical stack into a **two-column operator console layout**.

Recommended structure:

**Left column — Current State / Live Snapshot**
- runtime status
- active workflow
- planned actions
- blocked reason / guardrail state
- unfinished work
- proactive candidates
- current decision explanation

**Right column — Historical Context / Timeline**
- session history timeline
- task completions
- auto-created follow-up tasks
- guardrail events
- cooldown / waiting_input / blocked transitions
- brief emissions

This layout should ensure that:

- the user does not lose critical content below the fold,
- the current state and historical progression are visible at the same time,
- the panel feels like an autonomy operations console rather than a debug dump.

#### 4A-4. Aesthetic Upgrade for Dense Operator UX

The Kairos panel should not simply become a utilitarian admin grid. It should become a refined, dense, legible operator interface.

Design direction recommendation:

- dark-mode or dark-leaning monitoring-console aesthetic
- compact but breathable spacing
- clear panel separation using cards/panels rather than long blocks
- status colors used sparingly but meaningfully
- monospace only where it improves scanning, not everywhere
- stronger hierarchy for “current state” vs “history”
- make the timeline visually scannable, not just a JSON dump

This should be implemented through the existing frontend stack, with careful attention to:

- scroll containers
- pinned headers or section labels where useful
- card balance and viewport fit
- mobile degradation (if the modal is ever viewed on smaller screens)

#### 4A-5. Evidence of Work, Not Just Existence of Work

The new UI should make it obvious that Kairos truly progressed work.

That means surfacing entries like:

- “registered Dex task: todo_design”
- “completed Dex task: todo_tests — tests ready”
- “internal action: todo_delivery_ready”
- “auto-created follow-up: generate todo delivery report”

In other words, the panel should answer:

> “Did Kairos actually move this workflow forward?”

without requiring the user to grep logs or inspect the filesystem.

### 4A Acceptance Criteria

4A is complete only when all of the following are true:

1. A user can open the frontend Kairos panel and see both **current runtime state** and **historical progression** simultaneously.
2. A recently completed Kairos-driven session clearly shows the progression timeline (handoff, completion, follow-up creation, report completion, etc.).
3. The panel remains usable within a normal browser viewport and no longer feels vertically overgrown.
4. API responses expose structured history in a way the frontend can consume directly.
5. Tests verify both the history API contract and the new frontend structure.

---

## Phase 4B — Goal-Driven Planning Intelligence

### Goal

Strengthen Kairos’s autonomy from “rule-driven continuation with some LLM support” into a more explicitly **goal-driven, candidate-comparing, planning-visible assistant runtime**.

The system should still remain guardrailed, but it should now leave behind stronger evidence that it is:

- comparing alternatives,
- selecting a winner,
- rejecting weaker candidates,
- and re-planning when conditions change.

### Why 4B follows 4A

Once 4A is complete, the UI/API/history surfaces will let us safely expose richer planning state. That means 4B can add intelligence without making the system opaque.

### 4B Core Deliverables

#### 4B-1. Multi-Candidate Next-Step Selection

Today, Kairos’s unfinished work model is still relatively narrow. 4B should evolve this into a more explicit candidate-selection system.

Instead of treating the next step as a mostly fixed outcome, Kairos should be able to represent multiple candidate actions such as:

- continue current workflow stage
- trigger a follow-up task
- emit a progress brief
- emit an ask-user request
- sleep and defer
- mark blocked and wait

Each candidate should have structured fields such as:

- candidate type
- related workflow/stage
- estimated value / priority
- reason for candidacy
- reason for rejection if not selected
- blocked/guardrail flags

#### 4B-2. Real `last_planning_result`

`last_planning_result` should become a genuine planning artifact, not a placeholder field.

It should capture the latest planning outcome in a structured, inspectable format, such as:

- planning timestamp
- goal summary
- current workflow summary
- candidates considered
- selected candidate
- rejected candidates with rationale
- selected action class (`continue`, `brief`, `ask_user`, `sleep`, `blocked`)
- confidence or policy note if appropriate

This artifact should be visible in:

- runtime status
- API responses
- frontend panel
- archived history summaries when meaningful

#### 4B-3. Re-Plan Triggers

Kairos should explicitly re-plan when certain conditions occur, rather than merely stopping or waiting passively.

Examples:

- cooldown prevented progression
- verification failed
- artifact set is incomplete
- a tracked task failed
- a follow-up task produced insufficient output
- the best candidate is blocked
- the current workflow appears stalled

Re-planning should be represented as a first-class event and state transition, not merely inferred after the fact.

#### 4B-4. Distinguish “No Work” from “Cannot Progress” from “Need Human”

A stronger planning model must make these meanings distinct:

- **No meaningful candidate exists**
- **There is meaningful work, but policy prevents action now**
- **There is meaningful work, but human input is required**
- **There is meaningful work, and Kairos is choosing one candidate among several**

This distinction is essential if the system is to feel more intelligent and less like a hidden rule engine.

#### 4B-5. More Human-Like Decision Trace

By the end of 4B, a user should be able to observe evidence like:

- “Kairos considered continuing verification, producing a brief, and sleeping”
- “It chose to continue verification because artifacts were present and no human input was needed”
- “It rejected immediate action because cooldown was active”
- “It re-planned after verification failure and switched to blocked/ask-user”

This is the threshold at which Kairos starts to feel substantially more like a real assistant and less like a deterministic continuation daemon.

### 4B Acceptance Criteria

4B is complete only when all of the following are true:

1. Kairos can represent multiple candidates for next action in structured state.
2. `last_planning_result` is populated by production logic and visible in UI/API.
3. At least one realistic flow demonstrates explicit candidate comparison and winner selection.
4. At least one realistic failure/stall path demonstrates explicit re-planning.
5. Frontend and history surfaces make the planning trace intelligible to a human operator.

---

## 5. Recommended Technical Scope Boundaries

## In Scope for 4A

- history API design and implementation
- parsing/reading session-specific Kairos history from `memory_archive`
- frontend modal redesign
- timeline visualization
- current state + history side-by-side operator UX
- API/frontend tests for history and layout-relevant structure

## In Scope for 4B

- richer candidate model
- planning-result persistence and visibility
- explicit selection/rejection rationale
- explicit re-plan pathways
- tests for candidate comparison and planning artifacts

## Out of Scope for Phase 4

These should remain out of scope unless the user explicitly revises direction:

- full supervisor/worker multi-process rewrite
- generalized autonomous repo-wide work discovery across arbitrary tasks
- external notification/webhook systems
- memory distillation or long-term memory redesign
- making the LLM fully unconstrained planner for all next actions

---

## 6. Architecture Direction

### 6.1 Keep the Existing Core Backbone

The current core backbone remains valid:

- `SteeringSession`
- `KairosRuntime`
- `ContinuationEngine`
- `Dex`
- status/API/frontend visibility

Phase 4 should extend this backbone, not replace it.

### 6.2 Suggested 4A Additions

Likely implementation areas:

- `src/adk_agent/kairos/api.py`
  - add history route(s)
- `src/adk_agent/kairos/activity_log.py`
  - possibly add parsing helpers or a reader companion
- `src/adk_agent/static/index.html`
  - modal layout redesign
- `src/adk_agent/static/script.js`
  - fetch/render timeline and two-column operator UX
- frontend/API tests

### 6.3 Suggested 4B Additions

Likely implementation areas:

- `src/adk_agent/kairos/models.py`
  - richer candidate / planning result state
- `src/adk_agent/kairos/continuation.py`
  - multi-candidate construction and winner selection
- `src/adk_agent/kairos/runtime.py`
  - re-plan triggers and state transitions
- `src/adk_agent/main_web_start_steering.py`
  - richer prompt context for planning turns if needed
- runtime/continuation/api/live tests

---

## 7. Testing Strategy

### 7.1 4A Testing

Need tests proving:

- history API returns session-scoped entries
- frontend source contains required timeline/history rendering sections
- panel structure supports split current-state/history layout
- known Kairos sessions show historical events that demonstrate real progression

### 7.2 4B Testing

Need tests proving:

- multiple candidates can coexist in state
- a winner can be selected with explicit rationale
- cooldown/blocked/ask-user/sleep produce distinct planning results
- re-planning updates state rather than silently failing
- live or semi-live flows expose planning artifacts in a human-readable way

### 7.3 Guiding Testing Philosophy

Do not validate 4B only by “the workflow still completed.”

We must validate:

- what candidates existed,
- what Kairos chose,
- why it chose it,
- and what it did when conditions changed.

This is crucial because Phase 4 is partly about **perceived intelligence**, which must be backed by inspectable structured evidence.

---

## 8. Risks and Mitigations

### Risk 1 — More state, more confusion
Adding history, timeline, candidates, and planning results can create noisy or redundant state.

**Mitigation:**
- keep a clear split between current runtime state and archived history
- make planning result authoritative rather than duplicative
- avoid placeholder state with no production writer

### Risk 2 — UI becomes visually rich but operationally messy
A beautiful panel that still buries key meaning fails the goal.

**Mitigation:**
- optimize for scanning and operator decision-making first
- use a clean left/right hierarchy
- prioritize “What is Kairos doing?” and “Why?” over decorative flourish alone

### Risk 3 — Planning intelligence becomes unstable
If 4B becomes too free-form, autonomy may regress in reliability.

**Mitigation:**
- keep rule guardrails explicit
- make candidate selection inspectable
- constrain planning outputs to a structured action space

### Risk 4 — History says too little or too much
Raw event dumps can be unreadable; over-compressed summaries can hide key facts.

**Mitigation:**
- preserve raw-ish event timeline entries
- derive concise titles and structured metadata for UI display
- allow both quick scan and expandable detail where needed

---

## 9. Recommendation

Proceed with **two sequential phases**:

1. **Phase 4A — Explainability, History & Operator UX**
2. **Phase 4B — Goal-Driven Planning Intelligence**

This is the strongest path because it directly addresses the user’s actual observed problem first, then strengthens the underlying intelligence in a way that will be visible and testable.

In simpler terms:

- 4A ensures users can finally *see* that Kairos is doing real work
- 4B ensures Kairos will increasingly *deserve* to look intelligent

---

## 10. Proposed Next-Step Transition

After this design is accepted, the next planning step should not be “implement Phase 4” as one monolith. Instead, it should be:

- add **Phase 4A** to roadmap/milestone docs first
- plan its implementation in detail
- then add/plan **Phase 4B** as the follow-on phase once 4A lands

This preserves clarity and keeps the implementation/verification surface manageable.

---

## 11. Spec Self-Review

### Placeholder scan
- No TODO/TBD placeholders remain.
- All major sections have explicit content.

### Internal consistency
- The spec consistently treats Phase 4A as visibility-first and 4B as intelligence-strengthening.
- It does not reopen Phase 3.

### Scope check
- The work is intentionally decomposed into 4A/4B rather than one oversized phase.
- This is appropriate and reduces execution risk.

### Ambiguity check
- The central distinction between “history/UX” and “planning intelligence” is explicit.
- Acceptance criteria are concrete enough to plan from.

---

## 12. Review Gate

This design should be reviewed before planning. After approval, the next step is to turn:

- **Phase 4A** into a concrete phase entry and implementation plan
- then do the same for **Phase 4B**

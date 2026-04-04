# KAIROS Live Demo Design

Date: 2026-04-04
Topic: KAIROS live demo for product and engineering audiences
Status: Approved in conversation

## 1. Goal

Demonstrate that KAIROS is not just a polling helper for a single background task, but a coordination layer on top of Dex that can manage a small asynchronous workflow with visible state transitions.

The demo must work for two audiences at once:

- Product / non-technical viewers should understand the practical value: someone does not need to manually watch background jobs; the system tracks progress and advances the workflow.
- Engineering viewers should understand the mechanism is real: Dex executes real background jobs, KAIROS tracks and visualizes state transitions, and the frontend reflects actual runtime state.

## 2. Demo headline

Use this as the primary message during the demo:

> KAIROS is not a simple poller. It is an autonomy and coordination layer on top of Dex that turns a set of background tasks into a manageable staged workflow.

## 3. Scope

This demo focuses on a single staged workflow with:

1. A first phase of parallel background work.
2. A second phase that produces a combined report from the first phase outputs.
3. Observable KAIROS state changes in the frontend.

This demo does not attempt to prove fully automatic task chaining. The second phase may be manually triggered live, but must be framed as workflow progression after KAIROS has finished tracking the first phase.

## 4. Demo story

Business framing:

> We need to prepare three background inputs in parallel, then generate a final report after those inputs are ready.

This gives viewers a workflow to reason about rather than a toy "sleep and done" task.

## 5. Workflow design

### Phase 1: parallel input preparation

Run three Dex tasks in parallel. Each writes a small JSON artifact into a shared local demo output directory.

#### Task A — sales input
- Purpose: simulate a prepared sales input.
- Output file: `demo_outputs/sales.json`
- Duration target: about 8 seconds.
- Expected stdout: `sales ready`

#### Task B — traffic input
- Purpose: simulate a prepared traffic input.
- Output file: `demo_outputs/traffic.json`
- Duration target: about 14 seconds.
- Expected stdout: `traffic ready`

#### Task C — quality input
- Purpose: simulate a prepared quality or guardrail input.
- Output file: `demo_outputs/quality.json`
- Duration target: about 11 seconds.
- Expected stdout: `quality ready`

The task durations must be staggered so that KAIROS recent events and tracked task changes happen progressively instead of all at once.

### Phase 2: report generation

After the three parallel tasks complete, trigger a fourth Dex task:

#### Task D — report generation
- Purpose: read the three JSON inputs and build a final report.
- Output file: `demo_outputs/report.json`
- Expected stdout: `report ready: 3 inputs merged`

This phase is essential because it proves KAIROS is being used to manage workflow phases instead of merely observing one background process.

## 6. Task command design

All tasks must use pure local Python commands for stability and repeatability.

### Task A command

```bash
python -c "import json,time,os; os.makedirs('demo_outputs', exist_ok=True); time.sleep(8); json.dump({'source':'sales','value':128,'status':'ok'}, open('demo_outputs/sales.json','w',encoding='utf-8'), ensure_ascii=False); print('sales ready')"
```

### Task B command

```bash
python -c "import json,time,os; os.makedirs('demo_outputs', exist_ok=True); time.sleep(14); json.dump({'source':'traffic','value':3421,'status':'ok'}, open('demo_outputs/traffic.json','w',encoding='utf-8'), ensure_ascii=False); print('traffic ready')"
```

### Task C command

```bash
python -c "import json,time,os; os.makedirs('demo_outputs', exist_ok=True); time.sleep(11); json.dump({'source':'quality','value':'pass','status':'ok'}, open('demo_outputs/quality.json','w',encoding='utf-8'), ensure_ascii=False); print('quality ready')"
```

### Task D command

```bash
python -c "import json,os; data={}; files=['sales','traffic','quality']; [data.setdefault(name, json.load(open(f'demo_outputs/{name}.json', encoding='utf-8'))) for name in files]; report={'report':'ready','inputs':files,'summary':{'sales':data['sales']['value'],'traffic':data['traffic']['value'],'quality':data['quality']['value']}}; json.dump(report, open('demo_outputs/report.json','w',encoding='utf-8'), ensure_ascii=False, indent=2); print('report ready: 3 inputs merged')"
```

## 7. Frontend flow

### Setup
1. Open a fresh frontend session.
2. Run `skill_load("dex")`.
3. Confirm Dex is available.

### Phase 1 live steps
1. Ask the assistant to create and start the three phase-1 Dex tasks.
2. Capture the returned task IDs.
3. Open the KAIROS panel.
4. Start KAIROS.
5. Register all three task IDs via Dex handoff.
6. Wake KAIROS once.
7. Refresh status as needed while tasks complete.

### Phase 2 live steps
1. After the three phase-1 tasks are complete, create and start the report task.
2. Register the report task with KAIROS.
3. Wake KAIROS again.
4. Refresh status until the report task completes.
5. Show `report.json`, Dex task details, and KAIROS recent events.

## 8. What to emphasize on screen

### During phase 1
Point the audience at:
- `Tracked Dex Tasks`
- `最近事件`
- `tracked_dex_task_ids`
- `mode`

What viewers should observe:
- Multiple tracked tasks exist at once.
- Tasks complete at different times.
- KAIROS recent events accumulate over time.
- The tracked list shrinks as tasks finish.

### During phase 2
Point the audience at:
- The new report task registration.
- KAIROS recent events reflecting the transition into the next phase.
- The final report artifact.

What viewers should understand:
- The workflow did not end after one background task.
- The completed first stage produced conditions for the next stage.
- KAIROS is being used as a coordination runtime, not just a status viewer.

## 9. Presenter script outline

### Opening

> Today I am not showing whether one background task can finish. I am showing how KAIROS manages a staged asynchronous workflow on top of Dex.

### Dex setup

> Dex is the execution layer. KAIROS is the coordination layer. First I give the assistant Dex capability so it can start real background work.

### Phase 1 start

> I am launching three independent background tasks at once. These simulate separate inputs for a later report.

### KAIROS registration

> From this point on, I am not manually polling each task. KAIROS takes over tracking this task set.

### While tasks finish

> Notice this is not a single-task timeline. KAIROS is managing a small pool of background work, and the UI reflects the state transitions as the work converges.

### Phase 2

> Now that the first stage is complete, I move to the report stage. This is why I call KAIROS a coordination layer instead of a simple poller.

### Closing

> Dex solves background execution. KAIROS solves workflow state, visibility, and stage progression.

## 10. Success criteria

The demo is successful if all of the following are visible live:

1. A fresh session loads Dex successfully.
2. Three phase-1 Dex tasks are created and started.
3. KAIROS tracks those tasks and records completion events.
4. The tracked list changes over time rather than appearing static.
5. A report task is launched after the first phase is complete.
6. The report task completes and produces a visible artifact.
7. KAIROS recent events make the two-phase workflow legible.
8. Engineering viewers can verify tasks and logs are real on disk if needed.

### Verification status (2026-04-05)

This design is now backed by automated and live verification evidence in the repo:

- Runtime staged-workflow verification:
  - `tests/kairos/test_runtime.py`
  - covers parallel phase-1 convergence and report-stage re-entry into `handoff`
- Real Dex/Kairos integration verification:
  - `tests/dex/test_tools.py`
  - covers real Dex subprocess execution plus Kairos runtime polling
- Live HTTP + artifact verification against a running service:
  - `tests/kairos/live_http_kairos_demo_outputs_regression.py`
  - `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`
  - verifies `demo_outputs/sales.json`, `traffic.json`, `quality.json`, and `report.json`

Latest confirmed run before this document update:

```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/kairos/test_live_http_kairos_demo_outputs_regression.py \
  tests/dex/test_tools.py \
  tests/kairos/test_runtime.py -q
```

Result:

```text
31 passed
```

This means the success criteria are no longer only narrative targets; they are now partially enforced by repeatable regression coverage and a service-backed live verification path.

## 11. Fallback and failure handling

### If one phase-1 task fails unexpectedly
Frame it as evidence that KAIROS is managing actual background state, not faking progress. Then either:
- continue with two successful tasks and explain partial progression constraints, or
- restart that one task and show the recovery process.

### If UI refresh lags
Explain that KAIROS is tick-based and refresh the panel manually. This does not invalidate the runtime model.

### If the assistant does not launch all three tasks correctly
Fallback to more explicit instructions that name `dex_create_task` and `dex_start_task` directly. The demo still works as long as KAIROS manages the resulting task set.

### If the report task is blocked by missing files
Use the filesystem evidence to explain why staged workflows benefit from explicit coordination.

## 12. Recommended primary and backup demos

### Primary demo
- Three successful parallel tasks.
- One successful report task.
- Stable and product-friendly.

### Backup demo
Replace the quality task with a failure version to emphasize operational visibility and error handling.

## 13. Why this design is better than the previous smoke demo

The older smoke demo proved that the chain worked, but it did not demonstrate meaningful value. It looked like:
- one task
- one completion event
- minimal business meaning

This design proves:
- multiple concurrent tasks
- visible workflow convergence
- staged progression
- a final business-like output artifact

That is the minimum viable story needed to support the claim that KAIROS is a coordination layer on top of Dex.

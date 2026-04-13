# Phase 05 Research: 提示词约束的文档驱动持续推进

**Researched:** 2026-04-13
**Domain:** document-backed autonomous task progression for Kairos
**Confidence:** MEDIUM
**Phase:** 05-document-driven-continuation

## User Constraints

### Locked Decisions
- 文档是事实来源；不要回到 runtime-only patch。
- 提示词协议优先，代码只做薄护栏。
- 目录白名单、高风险动作默认 ask_user、所有发现与推进结果都要回写文档。
- 复用现有 Phase 4 planning/runtime/history/API/UI 资产，不推翻 candidate taxonomy。
- 目标是通用的软件任务推进，不是 Flask-specific workflow demo。

### Claude's Discretion
- 设计 document-backed work item 如何变成 executable next-step orchestration。
- 设计最小 generic progression model、artifact gate、verification gate、ask-user boundary。
- 明确哪些部分继续 rule-based，哪些交给 LLM。
- 设计测试策略，证明非硬编码 workflow 也能真实自主推进。

### Deferred Ideas (OUT OF SCOPE)
- fully autonomous git push / PR loop
- 跨仓库项目管理中台
- 高级长期记忆优化 / nightly dream
- 复杂 work graph scheduler

## Project Constraints (from CLAUDE.md)

- Windows 上执行会输出中文或 emoji 的 Python 命令必须带 `PYTHONIOENCODING=utf-8`。
- agent 从项目根运行；主入口是 `src/adk_agent/main_web_start_steering.py`。
- `private_key.yaml` 含 secrets，不应进入提交。
- `SkillManager` 采用两阶段 lazy loading；新增 skill 必须提供 `SKILL.md` 和 `tools.py:get_tools()`。
- 长时任务应走 Dex，而不是阻塞式 bash。
- 新增会输出中文/emoji 的 Python 脚本需包含 Windows UTF-8 stdout/stderr 修复块。

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DOC-01 | KAIROS 能通过提示词协议生成规范化工作文档 | 用 prompt-governed work doc + step ledger + gate sections 作为标准文档协议 |
| DOC-02 | KAIROS 能阅读已有工作文档并提取状态/步骤/阻塞/工件/下一步 | 用 normalized `WorkProgressSnapshot` 中间态承接 LLM 阅读结果 |
| DOC-03 | KAIROS 能把进展和决策回写为文档事实 | 用 append-only event log + current-step patch 双写策略 |
| DOC-04 | `/api/chat` 的受支持需求能落盘成 work item 并进入持续推进链路 | 用 intake -> draft doc -> materialize executable step -> scheduler enqueue 的 progression contract |
| DOC-05 | 自动唤醒时能从文档与工件状态中发现未完成任务和新派生任务并继续推进 | 用 gate-driven next-step materialization + spawned-work persistence 替代 `continue_workflow_scan` 空动作 |
| DOC-VER-01 | 文档生成/阅读/更新三类提示词协议具备 source/integration 测试 | 以 prompt contract tests + reader normalization tests 覆盖 |
| DOC-VER-02 | 文档驱动 continuation 具备 runtime/API/history regression | 以 orchestration state machine tests + API/history assertions 覆盖 |
| DOC-VER-03 | live HTTP flow 证明“用户需求 -> 文档 -> 推进 -> 派生工作 -> 再推进”闭环 | 以真实服务回归场景验证 document-backed winner 能产出 executable follow-up |

## Summary

当前 repo 的真实缺口不是“看不到 document-backed work”，而是“看到了也不会把它转成可执行下一步”。现状已经能把 requirement drafting 落盘成 `requirements/<session>/work.md`，也能在 `refresh_unfinished_work()` 中把 document-backed item 选成 planning winner；但 winner 最终落到 `continue_workflow_scan`，而 `create_follow_up` 对 document work 又被明确阻断，因此 document work 只具备 planning visibility，没有 execution continuity。

要补上这个缺口，推荐采用“文档为事实来源 + 规则化 progression contract + LLM 负责语义判断”的组合。LLM 负责从 work doc 提取 `当前步骤 / 预期工件 / 阻塞 / 验证需求 / 派生工作候选`，但真正把它转成系统内可执行 follow-up 的动作，必须经过一层通用、可审计、可测试的 rule-based materializer：把文档状态归一为少量执行原语，例如 `ask_user`、`run_dex_task`、`request_replan`、`record_blocked`、`spawn_child_work`、`sleep_until_signal`。这样既不会退回硬编码 workflow template，也不会把执行安全边界全部交给 LLM。

**Primary recommendation:** 用“Document Work Item + Step Attempt + Gate Evaluation + Executable Action”四段式 progression contract 替换 document-backed item 当前的 `continue_workflow_scan` 终点，让每次 planning winner 都能物化成一个明确、可追踪的下一步执行记录。

## Standard Stack

### Core
| Library / Primitive | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Markdown work docs + anchored sections | repo-native | 人类可读且可被 prompt 稳定解析的事实源 | 最符合当前 Kairos 的 document-first 方向，避免 rigid schema 僵化 |
| Pydantic models | installed via `requirements.txt` | 承接 LLM 阅读结果与执行原语的 normalized state | repo 已使用；适合做最小结构校验而不接管文档本身 |
| Dex task runtime | repo-native | 执行长时或异步 follow-up | 已是当前安全执行底座，避免把长时执行塞回 chat loop |
| FastAPI + Kairos runtime/history API | installed via `requirements.txt` | 暴露 planning winner、events、status | Phase 4 资产已成熟，应继续 additive 扩展 |

### Supporting
| Library / Primitive | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| SQLite session persistence | repo-native | 持久化 Kairos session/runtime state | 保存 step attempts、gate results、idempotency keys |
| Append-only activity/history log | repo-native | 审计 planning/re-plan/spawned work | 每次 materialized step、gate failure、ask-user 都应留痕 |
| Filelock | installed via `requirements.txt` | work doc 更新互斥 | 文档回写和后台续推并发时使用 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 软协议 Markdown + normalized read model | rigid JSON workflow schema | 更易 machine-parse，但会迅速把通用任务压扁成模板字段 |
| rule-based executable action materializer | LLM 直接输出 shell/tool calls | 更灵活，但安全边界、幂等和测试性显著变差 |
| generic gate model | 为每类任务单独写 workflow template | 初期更快，但会重回 if/elif 分支爆炸 |

**Installation:**
```bash
pip install -r requirements.txt
```

**Version verification:** 本仓库当前未锁定 requirements 版本；本研究基于 repo 已安装栈和现有架构，不引入新外部框架作为 Phase 5 必需前置。

## Architecture Patterns

### Recommended Project Structure
```text
src/adk_agent/kairos/
├── document_protocol.py      # 文档锚点、section patch/append helper
├── document_reader.py        # LLM -> normalized read result
├── progression_contract.py   # 新增：step/gate/action normalized model
├── orchestration.py          # 新增：materialize executable next step
├── runtime.py                # document_work_items / pending_requirements / state refresh
└── continuation.py           # 选择 winner 后调用 orchestration materializer
```

### Pattern 1: Separate semantic interpretation from executable materialization
**What:** LLM 只负责把 work doc 读成 `WorkProgressSnapshot`；真正决定是否创建 Dex task、是否 ask_user、是否 spawn child work，由规则层根据 gates 物化成 `ExecutableAction`。
**When to use:** 所有 document-backed continuation winner，尤其是当前 `continue_workflow_scan` 场景。
**Example:**
```python
snapshot = read_document_work_item(work_doc, runtime_context)

if snapshot.ask_user:
    action = ExecutableAction.ask_user(snapshot.questions)
elif snapshot.blocked_reason:
    action = ExecutableAction.blocked(snapshot.blocked_reason)
elif snapshot.ready_step and gates_pass(snapshot.ready_step, runtime_context):
    action = ExecutableAction.run_dex_task(snapshot.ready_step.task_spec)
else:
    action = ExecutableAction.sleep(snapshot.wait_reason)
```

### Pattern 2: Model step progression as attempts, not just current labels
**What:** 每个文档步骤进入执行前都创建 `StepAttempt` 记录，包含 source doc hash、step id、action kind、gate result、started_at、finished_at、outcome。文档是事实源，但 runtime 还要有“本次尝试”这一执行事实层。
**When to use:** 创建 follow-up、重试失败步骤、派生验证步骤时。
**Example:**
```python
attempt = StepAttempt.from_snapshot(snapshot, action)
store_attempt(attempt)
start_follow_up(attempt)
```

### Pattern 3: Gates first, action second
**What:** 将“是否能继续”拆成显式 gate：artifact gate、verification gate、policy gate、human-input gate。只有 gate 全通过，才物化 executable action。
**When to use:** 任何自动续推动作，尤其是代码修改、测试、交付、报告生成。
**Example:**
```python
gate_result = evaluate_gates(step, runtime_state)
if gate_result.requires_human:
    return ExecutableAction.ask_user(gate_result.questions)
if not gate_result.passed:
    return ExecutableAction.run_blocked(gate_result.reason)
return ExecutableAction.run_dex_task(step.task_spec)
```

### Pattern 4: Spawn child work as first-class documents
**What:** 派生任务不要只写一行 note；要立即物化为 child work doc 或 parent `Spawned Work` 下的可独立追踪条目，并为其生成 idempotency key。
**When to use:** 测试失败后出现修复任务、实现完成后出现验证任务、需求细化后拆分子任务。
**Example:**
```python
child = spawn_child_work(parent_doc, title="Fix failing regression", reason="verification gate failed")
persist_child_document(child)
queue_document_work_item(child.work_id)
```

### Anti-Patterns to Avoid
- **LLM directly decides executable tool call:** 会把安全策略、幂等与重试逻辑埋进 prompt，不可审计。
- **把 document work 当成弱化版 workflow template:** 如果仍要求每类任务都有专用 `create_follow_up_*`，Phase 5 只是在换壳。
- **只更新 current section，不记录 attempt history:** 会丢失“做过但失败/被阻塞”的事实，难以防重复和做 re-plan。
- **spawned work 只出现在 runtime memory:** 进程重启后丢失，违背 document-first。

## Progression Contract

### Canonical model
用下面四层作为通用 progression contract：

1. **Document Work Item**
   - work_id
   - source_doc_path
   - goal
   - current_step_id
   - step ledger
   - blockers
   - expected_artifacts
   - verification requirements
   - spawned work refs

2. **WorkProgressSnapshot**
   - 由 document reader 生成的 normalized 中间态
   - 字段最少包含：`status`, `ready_step`, `open_questions`, `blockers`, `artifact_expectations`, `verification_needs`, `spawn_candidates`, `risk_level`

3. **GateEvaluation**
   - artifact gate：所需输入/文件/前置步骤是否齐备
   - verification gate：是否必须先运行/补齐验证
   - policy gate：是否超过 autonomy limit、是否为高风险动作
   - human-input gate：是否存在未决问题或授权缺口

4. **ExecutableAction**
   - `run_dex_task`
   - `ask_user`
   - `record_blocked`
   - `spawn_child_work`
   - `request_replan`
   - `sleep_until_signal`

### Required state transitions
| From | Condition | To | Runtime effect |
|------|-----------|----|----------------|
| drafted | reader 找到可执行 step 且 gates 通过 | executing | 创建 `StepAttempt` + internal trigger / Dex task |
| drafted | 缺关键信息 | waiting_user | 写回 open questions + ask_user event |
| executing | step 完成且无新 gate | reviewing | 读取工件/结果并执行 verification gate |
| reviewing | verification 通过 | progressed | 文档回写完成，选择下一个 step 或 sleep |
| reviewing | verification 失败且可修复 | spawned_child | 新建 child work doc，并把 parent 标记 waiting_child |
| any | policy / artifact gate 不通过 | blocked | 写回 blocker + history event |
| any | 文档变化导致原计划失效 | replanning | 生成 new snapshot，更新 planning trace |

### Minimal generic step schema inside docs
文档无需 rigid JSON，但每个 step 必须能被 reader 识别出以下语义：
- step id / title
- goal of the step
- completion signal
- expected artifacts
- required verification
- fallback / ask-user condition

### Ask-user boundary
以下情况必须由 rule 层直接转 `ask_user`，不要让 LLM 自行越过：
- 缺少用户提供的业务决策或验收标准
- 需要高风险外部动作授权（push、删除、部署、密钥变更）
- 文档存在多种高影响解释且无法从仓库/工件判定

### What remains rule-based vs delegated to LLM
| Concern | Rule-based | LLM-driven |
|---------|------------|------------|
| 目录白名单、风险动作拦截、幂等键、防重复 follow-up | Yes | No |
| 从自由文档提炼当前步骤、阻塞、open questions、spawn candidates | No | Yes |
| gate 结果归类为 ask_user / blocked / executable | Yes | Assisted by snapshot |
| 生成/更新工作文档 prose、replan note、spawned work 描述 | No | Yes |
| Dex task 的具体 command 是否可执行 | Yes, from approved task spec only | LLM 提供候选说明，不直接落执行 |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 通用任务推进 | 每类软件任务一个 `workflow_id` / `create_follow_up_*` 分支 | 通用 progression contract + executable action materializer | 避免模板爆炸，复用同一套 gate / attempt / audit 机制 |
| 文档状态提取 | 针对 Markdown 写大量 brittle regex parser | LLM reader + minimal normalized state validation | 文档会演化；parser 易因措辞和 section 调整崩掉 |
| 去重与重试 | 靠文档文字比对判断是否已执行 | `StepAttempt` idempotency key (`work_id + step_id + doc_hash`) | 支持重启恢复、防重复执行、审计 |
| 派生任务追踪 | parent doc 里写一段 prose | child work doc + parent ref | child 可以独立进入 planning/execution，可被 UI/history/API 暴露 |
| 验证编排 | 在 prompt 里口头要求“记得测试” | 显式 verification gate + task type mapping | 让“先验证再推进”成为系统约束，而非提示词愿望 |

**Key insight:** 不要手写“通用任务语义解析器”或“每类任务的专属 follow-up 模板”；真正需要手写的是小而稳的执行原语、gates、幂等和审计层。

## Common Pitfalls

### Pitfall 1: Planning-visible but execution-dead tasks
**What goes wrong:** work item 出现在 `document_work_items`、planning winner 也选中了它，但最终没有 internal trigger 或 follow-up 创建。
**Why it happens:** planning artifact 与 execution layer 之间缺少 materialization contract；`continue_workflow_scan` 只是“再看看”。
**How to avoid:** 要求每个 selected winner 最终产出 `ExecutableAction`，禁止无副作用的 terminal planning kind 作为成功路径。
**Warning signs:** history 反复出现同一 winner；文档无变化；没有新 attempt/event。

### Pitfall 2: Letting LLM invent executable tasks
**What goes wrong:** LLM 直接产出命令或高风险动作，runtime 照单执行。
**Why it happens:** 把“理解下一步”与“批准下一步”混为一体。
**How to avoid:** LLM 只能产出候选 step spec；真正可执行 task 必须匹配受控 action kind 或受批准 task spec。
**Warning signs:** 新增 prompt 里出现 shell command、tool name、free-form execution fields。

### Pitfall 3: No attempt-level persistence
**What goes wrong:** 文档里的 current step 一改，之前失败/中断的执行事实消失；重启后可能重复建任务。
**Why it happens:** 只把文档当唯一持久层，没有执行层事实模型。
**How to avoid:** 每次执行前都持久化 `StepAttempt`；文档写“结论”，runtime 存“尝试”。
**Warning signs:** 同一个 step 多次创建 follow-up；无法解释为什么 blocked/replanned。

### Pitfall 4: Verification remains advisory
**What goes wrong:** 文档写了“需要验证”，但 runtime 仍把实现 step 当完成并继续推进。
**Why it happens:** verification 只存在 prose，不存在 gate。
**How to avoid:** 将 verification 提炼为显式 gate，未通过时只能进入 reviewing / blocked / spawned_child，不能直跳 done。
**Warning signs:** 实现完成后没有 test/report task；history 缺 verification event。

### Pitfall 5: Parent doc becomes an unbounded dump
**What goes wrong:** 所有 replan、attempt、spawned work 都不断 append 到一个文档，reader 稳定性下降。
**Why it happens:** 没有区分 current state 与 historical log。
**How to avoid:** parent doc 保持当前事实 + concise changelog；详细执行历史留在 runtime/activity store，child tasks 单独成文。
**Warning signs:** reader 输出开始漂移；同一文档越来越长、step 指向不稳定。

## Verification Strategy

### Test framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `D:\git_codes\google_adk_helloworld_git\pytest.ini` |
| Quick run command | `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_runtime.py tests/kairos/test_continuation.py -q` |
| Full suite command | `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_document_protocol.py tests/kairos/test_document_reader.py tests/kairos/test_models.py tests/kairos/test_continuation.py tests/kairos/test_runtime.py tests/kairos/test_activity_log.py tests/kairos/test_api.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py tests/test_dex_session_regression.py -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DOC-01 | 文档生成包含 step/gate/verif anchors | unit | `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_document_protocol.py -q` | ✅ |
| DOC-02 | reader 产出 normalized snapshot | unit | `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_document_reader.py -q` | ✅ |
| DOC-03 | progress update 回写 current state + spawned refs | unit/integration | `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_document_protocol.py tests/kairos/test_runtime.py -q` | ✅ |
| DOC-04 | `/api/chat` requirement drafting 进入 work doc | integration | `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_api.py tests/kairos/test_runtime.py -q` | ✅ |
| DOC-05 | document-backed winner 物化 executable next step，不再停在 scan | integration/runtime | `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_continuation.py tests/kairos/test_runtime.py tests/test_dex_session_regression.py -q` | ✅ but needs new cases |
| DOC-VER-03 | “需求 -> 文档 -> 推进 -> 派生工作 -> 再推进”真实闭环 | live HTTP | `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q` | ✅ but needs new scenario |

### Required new tests for this gap
- `tests/kairos/test_continuation.py`: document-backed winner returns `run_dex_task` / `ask_user` / `record_blocked` instead of `continue_workflow_scan` noop.
- `tests/kairos/test_runtime.py`: `apply_decisions()` or successor path creates internal trigger for materialized document action, not only `create_dex_task`.
- `tests/kairos/test_activity_log.py`: assert `step_materialized`, `verification_gate_failed`, `spawned_child_work` events are persisted sparsely.
- `tests/kairos/test_api.py`: status/API expose current executable step / pending gate / child work refs for document-backed items.
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`: add generic software-task scenario, not todo/Flask-specific template branch.

### Sampling rate
- **Per task commit:** quick run command
- **Per wave merge:** focused kairos runtime/api/history suite
- **Phase gate:** full suite green plus one live HTTP document-backed progression scenario

### Wave 0 gaps
- [ ] Add `progression_contract` unit tests covering gate evaluation and action materialization
- [ ] Add runtime regression for idempotent `StepAttempt` creation on repeated wakeups
- [ ] Add live HTTP fixture demonstrating spawned child work becomes executable follow-up automatically

## Code Examples

### Example 1: Materialize executable next step from document snapshot
```python
@dataclass
class ExecutableAction:
    kind: Literal[
        "run_dex_task",
        "ask_user",
        "record_blocked",
        "spawn_child_work",
        "request_replan",
        "sleep_until_signal",
    ]
    payload: dict[str, Any]


def materialize_document_action(snapshot: WorkProgressSnapshot, runtime: KairosState) -> ExecutableAction:
    if snapshot.open_questions:
        return ExecutableAction("ask_user", {"questions": snapshot.open_questions})
    if snapshot.blockers:
        return ExecutableAction("record_blocked", {"reason": snapshot.blockers[0]})

    step = snapshot.ready_step
    if step is None:
        return ExecutableAction("sleep_until_signal", {"reason": "no ready step"})

    gate = evaluate_gates(step=step, runtime=runtime)
    if gate.requires_human:
        return ExecutableAction("ask_user", {"questions": gate.questions})
    if not gate.passed:
        return ExecutableAction("record_blocked", {"reason": gate.reason})

    return ExecutableAction("run_dex_task", {"task_spec": step.task_spec, "step_id": step.step_id})
```

### Example 2: Persist execution attempt before follow-up creation
```python
def start_document_follow_up(work_item: DocumentWorkItem, snapshot: WorkProgressSnapshot) -> StepAttempt:
    action = materialize_document_action(snapshot, runtime=get_runtime_state())
    attempt = StepAttempt(
        key=f"{work_item.work_id}:{snapshot.ready_step.step_id}:{work_item.doc_hash}",
        work_id=work_item.work_id,
        step_id=snapshot.ready_step.step_id,
        action_kind=action.kind,
    )
    save_attempt(attempt)
    dispatch_action(action, attempt)
    return attempt
```

### Example 3: Spawn child work on verification failure
```python
def on_verification_failure(parent: DocumentWorkItem, failure: VerificationFailure) -> None:
    child_doc = append_spawned_work(
        parent_doc_path=parent.path,
        title=f"Fix verification failure: {failure.summary}",
        reason=failure.details,
    )
    register_document_work(child_doc)
    record_activity("spawned_child_work", {"parent": parent.work_id, "child_path": str(child_doc)})
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Hardcoded workflow template decides next Dex task | Document reader produces normalized snapshot; rule layer materializes generic executable action | 同一套引擎可覆盖更多软件任务类型 |
| Planning winner may end at noop scan | Selected winner must emit executable action or explicit blocked/ask-user outcome | 减少 planning-visible / execution-dead 假推进 |
| Verification as prose note | Verification as explicit gate | 自动推进更可控、更可测 |
| Spawned work as note | Spawned work as first-class document-backed child item | 可持续推进与恢复 |

**Deprecated/outdated for this phase:**
- “继续加 workflow template”——这会直接回到 Phase 5 想摆脱的路线。
- “让 LLM 自由决定下一切动作”——不符合当前 repo 的 safety / explainability / testability 目标。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Kairos runtime/tests | ✓ | repo Python available | — |
| pytest | regression suite | ✓ | configured via `pytest.ini` | — |
| Dex runtime | async follow-up execution | ✓ | repo-native | none |
| `.planning/config.json` nyquist flag | validation architecture toggle | ✗ | — | 按默认启用 validation section |

**Missing dependencies with no fallback:**
- None identified for this phase research.

**Missing dependencies with fallback:**
- `.planning/config.json` absent; treat validation architecture as enabled by default.

## Sources

### Primary (HIGH confidence)
- `D:\git_codes\google_adk_helloworld_git\.planning\REQUIREMENTS.md` — DOC-01..DOC-05 and verification requirements
- `D:\git_codes\google_adk_helloworld_git\.planning\phases\05-document-driven-continuation\05-CONTEXT.md` — locked Phase 5 design principles and scope
- `D:\git_codes\google_adk_helloworld_git\.planning\STATE.md` — current project state and completed Phase 5A/5B/5C facts
- `D:\git_codes\google_adk_helloworld_git\.planning\phases\05-document-driven-continuation\05-RESEARCH.md` (prior version) — baseline research direction to update
- `D:\git_codes\google_adk_helloworld_git\CLAUDE.md` — project constraints and operational rules
- `D:\git_codes\google_adk_helloworld_git\pytest.ini` — current test framework configuration
- `D:\git_codes\google_adk_helloworld_git\requirements.txt` — installed stack primitives

### Secondary (MEDIUM confidence)
- Current repo gap summary provided by orchestrator message: document-backed work is planning-visible but follow-up creation is blocked and `continue_workflow_scan` is non-executable.
- Established durable orchestration patterns synthesized from existing agent/runtime practice: separate semantic read model from rule-based executable action materialization.

### Tertiary (LOW confidence)
- External web documentation lookup was attempted but unavailable in this environment, so no external claims are treated as authoritative in this update.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — derived from current repo files and existing runtime architecture
- Architecture patterns: MEDIUM — repo gap is clear, but recommended generic progression contract is design guidance rather than already-implemented code
- Pitfalls: MEDIUM — directly inferred from current gap and common failure modes in document-backed orchestration

**Research date:** 2026-04-13
**Valid until:** 2026-05-13

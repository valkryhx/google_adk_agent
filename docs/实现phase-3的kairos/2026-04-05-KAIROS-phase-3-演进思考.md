# KAIROS Phase 3 演进思考：从后台任务观察者走向真正的 Autonomous Long-Term Running Agent

> 日期：2026-04-05
> 基于材料：
> - `docs/探讨claudecode/KAIROS-特性源码分析报告.md`
> - `docs/探讨claudecode/KAIROS-python复现设计文档.md`
> - `docs/探讨claudecode/KAIROS多方案选择.md`
> - `docs/实现phase-2的kairos/*`
> - 当前代码实现与近期提交：`47afe9b` ~ `6879214`

---

## 1. 先给结论

如果用一句话概括我对当前 KAIROS 的判断：

> **现在的 KAIROS 已经是一个“能长期存活、能被唤醒、能跟踪 Dex 后台任务、能把运行态暴露出来”的 runtime 雏形，但它本质上仍是一个 runtime + poller + handoff state machine，还不是一个会主动发现下一步、主动续推工作、主动闭环的自治 agent。**

这意味着 phase-3 不应该只是继续加几个状态字段或 API。

phase-3 真正要补的，是一层新的 **autonomy control plane（自治控制平面）**：

1. **让 KAIROS 不只是知道任务完成，而是知道“完成后下一步该做什么”**
2. **让 KAIROS 不只是等待外部 wake/schedule/handoff，而是能自己产生 continuation work（续推工作）**
3. **让 KAIROS 不只是看当前 tracked task，而是能基于最近完成事件、已有产物、历史失败、schedule 目标做主动判断**
4. **让 KAIROS 从 REPL 附属能力，演进为真正的 long-term running worker runtime**

我认为你提的那个关键点完全正确：

> **KAIROS 如果只能“观察后台任务状态”，那它只是一个高级轮询器；它只有在能主动发现“现在应该继续干什么”时，才真正跳出了需要人类主导的 REPL 范式。**

因此，phase-3 的核心不是“更强监控”，而是：

> **从 handoff-tracking 升级到 goal-driven continuation。**

---

## 2. 基于 phase-2，我认为当前已经真正具备的能力

先明确一点：当前实现并不弱，phase-2 已经把很多底座做出来了。

### 2.1 已有 runtime 宿主已经成立

当前 `SteeringSession` 已经能稳定持有一个会话级 KAIROS runtime：

- `src/adk_agent/main_web_start_steering.py:479-500` 通过 `get_or_create_kairos_runtime()` 懒创建 runtime
- runtime 绑定了：
  - `save_state`
  - `emit_event`
  - `append_log`
  - `run_turn`
  - `dex_bridge`
  - `scheduler`

这意味着 KAIROS 已经不是一个散落在 API 里的 patch，而是一个真正的 session-level runtime。

### 2.2 持久化与不污染历史这两个关键地基已经补上

这点非常重要，因为 long-running runtime 最怕把用户 history 搞坏。

phase-2 已经修复了：

- KAIROS state-only 更新误走 full save 导致 history 倍增
- sandbox 路径错误回写真实 DB

对应材料：

- `docs/实现phase-2的kairos/KAIROS-Phase-2-历史倍增Bug排查与修复记录.md`
- `src/adk_agent/main_web_start_steering.py:398-430`
- `src/adk_agent/main_web_start_steering.py:450-477`

当前设计已经明确区分：

- **用户会话历史**
- **KAIROS runtime state**
- **KAIROS activity log**

这为 phase-3 做更主动的后台自治提供了必要前提。

### 2.3 当前已经具备了 schedule / trigger / handoff / tracked tasks 的闭环骨架

当前 `KairosRuntime` 已经有一套非常清晰的主循环：

- `src/adk_agent/kairos/runtime.py:116-180` `tick_once()`
- `src/adk_agent/kairos/runtime.py:219-240` `_poll_dex()`
- `src/adk_agent/kairos/scheduler.py:10-35` `KairosScheduler`

它已经支持：

- wake -> enqueue manual trigger
- schedule -> collect due triggers
- register_dex_task -> handoff
- poll dex -> completed/failed -> recent events -> tracked 列表收敛

这是一个很关键的事实：

> **phase-2 已经把“被动观察后台任务”所需要的 runtime skeleton 基本做完了。**

### 2.4 前端可视化和 live verification 已经建立证据链

phase-2 不是只“写了逻辑”，还建立了展示与验证：

- `src/adk_agent/static/script.js:1916-2055` 已能展示 `tracked_dex_tasks`、`recent_events`、`schedules`
- `tests/kairos/test_runtime.py:831-922` 已验证 staged workflow
- `tests/kairos/live_http_kairos_demo_outputs_regression.py:134-191` 已验证 live HTTP + 产物落盘
- `docs/实现phase-2的kairos/2026-04-05-KAIROS-测试设计说明.md` 明确了 runtime / integration / service 三层验证策略

所以现在不是“空谈 autonomous”，而是已经有一个可运行、可看见、可验证的载体。

---

## 3. 当前实现距离“autonomous long-term running”还差什么

我把 gap 归纳成五个关键跃迁。

## 3.1 从“任务状态跟踪”到“任务意义理解”

现在 `_poll_dex()` 的行为是：

- 看到任务 completed / failed
- 记录一条 brief 事件
- 从 tracked 列表移除

见：

- `src/adk_agent/kairos/runtime.py:225-240`

这已经很好，但本质上还是：

> **state transition aware，而不是 work semantics aware。**

当前 KAIROS 知道：

- task finished

但它还不知道：

- task 产物是否可用
- task 完成意味着哪个阶段达成
- 现在是否满足进入下一阶段的条件
- 是否需要派生出新的 follow-up task
- 是否需要请求人类输入

举例：

在 staged workflow 里，KAIROS 现在能看到：
- sales 完成
- traffic 完成
- quality 完成

但“report 该不该自动启动”这件事，目前不是 KAIROS 自己判断出来的，而是人或测试脚本又注册了 report task。

这就是它离自治还差的第一跳。

---

## 3.2 从“外部驱动 wake”到“内部驱动 continuation”

当前 KAIROS 的 turn 来源主要有三类：

1. manual wake
2. schedule trigger
3. dex handoff 跟踪后的 tick

但它还缺一种最关键的 trigger：

> **internal continuation trigger（内部续推触发）**

也就是：

- 我刚刚发现 phase-1 已完成
- 所以我自己 enqueue 一个“plan_next_step” trigger
- 我刚刚发现 report 产物缺失
- 所以我自己 enqueue 一个“recover_report_generation” trigger
- 我刚刚发现某 schedule 连续失败
- 所以我自己 enqueue 一个“diagnose_failure_cluster” trigger

当前 `TriggerKind` 虽然已经有 `INTERNAL`：

- `src/adk_agent/kairos/models.py:17-21`

但目前 runtime 基本没有真正把 internal trigger 用起来。

所以 phase-3 的关键不只是增加 trigger kind，而是：

> **让 runtime 自己产生 trigger。**

---

## 3.3 从“tracked task 列表”到“goal / plan / next-action 结构”

当前状态模型重点是：

- `tracked_dex_task_ids`
- `pending_triggers`
- `active_trigger`
- `schedules`
- `recent_events`

见：

- `src/adk_agent/kairos/models.py:51-69`

这些字段足够支撑 runtime，但不够支撑自治规划。

因为一个真正会长期运行的 agent，除了知道“我在跟踪哪些任务”，还必须知道：

- 我当前在追的目标是什么
- 这个目标是否拆成若干阶段
- 哪些阶段已完成
- 哪些 follow-up 已生成但未执行
- 为什么我要继续推进
- 什么时候该停止主动推进，转入 waiting_input

也就是说，phase-3 需要一个比 `tracked_dex_task_ids` 更高一层的模型：

> **Goal / Workflow / NextAction / ContinuationPolicy**

不一定一开始就做得很重，但至少要引入。

---

## 3.4 从“brief 事件输出”到“对用户有意义的主动汇报”

现在 `run_kairos_turn()` 的 synthetic prompt 很轻：

- `src/adk_agent/main_web_start_steering.py:450-477`

提示大意是：

- 检查状态
- 检查 Dex 完成情况
- 是否应该继续 sleep
- 输出简洁 brief

这个 prompt 对 phase-2 是对的，因为它的定位是：

- 不污染 history
- 只做 lightweight autonomous check

但如果 phase-3 真要让它更 proactive，这个 prompt 必须升级。

它要让 agent 能判断：

- 最近事件是否意味着目标阶段已达成
- 是否存在未被继续处理的产物
- 是否需要生成后续 Dex task
- 是否需要汇报成果而不仅是状态
- 是否需要向用户请求缺失信息

换句话说，当前 brief 更像：

- status narration

phase-3 需要的是：

- continuation-oriented reasoning

---

## 3.5 从“单 runtime”到“弱 supervisor / policy layer”

当前架构仍然是推荐方案 A 的延伸：

- runtime 内嵌在 `SteeringSession`
- `SessionManager` 只是 registry
- attach 只是 snapshot API skeleton

这在 phase-2 是正确的。

但 phase-3 一旦开始做“自发现 + 自动续推 + 多阶段闭环”，就会出现一个新问题：

> **谁来决定什么时候值得继续推、什么时候只是 sleep、什么时候需要升级为用户可见的 proactive brief？**

如果把这些策略全塞进 `KairosRuntime.tick_once()`，它会很快变成一团。

所以我认为 phase-3 虽然还不用真正上多进程 supervisor，但必须引入一个更明确的策略层：

- 不一定叫 supervisor
- 但至少要有一个 **policy / planner / continuation engine**

这层负责的是：

- interpreting events
- deciding next actions
- scheduling follow-ups

而不是直接跑模型或直接 poll Dex。

---

## 4. 我认为 phase-3 的真正目标是什么

我建议把 phase-3 的目标定义成下面这句：

> **让 KAIROS 从“能持续观察 Dex 后台任务状态的 runtime”，升级为“能围绕一个长期目标主动发现下一步、自动续推工作流、并在必要时主动向人汇报或请求输入的自治执行体”。**

这个目标可以拆成四个更具体的子目标。

### 4.1 Goal-aware
KAIROS 不只跟踪 task，还跟踪 goal / workflow stage。

### 4.2 Continuation-aware
KAIROS 能在任务完成后自己判断是否需要 follow-up，而不是永远等人类注册下一步任务。

### 4.3 Artifact-aware
KAIROS 能读取产物/摘要/日志，而不是只看 completed/failed。

### 4.4 Policy-aware
KAIROS 能根据策略判断：
- 自动继续
- 主动汇报
- 请求人类输入
- 暂停并 sleep

---

## 5. 我建议的 phase-3 核心设计：新增一层 Continuation Engine

如果只允许我提出一个最关键的技术方案，我会建议：

> **在现有 runtime 之上新增一个“Continuation Engine（续推引擎）”，让它成为 KAIROS 从 poller 变成 proactive agent 的核心。**

这个 Continuation Engine 不需要一开始就很复杂，但要承担 4 个职责：

1. **事件解释（Interpretation）**
2. **目标状态更新（Goal state update）**
3. **下一步决策（Next action decision）**
4. **触发生成（Continuation trigger enqueue）**

### 5.1 为什么是 Continuation Engine，而不是直接把逻辑塞进 runtime

因为当前 runtime 已经有清晰职责：

- tick
- wake
- schedule
- poll dex
- persist state
- emit events

如果 phase-3 再把“目标推进策略”塞进去，`runtime.py` 会同时承担：

- orchestration
- policy
- semantic interpretation
- planning

这会很快失控。

更合理的做法是：

- `runtime.py` 保持 runtime orchestration
- `continuation_engine.py` 负责“看到这些状态后，下一步怎么办”

---

## 6. phase-3 最小可落地方案（推荐先做）

我建议 phase-3 不要一口气上完整 workflow planner，而是先做一个 **MVP 版 proactive continuation**。

这个最小方案我建议包含 4 个点。

## 6.1 扩展状态模型：加入 workflow / goal / pending actions

在 `src/adk_agent/kairos/models.py` 增加最小必要结构。

建议新增：

### `KairosWorkflow`
表示一个正在被 KAIROS 自治推进的工作流。

建议字段：

- `workflow_id`
- `goal`
- `status`：`active / waiting_input / completed / failed / paused`
- `current_stage`
- `stages`
- `metadata`

### `KairosPlannedAction`
表示 runtime 认为下一步应该做但尚未执行的动作。

建议字段：

- `action_id`
- `kind`：`create_dex_task / summarize_results / ask_user / verify_artifact / enqueue_trigger`
- `reason`
- `payload`
- `status`

### `KairosContinuationPolicy`
可先做成轻量配置，而不是复杂类。

比如：

- `auto_continue_on_all_inputs_ready`
- `auto_summarize_completed_task`
- `auto_verify_artifacts`
- `max_auto_steps_per_wake`

#### 为什么这一步关键
因为没有“goal / planned action”这层结构，KAIROS 永远只能以 task 为中心，而不是以工作为中心。

---

## 6.2 在 runtime 中加入 internal continuation trigger 生产逻辑

当前最适合插入的位置是：

- `src/adk_agent/kairos/runtime.py:219-240` `_poll_dex()`

当前这里在任务完成后只做：

- record brief
- remove tracked id
- mode converge

phase-3 可以升级成：

1. 任务完成后提取 richer summary
2. 更新 workflow stage state
3. 调用 continuation engine 判断是否需要 follow-up
4. 如果需要，则 enqueue 一个 `TriggerKind.INTERNAL` 的 trigger

例如：

- `phase1_all_inputs_ready`
- `report_artifact_missing`
- `task_failed_need_recovery`
- `artifact_ready_need_summary`

这样做的意义是：

> **KAIROS 的下一轮 turn 不再只是“又醒了一次”，而是“带着明确内部动机醒来”。**

这和现在的 manual wake / schedule wake 是质变。

---

## 6.3 升级 `run_kairos_turn()` 的 prompt：从状态检查变成续推思考

当前 synthetic prompt 太轻，不足以支撑主动续推。

建议把 `src/adk_agent/main_web_start_steering.py:450-477` 的 prompt 升级成 phase-3 版本。

应该加入的信息包括：

- 当前 workflow / goal 摘要
- 最近完成的 Dex task 摘要
- 已有产物摘要
- pending planned actions
- 本轮 trigger 的类型与原因
- autonomy policy 约束

phase-3 prompt 的核心要点应变成：

1. 判断目标是否已经推进
2. 若存在明确下一步且无需用户介入，优先自动推进
3. 若缺信息，生成 ask_user 型 brief
4. 若没有高价值动作，明确 sleep
5. 不要空转，不要重复汇报同一事实

这一步很重要，因为：

> **真正的 proactive 不是“多说两句”，而是 prompt 被明确塑造成 continuation planner。**

---

## 6.4 增加一个最小的自动续推闭环：all-inputs-ready -> auto-create report task

这是我最推荐的 phase-3 第一里程碑。

因为当前仓库已经有最好的 demo 场景：

- sales / traffic / quality -> report

phase-2 里，这一步还要靠外部手动注册 report task。

phase-3 可以把它做成第一个真正的自主闭环：

### 目标
当 KAIROS 检测到：

- workflow=demo_report_pipeline
- phase-1 三个输入任务都 completed
- 三个产物都存在
- 尚未存在 report task

则它自动：

1. 生成 report Dex task
2. 自动调用 DexManager 创建任务
3. 自动 register_dex_task
4. recent_events 写明：
   - `phase-1 converged, report task auto-created`
5. 进入 report 阶段 handoff

这将是一个非常强的跃迁，因为它第一次让系统从：

- 被动跟踪

变成：

- 主动推进 workflow

这正是你强调的“跳出 REPL、人类不再主导每一步”的最小可见证据。

---

## 7. 更完整的中期路线：从 Continuation Engine 走向 Goal-Oriented Kairos

在最小方案跑通后，我建议的中期路线是 3 层演进。

## 7.1 第一层：Autonomous Follow-up

这层解决的问题是：

- 任务完成后能否自动做后续动作

能力包括：

- 自动 summarize task result
- 自动 verify artifact exists
- 自动创建下一阶段 Dex task
- 自动决定是汇报还是继续执行

这是 phase-3 的核心。

## 7.2 第二层：Workflow Memory

当前 `recent_events` 只是短窗口。

phase-3 中期应该补一个轻量的 workflow memory：

- 最近完成的关键阶段
- 失败次数
- 最近生成过的 follow-up action
- 避免重复触发的去重指纹

建议不要一开始就上复杂 memory distill，而是先做：

- `workflow_journal` / `continuation_history`

这层很重要，因为一旦没有它，KAIROS 会有两个风险：

1. 重复创建同一 follow-up task
2. 每次 tick 都像第一次看到世界

## 7.3 第三层：Weak Supervisor / Policy Manager

当 workflow 与 continuation 变多后，需要把策略从 runtime 里再抽一层。

这层不一定要做成独立进程，但可以做成：

- `policy.py`
- `continuation_engine.py`
- `workflow_manager.py`

负责：

- 去重
- 优先级
- 最大自动步数限制
- 何时 ask_user
- 何时 emit proactive brief

这层实际上就是为未来真正 supervisor 化提前铺路。

---

## 8. 具体建议改哪些文件

下面给出我认为最值得动的文件。

## 8.1 `src/adk_agent/kairos/models.py`

### 建议新增
- `KairosWorkflow`
- `KairosPlannedAction`
- `KairosWorkflowStage`
- `ContinuationDecision`

### 原因
当前状态模型已经能表示 runtime，但不能表示 goal 与下一步。

如果 phase-3 不先扩状态模型，后续所有 proactive 行为都会变成散落逻辑。

---

## 8.2 `src/adk_agent/kairos/runtime.py`

### 建议增强点
1. `_poll_dex()` 完成后不只 `_record()`，还应触发 continuation decision
2. `tick_once()` 在处理完 due trigger / dex poll 后，应处理 internal continuation trigger
3. 增加 planned action 的执行入口
4. 增加“最大自动续推步数”限制，防止 runaway autonomy

### 原因
runtime 仍然是 orchestrator，续推闭环最终还是要在这里落地。

但注意：
- 决策逻辑不要全部硬编码在 runtime 内
- runtime 只负责调用 continuation engine + 执行动作

---

## 8.3 新增 `src/adk_agent/kairos/continuation.py`

这是我最推荐新增的文件。

### 负责
- 根据 runtime state、tracked task snapshots、recent events、artifacts，判断下一步
- 输出 `ContinuationDecision`
- 生成 internal trigger / planned action

### 可以先做成纯规则引擎
phase-3 第一版不必直接把 LLM 规划放进这里。

可以先做 deterministic rules：

- if all inputs ready and no report task -> create report
- if task completed and result_summary exists -> enqueue summarize_result
- if artifact missing after task completed -> enqueue verify_artifact_failure

这样更可测，也更稳。

---

## 8.4 新增 `src/adk_agent/kairos/workflows.py`

### 负责
- 定义若干 workflow template
- 把 demo/staged workflow 从“测试里隐含存在”变成显式配置

例如：

- `demo_report_pipeline`
- `scheduled_check_then_report`

这样 phase-3 的“主动推进”才不会完全依赖 prompt 猜测。

---

## 8.5 `src/adk_agent/main_web_start_steering.py`

### 建议增强点
1. `run_kairos_turn()` prompt 升级
2. 给 KAIROS turn 注入更多上下文摘要，而不是只给 reason
3. 给 phase-3 的主动汇报留出更明确的 stream event 类型

### 原因
当前 KAIROS turn 只是 lightweight brief check；phase-3 需要它成为 continuation-aware turn。

---

## 8.6 `src/adk_agent/kairos/api.py`

### 建议新增接口
- workflow status
- planned actions
- continuation decisions
- enable/disable autonomy policy

### 原因
phase-3 如果想可调试，不能只看 `tracked_dex_task_ids`。

你需要在 API 层看到：

- KAIROS 为什么决定继续
- 它计划做什么
- 它为什么没有继续

否则自治一增强，黑盒感会急剧上升。

---

## 8.7 `src/adk_agent/static/script.js`

### 建议增强 UI
新增几个区域：

1. `Current Workflow`
2. `Planned Next Actions`
3. `Autonomy Decisions`
4. `Blocked / Waiting Input Reason`

### 原因
phase-2 UI 解决了“我在跟踪什么 task”。
phase-3 UI 要解决的是：

> **我为什么继续、下一步准备做什么、为什么现在停住。**

这对调试自主性至关重要。

---

## 9. 我最推荐的 phase-3 分阶段实施顺序

我建议按下面顺序推进。

## Phase 3A：Autonomous Continuation MVP

目标：证明 KAIROS 能在一个明确 workflow 中自主续推下一阶段。

### 要做
1. 扩状态模型，引入 workflow / planned actions
2. 新增 continuation engine（规则版）
3. 在 `_poll_dex()` 后做 continuation decision
4. 支持 internal trigger
5. 实现 `all inputs ready -> auto create report task`
6. recent_events 记录主动续推决策

### 验收信号
- 不需要人手动注册 report task
- KAIROS 自己创建并 handoff report
- live demo 仍能稳定收敛

这是最重要的一步。

---

## Phase 3B：Artifact-aware Proactive Reporting

目标：让 KAIROS 不只知道 task finished，而是知道结果是什么。

### 要做
1. 完成后自动读取 result_summary / artifact / log tail
2. 生成更强的自然语言 brief
3. 区分：
   - 普通状态事件
   - 主动价值汇报
   - 请求用户输入

### 验收信号
- recent_events 和前端不再只是“task completed”
- 而是“完成了什么、结果是否达标、下一步是什么”

---

## Phase 3C：Workflow Memory + Policy Layer

目标：避免重复动作，让自治更像长期运行 worker。

### 要做
1. 记录 continuation history
2. 去重 follow-up creation
3. 加自动步数限制
4. 加 blocked / waiting_input 语义
5. 调整优先级：schedule / handoff / continuation / ask_user

### 验收信号
- 不会重复创建相同 report task
- 不会在每次 tick 重复做同样判断
- 遇到缺失输入时能进入 WAITING_INPUT 而不是空转

---

## 10. 关键风险

## 10.1 风险一：过早把“自治”全塞给 LLM

如果 phase-3 直接让 LLM 自己决定所有 next action，会有三个问题：

1. 不稳定
2. 难测
3. 难复现

所以我的建议是：

> **phase-3 第一版先做“规则驱动的 continuation engine + LLM 驱动的 brief/解释”，而不是一开始就做“LLM 完全自治规划器”。**

这样可控得多。

---

## 10.2 风险二：重复续推 / 无限循环

一旦 KAIROS 获得自动续推能力，马上会出现 runaway 风险：

- 自动创建任务
- 任务完成
- 又触发下一轮
- 重复创建/重复总结/重复唤醒

所以 phase-3 必须一开始就有：

- action fingerprint 去重
- max_auto_steps_per_cycle
- cooldown
- blocked reason

否则会把 long-running runtime 变成 long-running spammer。

---

## 10.3 风险三：自治状态不可解释

如果 KAIROS 越来越主动，但 API/UI 仍只展示 mode 与 tracked_dex_task_ids，开发者会非常难调。

所以 phase-3 必须同步补：

- decision visibility
- planned action visibility
- blocked reason visibility

这不是锦上添花，而是自治系统可运维性的必要条件。

---

## 10.4 风险四：把测试重心错误放在“自然语言 agent 是否稳定发挥”

phase-2 的测试设计已经很清楚：

- runtime 层
- integration 层
- live HTTP 层

phase-3 也应继续保持这个分层。

不要一开始就把“agent 自然语言驱动是否每次都自动选对 dex 工具”作为核心回归标准。

phase-3 第一版更应该验证：

- deterministic continuation rules 是否成立
- runtime 是否会正确 enqueue internal trigger
- 是否自动创建了正确 follow-up task
- 是否避免重复创建

---

## 11. phase-3 的测试建议

我建议新增三类测试。

## 11.1 Runtime 层

新增类似：

- `test_completed_inputs_auto_enqueue_internal_continuation_trigger`
- `test_all_inputs_ready_auto_create_report_task`
- `test_failed_task_enters_waiting_input_or_recovery_action`
- `test_continuation_engine_does_not_duplicate_follow_up`

目标：锁定自治语义。

---

## 11.2 Integration 层

新增：

- 真实 Dex task 完成后，KAIROS 自动生成 follow-up Dex task
- follow-up task 产物存在后，KAIROS 自动写 richer summary

目标：锁定 Dex + continuation 的真实边界。

---

## 11.3 Live HTTP 层

把当前 live demo 从：

- 人工注册 phase-1
- 人工注册 report

升级为：

- 人工注册 phase-1
- **KAIROS 自动推进 report**

这会成为 phase-3 最强证据。

如果这条 live 回归能稳定通过，就意味着：

> KAIROS 第一次真正跨过了“观察者”与“主动续推者”的分界线。

---

## 12. 我对“更 proactive 来自我发现需要继续的任务”这个问题的直接回答

我的回答很明确：

**我完全赞同，而且我认为这正是 phase-3 的中心命题。**

因为：

- 只会 `wake / poll / status` 的 KAIROS，本质还是 REPL 的后台辅助件
- 只有当它会：
  - 发现阶段完成
  - 判断下一步存在且值得做
  - 自己创建 continuation
  - 自己推进到下一阶段
  - 必要时再向人汇报或请求输入

它才真正开始像一个 autonomous long-term running agent。

换句话说：

> **KAIROS 的“自治感”不来自它会 sleep/wake，而来自它会在没有人类下一个 prompt 的情况下，自主生成“下一步工作”。**

这是我认为最重要的一点。

---

## 13. 最终建议

如果要把我的建议压缩成一组明确的 phase-3 实施方向，我会给出下面这组优先级。

### P0：必须优先做
1. **Continuation Engine（规则版）**
2. **internal continuation trigger**
3. **workflow / planned action 状态模型**
4. **all-inputs-ready -> auto-create report task**

### P1：紧随其后
5. **artifact-aware summary / richer proactive brief**
6. **planned actions / decision visibility API + UI**
7. **去重、cooldown、max_auto_steps 防 runaway**

### P2：中期补强
8. **workflow memory / continuation history**
9. **更明确的 WAITING_INPUT / BLOCKED 语义**
10. **弱 policy layer，为未来 supervisor 化做准备**

---

## 14. 一句话结束

如果 phase-2 证明的是：

> **KAIROS 能跟踪后台任务**

那么 phase-3 应该证明的是：

> **KAIROS 能在任务完成后自己发现“接下来该做什么”，并继续把工作往前推进。**

只有做到这一步，KAIROS 才真正开始从“后台任务观察器”，进化成你说的那种 **autonomous long-term running agent**。

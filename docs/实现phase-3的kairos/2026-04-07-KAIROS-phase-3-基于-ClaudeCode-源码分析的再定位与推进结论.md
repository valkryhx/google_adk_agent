# 2026-04-07 KAIROS Phase 3 新发现与推进结论

> 日期：2026-04-07
> 目的：基于 `docs/探讨claudecode/KAIROS-特性源码分析报告.md`、当前仓库 recent commits、`.planning` 状态与 live HTTP 验证结果，重新校准 Phase 3 的目标、定位与后续推进方向。

---

## 1. 先给结论

当前仓库对 Phase 3 的理解需要进一步升级：

> **Phase 3 不是“再补几个 continuation/policy 功能点”，而是要把当前 KAIROS 从“带自动续推能力的 runtime”演进成“长期运行的 assistant mode / autonomous runtime”。**

这意味着，Phase 1/2 并不是最终形态，它们更多是在为下面这些更高阶目标打基础：

- 让 agent 的智能在规则护栏内长期发挥
- 让系统能持续扫描未完成工作，而不只是响应用户 prompt
- 让系统在无人持续盯守时也能主动推进任务
- 让系统在需要时主动汇报、主动 ask-user、主动停住
- 让复杂任务的推进依赖更少的人类接力

换句话说：

> **Kairos 的目标不是单纯“自动续推一次 follow-up”，而是“把 agent 从 REPL 附属能力，变成长期存在、能自驱工作的自治执行体”。**

---

## 2. 重新阅读 Claude Code Kairos 源码分析报告后的关键发现

文件：`docs/探讨claudecode/KAIROS-特性源码分析报告.md`

### 2.1 Kairos 在 Claude Code 中的本质，不是单一功能，而是一种 Assistant Mode

报告直接指出：

- KAIROS 不是一个小功能
- KAIROS 不是简单的 `/assistant` 命令别名
- KAIROS 本质上是一组围绕 **assistant mode** 构建的长运行自治能力
- 它更接近：
  - 后台常驻
  - 可远程附着
  - 可定时唤醒
  - 支持 brief 回传
  - 支持长期记忆沉淀
  - 默认偏异步的 Agent 运行时

这对本项目的启发非常大：

> **我们不能把 Phase 3 只理解成 continuation engine 的增强；更准确的理解应该是：让当前 KAIROS 逐步进入一种“assistant mode 运行语义”。**

---

### 2.2 Kairos 的自治节拍不是“有事才工作”，而是 `<tick> -> 判断 -> sleep`

Claude Code 的 prompt 合约明确要求：

- 模型会收到 `<tick>`
- 若没有高价值工作，则必须 `Sleep`
- 不允许空转发言浪费 token

这说明真正的长期自治，不是“每次都输出一点状态”，而是：

- 被周期性唤醒
- 在唤醒点判断是否值得继续行动
- 若没有行动价值，就显式休眠

对本项目的意义：

> **Kairos 的主动性核心不在“更多 event handler”，而在“更强的 tick contract”。**

也就是说，`run_kairos_turn()` 未来不应只是 lightweight brief，而应该成为：

- unfinished work scan
- blocked recovery scan
- proactive next-step selection
- ask-user / brief / sleep 决策入口

---

### 2.3 Kairos 的独特性不只是 ReAct，也不只是 plan-to-do，而是“长期自治运行时”

从 Claude Code 源码报告和本项目当前状态对照看：

- **ReAct** 强在局部推理循环，但往往默认依赖人类 prompt 触发
- **plan-to-do** 强在任务拆解与阶段推进，但很多实现缺少长期存活 runtime
- **Kairos** 的独特价值在于：
  - 长期存活
  - 异步任务跟踪
  - 跨 tick 持续推进
  - 远程附着/恢复
  - brief 驱动的用户契约
  - 规则护栏 + 智能推进并存

所以更准确的理解应是：

> **Kairos = ReAct 的认知循环 + plan-to-do 的任务推进 + long-running autonomous runtime。**

---

### 2.4 Kairos 的主动性，本质上要求系统持续读取 unfinished work

这是本轮讨论里最关键的新增认识。

普通 ReAct / plan-to-do 往往默认：
- 用户先抛一个需求
- agent 再开始思考/执行

但如果 Kairos 要更接近 Claude Code 的 assistant mode，它就不该只在“用户说了什么”或“某个任务刚完成”后才动。

它至少需要具备：

- 持续查看当前有哪些 unfinished work
- 判断哪些 unfinished work 值得现在推进
- 在没有新用户 prompt 时也能主动发起下一步
- 在不适合推进时主动 sleep，而不是空转

因此，本项目的 Phase 3 不应只停留在 event-driven continuation，而要进入：

> **proactive unfinished-work stewardship（对未完成工作的主动持续接管）**

---

### 2.5 Brief 不是附属物，而是长期自治的用户契约

Claude Code Kairos 启动时会强制 brief，这说明：

- 长期自治并不是 silent daemon
- 也不是每轮都和用户闲聊
- 而是在关键时刻主动向用户输出简报

这对本项目非常重要：

未来的 Kairos 需要有更清晰的 proactive brief contract，例如：

- workflow 进入新阶段时 brief
- blocked 超过阈值时 brief
- 发现高价值下一步时 brief
- 需要用户做决定时 brief
- 达成关键产物/关键验证时 brief

否则系统要么过于沉默，要么过于喋喋不休。

---

## 3. 结合当前仓库状态，对 Phase 3 的重新定位

### 3.1 当前已经具备的基础（不是终点，而是铺垫）

当前 main 已经有：

- `KairosRuntime` 的 tick / wake / schedule / handoff 骨架
- `ContinuationEngine` 与 workflow-aware state
- `active_workflow / planned_actions / blocked_reason`
- `task_summaries / decision_explanation / condition_tree`
- todo boss demo 的真实单页 app 交付链
- verification gating / blocked-state handling
- live HTTP 回归
- 真实验证：`tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q` 在 8000 端口服务下已实测 `4 passed`

这些成果证明：

> **当前仓库已经做出了“最小自治闭环”的真实证据。**

但它们更像是 Kairos 长期自治能力的“跑道”，而不是最终目标本身。

---

### 3.2 当前不足之处

尽管已有不少成果，但当前系统距离真正的长期自治 assistant mode 仍有明显差距：

1. `run_kairos_turn()` 的 prompt 仍然偏 lightweight brief，不是 continuation-oriented / proactive-oriented prompt
2. 当前主动性主要还是围绕：
   - task 完成后续推
   - workflow 收敛后创建 follow-up
   而不是“持续扫描 unfinished work”
3. 规则护栏还不够完整：
   - continuation history
   - workflow 级 dedupe
   - cooldown
   - initiative budget / max auto steps
4. policy 状态还没有真正成为一等可观测对象
5. brief contract 还没正式设计
6. 当前 workflow 更多还是固定模板 demo，尚未真正形成“goal-driven, proactive runtime”

---

## 4. 对 Phase 3 的新目标定义

基于本轮重新思考，我建议把 Phase 3 的目标正式定义为：

> **让 KAIROS 从“可观测、可自动续推的 runtime”，演进为“在规则护栏约束下，能够持续扫描未完成工作、主动选择下一步、主动汇报或请求输入，并长期推进复杂任务的 assistant mode runtime”。**

这里有四个关键词必须同时成立：

### 4.1 Long-running
- 不依赖用户一直在线
- 支持 tick / sleep / wake 的长期循环
- 能围绕目标持续存在，而不是单轮问答结束即停

### 4.2 Proactive
- 不只等待用户 prompt
- 不只等待某个事件完成
- 能主动读取 unfinished work 并推动下一步

### 4.3 Guarded
- 不是让 LLM 自由失控
- 必须有 dedupe / cooldown / max auto steps / blocked semantics
- 必须可解释、可观察、可测试

### 4.4 Agentic
- Kairos 的核心不是规则本身，而是让 agent intelligence 真正介入：
  - 判断值得做什么
  - 判断何时该继续/brief/ask-user/sleep
  - 在复杂任务里承担中短期推进职责

---

## 5. 对 ReAct、plan-to-do、Kairos 的关系判断

本轮讨论后，可以明确形成如下判断：

### 5.1 它们有相似性
三者都在解决：
- 现在是什么状态
- 下一步该做什么
- 做完后如何继续

都属于某种“Observe -> Interpret -> Decide -> Act -> Repeat”循环。

### 5.2 但 Kairos 的独特价值更偏运行时
- ReAct 更像单轮认知循环
- plan-to-do 更像任务推进机制
- Kairos 更像承载这两者的长期自治 runtime

因此：

> **Kairos 不是 ReAct 的替代品，也不是 plan-to-do 的替代品，而是把它们放进一个能长期存活、异步推进、可恢复、可简报、可受策略约束的运行时里。**

---

## 6. 对后续开发最重要的推进建议

### 6.1 先不要把 Phase 3 继续理解成“纯 policy hardening”
如果只盯住：
- dedupe
- max auto steps
- blocked
- verification

那只是在补护栏，不是在完成 Kairos 的最终方向。

正确的理解应该是：

> **规则护栏是为了释放 agent intelligence，而不是替代它。**

---

### 6.2 Phase 3 应按新的结构拆分
我建议后续开发按下面 3 个阶段推进，而不是沿用过窄的旧口径。

#### 3A. Assistant Mode Contract
目标：把当前 Kairos 从“带 continuation 的 runtime”提升为“真正的长期自治运行模式”。

重点：
- tick contract
- sleep contract
- proactive brief contract
- unfinished work scan contract
- active/idle/blocked 的模式语义

#### 3B. Proactive Work Stewardship
目标：让 Kairos 主动持续读取未完成工作，而不只是被动响应事件。

重点：
- unfinished work 视图
- self-generated continuation trigger
- pending work prioritization
- blocked recovery / ask-user transition
- 更强的主动下一步选择

#### 3C. Guardrails & Verification Closure
目标：在释放主动性与智能的同时，确保系统可控、可测、可调试。

重点：
- continuation history
- stronger dedupe
- cooldown / max auto steps / initiative budget
- policy observability
- runtime / integration / live-http / frontend regression
- `03-VERIFICATION.md`

---

### 6.3 当前最值得优先落地的不是“再扩 demo”，而是“unfinished work scanning”
当前 todo demo 已经足够强，可以继续作为主验证样例。

后续最值得优先做的能力不是再把 demo 做复杂，而是让 Kairos 能回答：

- 我现在还有哪些未完成工作？
- 哪些应该现在继续推进？
- 哪些应该等？
- 哪些需要 ask-user？
- 哪些值得 brief 给用户？

这一步一旦做成，Kairos 才会从“自动 follow-up 系统”真正迈向“长期自治 assistant runtime”。

---

## 7. 当前建议的第一优先开发问题

如果只保留一个最关键的开发问题，我建议是：

> **如何让 Kairos 在没有新用户 prompt 的情况下，持续读取当前 active workflow 的 unfinished work，并在规则护栏内主动推进下一个高价值动作？**

这是连接：
- continuation
- proactive
- long-running autonomy
- assistant mode
- rule-guided agent intelligence

的真正桥梁。

---

## 8. 最终总结

本轮重新阅读 Claude Code Kairos 源码分析报告后，Phase 3 的方向可以更清晰地表述为：

> **Kairos 的最终目标不是做一个更强的规则引擎，也不是只证明一次自动续推；而是让 agent intelligence 在规则护栏约束下，长期、主动、稳定地接管未完成工作，并通过 brief / sleep / wake / async execution 形成真正的 assistant mode runtime。**

因此，后续开发应把：

- continuation
- proactive
- brief
- unfinished-work scanning
- guardrails
- long-running continuity

统一看作同一个目标的不同组成部分，而不是彼此独立的小功能。

---

## 9. 建议的下一步

基于本文件，建议立即做两件事：

1. 在 `.planning/phases/03-policy-hardening-verification/` 下生成正式的 `03-CONTEXT.md`，把这里的目标和结论折叠进主线 planning
2. 基于新的定位重写 Phase 3 的执行 plan，优先围绕：
   - Assistant Mode Contract
   - Proactive Work Stewardship
   - Guardrails & Verification Closure

只有这样，后续 Phase 3 的实现才不会继续停留在“增强 continuation 的局部视角”，而会真正朝 Kairos 的长期自治目标推进。

# Phase 05: 提示词约束的文档驱动持续推进（Prompt-Governed Document-Driven Continuation）

**Drafted:** 2026-04-11
**Status:** Draft proposal

<goal>
## 总目标

让 Kairos 从“依赖硬编码 workflow 模板的续推器”，升级为“通过提示词协议生成、阅读、更新规范化工作文档的后台常驻 assistant”。

它既要能接管人类用户的需求，把需求转化为可持续推进的工作文档；也要能在自动唤醒时，通过阅读文档和工件状态，主动发现未完成任务、识别新派生任务、进行 planning / re-plan，并在安全边界内持续推进。

这里的核心变化不是“再加更多 workflow 模板”，而是把工作定义来源从 Python 代码切换为**由 LLM 生成和维护的文档事实**。
</goal>

<design_principles>
## 设计原则

### 原则 1：文档是事实来源
Kairos 推进的对象不再主要是硬编码 workflow，而是工作文档中声明和演化出的目标、步骤、阻塞、产物和验证状态。

### 原则 2：提示词是协议，而不是 rigid schema
不采用强硬 JSON-only / fixed-field parser 作为主模式，而是通过提示词约束 Kairos 输出**规范化但不僵化**的文书，保证文档既可读、又可被后续 LLM 稳定理解。

### 原则 3：代码只做薄护栏
代码层负责目录扫描、安全边界、调用链编排、状态持久化、审计与少量关键字段校验；语义理解、任务分解、进度更新和重规划解释优先交给 LLM 在提示词协议下完成。

### 原则 4：所有发现与推进结果都要回写
Kairos 不应把新任务、重规划结论或推进进度只留在内存里，必须回写为项目文档事实，避免“幽灵任务”。
</design_principles>

<why_now>
## 为什么 Phase 5 现在做

Phase 4 已经完成了 continuation 骨架：
- 4A 提供 current state + history timeline 的可见性底座
- 4B 提供 planning artifact、candidate selection、re-plan、API/history/UI planning trace

但当前 Kairos 仍然依赖硬编码 workflow：
- `demo_report_pipeline`
- `todo_delivery_pipeline`

这意味着它已经“会推进”，但还不会“定义工作本身”。

如果继续沿着模板路线扩展，只会把 `sales/todo/...` 变成越来越大的 if/elif 分支树。Phase 5 的真正价值，在于让 Kairos 开始接手**文档定义的工作流**，从而服务代码任务，也服务更广义的通用任务。
</why_now>

<phase_shape>
## 建议阶段结构

推荐把 Phase 5 分成三个连续子阶段：
- **5A：文档协议与阅读/写入底座**
- **5B：需求落盘与工作草案生成**
- **5C：自主发现新任务与持续编排**

整体路线：
- 先定义提示词约束下的文档协议
- 再让 Kairos 把用户需求落成工作文档
- 最后让它在自动唤醒中从文档持续发现和派生工作
</phase_shape>

---

## Phase 5A：文档协议与阅读/写入底座

### 子阶段目标
建立 Kairos 的第一版“文档协议”：让 Kairos 能通过提示词稳定生成、阅读、更新工作文档，并把这些文档作为 continuation/planning 的新 source of truth。

### 要解决的问题
当前 Kairos 的工作状态主要来自代码模板。5A 要解决的是：
- 文档如何写，才能既自然又可持续读取
- Kairos 如何稳定从文档中提取 goal / current step / blockers / artifacts / next actions
- Kairos 如何把推进结果写回文档，而不破坏已有上下文

### Must-have capabilities
1. **定义文档协议（Prompt-Governed Doc Protocol）**
   - 不要求 rigid schema，但要求存在稳定语义锚点，例如：
     - Goal
     - Current Status
     - Current Step
     - Steps / Next Steps
     - Expected Artifacts
     - Blockers
     - Verification
     - Replan Notes
     - Spawned Work

2. **文档生成提示词**
   - 给定需求或工作上下文，Kairos 能生成第一版规范化工作文档
   - 输出必须包含推进所需关键语义，不允许只有泛泛 prose

3. **文档读取提示词**
   - 给定工作文档与现有工件状态，Kairos 能提取：
     - current status
     - current step
     - candidate actions
     - missing requirements
     - blockers
     - possible spawned work

4. **进度更新提示词**
   - 步骤完成、重规划、阻塞、派生任务出现时，Kairos 能更新文档
   - 保证历史上下文保留，新增信息明确可追踪

5. **最小运行时接线**
   - 代码层提供：
     - 白名单目录扫描
     - 文档读写入口
     - LLM 调用封装
     - 审计记录
     - 护栏控制

### Success criteria
1. 至少一种文档驱动工作能被 Kairos 稳定生成、读取、更新
2. `last_planning_result`、`unfinished_work_items`、`proactive_candidates` 开始面向文档 work item 而不只是硬编码 workflow stage
3. 自动唤醒时，Kairos 能从文档读出 current step / blockers / expected artifacts，并给出 continue / ask_user / blocked / sleep 决策
4. 有 source/integration tests 证明：不是 parser 在驱动，而是“提示词协议 + 文档读写”在驱动

### 建议测试策略
- 提示词输出 contract tests：文档必须包含关键语义块
- 读取结果 tests：相同文档在给定上下文下能稳定提取推进状态
- runtime tests：从文档 work item 开始 continuation，而不是从预定义 workflow 开始

### 明确不做
- 不做 arbitrary markdown 全仓库自由理解
- 不做复杂 work graph 调度器
- 不做无限制的自然语言直接执行

---

## Phase 5B：需求落盘与工作草案生成

### 子阶段目标
让用户通过接口输入需求后，Kairos 不再只回复文本，而是先把需求落成规范化工作文档，再把该文档纳入持续推进链路。

### 要解决的问题
当前 `/api/chat` 中的自然语言需求不会自动变成可推进工作。5B 要解决的是：
- 用户需求如何被吸收为项目事实
- 信息不足时如何 ask_user
- 信息足够时如何生成 work draft 并进入 Kairos loop

### Must-have capabilities
1. **需求转工作草案提示词**
   - 用户给出需求后，Kairos 生成 spec / plan / progress 初稿
   - 文书必须带推进关键语义块，而不是仅给建议

2. **轻量 archetype / 模式识别**
   - 初期可以允许少量 archetype 引导提示词，但不要把语义硬编码死在代码里
   - archetype 主要服务于提示词选择，而不是 workflow 模板分支

3. **开放问题生成**
   - 当需求不完整时，Kairos 要在文档中写明 open questions / assumptions
   - 并在 planning 中转为 `ask_user`

4. **自动接线进入 continuation**
   - 文档一旦落盘，Kairos 后续唤醒时就应能识别并推进它

### Success criteria
1. 用户给出一个受支持的需求后，系统会生成规范化工作文档，而不是只停留在聊天回复
2. 该工作文档可被 5A 的阅读提示词稳定识别
3. Kairos 至少能对该文档化工作执行一步自动推进
4. 当需求缺关键信息时，Kairos 进入 `ask_user`，而不是伪造后续计划

### 建议测试策略
- `/api/chat` -> 文档生成 source/integration tests
- runtime tests：新文档 work item 被自动发现
- live HTTP tests：用户需求输入后，status/API/history 中能看到新文档工作项出现

### 明确不做
- 不做开放域任意需求理解
- 不做完全自由代码自动执行
- 不做“用户一��话 -> 全自动多步开发完成”的激进闭环

---

## Phase 5C：自主发现新任务与持续编排

### 子阶段目标
让 Kairos 不只是推进已有文档任务，还能在自动唤醒时通过阅读文档、验证结果、工件状态和历史轨迹，识别并生成新工作文档，然后继续推进。

### 要解决的问题
当前 Kairos 可以在既有流程内 follow-up，但还不能把新发现的问题和派生工作系统化地沉淀为新任务事实。

### Must-have capabilities
1. **自主发现 unfinished / spawned work**
   - 从 progress / verification / artifacts / history 中发现：
     - 未完成工作
     - 派生验证任务
     - 缺陷修复任务
     - 交付/回归任务

2. **新工作文档化**
   - 新派生工作必须写入：
     - 当前文档的 `Spawned Work`
     - 或新建 work item 文档
   - 不允许只存在于 runtime memory

3. **文档驱动 re-plan**
   - 文档内容变化、artifact 变化、verification 变化时，Kairos 触发显式 re-plan
   - 继续复用 4B 的 planning trace / history / UI 资产

4. **统一入口**
   - 用户新需求和系统发现问题最终都归一为“文档工作项”

### Success criteria
1. Kairos 能在自动唤醒时发现至少一种新派生工作，并写回文档
2. history timeline 能记录显著的文档驱动 re-plan / new work creation
3. API/UI 能展示 document-backed planning winner、rejected summary、re-plan trace
4. live flow 证明：即使用户没有再次输入，Kairos 也能从文档状态继续推进新产生的工作

### 建议测试策略
- runtime integration：step 完成后派生新 documented work
- history/API/UI regression：新工作与 re-plan 可见
- live HTTP regression：完成“用户需求 -> 文档 -> 推进 -> 派生工作 -> 再推进”闭环

### 明确不做
- 不做 fully autonomous git push/PR loop
- 不做跨仓库项目管理中台
- 不做高级优先级学习/长期记忆优化

---

## 整体边界与安全原则

1. **目录白名单**
   - 仅扫描声明的 workspace / planning 目录

2. **提示词协议优先，代码校验为辅**
   - 文档主要靠 LLM 生成与理解
   - 代码只校验少量关键约束与安全条件

3. **高风险动作默认 ask_user**
   - 文档中若没有明确允许，不自动执行高风险代码/系统动作

4. **文档优先于内存**
   - 新任务、重规划、推进结果必须回写文档后才算真实存在

5. **复用 Phase 4 资产**
   - `last_planning_result`
   - `unfinished_work_items`
   - `proactive_candidates`
   - `planning_winner`
   - `planning_replan`
   - history trace
   - operator console

---

## 推荐落地顺序

### 第一优先级
先做 **5A：文档协议与阅读/写入底座**

### 第二优先级
再做 **5B：需求落盘与工作草案生成**

### 第三优先级
最后做 **5C：自主发现新任务与持续编排**

这个顺序的原因是：
- 先建立文档协议和读写能力
- 再让用户需求进入文档链路
- 最后让系统自主发现更多工作

---

## 建议一句话对外表述

“Phase 5 让 Kairos 首次具备通过提示词协议生成、阅读、更新工作文档的能力：既能把需求落为可推进工作项，也能在自动唤醒时从文档中发现未完成任务与新派生任务，并把决策与进展回写为项目事实。”

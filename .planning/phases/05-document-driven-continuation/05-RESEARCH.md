# Phase 05 Research: 提示词约束的文档驱动持续推进

**Researched:** 2026-04-11
**Status:** Draft
**Phase:** 05-document-driven-continuation

## 1. Research Summary

Phase 5 不应继续沿着“新增更多硬编码 workflow template”的方向演进，而应把 Kairos 的工作定义来源从代码模板切换为**由 LLM 生成、阅读和更新的工作文档**。

推荐路线是：
- 以文档为事实来源
- 以提示词为协议
- 以代码为薄护栏
- 复用 Phase 4 已完成的 planning/runtime/history/API/UI 资产

这意味着 Kairos 的下一阶段重点不是 parser-first，而是：
1. 定义一套 LLM-first 的文档协议
2. 让 Kairos 稳定生成、读取、更新这种文档
3. 让 runtime 在 wakeup 时基于文档状态而不是硬编码 stage 做 continuation

---

## 2. Core Insight

当前系统已经“会推进”，但还不会“定义工作本身”。

Phase 4 的完成带来了：
- planning artifact (`last_planning_result`)
- fixed candidate taxonomy
- winner / rejected / re-plan trace
- runtime / API / history / UI 可见性

这些资产已经足以支撑 Kairos 对“文档化工作”的推进。真正缺失的是：
- 工作如何被创建
- 工作如何被记录
- 新任务如何被发现
- 进度如何成为项目事实

因此 Phase 5 的核心问题不是“怎么继续做 planning”，而是“planning 面对的对象如何从代码模板切换为文档工作项”。

---

## 3. Recommended Architecture Direction

推荐采用四层结构：

### 3.1 Document Discovery Layer
职责：
- 扫描白名单目录（例如 `.planning/`、指定 `kairos_workspace/`）
- 找到候选工作文档
- 决定哪些文件可交给 LLM 阅读

建议边界：
- 只扫描显式允许目录
- 默认不扫描整个 repo 的任意 markdown
- 允许基于命名约定优先识别：
  - `*-PLAN.md`
  - `*-SUMMARY.md`
  - `*-VERIFICATION.md`
  - `.continue-here.md`
  - 后续的 `WORK_ITEM.md` / `PROGRESS.md`

### 3.2 Prompt-Governed Document Intelligence Layer
职责：
- 通过提示词生成工作文档
- 通过提示词读取工作文档
- 通过提示词更新工作文档

这层是 Phase 5 的核心，不建议被代码 parser 取代。

### 3.3 Continuation Runtime Layer
职责：
- 把“文档阅读结果”转成 Kairos continuation 需要的状态
- 继续沿用 4B：
  - `unfinished_work_items`
  - `proactive_candidates`
  - `last_planning_result`
  - `planning_winner`
  - `planning_replan`

建议做法：
- 让 continuation engine 逐步从 `workflow_id == ...` 条件判断，升级为面向 `document-backed work item`
- 仍保留 candidate taxonomy / tier 机制，不必推翻 4B

### 3.4 Audit & UI Layer
职责：
- 把显著 planning/re-plan/new-work 事件写入 history
- 通过 status/API 暴露 document-backed summary
- 在 operator console 上显示：
  - 当前文档工作项
  - 当前 winner
  - re-plan note
  - spawned work

---

## 4. Document Protocol Strategy

## 4.1 Why not rigid schema
不推荐以 rigid JSON schema 或强 parser 为主，因为：
- 任务类型天然异构
- 文档用途不仅是机器消费，也需要人类阅读与修改
- 未来不只代码任务，还会有调研、审核、运营、协作型任务

## 4.2 Why not unconstrained prose
也不推荐完全自由 prose，因为：
- 难以稳定提取推进状态
- 容易丢失 blocker / artifacts / next actions
- 无法稳定做 continuation 与回写

## 4.3 Recommended compromise: soft protocol
推荐“软协议文档”：
- 仍然是 Markdown / 人类可读文书
- 但通过提示词强制输出稳定语义锚点
- 例如：
  - Goal
  - Current Status
  - Current Step
  - Steps / Next Steps
  - Expected Artifacts
  - Blockers
  - Verification
  - Replan Notes
  - Spawned Work

关键点：
- 这些不是 rigid parser schema
- 而是 **LLM 协议锚点**
- 文档写法可灵活，但语义块必须可被下一次 LLM 读取

---

## 5. The Three Prompt Families

Phase 5 最关键的不是“新增多少数据类”，而是设计三类核心提示词。

### 5.1 文档生成提示词（Document Authoring Prompt）
输入：
- 用户需求 / 系统发现的问题
- 当前项目上下文
- 当前目录/范围限制

输出目标：
- 一份规范化工作文档
- 包含：
  - Goal
  - Current Status
  - Current Step
  - Steps
  - Expected Artifacts
  - Blockers
  - Verification
  - Open Questions（如需要）

关键要求：
- 不只是建议
- 要生成可持续推进的工作事实
- 需求不完整时必须显式记录开放问题

### 5.2 文档阅读提示词（Document Reading Prompt）
输入：
- 一份或多份工作文档
- 当前 artifact existence / verification status / recent events

输出目标：
- 一个结构化阅读结果，至少包含：
  - current_status
  - current_step
  - incomplete_steps
  - blockers
  - candidate_actions
  - missing_requirements
  - spawned_work_candidates
  - recommended_action

关键要求：
- 输出可直接给 continuation layer 用
- 重点是“抽取推进状态”，不是重写整份文档

### 5.3 文档更新提示词（Progress Update Prompt）
输入：
- 原工作文档
- 当前执行结果
- re-plan / blocker / spawned work 变化

输出目标：
- 更新后的工作文档
- 或增量 patch（后续可做）

关键要求：
- 保留原有上下文
- 明确记录新进展
- 当出现新工作时写入 Spawned Work
- 当出现 blocker 时写明 why + next ask

---

## 6. Suggested Internal State Mapping

虽然不建议用 rigid parser 主导，但 runtime 层仍需要一个稳定的“中间态”。

推荐中间态不是直接对 Markdown 强 parse，而是对 **LLM 阅读结果** 进行约束。

可参考最小字段：
- `work_id`
- `goal`
- `source_docs`
- `status`
- `current_step`
- `next_actions`
- `blockers`
- `expected_artifacts`
- `spawned_work_candidates`
- `human_input_required`

注意：
- 这是 runtime 的中间态
- 不是要求文档必须长成这个数据结构

---

## 7. Safety Boundaries

Phase 5 必须建立比模板时代更清晰的安全边界。

### 7.1 Directory whitelist
- 仅允许扫描和写入声明目录
- 默认不跨仓库、不跨项目

### 7.2 Action whitelist
- 自动推进只限低风险动作：
  - 文档生成/更新
  - 报告
  - 验证
  - 已声明的 Dex follow-up
- 高风险动作默认 ask_user：
  - 大规模文件修改
  - 删除
  - 推送
  - CI/部署
  - 凭空执行未知命令

### 7.3 Documentation-first persistence
- 新工作项只有写回文档后才算真实存在
- 防止新任务只存在 memory 中而不可恢复

### 7.4 Missing-info fallback
- 文档关键信息不足时必须进入：
  - `ask_user`
  - 或 `blocked`
- 不能伪造下一步

---

## 8. Recommended Phase Breakdown

## 8.1 Phase 5A：文档协议与阅读/写入底座
重点：
- 把文档协议与三类提示词打通
- 让 Kairos 能稳定读写 work docs

交付物建议：
- Prompt contract draft
- document-backed continuation proof
- source/integration tests

## 8.2 Phase 5B：需求落盘与工作草案生成
重点：
- 用户需求 -> 文档工作项
- 缺信息时 ask_user
- 文档进入 Kairos loop

交付物建议：
- `/api/chat` 触发 work doc 生成
- 新文档被 wakeup 识别
- live flow 中出现 document-backed work item

## 8.3 Phase 5C：自主发现新任务与持续编排
重点：
- 从 progress / verification / artifacts / history 中发现新工作
- 把新工作回写文档
- 继续推进

交付物建议：
- spawned work persistence
- re-plan event visibility
- end-to-end documented work loop

---

## 9. Testing Strategy

### 9.1 Prompt contract tests
验证：
- 生成文档包含必须语义锚点
- 阅读结果包含推进所需字段
- 更新文档能保留上下文并追加进展

### 9.2 Continuation/runtime tests
验证：
- 给定 document-reading result，Kairos 能正确生成 candidates / winner / final_action
- blocker / ask_user / sleep / continue 仍然可测

### 9.3 Integration tests
验证：
- 新文档生成后可被发现
- 完成一步后文档被更新
- 派生工作被写回文档

### 9.4 API/history/UI regression
验证：
- status 暴露 document-backed current work
- history 有显著 planning/re-plan/new-work 事件
- operator console 能看到 document-backed planning trace

### 9.5 Live HTTP regression
验证真实闭环：
- 用户输入需求
- Kairos 生成文档
- Kairos 自动推进
- 任务完成/阻塞/派生工作都可见

---

## 10. Trade-off Summary

### 推荐方案
**LLM-first + soft protocol + thin runtime guardrails**

### 优点
- 灵活
- 更通用
- 更符合 Kairos 长期定位
- 真正利用 LLM 的强项
- 不会把模板爆炸转化为 schema 爆炸

### 风险
- 文档理解稳定性要靠提示词与测试保障
- 比 parser-first 更依赖提示词质量
- 需要设计好审计与 fallback 行为

### 为什么仍然值得做
因为它比继续扩展硬编码 template 更符合长期价值，也比 rigid parser 更接近你想要的“常驻主动 assistant”。

---

## 11. Recommended next artifact after this research

基于本研究，最自然的下一步是：
1. 写 `05-PLAN.md` 或拆成 `05A/05B/05C` 执行计划
2. 先为 5A 定义三类提示词 contract
3. 先写失败测试，验证“文档生成/读取/更新”能力

---

## Final Recommendation

Phase 5 应被定义为：

> **提示词约束的文档驱动持续推进**
>
> Kairos 通过提示词协议生成、阅读、更新规范化工作文档，以文档而不是硬编码 workflow 模板作为任务定义来源；从而既能接管用户需求，也能在自动唤醒时发现并推进未完成任务与新派生任务。

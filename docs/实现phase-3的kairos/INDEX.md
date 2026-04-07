# KAIROS Phase 3 文档索引

> 日期：2026-04-07
> 目录：`docs/实现phase-3的kairos`
> 用途：汇总本轮已形成的 phase-3 文档，帮助后续直接进入实现、规划或验证。

---

## 1. 文档清单

### 1.1 演进思考
- `2026-04-05-KAIROS-phase-3-演进思考.md`

**用途：**
从愿景与架构层面回答：
- 当前 KAIROS 距离真正的 autonomous long-term running 还差什么
- 为什么 phase-3 的核心不是继续做观察，而是做 continuation
- 为什么要引入 Continuation Engine

**适合阅读时机：**
- 先理解 why / what
- 做架构评审前

---

### 1.2 实施计划（第一版）
- `2026-04-05-KAIROS-phase-3-实施计划-第一版.md`

**用途：**
把 phase-3 思考收敛成可执行方案，明确：
- 总体方案
- 关键代码改造方向
- 最小闭环
- 测试策略

**适合阅读时机：**
- 准备进入实现前
- 需要先确认主线方案时

---

### 1.3 精确代码改造清单
- `2026-04-05-KAIROS-phase-3-精确代码改造清单.md`

**用途：**
按文件粒度说明：
- 建议新增哪些文件
- 哪些现有文件必须修改
- 每个文件需要承担什么新职责
- 对应测试文件如何扩展

**适合阅读时机：**
- 开始拆开发任务时
- 需要明确“先改哪个文件”时

---

### 1.4 测试矩阵
- `2026-04-05-KAIROS-phase-3-测试矩阵.md`

**用途：**
为 phase-3 建立 runtime / integration / live-http / frontend 四层验证框架，明确：
- 各层要验证什么
- 建议新增哪些测试
- 推荐先跑哪些命令

**适合阅读时机：**
- 准备按 TDD 落地时
- 需要决定回归范围时

---

### 1.5 Roadmap 与验收标准
- `2026-04-05-KAIROS-phase-3-roadmap-与验收标准.md`

**用途：**
按 milestone（3A / 3B / 3C）说明：
- scope
- non-goals
- acceptance
- risks
- verification commands

**适合阅读时机：**
- 做排期与分阶段交付时
- 讨论 phase-3 应先做哪一段时

---

### 1.6 下一步行动清单
- `2026-04-05-KAIROS-phase-3-下一步行动清单.md`

**用途：**
把所有文档进一步压缩成“马上开工”的 checklist，明确：
- 第一轮先做什么
- 先写哪些测试
- 先改哪些文件
- 第一轮明确不做什么

**适合阅读时机：**
- 真正开始 coding 前
- 需要快速切入第一阶段实现时

---

### 1.7 基于 Claude Code 源码分析的再定位与推进结论
- `2026-04-07-KAIROS-phase-3-基于-ClaudeCode-源码分析的再定位与推进结论.md`

**用途：**
基于 `docs/探讨claudecode/KAIROS-特性源码分析报告.md`、当前仓库 recent commits、`.planning` 状态与 live HTTP 验证结果，重新定义：
- Kairos 在本项目中的真正目标
- Kairos 与 ReAct / plan-to-do 的关系
- proactive 的本质为何应是 unfinished-work scanning
- 为什么 Phase 3 应朝 assistant mode / long-running autonomous runtime 演进

**适合阅读时机：**
- 需要重新校准 Phase 3 方向时
- 准备从“自动续推 demo”升级到“长期自治 assistant mode”时
- 开始编写 `03-CONTEXT.md` 或重写 Phase 3 计划前

---

## 2. 推荐阅读顺序

如果是第一次接手 phase-3，建议按下面顺序读：

1. `2026-04-05-KAIROS-phase-3-演进思考.md`
2. `2026-04-07-KAIROS-phase-3-基于-ClaudeCode-源码分析的再定位与推进结论.md`
3. `2026-04-05-KAIROS-phase-3-实施计划-第一版.md`
4. `2026-04-05-KAIROS-phase-3-精确代码改造清单.md`
5. `2026-04-05-KAIROS-phase-3-测试矩阵.md`
6. `2026-04-05-KAIROS-phase-3-roadmap-与验收标准.md`
7. `2026-04-05-KAIROS-phase-3-下一步行动清单.md`

如果目标只是“现在就开始开发”，可以直接读：

1. `2026-04-07-KAIROS-phase-3-基于-ClaudeCode-源码分析的再定位与推进结论.md`
2. `2026-04-05-KAIROS-phase-3-下一步行动清单.md`
3. `2026-04-05-KAIROS-phase-3-精确代码改造清单.md`
4. `2026-04-05-KAIROS-phase-3-测试矩阵.md`

---

## 3. 当前统一结论

本目录当前更新后的统一结论应表述为：

> **Phase 3 的核心不再只是“增强 KAIROS 的观察能力”或“证明一次自动续推”，而是让它在规则护栏约束下，持续扫描未完成工作、主动选择下一步、主动 brief/ask-user/sleep，并逐步演进为长期运行的 autonomous assistant mode runtime。**

因此当前最关键、最值得优先推进的目标不应再局限于：

> 在 live HTTP demo 中，不再由人手工注册 report task，而是由 KAIROS 自己发现 phase-1 已收敛，并自动推进 report 阶段。

这条仍然是重要的最小闭环证据，但在当前阶段，它更准确地应被看作：

> **证明 KAIROS 已经具备“跳出 REPL 主导模式”的最小技术跑道，而不是 Phase 3 的最终目标本身。**

在此基础上，后续更关键的推进方向是：

1. 让 Kairos 具备真正的 unfinished-work scanning 能力
2. 让 tick/wake/sleep/brief 成为正式的 assistant mode contract
3. 让 agent intelligence 在规则护栏内主动推动任务，而不只是等待用户 prompt 或单次 follow-up 事件
4. 让系统逐步从“自动续推 demo”演进为“长期自治 assistant runtime”

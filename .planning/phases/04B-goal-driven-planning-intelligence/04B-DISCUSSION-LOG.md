# Phase 04B: Goal-Driven Planning Intelligence - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-10
**Phase:** 04B-goal-driven-planning-intelligence
**Areas discussed:** 候选模型, 规划产物, 重规划触发, 决策语气, winner 切换阈值, trace 观测面, 候选等级体系, history 写入密度

---

## 候选模型

| Option | Description | Selected |
|--------|-------------|----------|
| 固定小集合 | 先把候选动作严格限制为 5-6 类，优先把结构、trace、UI、测试打通 | ✓ |
| 半开放集合 | 核心候选固定，但允许按 workflow 再扩一些候选类型 | |
| 开放集合 | 候选类型尽量泛化，早期就为更强 planner 预留大扩展空间 | |

**User's choice:** 固定小集合
**Notes:** 用户要求四个灰区都讨论，但先从最小可落地版本开始。

---

## 规划产物

| Option | Description | Selected |
|--------|-------------|----------|
| 摘要级 rejected candidates | 只保留候选名 + rejected reason，一两行即可 | |
| 中等粒度 rejected candidates | 除 rejected reason 外，再保留 priority / blocked / policy note 等字段 | ✓ |
| 尽量完整 rejected candidates | 接近完整 planning snapshot，方便以后做更强分析，但更重更吵 | |

**User's choice:** 中等粒度 rejected candidates
**Notes:** 用户希望 `last_planning_result` 是真实但轻量的 planning artifact，不要走完整 deliberation transcript。

---

## 重规划触发

| Option | Description | Selected |
|--------|-------------|----------|
| 只收最硬的 guardrail 触发 | cooldown、artifact 缺失、verification failed、winner blocked | |
| 再加 workflow stalled | 在硬触发上再把 workflow 卡住纳入 re-plan | |
| 更主动一些 | 除 guardrail/stall 外，也允许更高价值候选出现时触发 re-plan | ✓ |

**User's choice:** 更主动一些
**Notes:** 用户接受最小版也允许“更高价值候选出现时触发 re-plan”。

---

## 决策语气

| Option | Description | Selected |
|--------|-------------|----------|
| 精简操作台 | 只展示最必要 planning trace：候选、赢家、拒绝原因、re-plan 原因 | |
| 平衡说明 | 在核心结论外再补一层简短 policy/context 说明 | |
| 较完整轨迹 | 尽量多展示比较过程与上下文，方便深度排查，但不展开成长篇思维流 | ✓ |

**User's choice:** 较完整轨迹
**Notes:** 用户想要更强的 operator-facing planning trace，但不意味着要持久化完整 chain-of-thought。

---

## winner 切换阈值

| Option | Description | Selected |
|--------|-------------|----------|
| 只允许明确高一个等级才切换 | 只有明显更高价值动作才能推翻当前 winner，稳定且好测 | ✓ |
| 允许分数更高就切换 | 只要新候选 priority 更高就替换 winner | |
| 允许切换但加防抖条件 | 更高价值时可切换，但要满足额外条件 | |

**User's choice:** 只允许明确高一个等级才切换
**Notes:** 用户希望避免分数抖动式 re-plan，偏好离散等级跃迁。

---

## trace 观测面

| Option | Description | Selected |
|--------|-------------|----------|
| 当前状态优先 | 重点放左侧 current snapshot / status API；history 只记摘要 | |
| 历史时间线优先 | 重点放 history timeline；当前状态只放当前 winner 和一句摘要 | |
| 双面都强 | 当前状态展示当前 planning result；history 记录显著 planning / re-plan 轨迹 | ✓ |

**User's choice:** 双面都强
**Notes:** 用户明确希望 planning trace 同时在当前状态和历史时间线中都可见。

---

## 候选等级体系

| Option | Description | Selected |
|--------|-------------|----------|
| 三层等级 | 高=`ask_user` / `blocked`；中=`create_follow_up` / `continue_workflow`；低=`emit_brief` / `sleep` | ✓ |
| 四层等级 | 拆得更细，区分 ask_user 与 blocked、brief 与 sleep | |
| 动作各自独立排序 | 不预设固定层级，每种动作单独比较 | |

**User's choice:** 三层等级
**Notes:** 讨论中一度探索“动作各自独立排序”，随后用户主动更正，明确改回“三层等级（推荐）”作为最终决定。

---

## history 写入密度

| Option | Description | Selected |
|--------|-------------|----------|
| 只记录显著事件 | 只在新 winner、winner 被推翻、进入 ask_user/blocked/sleep、显式 re-plan 时写 timeline | ✓ |
| 记录每次 planning 评估 | 每次 scan / planning 都记一条 | |
| 折中模式 | 默认只记显著事件，但候选集或 policy note 变化时也记 | |

**User's choice:** 只记录显著事件
**Notes:** 用户希望 4B 的 history timeline 更像 operator 轨迹，而不是内部调试流。

---

## Claude's Discretion

- 候选对象与 planning artifact 的精确字段命名
- `selected_reason` / `rejected_reason` / `policy_note` 的文案模板
- planning artifact 在 current snapshot 中的卡片排列方式
- planning / re-plan 事件在 history timeline 里的 title 与摘要文案

## Deferred Ideas

- 开放式 candidate taxonomy
- 纯 numeric priority 驱动切换
- 每次 planning scan 都进入 history timeline
- 完整 deliberation transcript 持久化

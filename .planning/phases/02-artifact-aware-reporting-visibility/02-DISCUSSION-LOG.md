# Phase 2: Artifact-Aware Reporting & Visibility - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-06
**Phase:** 02-artifact-aware-reporting-visibility
**Areas discussed:** 结果摘要, 阻塞解释, 前端排布, API 粒度, 摘要字段, 事件流分工, 缺失项粒度, 失败呈现

---

## 结果摘要

| Option | Description | Selected |
|--------|-------------|----------|
| 简洁结构化 | 每个任务显示 1-2 行结构化摘要：完成/失败、关键结果、必要 artifact 提示；不直接暴露大段原始日志。最适合 recent events、status 和面板共用。 | |
| 详细结果块 | 为每个任务展示更完整的结果块，包含更多字段与 artifact 列表，UI 和 API 都更重。 | |
| 原始片段优先 | 优先展示原始 result/log 片段，保真高，但噪音也更大。 | |

**User's choice:** 简洁结构化（后续细化时又要求字段更丰富，最终收敛为“结构化但字段更丰富”的摘要）
**Notes:** 初始选择偏向简洁结构化；在后续“摘要字段”讨论中，用户明确要求比四要素更丰富的字段集合，因此 CONTEXT.md 以扩展字段结构化摘要为准。

---

## 阻塞解释

| Option | Description | Selected |
|--------|-------------|----------|
| 三段式解释 | 不仅显示 blocked reason，还明确回答：为什么继续/为什么停住/还缺什么。适合 recent events 与状态面板统一表达。 | ✓ |
| 一句话原因 | 保留现在的一句话 blocked reason，改动最小。 | |
| 阶段条件清单 | 按当前 stage 展示条件满足/未满足项，信息更细，但也更复杂。 | |

**User's choice:** 三段式解释
**Notes:** 后续在“缺失项粒度”里继续加码，要求展示到完整条件树粒度。

---

## 前端排布

| Option | Description | Selected |
|--------|-------------|----------|
| 现有三区+摘要 | 保留现有 Active Workflow / Planned Actions / Blocked Reason 三块，在旁边或下方补一个结果摘要区，最稳妥。 | ✓ |
| 统一总览区 | 把自治状态合成一个更大的总览区，信息集中，但改动更大。 | |
| 事件流优先 | 主要强化 recent events，不新增明显的摘要区。 | |

**User's choice:** 现有三区+摘要
**Notes:** 用户接受在现有布局上增量增强，而不是推翻当前 modal 结构。

---

## API 粒度

| Option | Description | Selected |
|--------|-------------|----------|
| 兼容增强 | 保留现有 API 形状，再新增明确的摘要/决策字段，前端可渐进接入，兼容最好。 | ✓ |
| 只放 kairos 内部 | 把新增信息都收敛到 kairos 内部嵌套对象，接口更整洁，但前端读取要改更多。 | |
| 更多顶层镜像 | 把更多字段镜像到顶层，前端读取最方便，但接口会变得更平。 | |

**User's choice:** 兼容增强
**Notes:** 明确不希望推翻现有 `kairos` payload + top-level mirrors 的消费方式。

---

## 摘要字段

| Option | Description | Selected |
|--------|-------------|----------|
| 四要素摘要 | 每条任务摘要固定展示：状态、result/error 摘要、artifact 是否可用、日志路径/提示。信息够用且稳定。 | |
| 超简摘要 | 只展示状态 + result/error 摘要，最简洁。 | |
| 扩展字段摘要 | 展示更多原始字段，比如时间、task_id、更多 artifact 明细。 | ✓ |

**User's choice:** 扩展字段摘要
**Notes:** 这是对“简洁结构化”初始选择的细化修正：仍然结构化，但字段要更丰富。

---

## 事件流分工

| Option | Description | Selected |
|--------|-------------|----------|
| 事件=时间线 | recent events 保持时间线；新增摘要区负责当前结果总览，不重复堆日志。 | ✓ |
| 事件主导 | recent events 同时承担时间线和主要结果展示，不强调独立摘要区。 | |
| 摘要主导 | 摘要区主导，recent events 只保留少量系统事件。 | |

**User's choice:** 事件=时间线
**Notes:** 明确 recent events 与摘要区分工，避免重复信息。

---

## 缺失项粒度

| Option | Description | Selected |
|--------|-------------|----------|
| 缺失清单 | 明确列出缺什么输入/产物/条件，但保持 1 层列表，不做深层技术细节。 | |
| 一句话 | 只保留一句 blocked reason。 | |
| 完整条件树 | 展开到每个 stage 条件与检测细节，最完整但也最重。 | ✓ |

**User's choice:** 完整条件树
**Notes:** 说明 Phase 2 的 blocked / waiting_input 不只是“可见”，而且要足够可诊断。

---

## 失败呈现

| Option | Description | Selected |
|--------|-------------|----------|
| 错误摘要+指引 | 默认展示 error_summary + 建议去哪里看日志/产物，不直接塞大段错误栈。 | ✓ |
| 原始错误优先 | 尽量直接展示更多原始错误内容，方便排查。 | |
| 仅状态 | 只显示 failed，不强调错误内容。 | |

**User's choice:** 错误摘要+指引
**Notes:** 用户不想退回纯状态，也不想把 UI/API 变成原始报错堆栈浏览器。

---

## Claude's Discretion

- 结构化摘要对象的精确字段名与 API 编码形式
- 摘要区具体布局与视觉层级
- 条件树的 JSON 结构与前端渲染细节
- 时间线与摘要区之间的去重规则

## Deferred Ideas

None.

# Kairos Boss Demo: Real Todo App Delivery Pipeline - Design

**Date:** 2026-04-06
**Status:** Proposed
**Scope:** 升级现有 todo boss demo，从 stub 级产物链提升为设计驱动的真实单页应用交付链

## 1. Goal

把现有 `todo_delivery_pipeline` 从“占位文件演示”升级为一条真正可展示交付价值的 workflow：Kairos 继续扮演 boss / delivery manager，Dex 继续扮演执行层，但最终交付物不再只是 stub，而是一个真正可用的单页 todo app。

这次升级后的目标是同时证明两件事：

1. **Kairos 能持续推进真实任务直到完成**
2. **被推进出来的产物确实具备接近交付验收级的业务能力**

最终 demo 仍然写入独立目录 `demo_delivery/todo_app/`，不把当前主仓库源码当作业务交付目标。

## 2. Non-Goals

本次设计明确不做以下事情：

- 不引入完整 supervisor / worker 重构
- 不把 codegen 做成完全自由、不可预测的开放生成系统
- 不要求生成 React / Vue / build pipeline 项目
- 不要求引入后端或数据库
- 不要求把 todo app 变成生产级工程模板
- 不要求把 Kairos 的 continuation 抽象成通用 workflow 平台

本次重点是：**在保持 live demo 稳定性的前提下，把 demo 交付物从 stub 升级成真实前端应用。**

## 3. Recommended Approach

在讨论的三个方向中，采用 **方案 B：受约束的设计驱动生成**。

### 为什么不用 A
方案 A 只升级 codegen 和 tests，虽然风险低，但仍会让 demo 更像“预制脚手架”，不足以体现“前置设计如何约束后续交付”。

### 为什么不用 C
方案 C 允许更开放的生成逻辑，展示感最强，但会显著降低 live demo 的稳定性和回归可重复性，不适合当前 milestone。

### 为什么选 B
方案 B 允许：
- requirements 真正定义验收目标
- design 真正约束实现与测试
- codegen 根据设计交付完整应用
- verification 做接近验收级检查
- Kairos 仍通过稳定接口做 continuation 决策

这能兼顾：
- 真实感
- 可回归性
- demo 稳定性
- 当前架构改动可控

## 4. Target Product

升级后的 todo app 为纯 HTML/CSS/JS 单页应用，至少具备以下能力：

- 添加 todo
- 标记完成 / 取消完成
- 删除 todo
- 筛选：All / Active / Completed
- 编辑 todo 文本
- 显示剩余计数
- 空状态提示
- `localStorage` 持久化
- 基础可访问性（可见 label、明确按钮文案、基本键盘友好）

该应用不要求引入构建流程，也不要求拆成多文件工程。目标是一个**可直接打开理解、可稳定生成、可验收验证**的真实 demo 交付物。

## 5. Workflow Shape

继续沿用现有 5 阶段 workflow，不改大结构：

1. `requirements`
2. `design`
3. `codegen`
4. `verification`
5. `delivery_report`

这样可以最大化复用现有：
- `todo_delivery_pipeline`
- continuation 规则
- runtime stage 展示
- host auto follow-up
- live HTTP regression 路径

升级点不在“阶段数”，而在“每个阶段产物的语义和验收门槛”。

## 6. Upgraded Artifact Contract

### 6.1 Requirements Stage

**Task:** `todo_requirements`

**Output:**
- `demo_delivery/todo_app/requirements.md`

**Required content:**
- 功能清单：add / toggle / delete / filter / edit / count / empty state / persistence
- 非功能约束：纯前端、无构建步骤、单页应用
- 验收标准：每个功能如何被判定为通过
- 关键交互边界：空输入、编辑保存、筛选切换、刷新持久化

这个文件不再只是标题占位，而是后续 design / verification 的输入契约。

### 6.2 Design Stage

**Task:** `todo_design`

**Outputs:**
- `demo_delivery/todo_app/design.md`
- `demo_delivery/todo_app/file_plan.json`

**Required content:**
- UI 结构：输入区、筛选区、列表区、空状态、计数区
- DOM 节点约定：关键元素 id/class/data-* 约定
- 数据模型：todo item 至少包含 id / text / completed
- 事件流：add / toggle / delete / edit / filter / persist / restore
- 本地持久化策略：`localStorage` key、写入时机、恢复流程
- 测试点映射：哪些功能在 verification 中必须被覆盖

`file_plan.json` 要显式列出：
- `index.html`
- `style.css`
- `app.js`
- 可选测试输出文件

### 6.3 Codegen Stage

**Task:** `todo_codegen`

**Outputs:**
- `demo_delivery/todo_app/index.html`
- `demo_delivery/todo_app/style.css`
- `demo_delivery/todo_app/app.js`

**Required behavior:**
- `index.html` 提供真实 UI 骨架，不允许只有 `<title>` 级 stub
- `style.css` 提供可辨认布局与状态样式
- `app.js` 提供：
  - 状态存储
  - 渲染逻辑
  - 事件绑定
  - 编辑逻辑
  - 筛选逻辑
  - 计数更新
  - 空状态切换
  - `localStorage` 读写

**Design constraint:**
codegen 可以更开放，但不能脱离 requirements / design 任意漂移。它的输出必须仍然可预测到足以回归。

### 6.4 Verification Stage

**Task:** `todo_tests`

**Required outputs:**
- `demo_delivery/todo_app/test_plan.md`
- `demo_delivery/todo_app/smoke_check.json`

**Optional outputs:**
- `demo_delivery/todo_app/manual_checklist.md`
- `demo_delivery/todo_app/smoke_check_details.md`

Verification 采用双层策略：

#### Layer 1 — Structure / Contract Checks
检查：
- 文件是否存在
- DOM 骨架是否存在
- `app.js` 是否覆盖关键功能钩子
- `style.css` 是否包含关键状态样式
- design 中承诺的关键能力是否在实现中出现

#### Layer 2 — Near-Acceptance Behavior Checks
实际检查：
- add item
- toggle item
- delete item
- filter active
- filter completed
- edit item
- counter correctness
- empty state correctness
- persistence after reload

这些结果要结构化写入 `smoke_check.json`，例如：

```json
{
  "ready": true,
  "checks": {
    "dom_ready": true,
    "add_item": true,
    "toggle_item": true,
    "delete_item": true,
    "filter_active": true,
    "filter_completed": true,
    "edit_item": true,
    "counter_correct": true,
    "empty_state_correct": true,
    "persistence_after_reload": true
  },
  "failures": []
}
```

如果有失败项：
- `ready` 必须是 `false`
- `failures` 必须列出失败检查名和原因

### 6.5 Delivery Report Stage

**Task:** `generate todo delivery report` / `todo_delivery_report`

**Output:**
- `demo_delivery/todo_app/delivery_report.md`

**Required content:**
- 交付目标摘要
- 已交付功能清单
- 验证覆盖项与结果
- 关键文件清单
- 最终 ready 结论
- 若未 ready，失败项或缺口

该报告不再只是 `Ready: True`，而是把 requirements / design / verification 的证据折叠成一份可读交付汇总。

## 7. Kairos Decision Model

Kairos 仍然不理解浏览器实现细节，它只依赖稳定的产物接口做决策。

### Continue 条件
只有当以下条件同时满足时，才允许自动推进 `generate todo delivery report`：

1. 前 4 阶段 required artifacts 全部存在
2. `smoke_check.json` 存在
3. `smoke_check.json.ready == true`
4. 没有关键 failure 项

### Blocked 条件
以下任一情况都必须阻止自动推进：

- required artifact 缺失
- `smoke_check.json` 不存在
- `smoke_check.json.ready == false`
- 验收失败项存在

### Blocked 表达
blocked 时需要更新：
- `blocked_reason`
- `condition_tree`
- `decision_explanation`

建议新的 blocked reason 语义包括：
- `missing required artifacts for todo delivery report`
- `verification checks failed for todo delivery report`

其中第二类比当前单纯“缺文件”更能表达交付质量判断。

## 8. Runtime / Host Changes

### 8.1 Runtime

`src/adk_agent/kairos/runtime.py` 继续负责：
- stage seed
- Dex task completion tracking
- summary 聚合
- workflow completion

必要升级：
- verification 完成后，除检查 artifact 外，还要让 continuation 能读到 `smoke_check.json` readiness
- task summary 应能反映 verification 成功/失败摘要
- blocked 情况下 condition tree / explanation 需能反映“失败项”而不只是“缺文件”

### 8.2 Continuation

`src/adk_agent/kairos/continuation.py` 继续负责从 workflow 状态推导是否创建 follow-up。

必要升级：
- todo workflow 的推进条件从“文件存在”升级为“文件存在 + verification ready”
- 加入 verification failure 语义
- 继续保留 follow-up 去重逻辑

### 8.3 Host Follow-up

`src/adk_agent/main_web_start_steering.py` 中 `create_kairos_follow_up_task()` 保持宿主真实执行模式。

必要升级：
- `generate todo delivery report` 不只写简单 Ready 行
- 需要读取：
  - `requirements.md`
  - `design.md`
  - `smoke_check.json`
  - 必要时 `test_plan.md`
- 生成更完整的 `delivery_report.md`

## 9. Live Demo Behavior

升级后的 live demo 应表现为：

1. requirements / design / codegen / verification 四个任务被注册并真实执行
2. Dex 在 `demo_delivery/todo_app/` 中写出真实应用和验证结果
3. Kairos 在 workflow 中展示阶段推进
4. 只有当 verification 通过时，Kairos 才自动创建 `generate todo delivery report`
5. 最终 `delivery_report.md` 反映真实交付状态
6. workflow 收敛并回到 idle

这使得前端看到的 completed workflow 不再只是“文件链结束”，而是“交付验收通过后结束”。

## 10. Failure and Blocked Paths

### Failure Path
示例：行为 smoke 中 `edit_item` 失败。

预期：
- `smoke_check.json.ready = false`
- `failures` 列出 `edit_item`
- Kairos 不推进 `delivery_report`
- `blocked_reason = verification checks failed for todo delivery report`

### Blocked Path
示例：`app.js` 缺失，或 design 声明的关键节点未被实现。

预期：
- Kairos 不推进 `delivery_report`
- `condition_tree` 列出缺失 artifact 或失败检查
- `decision_explanation.why_stopped` 有明确值

这两条路径都要保留，以证明 Kairos 不是只会走 happy path。

## 11. Testing Strategy

### Unit / Runtime Layer
继续扩展：
- `tests/kairos/test_continuation.py`
- `tests/kairos/test_runtime.py`
- `tests/kairos/test_api.py`

重点覆盖：
- verification ready 才推进
- verification failed 不推进
- delivery report 阶段 summary / status 正确

### Integration Layer
继续扩展：
- `tests/dex/test_tools.py`
- `tests/test_dex_session_regression.py`

重点覆盖：
- 宿主 follow-up 真正生成 richer report
- real Dex tasks 写出完整 todo app 产物

### Live HTTP Layer
继续扩展：
- `tests/kairos/live_http_kairos_demo_outputs_regression.py`
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

重点覆盖：
- 完整 app 产物链
- verification 结果
- auto-created delivery report
- final workflow convergence

## 12. Implementation Order

推荐顺序：

1. 升级 requirements / design / codegen / tests 命令产物定义
2. 先写失败测试，锁定“真实 app + richer verification”预期
3. 升级 live helper 生成的 todo artifacts
4. 升级 continuation 对 verification-ready 的判断
5. 升级 host delivery report 生成内容
6. 扩展 live HTTP 回归
7. 最后补 blocked / failure 路径覆盖

这样做可以避免先大改 Kairos 判断逻辑，再回头补产物定义，导致调试困难。

## 13. Risks and Controls

### Risk 1 — Demo 变脆
更高保真的前端行为验证可能让 live demo 更脆。

**Control:** 双层验证；保留结构检查与行为检查分层，不把全部稳定性押在浏览器层。

### Risk 2 — Codegen 过于开放，难以回归

**Control:** 仍然让 requirements / design 明确约束输出范围，不允许随意扩张实现风格。

### Risk 3 — Kairos 逻辑被迫理解太多业务细节

**Control:** Kairos 只读取稳定的 artifact / verification contract，不读取前端细节实现。

## 14. Success Criteria

升级完成后，以下条件必须成立：

- `demo_delivery/todo_app/` 中生成真实可用的单页 todo app
- 应用支持 add / toggle / delete / filter / edit / count / empty / persistence
- verification 至少覆盖页面级主路径与刷新持久化
- Kairos 仅在 verification 通过时自动推进 `generate todo delivery report`
- delivery report 能反映真实交付结果，而不是简单占位摘要
- live HTTP regression 能稳定通过

## 15. Recommendation Summary

采用 **设计驱动、受约束的真实应用升级**：
- 保留现有 todo boss demo 架构
- 升级 requirements / design / codegen / verification 的语义密度
- 让 Kairos 判断“交付是否 ready”，而不只是“文件是否存在”
- 继续保持 demo 稳定、可测试、可 live 展示

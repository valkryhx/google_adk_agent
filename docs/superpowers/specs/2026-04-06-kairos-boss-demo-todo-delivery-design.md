# Kairos Boss Demo: Todo App Delivery Pipeline - Design

**Date:** 2026-04-06
**Status:** Proposed
**Scope:** 演示设计（不改当前项目源码）

## 1. Goal

设计一条适合前端演示的真实 Dex 多步骤开发任务链，让 **Kairos 以“boss / 项目经理”身份** 监控任务执行、判断阶段收敛、自动推进下一步，并在缺失产物或失败时停住并解释原因。

演示目标不是证明 Kairos 能写出最复杂的应用，而是证明它能：

- 监控一组真实开发任务
- 围绕目标推进 workflow，而不是只看单个任务状态
- 根据产物决定是否继续
- 自动生成最终交付汇总
- 在 UI 上把“为什么继续 / 为什么停住 / 还缺什么”展示给用户

## 2. Non-Goals

这个演示**不**做以下事情：

- 不修改当前 `google_adk_agent` 项目本身的源码作为业务目标
- 不要求真正启动 todo 应用并跑浏览器交互
- 不要求让 Kairos 自由规划所有后续步骤
- 不扩展到多 workflow template 通用化平台设计
- 不引入完整 supervisor / worker 架构

## 3. Demo Concept

Kairos 不直接“写 app”，而是扮演一个 **delivery boss**：

- Dex = 执行层 / 工人
- Kairos = 监控、判断阶段完成、推进下一步、阻塞时解释、最后出交付汇总

演示对象是一个**独立目录下的简单 todo app 代码产物链**，例如：

- `demo_delivery/todo_app/`

所有产物都写到这个目录下，与当前仓库主代码隔离。

## 4. Delivery Workflow

### Phase 1 — Requirements
Dex 任务：`todo_requirements`

输出：
- `demo_delivery/todo_app/requirements.md`

内容：
- todo app 的最小需求
- 支持添加、完成、删除、过滤
- 页面结构
- 数据模型草案

### Phase 2 — Design
Dex 任务：`todo_design`

输出：
- `demo_delivery/todo_app/design.md`
- `demo_delivery/todo_app/file_plan.json`

内容：
- 文件结构
- 组件或模块划分
- 数据流
- 关键交互说明

### Phase 3 — Code Generation
Dex 任务：`todo_codegen`

输出真实代码文件：
- `demo_delivery/todo_app/index.html`
- `demo_delivery/todo_app/style.css`
- `demo_delivery/todo_app/app.js`

要求：
- 是可读、成体系的真实代码文件
- 不只是占位文本
- 但不要求真的启动运行

### Phase 4 — Verification Artifacts
Dex 任务：`todo_tests`

输出：
- `demo_delivery/todo_app/test_plan.md`
- `demo_delivery/todo_app/smoke_check.json`

可选扩展：
- `demo_delivery/todo_app/tests/smoke.spec.js`

### Phase 5 — Final Delivery Report
**由 Kairos 自动续推，不人工注册**

Dex 任务：`todo_delivery_report`

输出：
- `demo_delivery/todo_app/delivery_report.md`

内容：
- 当前交付目标
- 已产出的文件
- 哪些阶段完成
- 是否 ready
- 如果不 ready，还缺什么

## 5. Why This Demo Works

这条链最能体现 Kairos 的价值，因为它不只是“任务完成通知器”，而是：

### 5.1 Goal-aware
Kairos 不是只看某个 task 是否 completed，而是看：
- requirements 是否齐
- design 是否齐
- code files 是否齐
- verification artifacts 是否齐

### 5.2 Continuation-aware
Kairos 能在某一阶段产物齐全后自动推进下一阶段，尤其是自动触发 `todo_delivery_report`。

### 5.3 Artifact-aware
Kairos 是否继续，不取决于“任务 finished”本身，而取决于目标产物是否真实存在。

### 5.4 Policy-aware
Kairos 需要在以下情况做不同决策：
- 所有前置产物齐全 → 自动继续
- 某一步失败 → 记录失败摘要，停止推进
- 某些必要文件缺失 → blocked / waiting_input，并告诉用户缺什么

### 5.5 User-visible
前端上能直接看到：
- Active Workflow
- Planned Actions
- Blocked Reason
- Result Summary
- 最近事件

这让“boss 正在盯交付”这件事变得可见。

## 6. Required Workflow State Model

为了支持这条 demo，Kairos 需要围绕该 workflow 维护：

- `active_workflow`
  - 当前 workflow id
  - goal
  - current stage
  - stage list
- `planned_actions`
  - 下一步准备创建的任务
- `blocked_reason`
  - 为什么停住
- `condition_tree`
  - 哪些 required artifacts 已满足，哪些缺失
- `task_summaries`
  - 每一步任务的结构化摘要
- `decision_explanation`
  - why_continued / why_stopped / missing_requirements

## 7. Success Path

成功演示时应看到：

1. 手工注册 4 个开发任务：
   - requirements
   - design
   - codegen
   - tests
2. Dex 真实执行并写出产物文件
3. Kairos 在前端显示这些任务的摘要和阶段推进
4. 当前置产物全部齐全后，Kairos 自动创建 `todo_delivery_report`
5. 最终生成 `delivery_report.md`
6. workflow 收敛，Kairos 回到 idle

## 8. Failure Path

为了展示 boss 的价值，演示必须支持至少一个失败路径：

例如：
- `todo_codegen` 任务失败

预期表现：
- `task_summaries` 中出现 error summary
- `recent_events` 记录失败事件
- Kairos 不推进 `todo_delivery_report`
- workflow 停住

## 9. Blocked Path

为了展示 policy/condition-tree 的价值，演示必须支持至少一个 blocked 路径：

例如：
- `todo_codegen` 声称完成，但缺少 `app.js`

预期表现：
- Kairos 不推进最终 report
- `blocked_reason` 明确说明缺少交付文件
- `condition_tree` 中列出：
  - satisfied: 已有文件
  - missing: 缺失文件（例如 `app.js`）
- `decision_explanation.why_stopped` 有值

## 10. Recommended Implementation Style

推荐使用**确定性脚本产物生成**，不要把这个演示做成依赖自由 LLM 输出的开放式工作流。

也就是说：
- Dex 任务可以是 Python 脚本或 shell 命令
- 它们真实写文件
- 但输出结构、文件名、目录布局要稳定
- 这样 Kairos 的续推与 blocked 判断才可测试、可重复演示

## 11. Recommended First Version

第一版建议采用：

- 纯 HTML/CSS/JS todo app
- 只生成代码产物，不要求启动运行
- 4 个手工注册的 Dex 开发任务
- 1 个 Kairos 自动续推的 delivery report 任务

这是最小但真实、最适合演示的版本。

## 12. Trade-offs Considered

### Option A — 只演示单个长任务
优点：简单
缺点：无法体现 Kairos 的 workflow / boss 价值

### Option B — 生成代码产物链（本设计）
优点：真实、稳定、可测试、不污染主项目
缺点：没有真正运行 todo app

### Option C — 真实启动并运行 todo app
优点：最完整
缺点：演示复杂度、失败点、依赖管理显著上升

**Recommendation:** 先做 Option B。

## 13. Testing Strategy for the Demo

需要验证三条路径：

### Success
- 4 个前置开发任务成功
- 产物文件齐全
- Kairos 自动创建 `todo_delivery_report`
- 最终生成 `delivery_report.md`

### Failure
- 某个 Dex 任务真实失败
- Kairos 显示失败摘要，不继续推进

### Blocked
- 某个关键文件缺失
- Kairos 进入 blocked / waiting_input
- `condition_tree` 精确列出缺失文件

## 14. Open Decisions Already Resolved

以下设计决策已经确定：

- 演示是 **开发交付链**，不是测试链或 debug 链
- 任务对象是 **独立 todo app**，不修改当前项目本身
- 第一版采用 **只生成代码产物**，不要求真正运行
- Kairos 的角色是 **boss / delivery manager**，不是直接编码者

## 15. Next Step

下一步不是直接实现，而是把这个设计转成实现计划：

- workflow 结构怎么编码
- 各 Dex 任务具体写哪些文件
- Kairos 如何判断前置产物齐全
- 如何在前端展示该 workflow
- 如何构造 success / failure / blocked 三条演示路径

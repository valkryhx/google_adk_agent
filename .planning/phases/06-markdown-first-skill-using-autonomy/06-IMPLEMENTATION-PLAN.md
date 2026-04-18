# Phase 06 Implementation Plan: LLM-First Autonomous Task Intelligence

## Goal

把 Kairos 从“document-backed continuation + 部分 LLM 参与”的过渡形态，推进到“以 LLM 为核心智能、以 markdown 工件为主要工作记忆、以 skills/tools 为执行能力层、能长期自主规划/执行/纠错”的最小可用自治体。

这份 Phase 6 计划明确承认并贯彻我们在最近讨论中形成的方向：
- Kairos 的本质不是规则编排器，而是要逐步成为可替代人推进复杂工作的智能实体
- 不应让严格 JSON schema 反过来束缚 Kairos 的智能表达；markdown-first 才是更自然的工作记忆形态
- 但也不能让 LLM 直接裸拿执行权限；规则与代码层仍要承担安全边界、状态迁移与审计责任
- 现有 `main_web_start_steering.py` 是通用会话宿主，Kairos 的价值在于成为长期自治运行时，而不是重复造一个普通 agent

---

## Problem Statement

当前仓库已经具备：
- 会话级主 Agent 宿主、动态 skill 加载、文件编辑、bash、Dex 异步任务执行
- document-backed requirement intake / spawned work persistence / continuation visibility
- requirement understanding / execution plan / action payload / verification / replan 的第一波 LLM-first 状态模型与代码接线
- document patch / design-codegen brief 的初步 LLM payload 生成与 dispatcher 消费

但仍有关键缺口：
- live 环境下 LLM planner 仍受结构化输出稳定性影响，导致经常 fallback 到规则链
- Kairos 还没有真正以 markdown 工件作为每一阶段的主要智能产物与输入
- Kairos 还不能像主 Agent 那样自主 skill_load / 调用现有 skills 来完成 code search / 文件编辑 / Dex / 验证
- execution payload 虽已开始出现，但离 requirements/design/codegen/verification 全阶段的真实 markdown-first 内容生成仍有距离
- verification / replan 还未形成真正的“失败后自动修正文档/计划/任务并继续推进”的闭环

因此，Phase 6 的目标不是继续堆更多规则，而是建立一个更正确的分层：
- `main_web_start_steering.py`：通用宿主层
- Kairos：长期自治运行时
- markdown work docs：工作记忆层
- skills/tools：执行能力层

---

## Core Design Direction

### 1. Kairos 与主宿主的职责边界

#### `main_web_start_steering.py`
负责：
- LLM 对话与 session runtime
- streaming / interruption / session persistence
- `skill_load` 与 tool runtime
- 通用 agent 执行骨架

#### Kairos
负责：
- 维护长期 work item / markdown 工件
- 自主 wake / schedule / resume / retry
- 围绕 unfinished work 做持续推进
- 跨轮次编排 skills/tools
- 维护 planning / attempt / verification / replan / history

#### markdown 工件
负责：
- 保存 Goal / Current Step / Blockers / Verification / Replan Notes / Spawned Work
- 作为 Kairos 每次苏醒后重新理解工作的主要输入
- 作为人类与 Kairos 共享的外显工作记忆

#### skills / tools
负责：
- file_editor / codebase_search / dex / search_exp / playwright / agent_team 等执行能力
- Kairos 应自主决定何时加载、何时调用，而不是把执行硬编码到 runtime 里

---

## Phase 6 Scope

Phase 6 聚焦一个最小但正确的自治闭环，而不是一步做成完全通用自治体。

### In Scope
- markdown-first requirement/design/codegen/verification 工件主链路
- Kairos 自主 skill_load / 调用现有 skills 的桥接层
- LLM planner 的降级策略与 live 稳定性修复
- LLM 驱动的 verification / replan / self-correction 闭环
- API / history / state 对自治认知链的暴露

### Out of Scope
- 完整通用 supervisor/worker 重构
- 任意 shell/raw code 直接由 LLM 生成并执行
- 无边界的自由自治（必须保留 allowlist / skill boundary / Dex / document protocol）
- 一步到位的全项目类型泛化

---

## Phase 6 Plan Breakdown

### 06A: Markdown-First Work Intelligence

**Objective**: 让 Kairos 各阶段的主要智能产物从 rigid JSON-first 过渡到 markdown-first，文档成为主要工作记忆与执行载体。

#### Required changes
- requirement/design/codegen/verification 都应形成清晰 markdown 工件
- 文档 patch 不再只是 append helper，而是支持 section-level read/update contract
- LLM planner/verifier 允许输出 markdown 为主、结构化字段为辅的结果
- 降低对严格 `response_format=json_object` 的依赖，优先保证 live 稳定性

#### Target files
- `src/adk_agent/kairos/document_protocol.py`
- `src/adk_agent/kairos/document_reader.py`
- `src/adk_agent/kairos/llm_planner.py`
- `src/adk_agent/kairos/models.py`
- `tests/kairos/test_document_protocol.py`
- `tests/kairos/test_models.py`

#### Acceptance criteria
- requirement understanding 结果能稳定落为可读 markdown
- design/codegen brief 能稳定落为 markdown 文件而不只是内存 payload
- live 环境下 planner 不因 structured JSON 失败而整体失效
- 文档能作为 Kairos 下一轮理解的稳定输入

---

### 06B: Skill-Using Autonomous Execution Bridge

**Objective**: 让 Kairos 不再局限于 runtime 内置执行分支，而能像主 Agent 一样，自主决定加载和调用现有 skills。

#### Required changes
- 为 Kairos 增加受控的 skill bridge：
  - 查询可用 skills manifest
  - 调用 `skill_load`
  - 在受控边界下调用已加载工具
- 优先接入的技能：
  - `file_editor`
  - `codebase_search`
  - `dex`
  - `search_exp`
  - `playwright` / `playwright-cli`
- execution plan / action payload 应能表达“下一步需要哪类 skill”
- runtime 根据 allowlist 决定是否允许加载与调用该 skill

#### Target files
- `src/adk_agent/main_web_start_steering.py`
- `src/adk_agent/kairos/runtime.py`
- `src/adk_agent/kairos/llm_planner.py`
- `src/adk_agent/kairos/models.py`
- `skills/dex/SKILL.md`
- `skills/codebase_search/SKILL.md`
- `skills/file_editor/SKILL.md`
- `tests/kairos/test_runtime.py`
- `tests/test_dex_session_regression.py`

#### Acceptance criteria
- Kairos 能在 live 任务中明确生成“使用哪个 skill/为什么”的执行意图
- 至少一条真实链路能从 markdown work item 自动推进到 skill 驱动执行
- 不能让 Kairos 直接跳过 skill boundary 执行任意命令

---

### 06C: Verification, Replan, and Self-Correction Loop

**Objective**: 让 Kairos 从“会继续做”升级为“会根据执行结果修正做法”。

#### Required changes
- 每次执行后的 artifact / task result / brief / log 都要进入 verifier
- verifier 结果要回写：
  - 是否推进了目标
  - 剩余 gaps
  - 是否需要 ask_user
  - 是否需要 replan
- replan 结果要能驱动：
  - 新的 markdown patch
  - 新的 design/codegen brief
  - 新的 skill execution step
- 保留 retry budget / fail-safe / blocked escalation

#### Target files
- `src/adk_agent/kairos/runtime.py`
- `src/adk_agent/kairos/llm_verifier.py`
- `src/adk_agent/kairos/llm_planner.py`
- `src/adk_agent/kairos/models.py`
- `src/adk_agent/kairos/activity_log.py`
- `src/adk_agent/kairos/api.py`
- `tests/kairos/test_runtime.py`
- `tests/kairos/test_api.py`

#### Acceptance criteria
- 执行失败后，不只是记录失败，而是生成新的 replan result
- replan result 能驱动下一步真实动作而不只是出现在状态里
- history / API 中可见完整的 reasoning lifecycle：understanding -> plan -> action -> verification -> replan

---

## Suggested Implementation Order

1. **Stabilize planner output path**
   - 完成 `llm_planner` 的 markdown-first / tolerant parsing / timeout fallback
2. **Promote work docs to first-class artifacts**
   - 把 design/codegen/verifier brief 真正写成 markdown
3. **Introduce skill bridge for Kairos runtime**
   - 让 Kairos 能自主利用 `file_editor` / `codebase_search` / `dex`
4. **Close verification/replan loop**
   - 让 verifier/replan 真正驱动下一轮动作
5. **Run live autonomy validation**
   - 用真实 Flask + SQLite + HTML 任务验证从 requirement -> design -> codegen -> verification 的至少两步自治推进

---

## Guardrails

- 不删除规则层，但要把规则层降级为：
  - safety boundary
  - allowlist
  - retry budget
  - persistence / auditing
- 不让 LLM 直接执行任意 shell/raw code
- 不把 Kairos 做成另一个普通对话 agent
- 不把 markdown 只当展示层；它必须是真正的工作记忆层
- 不忽视现有 `skills/` 生态；Kairos 必须逐步会用它们

---

## Success Criteria for Phase 6

Phase 6 完成后，必须同时满足：

1. Kairos 的 requirement / design / codegen / verification 至少有两类阶段以 markdown 工件为主要输出
2. Kairos 在 live 环境里能稳定调用 LLM planner，不因 strict JSON 失败而整体回退到规则链
3. Kairos 至少能在一个真实任务中自主加载/调用现有 skills 完成下一步推进
4. verification / replan 不只是状态展示，而能驱动真实后续动作
5. 从用户视角看，Kairos 已不再只是“会继续扫 work.md”，而是“围绕 work.md 持续理解、决定、执行、修正”的长期自治体

---

## One-sentence summary

Phase 6 的本质，不是继续增强 continuation engine，而是把 Kairos 真正推进成：**以 markdown 工件为工作记忆、以 LLM 为核心智能、以现有 skills 为执行能力层、以 runtime 为长期自治调度层的最小自治操作系统。**

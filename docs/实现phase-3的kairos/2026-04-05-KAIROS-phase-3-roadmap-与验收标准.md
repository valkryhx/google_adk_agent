# KAIROS Phase 3 Roadmap 与验收标准

> 日期：2026-04-05
> 目标：把当前 phase-3 的方向进一步整理成 roadmap 视角，明确 milestone、优先级、非目标、验收标准、风险和验证命令。

---

## 1. 总体路线

我建议把 phase-3 拆成 3 个明确 milestone，而不是一次性做成一个大杂烩版本。

### 为什么要拆
因为当前仓库已经有很好的 phase-2 地基：
- runtime / scheduler / handoff / attach / tracked tasks
- 不污染 history 的 state-only persistence
- front-end status 面板
- live HTTP regression

所以 phase-3 不是从零搭系统，而是要做一次“自治跃迁”。

这种跃迁最怕两件事：
1. 过早把逻辑全塞进一个 PR，导致不可解释
2. 直接把自治全交给 LLM，导致不稳定、难回归

因此更稳妥的路线是：

- **3A：先做 deterministic autonomous continuation**
- **3B：再做 artifact-aware proactive reporting**
- **3C：最后做 workflow memory 与 policy hardening**

---

## 2. Milestone 3A：Autonomous Continuation MVP

## 2.1 目标

让 KAIROS 第一次跨过“观察者”与“主动续推者”的分界线。

一句话目标：

> **当 phase-1 输入任务全部完成后，KAIROS 能自动发现 workflow 已收敛，并自动创建 report Dex task，而不再需要人手动注册下一阶段。**

---

## 2.2 Scope

### 包含
- workflow-aware state（最小必要字段）
- rule-based Continuation Engine
- internal continuation trigger
- 自动 follow-up Dex task 创建
- follow-up handoff 自动注册
- runtime status 暴露 workflow / planned actions / blocked reason
- 对应 runtime / integration / live-http 测试

### 不包含
- 完整 supervisor
- 多 workflow template 批量支持
- push / channel / webhook 扩展
- LLM 自由规划下一步
- nightly memory distill

---

## 2.3 建议改动范围

### 新增
- `src/adk_agent/kairos/continuation.py`
- `src/adk_agent/kairos/workflows.py`
- `tests/kairos/test_continuation.py`

### 修改
- `src/adk_agent/kairos/models.py`
- `src/adk_agent/kairos/runtime.py`
- `src/adk_agent/main_web_start_steering.py`
- `src/adk_agent/kairos/api.py`
- `tests/kairos/test_models.py`
- `tests/kairos/test_runtime.py`
- `tests/dex/test_tools.py`
- `tests/kairos/live_http_kairos_demo_outputs_regression.py`
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

---

## 2.4 验收标准

满足以下全部条件才算 3A 完成：

1. `KairosState` 能表达：
   - `active_workflow`
   - `planned_actions`
   - `blocked_reason`
2. 当 `sales/traffic/quality` 三个任务完成且产物齐全时：
   - KAIROS 自动生成 continuation decision
   - 自动创建 report Dex task
   - 自动注册 handoff
3. 不再需要人工注册 report task
4. `recent_events` 中能看到类似：
   - `phase-1 converged, auto-created report task`
5. `live_http_kairos_demo_outputs_regression.py` 最终仍能产出：
   - `demo_outputs/report.json`
6. 不会重复创建多个 report task
7. 最终 `mode` 收敛回 `idle`

---

## 2.5 主要风险

### 风险 A：重复续推
phase-1 收敛条件可能在多次 tick 中被重复识别，导致反复创建 report task。

### 风险 B：runtime 逻辑过载
如果 continuation logic 直接硬塞进 `runtime.py`，会让后续维护困难。

### 风险 C：live 验证不稳定
如果自动 follow-up 创建绕过宿主层安全边界，真实 HTTP 路径可能变得不稳定。

---

## 2.6 建议验证命令

### Runtime
```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/kairos/test_models.py \
  tests/kairos/test_continuation.py \
  tests/kairos/test_runtime.py -q
```

### Integration
```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/dex/test_tools.py \
  tests/kairos/test_dex_bridge.py -q
```

### Live HTTP
```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q
```

---

## 3. Milestone 3B：Artifact-Aware Proactive Reporting

## 3.1 目标

让 KAIROS 不再只是说“task completed”，而是能告诉用户：
- 完成了什么
- 输出是否可用
- 下一步是什么

一句话目标：

> **让 KAIROS 从 state-aware 变成 artifact-aware。**

---

## 3.2 Scope

### 包含
- 从 Dex snapshot / artifacts / log tail 生成更强 summary
- richer proactive brief
- API/UI 展示 workflow / planned actions / blocked reason
- waiting_input / blocked 的用户可见化

### 不包含
- push notification
- channels
- webhook-driven external workflow
- 真正 LLM 自主长规划

---

## 3.3 建议改动范围

### 重点修改
- `src/adk_agent/kairos/runtime.py`
- `src/adk_agent/kairos/dex_bridge.py`（如果需要更多 artifact info）
- `src/adk_agent/main_web_start_steering.py`
- `src/adk_agent/kairos/api.py`
- `src/adk_agent/static/script.js`
- `tests/kairos/test_frontend_script_kairos_ui.py`
- `tests/kairos/test_runtime.py`
- `tests/dex/test_tools.py`

---

## 3.4 验收标准

满足以下全部条件才算 3B 完成：

1. KAIROS 在任务完成时输出不再只是 `completed/failed`，而是包含：
   - `result_summary` / `error_summary`
   - 必要时的 artifact 判断
2. 前端面板能看到：
   - `Current Workflow`
   - `Planned Actions`
   - `Blocked Reason`
3. 当缺产物或缺输入时，KAIROS 能明确进入：
   - `WAITING_INPUT` 或 blocked 状态
4. `recent_events` 对人类已经可读，不需要再去 `.dex/tasks/*.json` 手工翻

---

## 3.5 主要风险

### 风险 A：摘要质量看起来更强，但稳定性不足
如果直接依赖 LLM 自由生成总结，测试很难锁住。

### 风险 B：前端调试能力跟不上自治增强
如果新增状态很多但 UI 不展示，系统会变得更黑盒。

---

## 3.6 建议验证命令

### Runtime + Integration
```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/kairos/test_runtime.py \
  tests/dex/test_tools.py \
  tests/kairos/test_dex_bridge.py -q
```

### Frontend
```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/kairos/test_frontend_script_kairos_ui.py -q
```

### Live HTTP
```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q
```

---

## 4. Milestone 3C：Workflow Memory 与 Policy Hardening

## 4.1 目标

让 KAIROS 更像长期运行 worker，而不是“每次 tick 都像第一次看到世界”。

一句话目标：

> **让 KAIROS 具备去重、记忆、限流、阻塞语义和更稳的自治策略。**

---

## 4.2 Scope

### 包含
- continuation history
- follow-up fingerprint 去重
- cooldown / max auto steps / per-workflow guardrail
- blocked / waiting_input 语义固化
- policy API
- 可选 workflow template 扩展

### 不包含
- 完整 daemon supervisor
- remote bridge protocol 高保真复现
- nightly dream / distill

---

## 4.3 建议改动范围

### 重点修改
- `src/adk_agent/kairos/models.py`
- `src/adk_agent/kairos/continuation.py`
- `src/adk_agent/kairos/runtime.py`
- `src/adk_agent/kairos/api.py`
- `tests/kairos/test_continuation.py`
- `tests/kairos/test_runtime.py`
- `tests/kairos/live_http_kairos_demo_outputs_regression.py`

---

## 4.4 验收标准

满足以下全部条件才算 3C 完成：

1. 同一 workflow follow-up 不会被重复创建
2. 同一 tick 内自动推进步数受限
3. 缺失输入时系统进入 blocked/waiting_input，而不是空转 brief
4. policy 可通过 API 读取/修改
5. regression 测试能覆盖重复续推、防失控和 blocked 语义

---

## 4.5 主要风险

### 风险 A：规则越来越多，最终又演化成大泥球
需要保持：
- continuation rules
- runtime orchestration
- workflow templates

三者职责分离。

### 风险 B：把“长期记忆”做得过重
3C 只需要 workflow memory / continuation history，不要过早上完整 dream/distill 体系。

---

## 4.6 建议验证命令

```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/kairos/test_continuation.py \
  tests/kairos/test_runtime.py \
  tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q
```

---

## 5. 推荐优先级

## P0：立刻做（3A）
- `continuation.py`
- `workflows.py`
- state 扩展
- runtime 接 continuation
- auto-create report task
- live-http regression 升级

## P1：紧接着做（3B）
- richer summary
- workflow / planned action / blocked reason API + UI
- artifact-aware brief

## P2：稳定化（3C）
- continuation history
- dedupe / cooldown / max auto steps
- policy hardening

---

## 6. 非目标（整个 phase-3 都暂不做）

下面这些我建议明确写为 non-goals，避免 scope 膨胀：

1. 完整 supervisor / worker 多进程体系
2. remote attach 高保真 bridge protocol
3. GitHub webhook workflow 自动接入
4. push/file-send/channels
5. nightly dream / memory distill
6. 让 LLM 自由决定一切下一步

这些都重要，但不属于当前“从观察走向自动续推”的最短路径。

---

## 7. 最终建议

如果只保留一个最关键的 roadmap 判定标准，我建议用这句：

> **phase-3 是否成功，不看它加了多少字段，而看 live HTTP demo 里 report task 是否已经不需要人手工注册，而是由 KAIROS 自己发现并推进。**

这就是当前最小、最真实、最可验证的“跳出 REPL 主导模式”的信号。

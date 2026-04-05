# KAIROS Phase 3 下一步行动清单

> 日期：2026-04-05
> 用途：把已有 phase-3 文档进一步压缩成一份“可以立刻开工”的 checklist。

---

## 1. 最推荐的切入点

如果现在就开始做 phase-3，我建议只盯住一个最小目标：

> **让 KAIROS 在 phase-1 输入任务全部完成后，自动创建并接管 report Dex task。**

这是当前最小、最真实、最能证明“已经开始跳出 REPL 主导模式”的能力跃迁。

---

## 2. 第一轮开发只做这 5 件事

## 2.1 扩状态模型

先改：
- `src/adk_agent/kairos/models.py`
- `src/adk_agent/kairos/__init__.py`
- `tests/kairos/test_models.py`

目标：新增最小必要状态：
- `active_workflow`
- `planned_actions`
- `blocked_reason`
- `policy`

先不要把模型做太大，只支持当前 demo workflow 即可。

---

## 2.2 新增 Continuation Engine

新增：
- `src/adk_agent/kairos/continuation.py`
- `src/adk_agent/kairos/workflows.py`
- `tests/kairos/test_continuation.py`

第一版只做规则引擎，不做自由 LLM 规划。

最小规则只需要覆盖：
- `sales/traffic/quality` 全完成
- 三个 artifact 都存在
- 尚未存在 report follow-up
- => 生成 `create_report_task` decision

---

## 2.3 把 continuation 接到 runtime

改：
- `src/adk_agent/kairos/runtime.py`
- `tests/kairos/test_runtime.py`

关键落点：
- `_poll_dex()` 后追加 continuation evaluation
- 支持 internal continuation trigger
- 支持 follow-up 去重
- `get_status()` 暴露 workflow / planned_actions / blocked_reason

---

## 2.4 由宿主提供安全的 follow-up 执行入口

改：
- `src/adk_agent/main_web_start_steering.py`
- 视情况小改 `src/adk_agent/kairos/api.py`

目标：
- 不让 runtime 直接散乱调用 Dex
- 由 `SteeringSession` 提供受控 callback
- 自动创建 Dex task 后自动 register handoff

---

## 2.5 升级 live regression

改：
- `tests/kairos/live_http_kairos_demo_outputs_regression.py`
- `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

目标：
- phase-1 tasks 仍可由脚本创建并注册
- **report task 不再由脚本手工注册**
- 等待 KAIROS 自动创建 report
- 最终验证 `report.json` 正常生成

---

## 3. 第一批必须写的测试

## 3.1 模型层
- `test_state_round_trip_preserves_workflow_and_planned_actions`
- `test_load_legacy_state_fills_phase3_defaults`

## 3.2 continuation 层
- `test_all_inputs_ready_returns_create_report_decision`
- `test_missing_artifact_returns_blocked_decision`
- `test_duplicate_follow_up_is_suppressed_by_fingerprint`

## 3.3 runtime 层
- `test_completed_inputs_enqueue_internal_continuation_trigger`
- `test_runtime_auto_creates_report_follow_up_when_all_inputs_ready`
- `test_runtime_does_not_duplicate_follow_up_task_creation`

## 3.4 live-http 层
- `test_live_http_kairos_auto_progresses_from_inputs_to_report`

---

## 4. 第一批验证命令

### 4.1 改模型和 continuation 规则时
```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/kairos/test_models.py \
  tests/kairos/test_continuation.py \
  tests/kairos/test_runtime.py -q
```

### 4.2 改真实 Dex follow-up 创建时
```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/dex/test_tools.py \
  tests/kairos/test_dex_bridge.py -q
```

### 4.3 改宿主接线与自动续推后
```bash
PYTHONPATH="D:/git_repos/google_adk_agent" PYTHONIOENCODING=utf-8 pytest \
  tests/kairos/test_live_http_kairos_demo_outputs_regression.py -q
```

---

## 5. 这轮明确不要做的事

为了避免 scope 膨胀，第一轮先不要做：

- 完整 supervisor
- webhook / GitHub 事件自动工作流
- push notification
- nightly memory distill
- 多 workflow template 并行支持
- LLM 自由决定所有 follow-up

先把最关键的一步做成：

> **KAIROS 能自己把 staged workflow 从 phase-1 推到 report。**

---

## 6. 完成判定

只有当下面这句话变成事实，phase-3 第一轮才算真的完成：

> **在 live HTTP demo 里，人类不再手工注册 report task，而是 KAIROS 自己发现该继续，并把 report 阶段推进完成。**

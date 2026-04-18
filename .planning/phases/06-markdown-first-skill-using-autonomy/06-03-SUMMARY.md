---
phase: 06-markdown-first-skill-using-autonomy
plan: 06-IMPLEMENTATION
slice: wave-3-pivot
status: in_progress
completed_at: 2026-04-19
tags:
  - kairos
  - pivot
  - planner-driven
  - stepwise-e2e
---

# 06-03 Summary (Phase-6 Pivot)

## Context: 思路切换（Pivot）

Phase-6 在执行中途确认原路径存在结构性问题：document work 在首轮后可能回退到 continuation `final_action(run_dex_task)`，被错误导入 `handoff/dex` 路径并出现停滞。  
因此明确切换为：**Kairos 以 LLM planner 持续驱动 document work，runtime 直接执行 `agent_execute`，continuation 仅保留安全边界角色。**

## 已完成

- runtime 修复（pivot 落地）：
  - 引入 document planner mode（有 document work 且 planner 可用时，优先 planner）。
  - 在该模式下，跳过 continuation `refresh_unfinished_work` 对 document work 的接管。
  - 即使已有 `current_execution_plan`，仍允许每轮重规划，避免“只规划一次”后失控。
  - 避免旧 `final_action` 回退接管导致再次进入 `run_dex_task/handoff`。
- live stepwise E2E 稳定性增强：
  - 防止 wake 洪泛（仅在空闲且无 pending trigger 时再手动唤醒）。
  - 强化 Step-5 验收：要求 `Current Status=completed` + `E2E-RESULT.md` 非空。
- 回归测试补齐：
  - 新增 runtime 回归：覆盖“已有 plan 时仍应 LLM 驱动且不得回退到 run_dex_task”。
  - stepwise live 脚本增加状态解析与完成态断言。

## 已验证

- 单元/回归通过：
  - `tests/kairos/test_runtime.py`
  - `tests/kairos/test_llm_planner.py`
  - `tests/kairos/test_live_http_kairos_stepwise_replan_e2e.py`（source/assert 层）
- 真实 live E2E 通过：
  - 会话：`session_1776539960813_5a6b48e4`
  - 指标：`turn_started=True`、`turn_finished=True`、`planning_selected=True`、`replan_evidence=True`、`planner_no_steps_error=False`
  - 产物：
    - `requirements/session_1776539960813_5a6b48e4/work.md`（`Current Status: completed ✅`）
    - `requirements/session_1776539960813_5a6b48e4/e2e/E2E-RESULT.md`（非空）

## 后续计划

1. 继续执行“真实任务（非固定 stepwise 脚本）”的长程验证，观察 10+ 轮自治稳定性与停止条件。
2. 收敛 planning trace 一致性（`selected_candidate/final_action` 与 runtime 当前动作、history 事件一致）。
3. 优化技能选择命中率（依赖 catalog id+desc），降低无效 hint 与重复加载噪声。


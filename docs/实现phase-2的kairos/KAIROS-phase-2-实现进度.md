# KAIROS Phase 2 实现进度

> 记录时间: 2026-04-03

## 当前状态: Task 1-6 全部完成，61 个测试全部通过

---

## 已完成的 Task

### Task 1: 扩展 KAIROS 状态模型 ✅

**修改文件:**
- `src/adk_agent/kairos/models.py` — 新增 `KairosTrigger`, `KairosSchedule`, `TriggerKind`, `KairosMode.HANDOFF`, `KairosMode.WAITING_INPUT`, `last_tick_at`, `active_trigger`, `pending_triggers`, `schedules` 字段
- `src/adk_agent/kairos/__init__.py` — 导出新类型
- `tests/kairos/test_models.py` — 14 个测试（3 Phase 1 + 11 Phase 2）

**新增测试:**
- `test_phase2_imports_exist` — 验证新类型可导入
- `test_new_kairos_modes_exist` — 验证 HANDOFF/WAITING_INPUT 模式
- `test_load_legacy_state_fills_phase2_defaults` — Phase 1 状态兼容
- `test_dump_round_trip_preserves_schedule_and_trigger` — 完整序列化
- `test_dump_round_trip_with_pending_triggers` — 多 trigger 序列化
- `test_dump_round_trip_with_multiple_schedules` — 多 schedule 序列化
- `test_trigger_kind_enum_values_are_strings` — enum 值类型
- `test_kairos_trigger_metadata_defaults_to_empty_dict` — 默认值
- `test_kairos_schedule_next_fire_at_defaults_to_none` — 默认值
- `test_dump_with_no_active_trigger` — None 处理
- `test_load_state_with_unknown_fields_is_tolerant` — 前向兼容

---

### Task 2: 新增 scheduler 模块 ✅

**新增文件:**
- `src/adk_agent/kairos/scheduler.py` — `KairosScheduler` 类，cron → trigger 转换
- `tests/kairos/test_scheduler.py` — 11 个测试

**依赖:**
- `croniter>=2.0.0` 已加入 `requirements.txt`

**新增测试:**
- `test_import_scheduler` — 模块可导入
- `test_seed_schedules_sets_next_fire_at` — 初始化 next_fire_at
- `test_seed_schedules_skips_already_seeded` — 不覆盖已有值
- `test_seed_schedules_skips_disabled` — 跳过禁用 schedule
- `test_collect_due_triggers_rolls_schedule_forward` — 到期触发并前滚
- `test_collect_due_triggers_skips_disabled_schedule` — 跳过禁用
- `test_collect_due_triggers_skips_future_schedule` — 跳过未到期
- `test_collect_due_triggers_skips_no_next_fire_at` — 跳过未 seed
- `test_collect_due_multiple_schedules` — 多 schedule 同时到期
- `test_trigger_id_contains_schedule_id` — trigger_id 可追溯
- `test_trigger_metadata_contains_schedule_id` — metadata 包含来源

---

### Task 3: 把 trigger/schedule 接入 runtime 与 API ✅

**修改文件:**
- `src/adk_agent/kairos/runtime.py` — 完整重写，支持 scheduler、trigger queue、enqueue_trigger、add/delete_schedule、register_dex_task、last_tick_at
- `src/adk_agent/kairos/api.py` — 新增 schedule CRUD 路由、dex register 路由、attach/list 路由
- `tests/kairos/test_runtime.py` — 22 个测试（6 Phase 1 + 16 Phase 2）
- `tests/kairos/test_api.py` — 12 个测试（1 Phase 1 + 11 Phase 2）

**Runtime 新增测试:**
- `test_runtime_accepts_scheduler_parameter`
- `test_add_schedule_persists_and_seeds_next_fire_at`
- `test_add_schedule_replaces_existing_with_same_id`
- `test_delete_schedule_removes_by_id`
- `test_tick_runs_due_schedule_trigger`
- `test_tick_records_last_tick_at`
- `test_enqueue_trigger_wakes_sleeping_runtime`
- `test_tick_processes_pending_triggers_fifo`
- `test_wake_uses_enqueue_trigger_with_manual_kind`
- `test_get_status_includes_phase2_fields`

**API 新增测试:**
- `test_stop_route_works`
- `test_wake_route_works`
- `test_add_schedule_route_works`
- `test_add_schedule_replaces_existing`
- `test_delete_schedule_route_works`
- `test_register_dex_route_works`
- `test_list_kairos_sessions_route_works`
- `test_list_kairos_sessions_filters_by_user`
- `test_attach_route_works`

---

### Task 4: attach/view skeleton + basic continuity ✅

**新增文件:**
- `src/adk_agent/kairos/attach.py` — `build_runtime_summary`, `list_runtime_summaries`

**路由:**
- `GET /api/kairos/sessions?user_id=<USER>` — 列出用户活跃 KAIROS session
- `GET /api/sessions/{session_id}/kairos/attach?app_name=<APP>&user_id=<USER>` — 获取 runtime snapshot

---

### Task 5: Dex handoff 注册与 richer lifecycle ✅

**Runtime 新增测试:**
- `test_register_dex_task_switches_runtime_to_handoff`
- `test_register_dex_task_does_not_duplicate`
- `test_completed_handoff_task_returns_runtime_to_idle`
- `test_partial_dex_completion_keeps_handoff`
- `test_failed_dex_task_is_untracked`
- `test_register_dex_task_does_not_switch_to_handoff_when_busy`

---

## 测试总结

| 文件 | 测试数 |
|---|---|
| test_models.py | 14 |
| test_scheduler.py | 11 |
| test_runtime.py | 22 |
| test_api.py | 12 |
| test_activity_log.py | 2 |
| test_dex_bridge.py | 2 |
| **总计** | **61** |

Phase 1 原有 14 个测试 → Phase 2 扩展到 62 个测试，全部通过。

---

## 新增/修改文件清单

### 新增
- `src/adk_agent/kairos/scheduler.py`
- `src/adk_agent/kairos/attach.py`
- `tests/kairos/test_scheduler.py`

### 修改
- `src/adk_agent/kairos/models.py`
- `src/adk_agent/kairos/runtime.py`
- `src/adk_agent/kairos/api.py`
- `src/adk_agent/kairos/__init__.py`
- `requirements.txt`
- `tests/kairos/test_models.py`
- `tests/kairos/test_runtime.py`
- `tests/kairos/test_api.py`

---

### Task 6: 回归测试 ✅

- `main_web_start_steering.py` 中 `get_or_create_kairos_runtime` 已适配 `scheduler=KairosScheduler()`
- 61 个测试全部通过
- Phase 1 所有原有功能未被破坏

---

## 验收标准对照

| # | 标准 | 状态 |
|---|---|---|
| 1 | `status` 返回 `last_tick_at / active_trigger / pending_triggers / schedules` | ✅ |
| 2 | 可以通过 API 新增和删除 schedule | ✅ |
| 3 | due schedule 会在 runtime tick 中自动转成 trigger 并执行 turn | ✅ |
| 4 | `attach` 路由能返回当前 runtime snapshot | ✅ |
| 5 | `list` 路由能列出某个 `user_id` 当前的活跃 KAIROS session | ✅ |
| 6 | `ensure_kairos_runtime()` 能从已持久化 `session.state["kairos"]` 恢复 runtime | ✅ |
| 7 | Dex task 可以通过 API 注册到 runtime，并把 mode 切到 `handoff` | ✅ |
## 9. Phase 2 后续补强进度（2026-04-04）

### Task 7: 修复 wake 导致历史倍增 ✅

**问题现象：**
- 用户正常对话后启动 KAIROS，再点击「唤醒」会导致旧 history 倍增
- 连续 wake 会让旧消息继续重复追加

**根因结论：**
- `main_web_start_steering.py` 中 KAIROS 的 state-only 更新错误走了 `save_session()`
- `custom_table_db_service.py` 的 `save_session()` 会整份重写 `events`
- 在 KAIROS 高频 state 持久化/并发保存场景下，旧 history 被重复写回数据库
- 同时 sandbox 路径还误用了 `InMemorySessionService.save_session()`

**修复内容：**
- `src/shared/db/custom_table_db_service.py`
  - 新增 `save_session_state(...)`，只更新 state，不重写 events
- `src/adk_agent/main_web_start_steering.py`
  - KAIROS state 持久化改走 state-only 路径
  - sandbox 初始化改为 `create_session(...) + 克隆 events/state`
  - sandbox 退出时只回写 state，不再 full save
  - 其他只改 metadata/state 的路径也切到 state-only 保存

**新增回归测试：**
- `tests/kairos/test_db_state_only_persistence.py`
- `tests/kairos/live_http_kairos_regression.py`

**验证结果：**
- DB 层验证：连续多次 state-only 保存后，events 数量保持不变
- 真实 HTTP 链路验证通过：
  - `hi -> agent reply -> start kairos -> 连续 wake 3 次`
  - 历史消息仍保持 2 条
  - 不再出现旧消息倍增

**相关文档：**
- `KAIROS-Phase-2-历史倍增Bug排查与修复记录.md`

---

### Task 8: 验证 KAIROS 可自主跟踪 Dex 后台任务 ✅

**目标：**
证明 KAIROS 不只是被动 wake/schedule runtime，而是已经具备一部分自主性：
- 能接手 Dex 后台任务的跟踪责任
- 能在 tick 中自主轮询任务状态
- 能在任务完成时自主记录结果

**真实接口演示结果：**
- Session ID: `session_1775239855513_18f4782e`
- Dex Task ID: `8211688c`
- 演示流程：
  1. 通过聊天接口加载 `dex`
  2. 让 agent 创建并启动后台任务
  3. 启动 KAIROS
  4. 通过 `/kairos/dex/register` 把任务注册给 KAIROS
  5. 轮询 `/kairos/status` 观察 runtime 状态变化

**演示观察到的关键状态：**
- 注册后：
  - `mode = handoff`
  - `tracked_dex_task_ids = ["8211688c"]`
- 任务完成后：
  - `mode = idle`
  - `tracked_dex_task_ids = []`

**recent_events 中出现的关键事件：**
- `dex handoff registered: 8211688c 演示 kairos 自动跟踪任务进度`
- `Dex task 8211688c completed: 演示 kairos 自动跟踪任务进度`

**结论：**
- 当前 KAIROS 已经可以自主检查 Dex 后台任务进度
- 但它目前更像 runtime + poller + state machine
- 它已经能“自己发现任务完成”，但还没有完全进化成会自动总结并主动汇报的完整 autonomous agent

**相关文档：**
- `KAIROS-自主跟踪后台任务演示说明.md`

---

## 当前 Phase 2 实际状态更新

在原有 Task 1-6 基础上，当前已额外完成：

- ✅ 修复 wake 导致历史倍增的真实后端根因
- ✅ 修复 sandbox 隔离路径的 API 误用
- ✅ 补 DB 层和 live HTTP 回归验证
- ✅ 证明 KAIROS 能自主跟踪 Dex 后台任务进度

这意味着当前的 Phase 2 已不只是：
- schedule / trigger / attach / handoff 的“结构性功能打通”

而是已经具备：
- **安全的 runtime 持久化**
- **不污染用户 history 的后台自治运行**
- **对 Dex 后台任务的自主跟踪能力**

---

## 下一步：让 KAIROS 更 autonomous 的实现计划设想

下面这些不是本轮已经完成的内容，而是下一阶段值得推进的方向。

### 方向 1：从“状态机”升级为“可汇报的自治执行体”

**当前能力：**
- KAIROS 能发现 Dex 任务完成
- 但只是在 `recent_events` 里记一条 brief 事件

**下一步建议：**
- 当 Dex 任务完成时，自动读取任务详情/结果摘要
- 生成一段可读的自然语言汇报
- 在合适时机把汇报送回主会话或 attach 视图

**预期效果：**
- 从“我知道任务完成了”升级到“我能告诉你任务完成了什么”

---

### 方向 2：支持任务完成后的自动 follow-up 动作

**当前能力：**
- KAIROS 只会记录完成事件

**下一步建议：**
- 为不同任务类型定义后续动作策略
  - 例如：测试任务完成后自动读取日志摘要
  - 构建任务完成后自动检查产物是否存在
  - 报告任务完成后自动整理结果并准备汇报
- 把 KAIROS 从“监听器”推进到“监督者/协作者”

**预期效果：**
- KAIROS 不只是知道状态变化，而是能接续处理后续步骤

---

### 方向 3：把 schedule + Dex + trigger 连接成真正的自治工作流

**当前能力：**
- schedule 会生成 trigger
- trigger 会驱动一次 kairos turn
- Dex 任务可以被 handoff 注册和轮询

**下一步建议：**
- 支持“schedule 到期 -> 自动创建 Dex 任务 -> 自动注册 handoff -> 自动跟踪完成”的闭环
- 支持把结果写回 session state，供下一次 tick 使用

**预期效果：**
- 从“可调度 + 可跟踪”变成“可闭环自治执行”

---

### 方向 4：增强任务记忆与长期自治上下文

**当前能力：**
- KAIROS state 里有 runtime 状态
- recent_events 只保留短期事件窗口

**下一步建议：**
- 为 KAIROS 增加轻量任务记忆：
  - 最近跟踪过哪些 task
  - 哪些任务经常失败
  - 哪些 schedule 有连续异常
- 支持在下一次 turn 中引用这些信息做判断

**预期效果：**
- KAIROS 不再只是“每次重新看当前状态”
- 而是具备连续自治判断能力

---

### 方向 5：增强自主唤醒与优先级管理

**当前能力：**
- wake / schedule / pending_triggers 已可工作
- worker busy 时会跳过 tick

**下一步建议：**
- 支持 trigger 优先级
- 支持不同 handoff task 的优先级排序
- 支持“低优先级事件延后，高优先级事件立即唤醒”
- 支持更明确的 `WAITING_INPUT / HANDOFF / SLEEPING / RUNNING` 之间的调度策略

**预期效果：**
- KAIROS 更像一个自主运行时，而不是简单轮询器

---

## 对下一阶段的建议排序

如果按投入产出比排序，我建议优先做：

1. **任务完成后的自动自然语言汇报**
2. **schedule -> Dex -> handoff -> completion 的闭环自治工作流**
3. **任务记忆与长期上下文**
4. **优先级调度与更细粒度的 autonomous policy**

这四步做完后，KAIROS 会从现在的：
- “有 runtime、有 trigger、有 handoff、有轮询”

进一步升级到：
- “能自主发起、跟踪、汇报、衔接后续动作的自治运行时”

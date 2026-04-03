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
| 8 | `tests/kairos/*.py` 全部通过 | ✅ (61 passed) |

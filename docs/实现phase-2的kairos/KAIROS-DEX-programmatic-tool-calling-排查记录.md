# KAIROS / Dex / programmatic-tool-calling 排查记录（供压缩会话后续接力）

> 记录时间：2026-04-04
> 目的：保存本轮对 `前端聊天框触发 Dex 长任务但 KAIROS 无法正常跟踪` 的排查过程、证据、结论、当前修复进度与下轮建议。

---

## 1. 问题背景

用户要求验证这条真实链路：

1. 从前端聊天框触发 Dex 长任务
2. KAIROS 注册并跟踪该任务
3. 前端 `Tracked Dex Tasks` 正确显示状态
4. 任务完成后 KAIROS 写入 `recent_events`
5. KAIROS 自动清理 tracked 列表

手工创建 Dex 任务并注册给 KAIROS 的链路是通的；但**通过前端聊天框让 agent 自己创建 Dex 任务**时，出现了异常行为。

---

## 2. 已确认的正常链路

### 2.1 手工创建 + KAIROS 跟踪：正常

已做过一次真实验证：

- `session_id = session_1775298977014_0e06c2d6`
- 手工创建 Dex 任务：`121583ef`
- 注册给 KAIROS 后：
  - `mode: handoff`
  - `Tracked Dex Tasks` 显示 `121583ef [pending]`
- 任务启动并完成后：
  - `recent_events` 出现：
    - `Dex task 121583ef completed: playwright dex handoff — task done`
  - 最终：
    - `tracked_dex_task_ids = []`
    - `tracked_dex_tasks = []`
    - `mode = idle`

说明：

> KAIROS runtime / dex_bridge / 前端展示链路本身是成立的。

---

## 3. 异常链路：前端聊天框触发 Dex 长任务

### 3.1 首次异常任务

通过前端聊天框请求 agent：

- 加载 dex skill
- 创建并启动一个长任务

agent 最终返回：

- `task_id: 3e51c425`
- 命令：
  - `python -c "import time; print('frontend task start'); time.sleep(20); print('frontend task done')"`

随后确认该任务真实存在，但路径是：

- `.dex/tasks/global/3e51c425.json`
- `.dex/logs/global/3e51c425.log`

任务 JSON 里还确认到：

```json
"user_id": null
```

而不是：

```json
"user_id": "user_001"
```

### 3.2 直接后果

将 `3e51c425` 注册给当前 KAIROS session 后：

- `tracked_dex_task_ids` 能出现 `3e51c425`
- 但 `tracked_dex_tasks` 为空
- `recent_events` 只有：
  - `dex handoff registered: 3e51c425 frontend dex handoff`
- 没有：
  - `Dex task 3e51c425 completed: ...`

说明：

> KAIROS 只登记了 task_id，但并没有真正从自己的 Dex bridge 中读到该任务详情。

---

## 4. 关键代码结论

### 4.1 KAIROS 只按当前 session 的 `user_id` 读取 Dex 任务

文件：
- `src/adk_agent/kairos/dex_bridge.py`

关键点：

```python
self.manager = DexManager(base_dir=base_dir, user_id=user_id)
```

当前 KAIROS session 用的是：
- `user_id = user_001`

所以它读取的是：
- `.dex/tasks/user_001/*`

### 4.2 Dex 在 `user_id` 为空时会落到 `global`

文件：
- `skills/dex/store.py`

关键点：

```python
def _user_segment(self) -> str:
    if not self.user_id:
        return "global"
```

所以：

> 只要 DexManager 没传 `user_id`，任务就会被写到 `global`。

### 4.3 KAIROS 只有在 `_poll_dex()` 读到完成态时才会写 completed 事件并清理

文件：
- `src/adk_agent/kairos/runtime.py`

关键点：

- `tick_once()` 会调用 `_poll_dex()`
- `_poll_dex()` 只有读到 `completed/failed` 的 snapshot 才会：
  - 记录 `Dex task <id> completed: ...`
  - 从 `tracked_dex_task_ids` 中移除

所以：

> 若 `recent_events` 中没有 `Dex task 3e51c425 completed: ...`，不能简单认为它只是“完成后被正常消费掉了”；更可能是 KAIROS 根本没读到该任务 snapshot。

---

## 5. 为什么 `3e51c425` 会落到 `global`

### 5.1 直接原因

检查会话历史后发现：

agent **并没有直接调用 dex skill 暴露的 `dex_create_task` / `dex_start_task` 工具**。

相反，它走了错误路径：

1. 先 `skill_load("dex")`
2. 然后又 `skill_load("programmatic-tool-calling")`
3. 在 `run_programmatic_task` 里尝试：
   - `await call_tool('dex_create_task', ...)`
4. 失败后，又退化成：
   - 直接 `import DexManager`
   - `dex = DexManager()`
   - `dex.create_task(...)`
   - `dex.start_background_process(...)`

这里的关键问题是：

```python
dex = DexManager()
```

没有传 `user_id`。

因此任务被写到：
- `global`

---

## 6. 为什么 agent 会走错到 `run_programmatic_task`

这部分要分两阶段理解。

### 6.1 第一阶段结论：不是 dex skill 普遍失效

做过 fresh session 自测：

新 session：
- `session_1775300862615_5d98a1b7`

步骤：
1. `skill_load("dex")`
2. 直接要求：
   - `请直接调用 dex_list_tasks(show_all=true)，不要加载其他 skill，不要使用 run_programmatic_task，也不要使用 bash。`

结果：
- agent **直接调用了** `dex_list_tasks`
- 成功返回 Dex 列表

说明：

> dex skill 本身可以正常加载，也可以被 agent 直接调用。

### 6.2 第二阶段结论：问题是特定 session 的 tool state 异常

继续做 fresh session 复现：

新 session：
- `session_1775301312675_f1a75f60`

步骤：
1. `skill_load("dex")`
2. `skill_load("programmatic-tool-calling")`
3. 让 agent 只调用一次 `run_programmatic_task` 执行：

```python
print(await call_tool("dex_list_tasks", show_all=True))
```

结果：
- 成功

再执行：

```python
result = await call_tool("dex_create_task", description="repro create", context="repro ctx")
print(result)
```

结果：
- 成功创建：`4e0835b6`
- 任务落在：
  - `.dex/tasks/user_001/4e0835b6.json`
  - `.dex/logs/user_001/4e0835b6.log`

说明：

> `programmatic-tool-calling` 并不是一直坏的；在 fresh session 里它可以正常访问 dex tools。

### 6.3 原问题 session 的真实异常

回到原问题 session：
- `session_1775298977014_0e06c2d6`

受控探测 `run_programmatic_task` 内看到的 `_AGENT_REF.tools`：

```text
TOOL_NAMES ['skill_load', 'skill_reload', 'file_editor', 'view_local_image', 'analyze_local_image', 'bash', 'search_experience', 'run_programmatic_task']
```

注意：
- **没有 dex_create_task / dex_start_task / dex_list_tasks / dex_get_task_details**

同样在 fresh session 里探测，结果是：

```text
TOOL_NAMES ['skill_load', 'skill_reload', 'file_editor', 'view_local_image', 'analyze_local_image', 'bash', 'search_experience', 'dex_create_task', 'dex_start_task', 'dex_list_tasks', 'dex_get_task_details', 'run_programmatic_task']
```

所以当前最关键的事实是：

> 原问题 session 当时的 agent 工具集合里，确实没有 dex tools。

这解释了为什么：

```python
print(await call_tool("dex_list_tasks", show_all=True))
```

在原 session 会报：

```text
[Error] Tool 'dex_list_tasks' not found.
```

---

## 7. 关于“是否跟刷新前端有关”的判断

用户问：

> 是否跟我刚才恰好刷新了前端有关系？

当前判断：

### 7.1 不是“刷新直接把 dex tools 刷没了”

前端普通刷新后：
- `sessionStorage.current_session_id` 通常还在
- 前端会继续使用同一个 `session_id`

后端 `SessionManager` 也是按：
- `(app_name, user_id, session_id)`
- 复用同一个 `SteeringSession`

所以更像是：

> 刷新后重新连回了一个**已经处于异常 tool state 的旧 session**。

### 7.2 刷新可能让问题“继续暴露”，但不像是根因

更准确地说：

- 刷新不是最根本原因
- 但刷新后继续落回同一个坏 session，会让问题持续存在
- 所以用户感受上会像“刷新后出问题了”

---

## 8. 热重载验证（关键闭环）

为了验证“原问题 session 只是缺 dex tools，而不是 sandbox 永久坏掉”，做了关键验证：

在原问题 session：
- `session_1775298977014_0e06c2d6`

执行：

```text
skill_reload("dex")
```

结果：

```text
[OK] 技能 'dex' 热重载成功，已加载工具: ['dex_create_task', 'dex_start_task', 'dex_list_tasks', 'dex_get_task_details']
```

随后再次探测原 session 的 `_AGENT_REF.tools`：

```text
TOOL_NAMES ['skill_load', 'skill_reload', 'file_editor', 'view_local_image', 'analyze_local_image', 'bash', 'search_experience', 'run_programmatic_task', 'dex_create_task', 'dex_start_task', 'dex_list_tasks', 'dex_get_task_details']
```

然后再次执行：

```python
print(await call_tool("dex_list_tasks", show_all=True))
```

结果：
- 成功

这一步已经基本坐实：

> 原问题 session 的核心问题就是：**当时 agent.tools 里没有 dex tools**。

而不是：
- `run_programmatic_task` 永远坏掉
- `_AGENT_REF` 串到了别的 session
- dex 实现本身完全不可用

---

## 9. 当前最可信的根因模型

### 一级根因

`skill_load("dex")` 的成功判定不可靠。

旧逻辑是：

```python
self._load_skill_tools(skill_id)
return "[OK] ..."
```

也就是说：
- 即使实际一个工具都没挂进去
- 仍然返回 `[OK]`

### 二级后果

agent 在某些 session 中会误以为 dex 已可用，但实际上当前 `agent.tools` 没有 dex tools。

### 三级后果

此时如果模型又错误选择了：
- `programmatic-tool-calling`

那么在 sandbox 里调用：
- `call_tool('dex_*')`

会失败。

### 四级后果

模型退化成：
- 直接 `import DexManager`
- `DexManager()` 不传 `user_id`

### 五级后果

任务落到：
- `.dex/tasks/global/*`

KAIROS 按 `user_001` 读不到。

---

## 10. 本轮已完成的修复（已落代码）

### 10.1 修复目标

修复“skill_load 虚假成功”问题。

### 10.2 已修改文件

- `src/adk_agent/main_web_start_steering.py`
- 新增测试：`tests/test_skill_load_behavior.py`

### 10.3 修复内容

`skill_load()` 现在会：

1. 调用 `_load_skill_tools(skill_id)` 获取 `tools`
2. 检查该 skill 是否存在 `tools.py`
3. 检查该 skill 是否已在 `_loaded_skills` 中
4. 当满足以下条件时返回 `[WARN]` 而不是 `[OK]`：
   - skill 有 `tools.py`
   - 但本次没有加载出任何工具
   - 且不是已经加载过的重复调用

warn 内容会提示：
- 技能已找到
- 但工具未成功加载
- 需要检查：
  - `tools.py` 导入错误
  - `get_tools()` 返回空列表

### 10.4 已加入的 TDD 测试

新测试文件：
- `tests/test_skill_load_behavior.py`

覆盖三类行为：

1. 有 `tools.py` 但没加载出工具 → 应返回 `[WARN]`
2. 已加载过的 skill 再次 load → 保持 `[OK]`
3. 没有 `tools.py` 的 instruction-only skill → 保持 `[OK]`

### 10.5 测试结果

- `python -m pytest tests/test_skill_load_behavior.py -q`
  - `3 passed`
- `python -m pytest tests/dex/test_tools.py -q`
  - `1 passed`

---

## 11. 当前还没彻底修完的部分

虽然已经修掉了“虚假 [OK]”这个重要问题，但还没完全闭环的点有：

### 11.1 还没 100% 找到“为什么某些 session 当时没挂进去 dex tools”的最上游原因

目前最合理怀疑：
- `_load_skill_tools('dex')` 当时没有真正挂成功
- 但旧 `skill_load()` 误报了成功

这已经能解释现象，但还没抓到当时失败的具体异常日志。

### 11.2 还没增强 `programmatic-tool-calling` 的防退化能力

当前它依然很弱：
- sandbox 里找不到 dex tool 后
- 模型容易自己走旁路：
  - import dex module
  - `DexManager()`

这会把任务写进 `global`。

### 11.3 还没给 Dex 的旁路使用加护栏

例如：
- `DexManager()` 无 `user_id` 时是否应明确告警
- 或在某些路径下拒绝静默写入 `global`

---

## 12. 建议下一轮会话的优先事项

### 优先级 1：继续 TDD 修第二层保护

建议下一轮修：

#### 方案 A（推荐）
增强 `programmatic-tool-calling`：
- 当 `call_tool('dex_*')` 找不到时
- 输出结构化诊断
- 明确告诉模型当前 agent.tools 中缺少 dex tools
- 不要诱导模型去手搓 `DexManager()` 旁路

#### 方案 B
给 Dex 增加 user_id 防呆：
- 当通过某些路径创建 DexManager 且 `user_id is None`
- 更显式地记录/报错/警告
- 降低静默落到 `global` 的风险

### 优先级 2：补一条端到端 regression test（若可行）

理想测试目标：
- 构造一个 session
- 模拟 `skill_load(dex)` 失败挂载
- 验证 `skill_load()` 返回 `[WARN]`
- 再 `skill_reload(dex)`
- 验证 sandbox 中 `call_tool('dex_list_tasks')` 可用

---

## 13. 关键会话 / 任务 ID 备忘

### 原问题 session
- `session_1775298977014_0e06c2d6`

### 手工正常链路任务
- `121583ef`

### 前端聊天框错误链路任务（落到 global）
- `3e51c425`

### fresh session 中 sandbox 成功创建的 user_001 任务
- `4e0835b6`

### 其他验证用 fresh session
- `session_1775300862615_5d98a1b7`
- `session_1775301312675_f1a75f60`

---

## 14. 当前可直接复述的核心结论

如果下轮会话需要快速恢复上下文，可以直接引用下面这段：

> 已确认：KAIROS / dex_bridge / 前端 tracked task 展示链路本身是正常的。异常只出现在“前端聊天框触发 Dex 长任务”这条路径上。根因不是 KAIROS，而是某些 session 中 `skill_load("dex")` 表面成功但 `agent.tools` 实际没有 dex tools，导致 agent 误走 `programmatic-tool-calling` / 直接 `DexManager()` 旁路；旁路因未传 `user_id` 把任务写进 `.dex/tasks/global`，从而 KAIROS 按 `user_001` 无法读取任务详情。本轮已修复 `skill_load()` 的虚假成功问题，并补了 TDD 测试。下一步建议继续 TDD 增强 `programmatic-tool-calling` 与 Dex 的 user_id 防呆。

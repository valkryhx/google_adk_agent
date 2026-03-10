# dispatch_batch_tasks `'str' object is not callable` 修复记录

## 问题现象

调用 `dispatch_batch_tasks` 时，所有子任务均返回异常：

```json
[
  {"index": 0, "result": "[Exception] 'str' object is not callable", "success": false},
  {"index": 1, "result": "[Exception] 'str' object is not callable", "success": false},
  {"index": 2, "result": "[Exception] 'str' object is not callable", "success": false}
]
```

同时，前端的 Leader 和 Worker 状态卡片全部消失。

---

## 根因分析

### 1. LLM 错误传入内部参数

LLM Agent 在调用工具时，错误地把内部参数当成普通参数传入：

```python
dispatch_batch_tasks({
    "_original_user_id": "user_001",
    "_status_reporter": "{}",        # <-- 这是 LLM 生成的字符串！
    "tasks": [...],
    "common_context": "...",
    ...
})
```

`_status_reporter` 本应是一个 **可调用对象（callable）**，由 `get_tools` 工厂函数通过 `functools.partial` 预绑定。但 LLM 传入了字符串 `"{}"`。

### 2. `functools.partial` 允许覆盖

旧代码使用 `functools.partial` 绑定内部参数：

```python
# 旧代码 - tools.py get_tools() 函数
dbt = functools.partial(
    dispatch_batch_tasks,
    _status_reporter=status_reporter,      # 预绑定 callable
    _original_user_id=original_user_id
)
```

**关键问题**：`functools.partial` 的机制是，后传入的同名参数会 **覆盖** 预绑定的值。因此当 LLM 调用时传入 `_status_reporter="{}"` 时：

```
预绑定: _status_reporter = <callable>
LLM传入: _status_reporter = "{}"    # 字符串覆盖了 callable！
最终值:  _status_reporter = "{}"    # 变成字符串
```

### 3. 连锁反应

代码中所有使用 `_status_reporter(...)` 的地方都会触发 `'str' object is not callable`：

```python
# dispatch_task 中的 report 函数
def report(event_type, data):
    _status_reporter(event_type, {**data, ...})  # 这里炸了！
```

由于 `report()` 函数调用失败，前端收不到任何 `init` / `chunk` / `finish` 事件，导致卡片全部消失。

---

## 修复方案

### 修复 1：闭包 Wrapper 替代 `functools.partial`（核心修复）

**文件**：`skills/agent_team/tools.py` - `get_tools()` 函数（约 1564 行起）

将 `functools.partial` 替换为闭包 wrapper 函数，**强制从闭包作用域注入内部参数**，LLM 传什么都无法覆盖：

```python
# 新代码 - 闭包 wrapper
async def dbt(tasks, common_context="", priority="NORMAL",
              return_structured=False, **kwargs):
    # 强制使用闭包捕获的 status_reporter，忽略 LLM 可能传入的值
    return await dispatch_batch_tasks(
        tasks=tasks,
        common_context=common_context,
        priority=priority,
        return_structured=return_structured,
        _status_reporter=status_reporter,        # 从闭包注入，不可覆盖
        _original_user_id=original_user_id,      # 从闭包注入，不可覆盖
        _meeting_context=kwargs.get("_meeting_context")
    )
dbt.__name__ = "dispatch_batch_tasks"
dbt.__doc__ = dispatch_batch_tasks.__doc__
functools.update_wrapper(dbt, dispatch_batch_tasks)
```

**原理**：
- Wrapper 函数只暴露 LLM 应该传的参数（`tasks`、`common_context` 等）
- `**kwargs` 吞掉 LLM 可能传的其他多余参数（如 `_status_reporter="{}"`)
- 内部调用时强制使用闭包作用域中的 `status_reporter` 和 `original_user_id`

同样的 wrapper 模式应用于所有 5 个工具函数：
- `dispatch_task` -> `dt`
- `dispatch_batch_tasks` -> `dbt`
- `hold_meeting` -> `hm`
- `sync_task_context` -> `stc`
- `deep_think` -> `dpt`

### 修复 2：防御性检查（二级保障）

**文件**：`skills/agent_team/tools.py`

在 `dispatch_task`（约 159 行）、`dispatch_batch_tasks`（约 659 行）、`hold_meeting`（约 750 行）三个函数入口处添加防御检查：

```python
# [防御] LLM 可能把 _status_reporter 当普通参数传入字符串，必须校验
if not callable(_status_reporter):
    _status_reporter = None
```

这确保即使 wrapper 被绕过（如内部直接调用），也不会因为非 callable 的 `_status_reporter` 而崩溃。

### 修复 3：文档警告

**文件**：`skills/agent_team/SKILL.md`（约 33 行）

添加明确警告，防止 LLM 再次传入内部参数：

```markdown
> 严禁传入内部参数
> 所有以下划线 `_` 开头的参数（如 `_status_reporter`、`_original_user_id`、
> `_meeting_context`）均为系统内部注入参数，**严禁在调用时手动传入**。
> 手动传入会导致 `'str' object is not callable` 等严重错误。
```

---

## 附加优化：节点切换卡片状态

### 问题

Worker 返回 503 Busy 时，调度逻辑会自动切换到下一个节点。但旧代码会发送 `report('fail')`，导致前端出现红色 Failed 卡片，即使任务最终在其他节点成功完成。

### 修复

**后端** `skills/agent_team/tools.py`（约 304 行）：

```diff
-report('fail', {"worker_port": worker_port, "session_id": use_session_id, "error": "Worker busy"})
+report('retry', {"worker_port": worker_port, "session_id": use_session_id, "retry_reason": "Worker busy"})
```

**前端** `src/adk_agent/static/script.js` 和 `static-2/script.js`：

在 `processSwarmEvent` 函数中新增 `retry` 事件处理：

```javascript
// 5. Retry: 标记跳过（节点忙碌，正在切换到其他节点）
if (subType === 'retry') {
    card.classList.remove('running');
    card.classList.add('skipped');
    meta.textContent = data.retry_reason || 'Skipped';
    icon.innerHTML = '<span class="material-symbols-outlined">swap_horiz</span>';
}
```

**CSS** `src/adk_agent/static/style.css` 和 `static-2/style.css`：

```css
.swarm-card.skipped {
    border-left: 4px solid #9aa0a6; /* Grey */
    opacity: 0.7;
}
.swarm-card.skipped .swarm-status-icon {
    color: #9aa0a6;
}
```

**效果**：忙碌被跳过的节点显示灰色 "Worker busy" 卡片，真正失败的节点仍为红色 "Failed"。

---

## 涉及文件汇总

| 文件                               | 修改内容                             |
| ---------------------------------- | ------------------------------------ |
| `skills/agent_team/tools.py`       | 闭包 wrapper + 防御检查 + retry 事件 |
| `skills/agent_team/SKILL.md`       | 禁止传入内部参数的警告               |
| `src/adk_agent/static/script.js`   | retry 事件处理                       |
| `src/adk_agent/static/style.css`   | .skipped 样式                        |
| `src/adk_agent/static-2/script.js` | 同步 retry 事件处理                  |
| `src/adk_agent/static-2/style.css` | 同步 .skipped 样式                   |

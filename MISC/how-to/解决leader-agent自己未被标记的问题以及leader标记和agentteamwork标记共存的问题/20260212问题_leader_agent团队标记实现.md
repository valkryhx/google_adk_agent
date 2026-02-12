# Leader Agent 标记缺失与多重身份共存问题排查报告

**日期**: 2026-02-12
**作者**: Antigravity (Google Swarm Team)
**关联模块**: `tools.py`, `main_web_start_steering.py`, `script.js`

---

## 1. 问题一：Leader Agent 自身未被标记

### 1.1 现象描述
当一个 Agent 扮演 Leader 角色通过 `dispatch_task` 工具下发任务时，该 Leader 自身的 Session 在前端列表中缺少紫色的 `[Agent-Team-LEADER]` 标记。刷新页面或查看数据库发现 `task_type` 字段为空或未更新。即使偶尔出现标记，会话内容（LLM 生成的文本）会丢失。

### 1.2 排查分析（Root Cause Analysis）

1.  **架构隔离限制**：`tools.py` 中的工具函数运行在受限环境中，无法获取当前的 `Session` 对象，且不应直接操作数据库（这也是为了避免循环依赖和架构腐化）。
2.  **早期尝试的失败**：我们曾尝试注入 `session_service` 到工具中进行直接保存。但这引发了严重的 **竞态条件 (Race Condition)**：
    *   **Runner 线程**：LLM 生成回复 -> 写入 Content -> 保存 Session (Version A)。
    *   **Tool 线程**：工具执行 -> 修改 Metadata -> 保存 Session (Version B, 但 Content 是旧的)。
    *   **结果**：Tool 的保存覆盖了 Runner 的保存，导致“只有标记，没有内容”。

### 1.3 最终解决方案：信号机制 (Signal-Based Architecture)

我们采用了非侵入式的 **"Signal & Hook"** 模式：

1.  **发射信号 (Tools)**：
    在 `skills/agent_team/tools.py` 中，工具不再直接修改数据，而是通过 `status_reporter` 发送一个轻量级信号：
    ```python
    await _status_reporter("update_session_state", {
        "task_type": "swarm_leader",
        "swarm_mode": "batch_dispatch"
    })
    ```

2.  **拦截与合并 (Steering)**：
    在 `src/adk_agent/main_web_start_steering.py` 中：
    *   `SteeringSession` 监听该信号，并将变更暂存在内存中的 `_current_session` 对象。
    *   在任务结束的 `finally` 块中，**重新从数据库加载** 最新的 Session（包含 Runner 刚写入的内容）。
    *   将内存中的 Metadata 变更 **合并 (Merge)** 到这个最新 Session 中。
    *   最后统一保存。

    ```python
    # run_task finally block
    latest_session = await session_service.get_session(...)
    latest_session.state.update(local_state_changes)
    await session_service.save_session(latest_session)
    ```

---

## 2. 问题二：Leader 标记与 Worker 标记无法共存

### 2.1 现象描述
当一个 Agent（例如端口 8003）既接收了上级的任务（本应有橙色 Worker 标记），又在执行过程中下发了子任务（本应有紫色 Leader 标记）时，界面上只显示了橙色标记，紫色标记消失。

### 2.2 排查分析

查看前端代码 `src/adk_agent/static/script.js`，发现逻辑也是互斥的：

```javascript
// 旧代码
if (session.isSwarm) {
    // 渲染橙色 [Agent-Team-TASK]
} else if (session.task_type === 'swarm_leader') {
    // 渲染紫色 [Agent-Team-LEADER]
    // ^^^ BUG: 因为用了 else if，一旦满足上面，这里永远不会执行
}
```

### 2.3 最终解决方案

修改前端渲染逻辑，去除互斥条件，允许两种身份叠加：

```javascript
// 新代码
if (session.isSwarm) {
    // 渲染橙色 [Agent-Team-TASK]
}

// 去掉 else，独立判断
if (session.task_type === 'swarm_leader') {
    // 渲染紫色 [Agent-Team-LEADER]
}
```

---

## 3. 验证结果

1.  **数据完整性**：Leader Session 现在既能保留完整的对话历史（Runner 产出），又能正确持有 `task_type="swarm_leader"` 标记。
2.  **身份展示**：在复杂嵌套任务中（A -> B -> C），中间层 B 节点现在能正确同时显示：
    *   🟠 `[Agent-Team-TASK]` (来自 A 的任务)
    *   🟣 `[Agent-Team-LEADER]` (对 C 的指挥)

此方案未引入全局锁或复杂的缓存机制，保持了系统的简洁性和稳定性。

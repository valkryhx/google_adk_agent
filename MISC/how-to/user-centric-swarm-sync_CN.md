# 以用户为中心的 Agent Team 任务进度同步方案

本文档详细介绍了如何实现跨节点的 Agent Team (Swarm) 任务进度同步与管理。针对 Swarm 架构中 Leader 与 Worker 节点 `app_name` 不一致导致的任务无法追踪、无法中断等问题，我们提出并实施了“以用户为中心 (User-Centric)”的解决方案。

## 1. 背景与问题

在 Swarm 架构中：
*   **Leader 节点** (如 Port 8000) 通常运行在默认的 `app_name` (如 `dynamic_expert`) 下。
*   **Worker 节点** (如 Port 8001, 8002) 被调度执行任务时，往往运行在特定的 `app_name` 下 (如 `swarm_from_8000`)。

**问题**：
当用户（或 Leader 代理）尝试通过标准的 API 接口（如查询历史、取消任务、删除会话）操作 Worker 节点上的任务时，由于前端默认发送的是 `dynamic_expert`，而 Worker 实际运行的是 `swarm_from_8000`，导致服务端因 `app_name` 不匹配而返回 "Session not found"。这使得：
1.  无法在 UI 上查看到 Worker 节点的实时日志。
2.  无法通过 UI 中断或取消正在运行的 Worker 任务。
3.  无法删除历史的 Worker 会话。
4.  Worker 无法通过 `sync_task_context` 从 Leader 获取完整的任务上下文（因为 Leader 可能有多个 app space）。

## 2. 核心解决方案：以用户为中心 (User-Centric)

我们不再严格依赖 `app_name` 作为唯一的隔离边界，而是将 **User ID** 作为跨节点身份的唯一锚点。

**核心逻辑**：
> "只要通过了 User ID 的身份验证，无论任务运行在哪个 App (Namespace) 下，用户都应该有权访问和控制。"

### 2.1 全局回退搜索 (Global Fallback Search)

我们在关键的 API 端点（取消、删除、历史查询）实现了“全局回退搜索”机制。

**工作流程**：
1.  **精确查找**：首先尝试使用请求中提供的 `app_name` (通常是默认值) + `user_id` + `session_id` 进行查找。
2.  **回退搜索**：如果精确查找失败，系统将忽略 `app_name`，在**所有** App Namespace 中搜索匹配 `user_id` 和 `session_id` 的会话。
3.  **定位与操作**：一旦找到（因为 `session_id` 是全局唯一的），就锁定该会话真实的 `app_name` 并执行相应操作。

**代码实现示例 (`main_web_start_steering.py`)**:

```python
# 伪代码：以删除会话为例
session = await session_service.get_session(app_name, user_id, session_id)

if not session:
    # 精确查找失败，启动全局搜索
    all_sessions = await session_service.list_sessions(app_name="*", user_id=user_id)
    for s in all_sessions:
        if s.id == session_id:
            target_app_name = s.app_name # 找到真实的 app_name
            break
            
# 使用找到的真实 app_name 执行删除
await session_service.delete_session(target_app_name, user_id, session_id)
```

## 3. 关键组件修改

### 3.1 数据库服务层 (`custom_table_db_service.py`)

为了支持全局搜索，我们修改了底层的数据库查询逻辑，使其支持通配符。

*   **修改点**：`list_sessions` 方法。
*   **逻辑**：当传入 `app_name="*"` 时，SQL 查询将不再过滤 `app_name` 字段，从而返回指定 User ID 下的所有会话。

```python
stmt = select(self.DbSession)
if app_name != "*":
    stmt = stmt.where(self.DbSession.app_name == app_name)
# 始终过滤 User ID
if user_id is not None:
    stmt = stmt.where(self.DbSession.user_id == user_id)
```

### 3.2 任务上下文同步工具 (`tools.py` & API)

Agent 使用的 `sync_task_context` 工具现在可以跨 App Namespace 工作。

*   **Leader 侧 API**：Leader 节点的 `/api/context/leader_summary` 接口现在会先用 `list_sessions(app_name="*")` 找到最新的会话，然后用其真实的 `app_name` 加载详细历史。
*   **Worker 侧工具**：Worker 调用该接口时，不再受限于 Leader 的 `app_name` 设置，通过 User ID 即可拉取到 Leader 上的最新任务指令。

### 3.3 前端体验优化 (`script.js`)

为了让用户清晰地区分哪些是普通的对话，哪些是 Agent Team 的后台任务：

*   **UI 标识**：Swarm 触发的会话在侧边栏列表中会被自动标记为 **`[Agent-Team-TASK]`**（橙色加粗）。
*   **交互一致性**：点击这些任务，现在可以正常加载历史消息；点击“停止”或“删除”按钮也能正常工作。

## 4. 如何使用与验证

### 4.1 验证同步

作为开发者或 Agent，你可以调用 `sync_task_context` 来测试：

```python
# 获取 Leader (Port 8000) 的任务上下文
sync_task_context(
    reason="同步任务状态",
    target_ports=[8000]
)
```

即使 Leader 的任务运行在 `dynamic_expert` 下，而你的请求默认 `app_name` 是别的，也能成功获取结果。

### 4.2 验证控制

1.  启动 Swarm 演示 (`start_demo_swarm.bat`)。
2.  在浏览器打开 Worker 节点 (如 `http://localhost:8002`)。
3.  在 User 界面看到标记为 `[Agent-Team-TASK]` 的会话。
4.  **查看历史**：点击会话，应能看到详细日志。
5.  **尝试中断**：在任务运行时点击 "Stop" 按钮，后台应打印 `Cancel signal received` 并停止任务。
6.  **尝试删除**：点击删除图标，会话应从列表和数据库中移除。

## 5. 总结

本方案通过在 API 层和数据库层引入“用户维度优先”的查询策略，完美解决了 Swarm 异构 App Name 环境下的管理难题，实现了：
1.  **无缝控制**：用户对 Swarm 任务拥有完全的控制权（查看、停止、删除）。
2.  **数据互通**：Agent 之间可以跨 App Namespace 自由同步上下文。
3.  **兼容性**：完全兼容旧有的精确匹配逻辑，只在失败时触发回退，保证了系统的稳定性。

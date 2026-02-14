# Swarm 集群排查报告: sync_task_context 三模式重设计 & Worker 任务无法中断

> **排查日期**: 2026-02-12  
> **涉及文件**: `skills/agent_team/tools.py`, `src/adk_agent/main_web_start_steering.py`  
> **严重程度**: P0 (集群核心功能失效)  

---

## 目录

- [问题一: sync_task_context 架构重设计](#问题一-sync_task_context-架构重设计)
  - [1.1 旧架构的致命缺陷](#11-旧架构的致命缺陷)
  - [1.2 核心思路转变](#12-核心思路转变)
  - [1.3 三模式架构设计](#13-三模式架构设计)
  - [1.4 新增基础设施](#14-新增基础设施)
  - [1.5 完整实现详解](#15-完整实现详解)
  - [1.6 附带修复: Session ID 截断](#16-附带修复-session-id-截断)
  - [1.7 附带优化: 来源节点标记](#17-附带优化-来源节点标记)
- [问题二: Worker 任务无法中断 (Cancel 失效)](#问题二-worker-任务无法中断-cancel-失效)
  - [2.1 故障现象](#21-故障现象)
  - [2.2 根因定位: 三元组参数不匹配](#22-根因定位-三元组参数不匹配)
  - [2.3 修复方案](#23-修复方案)
- [修改文件清单](#修改文件清单)
- [验证结果](#验证结果)
- [经验总结与防御建议](#经验总结与防御建议)

---

## 问题一: sync_task_context 架构重设计

### 1.1 旧架构的致命缺陷

旧版 `sync_task_context` 采用**按 worker name 查询**的模式：Agent 调用时需要传入 `worker_name`（如 `"Agent_Node_8001"`），然后到 Leader 的 session 表里搜索该名称对应的会话。

这个设计有多个根本性问题：

| 问题                   | 说明                                                                                                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Worker Name 不稳定** | `worker_name` 只是 Agent 的自称，不是系统级标识，格式容易改变                                                                  |
| **Session 归属模糊**   | 旧查询用 `user_id = "Agent_Node_8001"` 搜索，但 `dispatch_task` 创建的 session 实际用的是人类用户 ID（如 `"dwh"`），根本搜不到 |
| **只能单向查**         | Worker 只能查"Leader 那边有什么"，无法反向查"其他 Worker 在做什么"                                                             |
| **无法精准定位**       | 只能拿到会话列表，没有办法进一步查看某个具体会话的完整对话内容                                                                 |
| **集群拓扑盲区**       | 不知道集群里有哪些节点在线，只能盲猜端口号                                                                                     |

**根本症结**: 旧架构基于不可靠的 `worker_name` 标识，而实际的 session 是用 `(app_name, user_id, session_id)` 三元组来唯一标识的。标识体系不匹配导致查询永远失败。

### 1.2 核心思路转变

重设计的核心哲学变化:

```
旧思路: "我是谁" (worker_name) -> 查 Leader -> 看 Leader 知道什么
新思路: "我的用户是谁" (user_id) + "哪个会话" (session_id) -> 查任意节点 -> 直接查真实数据
```

**关键认知突破**:

1. **身份锚点从 Agent 切换为人类用户**: 不管任务在哪个节点上跑，创建 session 时的 `user_id` 始终是人类用户（如 `"dwh"`）。所以用 `user_id` 作为查询维度是最稳定、最准确的。
2. **session_id 是全局唯一的**: 每个会话的 `session_id`（如 `sub_87207465`）是 UUID 级别唯一的，可以跨 `app_name` 精确定位。
3. **从 Leader 中心化查询变为对等网络查询**: 任何节点都可以查任何节点，不依赖 Leader 中转。

### 1.3 三模式架构设计

新版 `sync_task_context` 采用**三模式渐进查询**架构：

```
模式判断逻辑:

  target_ports 有值?
       |
   ----+----
   |        |
  有        无
   |         \
session_id    广播模式 (broadcast)
有值?          -> 查所有在线节点
   |
 --+--
 |    |
 有    无
 |     \
精准    定向模式 (targeted)
模式     -> 只查指定节点上的会话列表
(precise)
 -> 按 session_id 查完整对话
```

#### 模式一: 广播发现 (Broadcast)

```python
# Agent 调用方式
sync_task_context(reason="查看所有节点的任务进度")
# target_ports=None, session_id=None
```

**行为**: 
- 从 `swarm_registry.db` 自动发现所有在线节点（含自身）
- 向每个节点发送 `GET /api/context/user_sessions?user_id=dwh`
- 聚合返回所有节点上属于当前用户的会话摘要列表

**输出示例**:
```
[Swarm Task Discovery Report]
========================================
User: dwh
Mode: Broadcast (all nodes)
Nodes queried: [8000, 8001, 8003]

[OK] Node 8000: 2 session(s)
     - [session_abc123] 管理集群调度 [swarm_leader]  (2026-02-12T15:15:22)
     - [session_def456] 文档整理任务  (2026-02-12T14:30:00)

[OK] Node 8001: 1 session(s)
     - [sub_87207465] 向 misc/test目录写入2个文件 [swarm_worker]  (2026-02-12T15:20:00)

[OK] Node 8003: No sessions

========================================
Summary: 3/3 nodes responded, 3 total sessions found

Tip: To view details of a specific session, call:
  sync_task_context(target_ports=<port>, session_id='<session_id>')
```

#### 模式二: 定向查询 (Targeted)

```python
# Agent 调用方式
sync_task_context(target_ports=8001, reason="查看 8001 的任务")
# 或多节点: sync_task_context(target_ports=[8001, 8003])
```

**行为**: 只查指定节点，不扫描整个集群。适合已知目标节点时减少网络开销。

#### 模式三: 精准查看 (Precise)

```python
# Agent 调用方式 —— 必须同时指定 target_ports 和 session_id
sync_task_context(target_ports=8001, session_id="sub_87207465", reason="查看子任务完整对话")
```

**行为**:
- 向目标节点发送 `GET /api/context/leader_summary?app_name=*&user_id=dwh&session_id=sub_87207465`
- 返回该会话的**完整对话历史**（最近 100 条 event），而非仅摘要

**输出示例**:
```
[Swarm Task Detail Report]
========================================
User: dwh
Session: sub_87207465

[OK] Node 8001: 向 misc/test目录写入2个文件
     App: swarm_from_8000
     Messages: 12
     Conversation:
     User: 【背景】[Origin: Node 8000] ... 【任务】请在...
     Assistant: 好的，我来创建两个文件...
     Assistant: 文件已创建完成...

========================================
```

### 1.4 新增基础设施

为支撑三模式架构，新增了以下基础设施组件：

#### (A) `_get_all_nodes()` 函数 — 集群拓扑发现

```python
# tools.py (新增)
def _get_all_nodes(include_self=True) -> List[dict]:
    """
    获取所有在线节点（含或不含自身），用于广播查询。
    与 _get_active_workers 的区别：不排除自身节点。
    """
```

| 对比项   | `_get_active_workers` (旧)  | `_get_all_nodes` (新)      |
| -------- | --------------------------- | -------------------------- |
| 用途     | dispatch_task 找可用 Worker | sync_task_context 广播查询 |
| 含自身   | 永远排除自身                | `include_self` 参数控制    |
| 心跳检测 | 15秒超时                    | 15秒超时 (一致)            |

#### (B) `/api/context/user_sessions` API — 轻量级会话列表

```python
# main_web_start_steering.py (新增 API)
@app.get("/api/context/user_sessions")
async def get_user_sessions(user_id: str):
    """
    列出该用户名下的所有会话摘要（不含完整对话历史）。
    用于广播/定向发现模式。
    """
    sessions_response = await session_service.list_sessions(app_name="*", user_id=user_id)
    # ... 返回 [{session_id, app_name, title, task_type, updated_at}, ...]
```

**关键设计**: 
- 使用 `app_name="*"` **通配符查询**，不指定具体 app_name，确保能查到所有来源的 session
- 只返回元数据摘要（标题、类型、时间），不加载完整对话，保持轻量

#### (C) `/api/context/leader_summary` 增强 — 支持 session_id 精准查询

旧版只能查"最新会话"，新版增加了 `session_id` 参数：

```python
# main_web_start_steering.py (增强)
@app.get("/api/context/leader_summary")
async def get_leader_summary(
    app_name: str = DEFAULT_APP_NAME,
    user_id: str = DEFAULT_USER_ID,
    session_id: str = None,       # [新增] 精准定位
    limit: int = 1
):
    """
    支持两种模式：
    1. 精准模式: 传入 session_id -> 直接查该会话的完整对话
    2. 最新模式: 不传 session_id -> 查最新会话 (保持向后兼容)
    """
```

精准模式的会话查找也有容错:
1. 先尝试 `session_service.get_session(app_name, user_id, session_id)` 精确查
2. 如果失败（`app_name` 是通配符或不匹配），用 `list_sessions(app_name="*")` 全局扫描
3. 在全局列表中找到匹配的 `session_id` 后，再用其真实的 `app_name` 加载完整会话

### 1.5 完整实现详解

新版 `sync_task_context` 的核心调用流程图:

```
sync_task_context(reason, target_ports, session_id)
    |
    v
[1] 获取当前用户身份
    - 从 _app_info["user_id"] 获取
    - 兼容 Worker 模式: 从 session.state["original_user_id"] 获取真实人类 ID
    |
    v
[2] 确定目标端口 & 查询模式
    - target_ports=None -> broadcast, 调用 _get_all_nodes() 发现所有在线节点
    - target_ports=8001 -> targeted (无 session_id) 或 precise (有 session_id)
    - 支持 str/int/list 多种输入格式 (LLM 兼容)
    |
    v
[3] 并发查询 (asyncio.gather)
    |
    +-- broadcast/targeted --> _query_node_sessions(port)
    |   每个节点: GET /api/context/user_sessions?user_id=dwh
    |   返回: [{session_id, title, task_type, updated_at}, ...]
    |
    +-- precise --> _query_node_detail(port, session_id)
        目标节点: GET /api/context/leader_summary?app_name=*&user_id=dwh&session_id=sub_xxx
        返回: {title, app_name, recent_summary, total_messages}
    |
    v
[4] 格式化输出
    +-- _format_discovery_results() -> 发现报告 (含 session_id + Tip 提示)
    +-- _format_detail_results()    -> 详情报告 (含完整对话)
```

**函数签名**:

```python
async def sync_task_context(
    reason: str = "",                 # 同步原因
    target_ports = None,              # None=广播, int/List[int]=定向
    session_id: str = None,           # 精准模式用
    _session_service = None,          # [Internal] 由框架注入
    _app_info = None                  # [Internal] 由框架注入
) -> str:
```

**LLM 兼容性处理**: `target_ports` 支持 `int`, `str`, `List[int]`, JSON 字符串等多种格式，因为 LLM 可能输出不同类型（如 `"8001"`, `[8001, 8003]`, `"[8001]"`）。

### 1.6 附带修复: Session ID 截断

在实现三模式后发现广播报告中 session_id 被截断:

```python
# 修复前 (旧代码):
parts.append(f"     - [{sid[:8]}...] {title}{tag}")
#                       ^^^^^^^^^ 截成 "sub_8720..."

# 修复后:
parts.append(f"     - [{sid}] {title}{tag}  ({updated})")
#                       ^^^^ 完整显示 "sub_87207465"
```

**影响**: 截断后 Agent 拿不到完整 session_id，无法进入精准模式，三模式查询机制的链路被截断。

### 1.7 附带优化: 来源节点标记

在 `dispatch_task` 的消息体中注入 `[Origin: Node {PORT}]` 标记:

```python
# tools.py - dispatch_task
# 修复前:
full_message = f"【背景】\n{context_info}\n\n【任务】\n{task_instruction}..."

# 修复后:
full_message = f"【背景】\n[Origin: Node {CURRENT_NODE_PORT}]\n{context_info}\n\n【任务】\n{task_instruction}..."
```

**效果**: 在发现报告和精准查看中，都能看到每个任务是从哪个节点发起的，便于追溯调度链路。

---

## 问题二: Worker 任务无法中断 (Cancel 失效)

### 2.1 故障现象

用户在 Leader(8000) 的 Web UI 上点击 Worker(8003) 的卡片发送停止指令后：
- **前端**显示: `"Instruction sent to stop Worker-8003."`（看似成功）
- **Worker 端**: 任务继续执行，没有任何停止迹象
- **Worker 后台日志**: 无 cancel API 被调用的记录

### 2.2 根因定位: 三元组参数不匹配

**核心问题: `/api/stop_worker` 发给 Worker 的 cancel 请求中 `app_name` 和 `user_id` 都不匹配。**

Worker 端的 `session_manager` 使用 `(app_name, user_id, session_id)` 三元组作为 key 查找会话。

#### 请求链路

```
[前端 script.js]        [Leader main_web.py]         [Worker main_web.py]
       |                        |                           |
  点击"Stop"按钮          POST /api/stop_worker        POST /api/cancel
       |------- fetch() ------->|                           |
       |                        |--- httpx.post() --------->|
       |                        |                    session_manager.get()
       |                        |                    => 查找失败! (None)
       |<--- {status:success} --|                           |
       |                        |                    (静默失败，任务继续)
  显示 "Instruction sent"
```

#### dispatch_task 创建 Worker 会话时的参数

```python
# tools.py - dispatch_task
payload = {
    "app_name": f"swarm_from_{CURRENT_NODE_PORT}",  # 例: "swarm_from_8000"
    "user_id": _original_user_id,                    # 例: "dwh" (人类用户)
    "session_id": use_session_id                     # 例: "sub_87207465"
}
```

#### /api/stop_worker 发送 cancel 时用的参数 (BUG 所在)

```python
# main_web_start_steering.py - /api/stop_worker (修复前)
swarm_app_name = "adk_universal_swarm"           # 错! 应为 "swarm_from_8000"
leader_user_id = f"Agent_Node_{node_config.port}" # 错! 应为 "dwh"
```

#### 不匹配对照表

| 字段         | dispatch_task 创建时 | stop_worker 发送时    | 匹配? |
| ------------ | -------------------- | --------------------- | ----- |
| `app_name`   | `swarm_from_8000`    | `adk_universal_swarm` | X     |
| `user_id`    | `dwh`                | `Agent_Node_8000`     | X     |
| `session_id` | `sub_87207465`       | `sub_87207465`        | O     |

三元组中**两个字段不匹配** -> Worker 的 `session_manager.get()` 返回 `None` -> cancel 信号无法送达。

### 2.3 修复方案

#### 修复一: `/api/stop_worker` (Leader 端) — 修正 cancel 参数

```python
# main_web_start_steering.py (修复后)

# 修复前:
swarm_app_name = "adk_universal_swarm"
leader_user_id = f"Agent_Node_{node_config.port}"

# 修复后:
swarm_app_name = f"swarm_from_{node_config.port}"  # 与 dispatch_task 一致
human_user_id = request.user_id                     # 前端传来的真实人类用户 ID
```

#### 修复二: `/api/cancel` (Worker 端) — 三层渐进式容错搜索

改为三层搜索策略，确保即使参数有偏差也能找到目标会话：

```python
# main_web_start_steering.py - /api/cancel (修复后)

# 第1层: 精确匹配 (app_name, user_id, session_id) 三元组
session = session_manager.get(req.app_name, req.user_id, req.session_id)

if session is None:
    # 第2层: 忽略 app_name，匹配 user_id + session_id
    for (a_name, u_id, s_id), sess in session_manager._sessions.items():
        if u_id == req.user_id and s_id == req.session_id:
            session = sess
            break
    
    # 第3层兜底: 仅按 session_id 匹配 (session_id 是全局唯一 UUID)
    if session is None:
        for (a_name, u_id, s_id), sess in session_manager._sessions.items():
            if s_id == req.session_id:
                session = sess
                break
```

**三层搜索的设计哲学**: 在分布式系统中，参数经过多跳传递（前端 -> Leader -> Worker），每一跳都可能引入误差。`session_id` 作为创建时生成的 UUID，是整条链路中**最不可能被篡改的标识**，因此作为最终兜底。

#### 修复后的完整链路

```
[前端 script.js]        [Leader main_web.py]         [Worker main_web.py]
       |                        |                           |
  点击"Stop"按钮          POST /api/stop_worker        POST /api/cancel
       |------- fetch() ------->|                           |
       |                 构造正确参数:                        |
       |                 app_name=swarm_from_8000             |
       |                 user_id=dwh (人类用户)               |
       |                        |--- httpx.post() --------->|
       |                        |                    session_manager.get()
       |                        |                    => 精确匹配成功!
       |                        |                    session.queue.put("CANCEL")
       |<--- {status:success} --|                           |
  显示 "Instruction sent"                            (任务停止)
```

---

## 修改文件清单

### `skills/agent_team/tools.py` (4 处改动)

| 位置     | 改动类型 | 内容                                                   | 影响                                            |
| -------- | -------- | ------------------------------------------------------ | ----------------------------------------------- |
| L74-103  | **新增** | `_get_all_nodes(include_self)` 函数                    | 广播模式的集群拓扑发现                          |
| L202     | 增强     | 注入 `[Origin: Node {PORT}]` 标记                      | 任务来源可追溯                                  |
| L390-504 | **重写** | `sync_task_context` 三模式架构                         | 从 worker_name 查询转为 user_id+session_id 查询 |
| L507-582 | **新增** | `_format_discovery_results` + `_format_detail_results` | 发现报告 + 详情报告格式化                       |

### `src/adk_agent/main_web_start_steering.py` (4 处改动)

| 位置       | 改动类型 | 内容                                                     | 影响                    |
| ---------- | -------- | -------------------------------------------------------- | ----------------------- |
| L1441-1465 | 增强     | `/api/cancel` 三层渐进式容错搜索                         | cancel 容错性极大提升   |
| L1511-1512 | 修复     | `/api/stop_worker` 修正 `app_name` 和 `user_id`          | 恢复 Worker 中断能力    |
| L1841-1879 | **新增** | `/api/context/user_sessions` API                         | 广播/定向模式的查询后端 |
| L1882-1975 | 增强     | `/api/context/leader_summary` 增加 `session_id` 精准查询 | 精准模式的查询后端      |

---

## 验证结果

### sync_task_context 三模式验证

编写自动化测试脚本覆盖 4 大测试区域、28 个测试点，全部通过：

```
== Test 1: _get_all_nodes() ==
  [PASS] _get_all_nodes is callable
  [PASS] Returns list with 5 nodes
  [PASS] _get_all_nodes(include_self=False) == _get_active_workers()

== Test 2: sync_task_context 参数解析 ==
  [PASS] reason parameter exists
  [PASS] session_id default is None
  [PASS] Docstring contains 'broadcast' / 'targeted' / 'precise'

== Test 3: 格式化函数 ==
  [PASS] Discovery report shows full session_id  (核心验证点)
  [PASS] Discovery report shows task title
  [PASS] Discovery report includes 'Tip' with follow-up command
  [PASS] Detail report shows session_id

== Test 4: API Endpoints (Live) ==
  [PASS] /api/context/user_sessions returns correct schema
  [PASS] leader_summary with bad session_id returns error
  [PASS] leader_summary(session_id=...) precise query works

==================================================
Results: 28 passed, 0 failed, 0 skipped
==================================================
```

### Worker 中断验证

修复后 Leader 端日志:
```
[API] Request to stop worker 8003 (Session: sub_fa5615f2)
 -> Sending Cancel to http://localhost:8003 for swarm_from_8000/dwh/sub_fa5615f2
 -> Success
```

Worker 端日志:
```
[API] Cancel: exact match -> swarm_from_8000/dwh/sub_fa5615f2
[API] Cancel signal sent -> sub_fa5615f2
```

---

## 经验总结与防御建议

### 1. 身份标识:以人类用户为锚点

**教训**: 旧代码中，有的地方用 `Agent_Node_8001`（Agent 自称）作 `user_id`，有的用 `dwh`（人类用户）。两套标识体系混用导致所有基于 `user_id` 的查询都可能失败。

**原则**: 在 Swarm 中，所有 session 的 `user_id` 统一使用**人类用户 ID**。Agent 身份通过 `app_name`（如 `swarm_from_8000`）来区分，而不是侵入 `user_id` 字段。

### 2. 查询模式: 从"知道名字才能查"到"先发现再深入"

**教训**: 旧的 `sync_task_context` 要求 Agent 事先知道 Worker 的名字才能查询，但 Agent 经常不知道、或者名字格式不对。

**原则**: 采用**发现 -> 确认 -> 深入**的渐进式查询模式:
1. 广播发现: "集群里有什么?"（不需要任何前置知识）
2. 定向查看: "8001 上有什么?"（确认目标后收窄范围）
3. 精准查看: "sub_87207465 的完整对话是什么?"（用第一步返回的 session_id）

### 3. 参数一致性:dispatch 和 cancel 是同一生命周期

**教训**: `dispatch_task` 和 `/api/stop_worker` 是同一个 Swarm 任务生命周期的"创建"和"终止"阶段，但它们对 `app_name` 和 `user_id` 的定义完全不同。

**防御**: 将 Swarm 的关键参数（`app_name` 模板、`user_id` 策略）提取为**共享常量**:
```python
# 建议: 在 config.py 或 tools.py 中统一定义
SWARM_APP_NAME_TEMPLATE = "swarm_from_{port}"
# 所有引用处统一使用此模板，杜绝硬编码
```

### 4. 容错搜索: session_id 是最可靠的锚

**教训**: 在分布式系统中，参数经过多跳传递（前端 -> Leader -> Worker），每一跳都可能引入漂移。

**原则**: 
- 精确匹配优先，但必须有 fallback
- `session_id` 作为创建时生成的 UUID，是**最稳定的标识**，应作为最终兜底依据
- 三层搜索模式: `(app_name+user_id+session_id)` -> `(user_id+session_id)` -> `(session_id)`

### 5. Session ID 不截断

**教训**: 任何用于后续操作的标识符都不应被截断显示。`sid[:8]` 让 Agent 丢失了精准查询的能力。

**原则**: 在 Agent 工具的返回值中，**永远显示完整 ID**。如果 ID 太长影响人类阅读，可以在 UI 层面缩略，但工具返回值必须保持完整。

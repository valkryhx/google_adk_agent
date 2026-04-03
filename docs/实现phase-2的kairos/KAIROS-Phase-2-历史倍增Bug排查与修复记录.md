# KAIROS Phase 2 历史倍增 Bug 排查与修复记录

> 记录时间: 2026-04-04
> 适用范围: `main_web_start_steering.py` / KAIROS wake 流程 / session 持久化

---

## 1. 问题现象

用户在真实前端链路中复现到如下问题：

1. 新建会话
2. 发送 `hi`
3. agent 正常回复
4. 启动 KAIROS
5. 点击「唤醒」
6. 历史消息出现倍增
7. 继续点击「唤醒」，旧消息继续按倍数增长

典型表现：

- 唤醒前 history 只有 2 条消息（user/model 各 1 条）
- 唤醒后变成 4 条、6 条甚至更多
- 重复出来的旧消息 `invocation_id` 相同，说明不是新生成消息，而是旧 history 被重复写入

---

## 2. 最初怀疑点与排除过程

### 2.1 前端重复渲染

最先发现前端确实有一个真实问题：

- `src/adk_agent/static/script.js` 的 `loadSessionHistory()` 在某些场景会把同一批历史再次 append 到 DOM
- `wakeKairos()` 触发 history reload 时，也可能放大这个表现

这个问题会导致 **“看起来重复”**，但它不是最终根因。

排查结果：

- 前端 DOM 清空后再重载，UI 层重复可以消失一部分
- 但真实数据库里的 event 行数仍然在增加
- 因此确认：**前端只是放大器，不是最终元凶**

### 2.2 `SessionManager.get_or_create()` 是否重复处理 `session.events`

用户明确要求检查这个点。

排查结果：

- `SessionManager.get_or_create()` 只是按 `(app_name, user_id, session_id)` 做缓存命中或创建 `SteeringSession`
- 这个方法本身不追加 `events`、不复制 `events`、不做持久化

结论：

- **`SessionManager.get_or_create()` 不是历史倍增根因**

### 2.3 history API 是否自己拼错了消息

继续检查 `GET /api/sessions/{session_id}/history`。

排查结果：

- history API 只是读取 session 中已有 events，再做 rewind-aware 过滤和格式转换
- 它不会凭空造出重复消息

结论：

- **history API 只是把已持久化的重复数据返回给前端**

---

## 3. 真正根因

### 3.1 KAIROS 的 state-only 更新错误地走了 full save

关键路径在：

- `src/adk_agent/main_web_start_steering.py`
- `SteeringSession._save_kairos_state()`

旧逻辑：

```python
async def _save_kairos_state(self, kairos_state):
    session = await self.session_service.get_session(...)
    if not session:
        session = await self.session_service.create_session(...)
    if not session.state:
        session.state = {}
    session.state["kairos"] = dump_kairos_state(kairos_state)
    await self.session_service.save_session(session)
```

表面上看它只是更新 `session.state["kairos"]`，但实际上调用的是：

- `FullyCustomDbService.save_session(session)`

而这个方法是 **全量保存**，不仅写 state，还会整份重建 `db_session.events`。

### 3.2 DB 层的 `save_session()` 会整份重写 events

关键路径在：

- `src/shared/db/custom_table_db_service.py`
- `FullyCustomDbService.save_session()`

旧逻辑核心：

```python
new_db_events = []
for evt in session.events:
    new_db_events.append(self.DbEvent(...))

db_session.events = new_db_events
```

也就是说：

- 只要走 `save_session()`
- 即便你只改了 `state`
- DB 层仍然会整份替换 events relationship

在 KAIROS 的 start / wake / tick 高频保存场景里，这就变成了风险点。

### 3.3 在 KAIROS 高频保存与并发场景下，旧 history 被重复写入

KAIROS 的 wake/start 会频繁触发：

- `_record()`
- `_persist()`
- `_save_kairos_state()`

这些调用叠加后，导致：

- 同一个 session 的 events 被多次整份重写
- 最终数据库里出现同一批旧消息被复制
- 这些重复消息共享相同 `invocation_id`

这和用户观察到的现象完全一致。

---

## 4. 额外发现的第二个问题：sandbox API 误用

在真实验证过程中，又发现一个独立但相关的问题：

- sandbox 路径使用了 `google.adk.sessions.InMemorySessionService`
- 但代码错误调用了不存在的 `save_session()`
- 同时还混用了错误的 `get_session(...)` 调用形式

旧逻辑问题点：

```python
active_session_service = InMemorySessionService()
...
await active_session_service.save_session(sandbox_session)
```

实际排查 ADK 本地安装包后确认：

- `InMemorySessionService` 有：`create_session(...)`
- 有：`get_session(...)`
- 有：`append_event(...)`
- **没有：`save_session(...)`**

这会导致：

- sandbox turn 报错
- 或者绕回真实 DB 的持久化路径，放大历史污染风险

---

## 5. 修复思路

修复原则只有一句话：

> **只改 state 的地方，绝不能再走 full save。**

### 5.1 在 DB service 中新增 state-only 持久化接口

修改文件：

- `src/shared/db/custom_table_db_service.py`

新增方法：

- `save_session_state(app_name, user_id, session_id, state)`

这个接口只做两件事：

1. 更新 `session_metadata`
2. 更新 `updated_at`

明确不做的事：

- 不重建 `db_session.events`
- 不碰已有 event rows

这样就把 **state 更新** 和 **events 重写** 拆开了。

### 5.2 把 KAIROS 的 state 持久化切到 state-only 路径

修改文件：

- `src/adk_agent/main_web_start_steering.py`

新增：

- `SteeringSession._persist_session_state()`

并让 `_save_kairos_state()` 改为：

- 先拿当前 session.state
- 更新 `state["kairos"]`
- 调用 `_persist_session_state()`

结果：

- wake/start/tick 期间只更新 kairos runtime state
- 不再重写旧会话历史

### 5.3 修复 sandbox 初始化方式

修改文件：

- `src/adk_agent/main_web_start_steering.py`

新的 sandbox 初始化方式：

1. `InMemorySessionService.create_session(...)`
2. 把真实 session 的 state 克隆进去
3. 再把真实 session 的 events 克隆到内存存储对象里

这样做的目的：

- KAIROS sandbox 能看到真实上下文
- 但中间思考和后台 turn 不会写回真实 DB

### 5.4 修复 sandbox 退出时的回写方式

旧问题：

- sandbox 结束时把 state merge 回真实 session 后，仍然调用 full `save_session()`

新逻辑：

- 只把 sandbox 里新变化的 state merge 到真实 state
- 再调用 `save_session_state(...)`

结果：

- 保留系统状态更新
- 不污染真实 history

### 5.5 进一步收缩其他 state-only 保存路径

这次顺手把同类风险点也一并改了：

- 自动生成 `title` 时
- 自动恢复 `task_type` 时
- session metadata 更新接口时
- 普通 turn finally 合并 state 时

凡是“只改 state”的路径，都优先走 state-only 保存。

这样可以避免后续同类问题从别的入口再次出现。

---

## 6. 验证过程

### 6.1 单元/回归测试

新增测试：

- `tests/kairos/test_db_state_only_persistence.py`

验证目标：

- 初始先写入 2 条 event
- 连续多次调用 `save_session_state(...)`
- 最终 session.events 仍然是原来的 2 条

结果：

- 通过

已有测试：

- `tests/kairos/test_kairos_no_pollution.py`

结果：

- 通过

### 6.2 真实 HTTP 链路验证

新增 live 回归脚本：

- `tests/kairos/live_http_kairos_regression.py`

真实链路：

1. 启动本地服务 `http://127.0.0.1:8000`
2. 创建新 session
3. 发送 `hi`
4. 确认 history 为 2 条
5. 启动 KAIROS
6. 连续 wake 3 次
7. 等待 KAIROS 回到非 busy
8. 再查 history

实测结果：

- `history before kairos: 2 messages`
- `history after kairos: 2 messages`
- `PASS: wake did not duplicate chat history`

同时日志里也确认：

- 出现了 `Merged state-only session ... (Events: 2)`
- 出现了 `Sandbox] 沙盒安全销毁，仅保留系统状态变更。`
- 没再出现 `InMemorySessionService.save_session` 相关错误
- 没再出现 `Session state synchronization failed`

---

## 7. 最终结论

这次 bug 的真正根因不是前端，不是 `SessionManager.get_or_create()`，也不是 history API。

真正根因是：

> **KAIROS 的 state-only 持久化错误地走了 full `save_session()`，而 full save 会整份重写 events；在 wake/start/tick 高频保存过程中，旧 history 因此被重复写回数据库。**

配套问题是：

> **sandbox 错用了 `InMemorySessionService` 的 API，导致隔离路径不可靠。**

最终修复是：

1. 新增 DB 层 `save_session_state(...)`
2. KAIROS state 更新全部切到 state-only 持久化
3. sandbox 初始化和退出全部改成只隔离/回写 state
4. 补 DB 回归测试和 live HTTP 回归脚本

修复后的真实结果已经验证：

- `hi -> agent reply -> start kairos -> 多次 wake`
- 历史消息不再倍增

---

## 8. 相关文件

### 核心修复
- `src/shared/db/custom_table_db_service.py`
- `src/adk_agent/main_web_start_steering.py`

### 回归测试
- `tests/kairos/test_db_state_only_persistence.py`
- `tests/kairos/live_http_kairos_regression.py`

### 相关历史问题背景
- `src/adk_agent/static/script.js`
- `tests/kairos/test_kairos_no_pollution.py`

---

## 9. 推荐后续动作

1. 把 `live_http_kairos_regression.py` 纳入手工 smoke checklist
2. 后续如果继续演进 KAIROS persistence，默认遵循：
   - 改 history → full save
   - 只改 state → state-only save
3. 若未来还要排查类似问题，优先检查：
   - 是否误走 `save_session()`
   - 是否有 sandbox / background turn 绕回真实 DB

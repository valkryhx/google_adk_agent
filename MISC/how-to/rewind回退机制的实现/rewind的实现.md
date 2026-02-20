# Rewind（对话回退）机制的完整实现

> **文档目的**：记录从需求提出到代码落地的全过程，包含每一个 bug 的根本原因和修复细节。
> **覆盖范围**：后端 ADK 原理、后端接口、前端 UI、所有后续 bug 修复。

---

## 1. 需求背景

用户在与 Agent 对话时，希望能"撤回"某一条历史消息，让 Agent **忘掉该消息及其之后的所有交互**，重新从该节点开始对话。

这个功能在 LLM 应用中称为 **Rewind（时间线回退）**，类似 Git 的 `git revert` 概念：不是删除历史记录，而是在时间线末尾插入一个"撤销"标记。

### 用户期望的 UX 流程

1. 鼠标悬停在某条**用户气泡**上 → 出现编辑图标
2. 点击图标 → 弹出确认框
3. 确认后：
   - 该消息的**原始文本**自动回填到输入框
   - 该消息及其之后的所有气泡从界面消失
   - Agent 的"记忆"也被抹除到该节点之前
4. 用户修改文本后重新发送 → 对话在新的"时间线"上继续

---

## 2. ADK 的 Rewind 原理

### 2.1 不删除记录，而是插入标记

Google ADK 的 `runner.rewind_async` **不会物理删除**数据库中的历史事件。相反，它在事件列表末尾**追加一个特殊的"回退标记"事件**：

```python
# google.adk.runner.Runner.rewind_async 的核心逻辑
rewind_event = Event(
    invocation_id=new_invocation_context_id(),
    author='user',
    actions=EventActions(
        rewind_before_invocation_id=rewind_before_invocation_id,  # 目标节点 ID
        state_delta=state_delta,    # 需要撤销的状态变更
        artifact_delta=artifact_delta,  # 需要撤销的文件变更
    ),
)
await self.session_service.append_event(session=session, event=rewind_event)
```

### 2.2 Agent 如何"遗忘"

ADK 在每次 `run_async` 前，会调用 `_get_contents()` 将事件列表转换为 LLM 的 context。该函数实现了 rewind 感知的过滤逻辑：

```python
# google.adk.flows.llm_flows.contents._get_contents (伪代码)
def _get_contents(events):
    i = len(events) - 1
    rewind_filtered_events = []
    while i >= 0:
        event = events[i]
        if event.actions and event.actions.rewind_before_invocation_id:
            # 遇到 rewind 标记 → 跳回目标 invocation_id 的起始位置
            rewind_invocation_id = event.actions.rewind_before_invocation_id
            for j in range(0, i):
                if events[j].invocation_id == rewind_invocation_id:
                    i = j  # 跳回
                    break
        else:
            rewind_filtered_events.append(event)
        i -= 1
    rewind_filtered_events.reverse()
    return rewind_filtered_events
```

**结论**：DB 中的事件顺序是：  
`A → B → C → [REWIND标记(target=B)] → D → E`

ADK 构建 context 时跳过 `B, C, [标记]`，只看 `A, D, E`。这样 Agent 就"忘记"了 B 和 C，同时保留了 rewind 后新产生的 D、E 对话。

---

## 3. 后端实现

### 3.1 新增 `/api/sessions/{session_id}/rewind` 接口

在 `main_web_start_steering.py` 中新增 POST 接口：

```python
@app.post("/api/sessions/{session_id}/rewind")
async def rewind_session_endpoint(session_id: str, request: Request):
    body = await request.json()
    app_name   = body.get("app_name", DEFAULT_APP_NAME)
    user_id    = body.get("user_id", DEFAULT_USER_ID)
    invocation_id = body.get("invocation_id")

    runner = Runner(
        agent=steering_sessions[...].agent,
        app_name=app_name,
        session_service=session_service
    )
    await runner.rewind_async(
        user_id=user_id,
        session_id=session_id,
        rewind_before_invocation_id=invocation_id
    )
    return {"status": "success"}
```

### 3.2 Bug Fix 1：`Runner is not defined`

**现象**：调用 rewind 接口时，后端报 `NameError: name 'Runner' is not defined`。

**原因**：`main_web_start_steering.py` 中未导入 `Runner` 类。

**修复**：在文件顶部添加：

```python
from google.adk import Runner
```

### 3.3 History API 的 Rewind 感知（最核心的修复）

**问题**：页面刷新后，被 rewind 的消息仍然显示在界面上。

**根本原因**：`/api/sessions/{session_id}/history` 接口直接遍历 `session.events`，不了解 rewind 标记，把所有事件都返回给前端，包括已被"撤销"的部分。

**错误版本**（只截断，但会丢掉标记后的新对话）：

```python
# 旧代码 - 有 bug！
if cutoff_invocation_id:
    for event in session.events:
        if ev_inv_id == cutoff_invocation_id:
            break  # 直接 break，把 rewind 后新发的对话 D、E 全丢了！
        effective_events.append(event)
```

**正确版本**（索引排除法，镜像 ADK 的 `_get_contents`）：

```python
# 正确代码
events_list = session.events
exclude_indices = set()

for marker_idx, event in enumerate(events_list):
    actions = getattr(event, 'actions', None)
    if not actions:
        continue
    rewind_target = getattr(actions, 'rewind_before_invocation_id', None)
    if not rewind_target:
        continue

    # 找到目标 invocation_id 在标记之前最早出现的位置
    target_start_idx = None
    for j in range(marker_idx):
        if getattr(events_list[j], 'invocation_id', None) == rewind_target:
            target_start_idx = j
            break

    if target_start_idx is not None:
        # 排除 [target_start_idx, marker_idx] 区间（含标记自身）
        for k in range(target_start_idx, marker_idx + 1):
            exclude_indices.add(k)

effective_events = [e for idx, e in enumerate(events_list) if idx not in exclude_indices]
```

**算法图示**：

```
DB 事件索引:  0    1    2    3(标记)    4    5
事件内容:     A    B    C    REWIND→B   D    E
排除索引:          [1   2    3]
有效事件:     A                          D    E
```

---

## 4. 前端实现

### 4.1 在用户气泡上添加悬浮编辑按钮

修改 `appendMessage()` 函数，增加 `invocationId` 参数。当 `role === 'user'` 且有 `invocationId` 时，注入编辑按钮 HTML：

```javascript
function appendMessage(role, text, isLoading, appName, images, invocationId = null) {
    const msgDiv = document.createElement('div');
    msgDiv.dataset.rawText = encodeURIComponent(text || '');  // 保存原始文本
    if (invocationId) msgDiv.dataset.invocationId = invocationId;

    let actionHtml = '';
    if (role === 'user' && invocationId) {
        actionHtml = `
            <div class="msg-actions">
                <button class="icon-btn rewind-btn" title="回退并重新编辑"
                    onclick="window.triggerRewind('${invocationId}', '${id}')">
                    <span class="material-symbols-outlined">edit</span>
                </button>
            </div>
        `;
    }
    // ...
}
```

### 4.2 刷新历史时传入 `invocation_id`

从后端 history API 拿到历史消息后，把 `msg.invocation_id` 传给 `appendMessage`：

```javascript
appendMessage('user', msg.text, false, 'Ciri', msg.images || [], msg.invocation_id);
```

同时后端 history API 也需要在每条 user message 上附上 `invocation_id`：

```python
messages.append({
    "role": "user",
    "text": text_content,
    "invocation_id": getattr(event, 'invocation_id', None),
    # ...
})
```

### 4.3 `triggerRewind` 核心函数

```javascript
window.triggerRewind = async function (invocationId, msgId) {
    if (!confirm('确定要修改？此节点之后的对话记忆将被抹除')) return;

    const msgEl = document.getElementById(msgId);
    const rawText = decodeURIComponent(msgEl.dataset.rawText || '');

    // 1. 调用后端 rewind 接口（兼容 Swarm 模式的 appName）
    let rewindAppName = APP_NAME;
    const isSwarm = sessionStorage.getItem('current_is_swarm');
    const leaderPort = sessionStorage.getItem('current_leader_port');
    if (isSwarm === 'true' && leaderPort) {
        rewindAppName = `swarm_from_${leaderPort}`;
    }

    const response = await fetch(`/api/sessions/${currentSessionId}/rewind`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            app_name: rewindAppName,
            user_id: getUserId(),
            invocation_id: invocationId
        })
    });

    const res = await response.json();
    if (res.status === 'success') {
        // 2. 原始文本回填到输入框
        userInput.value = rawText;
        userInput.style.height = 'auto';
        userInput.style.height = userInput.scrollHeight + 'px';
        userInput.focus();

        // 3. 从该气泡开始往后，清除所有 DOM 元素
        let currentEl = msgEl;
        while (currentEl) {
            let nextEl = currentEl.nextElementSibling;
            currentEl.remove();
            currentEl = nextEl;
        }

        // 4. 保持 chat-mode（输入框可见）
        document.getElementById('welcomeScreen').style.display = 'none';
        document.body.classList.remove('welcome-mode');
        document.body.classList.add('chat-mode');
    }
};
```

### 4.4 CSS 样式

```css
/* 用户气泡右上角悬浮操作区 */
.message.user .message-content {
    position: relative;
}

.msg-actions {
    position: absolute;
    top: -12px;
    right: -12px;
    opacity: 0;
    transition: opacity 0.2s, transform 0.2s;
    transform: translateY(5px);
    background: var(--bg-color);
    border-radius: 50%;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    z-index: 10;
}

/* 鼠标悬停时显示按钮 */
.message.user .message-content:hover .msg-actions {
    opacity: 1;
    transform: translateY(0);
}
```

---

## 5. 后续 Bug 修复记录

### 5.1 Bug：Rewind 后输入框消失

**现象**：点击 rewind 后，聊天输入框消失，无法继续输入。

**根本原因**：清除气泡后，旧代码检查 `chatContainer.children.length === 0` 来决定是否切换到"欢迎模式"（welcome-mode）。welcome-mode 会重新布局输入框，视觉上看起来像"消失"了。

**代码 diff（旧 → 新）**：

```javascript
// 旧代码（有 bug）
if (chatContainer.children.length === 0 || chatContainer.children[0].id === 'welcomeScreen') {
    document.getElementById('welcomeScreen').style.display = 'flex';
    document.body.classList.remove('chat-mode');
    document.body.classList.add('welcome-mode');  // 切到欢迎模式 → 输入框"消失"
}

// 新代码（修复）
// rewind 后始终保持 chat-mode，用户还需要重新输入
const welcomeScreenEl = document.getElementById('welcomeScreen');
if (welcomeScreenEl) welcomeScreenEl.style.display = 'none';
document.body.classList.remove('welcome-mode');
document.body.classList.add('chat-mode');
```

---

### 5.2 Bug：Rewind 后新对话刷新后消失

**现象**：rewind 完成后继续对话，前端显示正常，但页面刷新后新对话全部消失。

**根本原因**：history API 的旧代码用 `break at cutoff_invocation_id`，一刀切掉了从 rewind 目标起的**所有**后续事件，包括新产生的对话 D、E。

**修复**：改为基于**索引排除集合**的方式（见第 3.3 节），只排除 `[被撤销的起始索引, rewind标记索引]` 区间，标记之后的新事件全部保留。

---

### 5.3 Bug：新 Session 首条消息是 Swarm 任务时，侧边栏不显示 Leader 标记且名称为"新对话"

**现象**：如果打开一个全新的对话，第一句就使用 `dispatch_batch_tasks`，侧边栏始终显示"新对话"，没有 `[Agent-Team-LEADER]` 标记。如果先发一条普通消息再发 Swarm 任务，则正常。

**根本原因链**：

```
新 Session 的流程：
1. get_session() → 返回 None
2. self._current_session = None   ← 赋值 None
3. create_session() → 创建新 session 对象
4. ← 忘记更新 self._current_session ！
5. dispatch_batch_tasks() 触发 update_session_state 信号
6. report_swarm_event() 检查 if self._current_session → None → 直接 return
7. task_type = 'swarm_leader' 被丢弃
```

**修复**：在 `create_session` 成功后立即更新 `_current_session`：

```python
# main_web_start_steering.py
if not session:
    session = await self.session_service.create_session(
        app_name=self.app_name,
        user_id=self.user_id,
        session_id=self.session_id
    )
    # [修复] 新创建的 session 也要绑定到 _current_session
    self._current_session = session  # ← 关键修复
```

---

### 5.4 Bug：侧边栏标题需要手动刷新才更新

**现象**：对话完成后，侧边栏的 session 标题和 Leader 标记不会自动更新，必须刷新整个页面。

**两层原因**：

1. **前端从不主动刷新列表**：流式响应结束后，`loadSessions()` 从未被调用。
2. **时序竞争**：即使立刻调用 `loadSessions()`，后端的 `save_session` 可能还未执行完毕（它在最后一个 `yield` 之后才写 DB）。

**修复**：流式响应结束后，延迟 800ms 调用 `loadSessions()`：

```javascript
// 流式完成后（在 markSwarmTasksFinished 之后）
setTimeout(
    () => loadSessions().catch(e => console.warn('loadSessions failed:', e)),
    800  // 等后端 save_session 写完 DB
);
```

---

### 5.5 Bug：Rewind 首条消息后，新对话标题仍显示"新对话"

**现象**：rewind 掉第一条消息后，重新发新消息，侧边栏标题不更新，仍然是"新对话"。

**根本原因**：标题自动生成逻辑计数用户事件时，遍历的是 `session.events`（全部原始事件），没有排除已被 rewind 的部分。因此即使第一条消息已被 rewind，计数仍 `> 0`，不会触发标题更新。

**修复**：在标题计数逻辑中，先用同样的索引排除算法过滤掉被 rewind 的事件：

```python
# 标题自动生成 - rewind 感知版
_title_events = session.events if session else []
_title_exclude = set()

for _midx, _mev in enumerate(_title_events):
    _mactions = getattr(_mev, 'actions', None)
    if not _mactions: continue
    _mtarget = getattr(_mactions, 'rewind_before_invocation_id', None)
    if not _mtarget: continue
    for _j in range(_midx):
        if getattr(_title_events[_j], 'invocation_id', None) == _mtarget:
            for _k in range(_j, _midx + 1):
                _title_exclude.add(_k)
            break

# 只计数有效（未被 rewind）的 user 事件
user_event_count = 0
for _tidx, evt in enumerate(_title_events):
    if _tidx in _title_exclude: continue
    role = getattr(evt.content, 'role', None) or getattr(evt, 'author', 'unknown')
    if role == 'user':
        user_event_count += 1

if user_event_count == 0:
    # 首次有效消息 → 生成标题
    title = task[:30] + ("..." if len(task) > 30 else "")
    session.state['title'] = title
    await self.session_service.save_session(session)
```

---

## 6. 整体架构图

```
用户点击编辑按钮
        │
        ▼
[前端] triggerRewind(invocationId, msgId)
        │
        ├─ POST /api/sessions/{id}/rewind
        │         │
        │         ▼
        │  [后端] runner.rewind_async()
        │         │
        │         └─ 向 DB 追加 REWIND 标记事件
        │
        ├─ 原始文本回填到 input
        │
        └─ 清除 DOM 中该节点及后续气泡
                  │
                  ▼
        保持 chat-mode，用户重新输入
                  │
                  ▼
[前端] sendMessage() → POST /api/chat
                  │
                  ▼
[后端] runner.run_async()
       _get_contents() 自动跳过 rewind 区间
       Agent 看不到被 rewind 的对话
                  │
                  ▼
流式响应结束 → setTimeout(loadSessions, 800)
       侧边栏自动更新标题和 Leader 标记
```

---

## 7. 涉及文件变更汇总

| 文件 | 变更描述 |
|------|---------|
| `main_web_start_steering.py` | 新增 `/rewind` 接口；添加 `Runner` 导入；History API 改为索引排除法；`create_session` 后绑定 `_current_session`；标题生成使用 rewind 感知计数 |
| `static/script.js` | `appendMessage` 新增 `invocationId` 参数和编辑按钮 HTML；新增 `triggerRewind` 函数；Swarm 模式 appName 兼容；流式结束后 800ms 刷新 sidebar；History 拉取补全参数 |
| `static/style.css` | 新增 `.msg-actions`、`.rewind-btn` 悬浮编辑按钮样式；用户气泡加 `position: relative` |

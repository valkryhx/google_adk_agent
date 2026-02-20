这是一份为你量身定制的**“Google ADK 原生 Rewind (时光倒流) 功能接入全指南”**。你可以直接对照这份指南，一步步完成代码的复制粘贴和修改。

第一部分：为何引入 Rewind (时光倒流)？
在复杂的 Agent（智能体）交互中，Agent 极易因为某一步的错误理解或工具调用失败，陷入**“幻觉死循环”**。无论用户之后怎么纠正，前面的错误上下文都会持续污染大模型的判断。

引入基于 Google ADK 原生 runner.rewind_async 的回退机制，具有以下战略级优势：

认知洗脑 (Cognitive Rollback)：精准截断并遗忘指定回合（invocation_id）之后的所有对话、思考过程和工具调用日志，彻底打破幻觉链。

状态自动修正 (State Reversion)：原生的 ADK 回退会自动逆转会话状态（session.state），保证 Agent 的全局变量不会因为记忆消除而产生错位。

极致的用户体验 (Undo & Edit)：配合前端的“内容回填”，用户点击撤销后，之前的长段提示词会自动回到输入框供修改重发，体验丝滑（媲美 Cursor/ChatGPT）。

务实的工程边界：当前版本仅做“洗脑回退”，不自动做“洗地（物理文件/数据库回滚）”。遇到 Agent 弄乱文件的极端情况，通过“人类兜底（Human-in-the-loop）”手动修复文件，然后使用洗脑回退让 Agent 重新干活，这是兼顾安全性与开发成本的最佳实践。

第二部分：后端代码修改 (main_web_start_steering.py)
后端的修改分为两步：暴露调用 ID 给前端，以及增加回退接口。

1. 完善历史记录接口，暴露 invocation_id
找到 @app.get("/api/sessions/{session_id}/history") 路由，定位到大约 870 行左右组装 msg_data 的位置，增加一行代码：

Python
            if role == 'user' or role == 'model':
                msg_data = {
                    "role": role,
                    "blocks": merged_blocks,
                    "text": text_content,
                    # 👇 [必须新增这行] 暴露 invocation_id 给前端
                    "invocation_id": getattr(event, 'invocation_id', None)
                }
                # [多模态] 如果有图片，附加到消息中
                if images:
                    msg_data["images"] = images
                messages.append(msg_data)
2. 新增原生 Rewind API 接口
在 main_web_start_steering.py 中（建议放在 /api/cancel 路由附近），先确保文件顶部导入了相关的类，然后加入完整的路由代码：

Python
# 确保在文件顶部或合适位置有此导入
from google.adk.runners import Runner
from pydantic import BaseModel

class RewindRequest(BaseModel):
    app_name: str = DEFAULT_APP_NAME
    user_id: str = DEFAULT_USER_ID
    invocation_id: str

@app.post("/api/sessions/{session_id}/rewind")
async def rewind_session_endpoint(session_id: str, req: RewindRequest):
    """
    [新增] 原生轻量级回退 (纯上下文洗脑)
    重置 Agent 的记忆和状态，不处理外部物理文件。
    """
    global session_manager
    if session_manager is None:
        return {"status": "error", "message": "SessionManager not initialized"}
        
    try:
        # 1. 获取当前会话 (支持多租户隔离)
        steering_session = session_manager.get_or_create(req.app_name, req.user_id, session_id)
        
        # 2. 实例化原生 Runner
        runner = Runner(
            agent=steering_session.agent, 
            app_name=req.app_name, 
            session_service=steering_session.session_service
        )
        
        print(f"⏪ [Rewind] 准备清除 Session {session_id} 的不良记忆 (目标节点: {req.invocation_id})...")
        
        # 3. 执行原生洗脑（底层会自动计算状态差，并触发 DB 的孤儿级联删除）
        await runner.rewind_async(
            user_id=req.user_id,
            session_id=session_id,
            rewind_before_invocation_id=req.invocation_id
        )
        
        print(f"✅ [Rewind] 记忆清洗完成！Agent 已恢复到该节点前的干净状态。")
        return {"status": "success", "message": "Context rewound successfully."}
        
    except Exception as e:
        print(f"❌ [Rewind] 回退失败: {e}")
        return {"status": "error", "message": str(e)}
第三部分：前端代码修改 (script.js & style.css)
前端的修改核心是渲染隐藏的悬浮按钮，并在点击时实现乐观UI清除和输入框回填。

1. 增加 CSS 悬浮按钮样式 (style.css)
在你的 style.css 文件末尾，直接追加以下样式：

CSS
/* =========================================
   回退与重新编辑按钮样式
   ========================================= */
.message.user .message-content {
    position: relative;
}

.msg-actions {
    position: absolute;
    top: -12px;
    right: -12px;
    opacity: 0;
    transition: opacity 0.2s cubic-bezier(0.4, 0, 0.2, 1), transform 0.2s;
    transform: translateY(5px);
    background: var(--bg-color);
    border-radius: 50%;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    z-index: 10;
}

/* 鼠标悬停在用户气泡上时显示编辑按钮 */
.message.user .message-content:hover .msg-actions {
    opacity: 1;
    transform: translateY(0);
}

.rewind-btn {
    width: 32px;
    height: 32px;
    padding: 0;
    background: transparent;
    border: 1px solid rgba(0,0,0,0.05);
}

.rewind-btn .material-symbols-outlined {
    font-size: 16px;
    color: var(--secondary-text);
    transition: color 0.2s;
}

.rewind-btn:hover {
    background: var(--hover-bg);
}

.rewind-btn:hover .material-symbols-outlined {
    color: var(--accent-color);
}
2. 改造气泡渲染函数 (script.js)
在 script.js 中找到 appendMessage 函数，替换为以下代码（主要是增加了 invocationId 参数、dataset 缓存和 HTML 按钮结构）：

JavaScript
    // [修改] 增加 invocationId 参数
    function appendMessage(role, text, isLoading = false, appName = 'Ciri', images = [], invocationId = null) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        // Use Date.now() + random to ensure uniqueness even if called rapidly
        const id = 'msg-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
        msgDiv.id = id;

        // 👇 [新增] 把原始文本和调用ID藏在 DOM 的 dataset 里，供回填使用
        msgDiv.dataset.rawText = encodeURIComponent(text || '');
        if (invocationId) msgDiv.dataset.invocationId = invocationId;

        let contentHtml = '';
        if (isLoading) {
            contentHtml = '<div class="typing-indicator"></div>';
        } else {
            if (images && images.length > 0) {
                contentHtml += '<div class="user-images-row">';
                images.forEach(src => {
                    contentHtml += `<img src="${src}">`;
                });
                contentHtml += '</div>';
            }
            if (text) {
                contentHtml += marked.parse(text);
            }
        }

        // 👇 [新增] 生成悬浮的回退编辑按钮（仅对带有 ID 的用户消息渲染）
        let actionHtml = '';
        if (role === 'user' && invocationId) {
            actionHtml = `
                <div class="msg-actions">
                    <button class="icon-btn rewind-btn" title="回退到此处并重新编辑" onclick="window.triggerRewind('${invocationId}', '${id}')">
                        <span class="material-symbols-outlined">edit</span>
                    </button>
                </div>
            `;
        }

        msgDiv.innerHTML = `
            <div class="message-content">
                ${contentHtml}
                ${actionHtml} </div>
        `;

        chatContainer.appendChild(msgDiv);
        scrollToBottom();
        return id;
    }
3. 加载历史时传递 ID (script.js)
在 script.js 的 loadSessionHistory 函数中，找到解析 role === 'user' 的部分，将 msg.invocation_id 传递给 appendMessage：

JavaScript
                if (msg.role === 'user') {
                    // 用户消息渲染 text + images
                    const hasText = msg.text && msg.text.trim();
                    const hasImages = msg.images && msg.images.length > 0;
                    if (hasText || hasImages) {
                        // 👇 [修改] 最后一个参数传入后端的 msg.invocation_id
                        appendMessage('user', msg.text || '', false, 'Ciri', msg.images || [], msg.invocation_id);
                    }
                }
4. 加入触发回退的核心交互逻辑 (script.js)
将以下代码添加到 script.js 文件的全局层级（例如在 window.stopWorker 附近）：

JavaScript
    // ==========================================
    // [新增] 触发时光倒流与重新编辑核心逻辑
    // ==========================================
    window.triggerRewind = async function(invocationId, msgId) {
        if (!confirm('确定要修改这条消息吗？此节点之后的对话记忆将被彻底抹除 ⏪')) return;

        const msgEl = document.getElementById(msgId);
        if (!msgEl) return;

        // 1. 提取刚才藏在 dataset 里的用户原始输入文本
        const rawText = decodeURIComponent(msgEl.dataset.rawText || '');
        const currentSessionId = getCurrentSessionId();

        try {
            // UI 交互：把按钮图标变成沙漏，表示正在请求
            const btnIcon = msgEl.querySelector('.rewind-btn .material-symbols-outlined');
            if (btnIcon) btnIcon.textContent = 'hourglass_empty';

            // 2. 调用后端 /rewind 接口给 Agent “洗脑”
            const response = await fetch(`/api/sessions/${currentSessionId}/rewind`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    app_name: APP_NAME,
                    user_id: getUserId(),
                    invocation_id: invocationId
                })
            });

            const res = await response.json();
            
            if (res.status === 'success') {
                // 3. 核心体验：内容回填 (Undo and Edit)
                const inputArea = document.getElementById('userInput');
                inputArea.value = rawText;
                
                // 触发 auto-resize，让文本框自适应高度并获取焦点
                inputArea.style.height = 'auto';
                inputArea.style.height = (inputArea.scrollHeight) + 'px';
                inputArea.focus(); 

                // 4. 乐观 UI 更新：在界面上“斩断时间线”
                // 把当前气泡及下方所有气泡全部从 DOM 中移除
                let currentEl = msgEl;
                while (currentEl) {
                    let nextEl = currentEl.nextElementSibling;
                    currentEl.remove();
                    currentEl = nextEl;
                }
                
                // 兜底：如果删空了，显示欢迎屏
                if (chatContainer.children.length === 0 || chatContainer.children[0].id === 'welcomeScreen') {
                    document.getElementById('welcomeScreen').style.display = 'flex';
                    document.body.classList.remove('chat-mode');
                    document.body.classList.add('welcome-mode');
                }

            } else {
                alert(`回退失败: ${res.message}`);
                if (btnIcon) btnIcon.textContent = 'edit';
            }
        } catch (e) {
            console.error("Rewind API Error:", e);
            alert("回退请求网络出错");
            const btnIcon = msgEl.querySelector('.rewind-btn .material-symbols-outlined');
            if (btnIcon) btnIcon.textContent = 'edit';
        }
    };
🎉 检查清单
保存好这几个文件后，重启你的 Web 服务。在页面中：

刷新聊天界面（必须是在页面刷新重新调用了 /history 接口之后）。

将鼠标悬停在你过去发出的任意一条消息上，右上角应该出现一支小铅笔（Edit）图标。

点击并确认，该消息下方所有的聊天记录将瞬间消失，而你当时说的话会乖乖回到最下方的输入框中等待你修改。

一切就绪，祝你部署顺利！
document.addEventListener('DOMContentLoaded', () => {
    const userInput = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const chatContainer = document.getElementById('chatContainer');
    const welcomeScreen = document.getElementById('welcomeScreen');

    // Initialize marked with highlight.js
    marked.setOptions({
        highlight: function (code, lang) {
            if (lang && hljs.getLanguage(lang)) {
                return hljs.highlight(code, { language: lang }).value;
            }
            return hljs.highlightAuto(code).value;
        },
        breaks: true // Enable line breaks
    });

    // Auto-resize textarea
    userInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        if (this.value === '') {
            this.style.height = 'auto';
        }
    });

    // Handle Enter key
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    sendBtn.addEventListener('click', sendMessage);

    const stopBtn = document.getElementById('stopBtn');

    // Session Constants (Should match backend defaults)
    const APP_NAME = "dynamic_expert";
    const USER_ID = "user_001";

    // 动态获取当前 session_id
    function getCurrentSessionId() {
        return localStorage.getItem('current_session_id');
    }

    function setCurrentSessionId(sessionId) {
        localStorage.setItem('current_session_id', sessionId);
    }

    stopBtn.addEventListener('click', async () => {
        try {
            const currentSessionId = getCurrentSessionId();
            console.log("Sending cancel request...");
            await fetch('/api/cancel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    app_name: APP_NAME,
                    user_id: USER_ID,
                    session_id: currentSessionId
                })
            });
        } catch (e) {
            console.error("Failed to cancel:", e);
        }
    });

    async function sendMessage() {
        const text = userInput.value.trim();
        if (!text) return;

        // Hide welcome screen on first message
        if (welcomeScreen && welcomeScreen.style.display !== 'none') {
            welcomeScreen.style.display = 'none';
            // 切换到对话模式,输入框移到底部
            document.body.classList.remove('welcome-mode');
            document.body.classList.add('chat-mode');
        }

        // Add User Message
        appendMessage('user', text);
        userInput.value = '';
        userInput.style.height = 'auto';

        // UI Toggle: Show Stop, Hide Send
        sendBtn.style.display = 'none';
        stopBtn.style.display = 'inline-flex';

        // Add Loading Indicator (Temporary Model Message)
        const loadingId = appendMessage('model', '', true); // Start with empty message

        // Store response blocks: [{type: 'text'|'tool_call'|'tool_result', content: '...'}]
        let responseBlocks = [];
        let appNameSet = false;

        try {
            const currentSessionId = getCurrentSessionId();
            if (!currentSessionId) {
                console.error('No active session');
                return;
            }

            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: text,
                    app_name: APP_NAME,
                    user_id: USER_ID,
                    session_id: currentSessionId
                })
            });

            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep the last incomplete line in buffer

                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const data = JSON.parse(line);

                        if (data.app_name && !appNameSet) {
                            appNameSet = true;
                        }

                        if (data.chunk) {
                            const chunk = data.chunk; // Expecting {type: '...', content: '...'}

                            // Handle both legacy string chunks (if any) and new object chunks
                            if (typeof chunk === 'string') {
                                // Fallback for legacy string chunks (shouldn't happen with new backend)
                                const lastBlock = responseBlocks[responseBlocks.length - 1];
                                if (lastBlock && lastBlock.type === 'text') {
                                    lastBlock.content += chunk;
                                } else {
                                    responseBlocks.push({ type: 'text', content: chunk });
                                }
                            } else {
                                if (chunk.type === 'text' || chunk.type === 'thought') {
                                    // Merge with previous block of the same type if exists
                                    const lastBlock = responseBlocks[responseBlocks.length - 1];
                                    if (lastBlock && lastBlock.type === chunk.type) {
                                        lastBlock.content += chunk.content;
                                    } else {
                                        responseBlocks.push({ type: chunk.type, content: chunk.content });
                                    }
                                } else {
                                    // Tool calls and results are distinct blocks
                                    responseBlocks.push(chunk);
                                }
                            }

                            // Update the message content with the full list of blocks
                            // console.log('Updating message with blocks:', responseBlocks);
                            updateMessage(loadingId, responseBlocks);
                        }
                    } catch (e) {
                        console.error('Error parsing JSON chunk', e);
                    }
                }
            }

        } catch (error) {
            console.error('Error:', error);
            // removeMessage(loadingId);
            // appendMessage('model', 'Sorry, something went wrong. Please try again.');
            // Don't remove message, just append error info if needed, or let the partial response stay.
        } finally {
            // UI Toggle: Show Send, Hide Stop
            sendBtn.style.display = 'inline-flex';
            stopBtn.style.display = 'none';

            // Remove cursor from the finished message
            const loadingEl = document.getElementById(loadingId);
            if (loadingEl) {
                const cursor = loadingEl.querySelector('.streaming-cursor');
                if (cursor) cursor.remove();
            }
        }
    }

    function updateMessage(id, blocks, isHistory = false) {
        const el = document.getElementById(id);
        if (el) {
            const messageContent = el.querySelector('.message-content');

            // 1. 记录当前所有 details 标签的展开状态 (open 属性)
            const detailsStates = Array.from(messageContent.querySelectorAll('details')).map(d => d.open);

            // 2. 渲染新内容 (+ cursor,除非是历史消息)
            const html = renderBlocks(blocks);
            if (isHistory) {
                messageContent.innerHTML = html; // 历史消息不显示光标
            } else {
                messageContent.innerHTML = html + '<span class="streaming-cursor"></span>';
            }

            // 3. 恢复状态与智能初始化
            const newDetails = messageContent.querySelectorAll('details');
            newDetails.forEach((d, index) => {
                if (index < detailsStates.length) {
                    // 对于已经存在的块，完全还原用户之前的手动操作状态
                    d.open = detailsStates[index];
                } else {
                    // 对于新出现的块 (index >= detailsStates.length)
                    // 如果是思考过程，默认展开以便用户观察进度
                    if (d.classList.contains('thought-process')) {
                        d.open = true;
                    }
                }
            });

            if (!isHistory) {
                scrollToBottom();
            }
        }
    }

    function appendMessage(role, text, isLoading = false, appName = 'Gemini') {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        // Use Date.now() + random to ensure uniqueness even if called rapidly
        const id = 'msg-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
        msgDiv.id = id;

        let contentHtml = '';
        if (isLoading) {
            contentHtml = '<div class="typing-indicator"></div>';
        } else {
            // Initial message is just text
            contentHtml = marked.parse(text);
        }

        msgDiv.innerHTML = `
            <div class="message-content">
                ${contentHtml}
            </div>
        `;

        chatContainer.appendChild(msgDiv);
        scrollToBottom();
        return id;
    }

    function removeMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function scrollToBottom() {
        // 阈值：距离底部多少像素以内认为是“处于底部”
        const threshold = 150;
        const isAtBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight <= threshold;

        // 只有当用户本来就在底部附近时，才自动滚动
        if (isAtBottom) {
            chatContainer.scrollTo({
                top: chatContainer.scrollHeight,
                behavior: 'smooth' // 使用平滑滚动提升观感
            });
        }
    }

    function renderBlocks(blocks) {
        let html = '';

        blocks.forEach(block => {
            if (block.type === 'text') {
                html += marked.parse(block.content);
            } else if (block.type === 'tool_call') {
                html += `<div class="tool-call">
                            <div class="tool-header">
                                <span class="material-symbols-outlined">build</span>
                                <span>Tool Call</span>
                            </div>
                            <div class="tool-content">${block.content}</div>
                        </div>`;
            } else if (block.type === 'tool_result' || block.type === 'function_response') {
                console.log('Rendering tool_result block:', block);
                html += `<details class="tool-result">
                            <summary class="tool-header">
                                <span class="material-symbols-outlined">check_circle</span>
                                <span>Tool Result (点击展开)</span>
                            </summary>
                            <div class="tool-content">${block.content}</div>
                        </details>`;
            } else if (block.type === 'thought') {
                html += `<details class="thought-process">
                            <summary class="tool-header">
                                <span class="material-symbols-outlined">psychology</span>
                                <span>思考过程 (点击展开)</span>
                            </summary>
                            <div class="tool-content">${marked.parse(block.content)}</div>
                        </details>`;
            }
        });

        return html;
    }

    // ========================================
    // 会话管理功能
    // ========================================

    // 创建新会话
    async function createNewSession() {
        try {
            const response = await fetch('/api/sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    app_name: APP_NAME,
                    user_id: USER_ID
                })
            });
            const data = await response.json();
            // 不在这里设置 current_session_id,让 switchSession 来设置
            console.log('创建新会话:', data.session_id);
            return data.session_id;
        } catch (e) {
            console.error('创建会话失败:', e);
            return null;
        }
    }

    // 加载会话列表
    async function loadSessions() {
        try {
            const response = await fetch(
                `/api/sessions?app_name=${APP_NAME}&user_id=${USER_ID}`
            );
            const data = await response.json();
            renderSessionList(data.sessions);
        } catch (e) {
            console.error('加载会话列表失败:', e);
        }
    }

    // 渲染会话列表
    function renderSessionList(sessions) {
        const container = document.querySelector('.recent-chats');
        const currentSessionId = getCurrentSessionId();

        // 清空现有列表 (保留标题)
        const title = container.querySelector('.recent-title');
        container.innerHTML = '';
        if (title) container.appendChild(title);

        // 如果没有会话,显示提示
        if (!sessions || sessions.length === 0) {
            const emptyMsg = document.createElement('div');
            emptyMsg.className = 'chat-item';
            emptyMsg.style.opacity = '0.6';
            emptyMsg.textContent = '暂无对话';
            container.appendChild(emptyMsg);
            return;
        }

        // 渲染会话项
        sessions.forEach(session => {
            const item = document.createElement('div');
            item.className = 'chat-item';
            if (session.session_id === currentSessionId) {
                item.classList.add('active');
            }

            // 会话标题容器
            const titleSpan = document.createElement('span');
            titleSpan.textContent = session.title || '新对话';
            titleSpan.style.flex = '1';
            titleSpan.style.overflow = 'hidden';
            titleSpan.style.textOverflow = 'ellipsis';
            titleSpan.style.whiteSpace = 'nowrap';
            item.appendChild(titleSpan);

            // 删除按钮
            const deleteBtn = document.createElement('span');
            deleteBtn.className = 'material-symbols-outlined';
            deleteBtn.textContent = 'delete';
            deleteBtn.style.fontSize = '18px';
            deleteBtn.style.opacity = '0';
            deleteBtn.style.transition = 'opacity 0.2s';
            deleteBtn.style.cursor = 'pointer';
            deleteBtn.style.marginLeft = '8px';

            deleteBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                if (confirm(`确认删除对话 "${session.title}"?`)) {
                    await deleteSession(session.session_id);
                }
            });

            item.appendChild(deleteBtn);

            // 鼠标悬停显示删除按钮
            item.addEventListener('mouseenter', () => {
                deleteBtn.style.opacity = '0.7';
            });
            item.addEventListener('mouseleave', () => {
                deleteBtn.style.opacity = '0';
            });
            deleteBtn.addEventListener('mouseenter', () => {
                deleteBtn.style.opacity = '1';
            });

            item.dataset.sessionId = session.session_id;

            item.addEventListener('click', () => {
                switchSession(session.session_id);
            });

            container.appendChild(item);
        });
    }

    // 切换会话
    async function switchSession(sessionId) {
        const currentSessionId = getCurrentSessionId();
        if (sessionId === currentSessionId) return;

        console.log('切换会话:', sessionId);

        // 清空聊天容器
        while (chatContainer.firstChild) {
            chatContainer.removeChild(chatContainer.firstChild);
        }

        // 更新状态
        setCurrentSessionId(sessionId);

        // 刷新列表高亮
        await loadSessions();

        // 加载历史消息
        await loadSessionHistory(sessionId);
    }

    // 辅助函数: 检查 blocks 是否包含有效内容
    function hasValidContent(blocks) {
        if (!blocks || blocks.length === 0) return false;
        // 只要有一个 block 内容不为空(trim后),就视为有效
        return blocks.some(b => b.content && b.content.trim().length > 0);
    }

    // 加载会话历史
    async function loadSessionHistory(sessionId) {
        try {
            const response = await fetch(
                `/api/sessions/${sessionId}/history?app_name=${APP_NAME}&user_id=${USER_ID}`
            );
            const data = await response.json();

            if (!data.messages || data.messages.length === 0) {
                // 没有历史消息,显示欢迎页面
                showWelcomeScreen();
                return;
            }

            // 有历史消息时,确保欢迎屏幕被隐藏
            if (welcomeScreen) {
                welcomeScreen.style.display = 'none';
            }

            // 切换到对话模式
            document.body.classList.remove('welcome-mode');
            document.body.classList.add('chat-mode');

            // 渲染历史消息
            data.messages.forEach(msg => {
                if (msg.role === 'user') {
                    if (msg.text && msg.text.trim()) {
                        appendMessage('user', msg.text, false);
                    }
                } else if (msg.role === 'model') {
                    // 优先处理 blocks 结构
                    if (msg.blocks && hasValidContent(msg.blocks)) {
                        const msgId = appendMessage('model', '', false);
                        updateMessage(msgId, msg.blocks, true);
                    }
                    // 兼容旧的文本格式 (只有 text 没有 blocks)
                    else if (msg.text && msg.text.trim()) {
                        appendMessage('model', msg.text, false);
                    }
                    else {
                        // 真的没有内容,忽略
                        // console.warn('忽略空消息:', msg); 
                    }
                }
            });

        } catch (e) {
            console.error('加载历史消息失败:', e);
            showWelcomeScreen();
        }
    }

    // 显示欢迎屏幕
    function showWelcomeScreen() {
        // 清空聊天容器中的所有消息
        while (chatContainer.firstChild) {
            chatContainer.removeChild(chatContainer.firstChild);
        }

        // 确保欢迎屏幕可见并添加到容器
        welcomeScreen.style.display = 'block';
        chatContainer.appendChild(welcomeScreen);

        // 切换到欢迎模式,输入框居中
        document.body.classList.remove('chat-mode');
        document.body.classList.add('welcome-mode');
    }

    // 删除会话
    async function deleteSession(sessionId) {
        try {
            const response = await fetch(
                `/api/sessions/${sessionId}?app_name=${APP_NAME}&user_id=${USER_ID}`,
                { method: 'DELETE' }
            );

            if (!response.ok) {
                throw new Error('删除失败');
            }

            // 如果删除的是当前会话,创建新会话
            if (sessionId === getCurrentSessionId()) {
                const newSessionId = await createNewSession();
                if (newSessionId) {
                    setCurrentSessionId(newSessionId);
                    // 清空界面
                    while (chatContainer.firstChild) {
                        chatContainer.removeChild(chatContainer.firstChild);
                    }
                    showWelcomeScreen();
                }
            }

            // 刷新列表
            await loadSessions();

        } catch (e) {
            console.error('删除会话失败:', e);
            alert('删除会话失败,请重试');
        }
    }

    // 绑定"新建对话"按钮
    document.querySelector('.new-chat-btn').addEventListener('click', async () => {
        const newSessionId = await createNewSession();
        if (newSessionId) {
            await switchSession(newSessionId);
        }
    });

    // 页面加载时初始化
    async function initializePage() {
        // 初始设置为欢迎模式
        document.body.classList.add('welcome-mode');

        // 确保有当前会话
        let sessionId = getCurrentSessionId();
        if (!sessionId) {
            sessionId = await createNewSession();
            if (!sessionId) {
                console.error('无法创建初始会话');
                return;
            }
            // 首次创建会话,需要手动设置
            setCurrentSessionId(sessionId);
        }

        // 加载会话列表
        await loadSessions();

        // 加载当前会话的历史消息
        await loadSessionHistory(sessionId);
    }

    // 调用初始化
    initializePage();
});
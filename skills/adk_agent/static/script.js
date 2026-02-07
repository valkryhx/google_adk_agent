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

    // 动态获取当前 user_id (必须是函数，不能是常量！)
    // ⚠️ 使用 sessionStorage 而非 localStorage，确保每个标签页独立
    function getUserId() {
        return sessionStorage.getItem('user_id_override') || "user_001";
    }

    // 在控制台显示当前用户ID
    console.log(`[当前用户] ${getUserId()}`);

    // ⚠️ sessionStorage 不会触发 storage 事件（每个标签页独立）
    // 移除此监听器，因为现在每个标签页有自己的 sessionStorage

    // 动态获取当前 session_id (使用 sessionStorage 实现标签页隔离)
    function getCurrentSessionId() {
        return sessionStorage.getItem('current_session_id');
    }

    function setCurrentSessionId(sessionId) {
        sessionStorage.setItem('current_session_id', sessionId);
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
                    user_id: getUserId(),  // 动态获取
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
            // ⚠️ 延迟创建session：如果没有session，现在才创建
            let currentSessionId = getCurrentSessionId();
            if (!currentSessionId) {
                console.log('[首次发送] 检测到无session，正在创建...');
                currentSessionId = await createNewSession();
                if (!currentSessionId) {
                    alert('无法创建会话，请刷新页面重试');
                    return;
                }
                setCurrentSessionId(currentSessionId);
                console.log(`[首次发送] session创建成功: ${currentSessionId}`);

                // 刷新会话列表以显示新创建的session
                await loadSessions();
            }

            // 调试日志：显示发送的参数
            const currentUserId = getUserId();
            console.log('[发送请求] user_id:', currentUserId, 'session_id:', currentSessionId);

            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: text,
                    app_name: APP_NAME,
                    user_id: currentUserId,  // 使用上面获取的
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

                        // [New Feature] 处理 Swarm 旁路事件流
                        // Backend wraps everything in "chunk": { "chunk": { "type": "swarm_event", ... } }
                        // Wait, backend does yield json.dumps({"chunk": chunk})
                        // So data is { chunk: { type: "swarm_event", ... } }

                        if (data.chunk && data.chunk.type === 'swarm_event') {
                            const evt = data.chunk;
                            // [Fix] Chronological Ordering:
                            // When 'init' event arrives, insert a placeholder block into the stream.
                            if (evt.sub_type === 'init') {
                                responseBlocks.push({
                                    type: 'swarm_placeholder',
                                    msgId: loadingId, // Helper to construct ID
                                    port: evt.data.worker_port,
                                    data: evt.data
                                });
                                // Force render immediately so the placeholder exists for processSwarmEvent
                                updateMessage(loadingId, responseBlocks);
                            }

                            // Process the event (create/update the actual card element)
                            processSwarmEvent(loadingId, evt.sub_type, evt.data);
                            continue;
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

                // 标记 Swarm 任务结束
                markSwarmTasksFinished(loadingId);
            }
        }
    }

    // ==========================================
    // Swarm Monitoring UI Logic
    // ==========================================

    function processSwarmEvent(msgId, subType, data) {
        const msgEl = document.getElementById(msgId);
        if (!msgEl) return;

        const workerPort = data.worker_port;
        const cardId = `swarm-card-${msgId}-${workerPort}`;
        const placeholderId = `swarm-placeholder-${msgId}-${workerPort}`;

        let card = document.getElementById(cardId);

        // 1. Init: 创建卡片
        if (subType === 'init' && !card) {
            // Find the placeholder created by renderBlocks
            let placeholder = document.getElementById(placeholderId);

            // Fallback: If no placeholder (legacy or race condition), use bottom container
            if (!placeholder) {
                console.warn(`Placeholder ${placeholderId} not found, falling back to bottom container.`);
                let container = msgEl.querySelector('.swarm-monitor-container');
                if (!container) {
                    container = document.createElement('div');
                    container.className = 'swarm-monitor-container';
                    const content = msgEl.querySelector('.message-content');
                    if (content) {
                        content.parentNode.insertBefore(container, content.nextSibling);
                    } else {
                        msgEl.appendChild(container); // Absolute fallback
                    }
                }
                placeholder = container; // Treat container as parent
            }

            card = document.createElement('div');
            card.id = cardId;
            card.className = 'swarm-card running';
            // Mark as 'in-placeholder' if it is inside one, to aid styling if needed
            if (placeholder.classList.contains('swarm-placeholder')) {
                card.classList.add('inline-card');
            }

            card.innerHTML = `
                <div class="swarm-card-header">
                    <div class="swarm-status-icon"><span class="material-symbols-outlined spin">sync</span></div>
                    <div class="swarm-info">
                        <div class="swarm-worker-id">Worker-${workerPort}</div>
                        <div class="swarm-task-preview" title="${data.task_preview}">${data.task_preview || 'Task Started...'}</div>
                    </div>
                    <div class="swarm-meta">Running</div>
                    <div class="swarm-actions" style="margin-left: 10px;">
                        <button class="stop-worker-btn" title="Force Stop Worker" onclick="stopWorker(${workerPort}, '${data.session_id}')" style="background:none; border:none; cursor:pointer;" onmouseover="this.style.opacity=0.8" onmouseout="this.style.opacity=1">
                            <span class="material-symbols-outlined" style="font-size: 20px; color: #ff5252;">stop_circle</span>
                        </button>
                    </div>
                </div>
                <details class="swarm-logs-wrapper">
                    <summary>Show Real-time Logs</summary>
                    <pre class="swarm-terminal"></pre>
                </details>
            `;
            placeholder.appendChild(card);
            scrollToBottom();
        }

        if (!card) return; // 容错

        const terminal = card.querySelector('.swarm-terminal');
        const meta = card.querySelector('.swarm-meta');
        const icon = card.querySelector('.swarm-status-icon');
        const details = card.querySelector('details');

        // 2. Chunk: 追加日志
        if (subType === 'chunk') {
            if (terminal) {
                terminal.textContent += data.content;
                // 自动滚动到底部
                terminal.scrollTop = terminal.scrollHeight;

                // 如果有新内容，且用户没有手动折叠/展开过，可以考虑自动展开？
                // 不，用户说要保持整洁，所以默认折叠。
                // 可以加个小红点提示有更新？(High effort, skip for now)
            }
        }

        // 3. Finish: 标记成功
        if (subType === 'finish') {
            card.classList.remove('running');
            card.classList.add('success');
            meta.textContent = 'Completed';
            icon.innerHTML = '<span class="material-symbols-outlined">check_circle</span>';
            // 任务完成后可以自动收起日志? 默认本身就是收起的。
        }

        // 4. Fail: 标记失败
        if (subType === 'fail') {
            card.classList.remove('running');
            card.classList.add('fail');
            meta.textContent = 'Failed';
            icon.innerHTML = '<span class="material-symbols-outlined">error</span>';

            // 失败时，如果还没有创建卡片（比如连接失败），则需临时创建一个
            if (terminal) {
                terminal.textContent += `\n[ERROR] ${data.error}`;
                details.open = true; // 失败时自动展开看原因
            }
        }
    }

    function markSwarmTasksFinished(msgId) {
        // 遍历所有还在 running 的卡片，强制标记为结束（防止 UI 卡在转圈）
        // 正常情况下 finish 事件会处理，但防止异常中断
        const msgEl = document.getElementById(msgId);
        if (!msgEl) return;
        const runningCards = msgEl.querySelectorAll('.swarm-card.running');
        runningCards.forEach(card => {
            card.classList.remove('running');
            // 如果没有明确 failed，就默认为 done? 或者 stopped?
            // 还是保持 running 状态说明连接断了？
            // 最好变成灰色 unknown
            const meta = card.querySelector('.swarm-meta');
            const icon = card.querySelector('.swarm-status-icon');
            if (meta) meta.textContent = 'Disconnected';
            if (icon) icon.innerHTML = '<span class="material-symbols-outlined">wifi_off</span>';
        });
    }

    function updateMessage(id, blocks, isHistory = false) {
        const el = document.getElementById(id);
        if (el) {
            const messageContent = el.querySelector('.message-content');

            // 1. 记录当前所有 details 标签的展开状态 (open 属性)
            const detailsStates = Array.from(messageContent.querySelectorAll('details')).map(d => d.open);

            // [New] Preserve Swarm Cards across re-renders
            // "Teleport" them out of the DOM before innerHTML wipe
            const savedCards = new Map();
            messageContent.querySelectorAll('.swarm-card').forEach(card => {
                savedCards.set(card.id, card);
                // Note: We don't need to explicitly remove them, innerHTML will do it.
                // But we hold the reference, so they are not garbage collected.
            });

            // 2. 渲染新内容 (+ cursor,除非是历史消息)
            const html = renderBlocks(blocks);
            if (isHistory) {
                messageContent.innerHTML = html; // 历史消息不显示光标
            } else {
                messageContent.innerHTML = html + '<span class="streaming-cursor"></span>';
            }

            // [New] Restore Swarm Cards to their specific placeholders
            messageContent.querySelectorAll('.swarm-placeholder').forEach(ph => {
                const port = ph.dataset.port;
                // Construct ID (assuming we know the rule) or just use the ID mapping
                // Helper: logic is `swarm-card-${msgId}-${port}`
                // The placeholder ID is `swarm-placeholder-${msgId}-${port}`
                const cardId = ph.id.replace('swarm-placeholder-', 'swarm-card-');

                const card = savedCards.get(cardId);
                if (card) {
                    ph.appendChild(card);
                }
            });

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

    function appendMessage(role, text, isLoading = false, appName = 'Ciri') {
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

        for (let i = 0; i < blocks.length; i++) {
            const block = blocks[i];

            if (block.type === 'text') {
                html += marked.parse(block.content);
            } else if (block.type === 'tool_call') {
                // 1. Always Render Generic Tool Call (Raw)
                let contentDisplay = block.content;
                if (block.tool_name && block.tool_args) {
                    contentDisplay = `${block.tool_name}(${JSON.stringify(block.tool_args, null, 2)})`;
                }

                html += `<div class="tool-call">
                            <div class="tool-header">
                                <span class="material-symbols-outlined">build</span>
                                <span>Tool Call: ${block.tool_name || 'Unknown'}</span>
                            </div>
                            <div class="tool-content">${contentDisplay}</div>
                        </div>`;

                // 2. Swarm Visual Extensions (History Cards)
                if (block.tool_name === 'dispatch_task' && block.tool_args) {
                    const args = block.tool_args;
                    const taskPreview = args.task_instruction ? (args.task_instruction.substring(0, 50) + '...') : 'Swarm Task';
                    const workerInfo = args.target_port ? `Worker-${args.target_port}` : 'Swarm-Auto';

                    // Try to peek next block for result to display inside card too
                    let resultHtml = '';
                    if (i + 1 < blocks.length && (blocks[i + 1].type === 'tool_result' || blocks[i + 1].type === 'function_response')) {
                        const resultBlock = blocks[i + 1];
                        // Optionally consume it? For now, let's just peek and show it inside card too.
                        // But if we show it inside, maybe we should skip the next block?
                        // Let's NOT skip, to be safe. Just duplicate info is better than missing.
                        // Or better: render it inside card and rely on user expanding it.
                        resultHtml = `<details class="swarm-logs-wrapper">
                                         <summary>Execution Result</summary>
                                         <pre class="swarm-terminal">${resultBlock.content}</pre>
                                       </details>`;
                    }

                    html += `<div class="swarm-card success" style="margin: 10px 0;">
                                <div class="swarm-card-header">
                                    <div class="swarm-status-icon"><span class="material-symbols-outlined">history</span></div>
                                    <div class="swarm-info">
                                        <div class="swarm-worker-id">${workerInfo}</div>
                                        <div class="swarm-task-preview" title="${args.task_instruction}">${taskPreview}</div>
                                    </div>
                                    <div class="swarm-meta">History</div>
                                </div>
                                ${resultHtml}
                            </div>`;

                } else if (block.tool_name === 'dispatch_batch_tasks' && block.tool_args) {
                    const tasks = block.tool_args.tasks || [];

                    // Peek for batch results
                    let batchResults = {};
                    if (i + 1 < blocks.length && (blocks[i + 1].type === 'tool_result' || blocks[i + 1].type === 'function_response')) {
                        const nextBlock = blocks[i + 1];

                        // [New] Use clean result field if available!
                        const content = nextBlock.tool_result_clean || nextBlock.content || '';

                        // Regex now expects CLEAN string with newlines
                        const regex = /--- 任务 (\d+) 结果 ---[\r\n]+([\s\S]*?)(?=[\r\n]+--- 任务|[\r\n]+$|$)/g;
                        let match;
                        while ((match = regex.exec(content)) !== null) {
                            const taskIndex = parseInt(match[1]) - 1;
                            batchResults[taskIndex] = match[2].trim();
                        }
                    }

                    tasks.forEach((task, index) => {
                        const taskPreview = task.substring(0, 50) + '...';
                        const result = batchResults[index];

                        let resultHtml = '';
                        if (result) {
                            resultHtml = `<details class="swarm-logs-wrapper">
                                            <summary>Result (History)</summary>
                                            <pre class="swarm-terminal">${result}</pre>
                                          </details>`;
                        } else {
                            resultHtml = `<div style="font-size:12px; color:#999; padding:0 10px 5px;">(No individual result parsed)</div>`;
                        }

                        html += `<div class="swarm-card success" style="margin: 10px 0;">
                                    <div class="swarm-card-header">
                                        <div class="swarm-status-icon"><span class="material-symbols-outlined">history</span></div>
                                        <div class="swarm-info">
                                            <div class="swarm-worker-id">Batch-Worker-${index + 1}</div>
                                            <div class="swarm-task-preview" title="${task}">${taskPreview}</div>
                                        </div>
                                        <div class="swarm-meta">History</div>
                                    </div>
                                    ${resultHtml}
                                </div>`;
                    });

                    // [Dev Mode] Do not skip next block. Let it render as raw tool result too.
                    // if (Object.keys(batchResults).length > 0) {
                    //     i++; // Skip next block
                    // }

                }
            } else if (block.type === 'tool_result' || block.type === 'function_response') {
                console.log('Rendering tool_result block:', block);
                html += `<details class="tool-result">
                            <summary class="tool-header">
                                <span class="material-symbols-outlined">check_circle</span>
                                <span>Tool Result (点击展开)</span>
                            </summary>
                            <div class="tool-content">${marked.parse(block.content)}</div>
                        </details>`;
            } else if (block.type === 'thought') {
                html += `<details class="thought-process">
                            <summary class="tool-header">
                                <span class="material-symbols-outlined">psychology</span>
                                <span>思考过程 (点击展开)</span>
                            </summary>
                            <div class="tool-content">${marked.parse(block.content)}</div>
                        </details>`;
            } else if (block.type === 'swarm_placeholder') {
                // [New] Render placeholder for inline swarm card
                // ID strictly follows the pattern needed for processSwarmEvent to find it
                html += `<div id="swarm-placeholder-${block.msgId}-${block.port}" class="swarm-placeholder" data-port="${block.port}" style="margin: 10px 0;"></div>`;
            }
        }

        return html;
    }

    // ========================================
    // 会话管理功能
    // ========================================

    // 创建新会话
    async function createNewSession() {
        try {
            const currentUserId = getUserId();  // 动态获取当前用户
            const response = await fetch('/api/sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    app_name: APP_NAME,
                    user_id: currentUserId
                })
            });
            const data = await response.json();

            // ⚠️ 关键修复：为了确保不同用户的 session_id 完全隔离
            // 在前端为 session_id 添加 user 前缀（后端已经这样做了，但前端也需要知道）
            console.log(`[创建会话] user_id: ${currentUserId}, session_id: ${data.session_id}`);

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
                `/api/sessions?app_name=${APP_NAME}&user_id=${getUserId()}`  // 动态获取
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
                if (confirm(`确认删除对话 "${session.title}" ? `)) {
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
                `/api/sessions/${sessionId}/history?app_name=${APP_NAME}&user_id=${getUserId()}` // 动态获取
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
                    // 用户消息直接渲染 text
                    if (msg.text && msg.text.trim()) {
                        appendMessage('user', msg.text, false);
                    }
                } else if (msg.role === 'model') {
                    console.log('[前端调试] Model 消息:', msg);
                    console.log('[前端调试] msg.blocks:', msg.blocks);
                    console.log('[前端调试] hasValidContent(msg.blocks):', hasValidContent(msg.blocks));

                    // 优先处理 blocks 结构
                    if (msg.blocks && hasValidContent(msg.blocks)) {
                        console.log('[前端调试] 准备渲染 blocks，数量:', msg.blocks.length);
                        msg.blocks.forEach((block, idx) => {
                            console.log(`[前端调试] Block ${idx}: type=${block.type}, content_length=${block.content?.length}`);
                        });

                        const msgId = appendMessage('model', '', false);
                        updateMessage(msgId, msg.blocks, true);
                    }
                    // 兼容旧的文本格式 (只有 text 没有 blocks)
                    else if (msg.text && msg.text.trim()) {
                        console.log('[前端调试] 使用旧格式 text');
                        appendMessage('model', msg.text, false);
                    }
                    else {
                        // 真的没有内容,忽略
                        console.warn('[前端调试] 忽略空消息:', msg);
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
                `/api/sessions/${sessionId}?app_name=${APP_NAME}&user_id=${getUserId()}`,  // 动态获取
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

    // 用户切换器事件监听
    const userSelector = document.getElementById('userSelector');
    if (userSelector) {
        // 设置初始选中值 (使用 sessionStorage 实现标签页隔离)
        const currentUserId = sessionStorage.getItem('user_id_override') || 'user_001';
        userSelector.value = currentUserId;

        // 监听切换事件
        userSelector.addEventListener('change', (e) => {
            const newUserId = e.target.value;
            console.log(`[切换用户] ${currentUserId} -> ${newUserId}`);

            // 更新用户ID (sessionStorage: 每个标签页独立)
            sessionStorage.setItem('user_id_override', newUserId);

            // ⚠️ 关键修复：清除旧的 session_id，强制为新用户创建新会话
            sessionStorage.removeItem('current_session_id');
            console.log('[清除会话] 已清除旧会话，将为新用户创建新会话');

            // 静默刷新页面
            location.reload();
        });
    }

    // 页面加载时初始化
    async function initializePage() {
        // 显示当前用户（调试用）
        const currentUser = getUserId();
        console.log(`%c[页面加载] 当前用户: ${currentUser}`, 'background: #222; color: #bada55; font-size: 14px; padding: 2px 5px;');

        // 初始设置为欢迎模式
        document.body.classList.add('welcome-mode');

        // ⚠️ 延迟创建session：不在页面加载时创建，只在用户发送第一条消息时创建
        // 这样可以避免用户切换用户时创建大量空session

        // 加载会话列表（如果有的话）
        await loadSessions();

        // 如果有当前会话，才加载历史消息
        const sessionId = getCurrentSessionId();
        if (sessionId) {
            await loadSessionHistory(sessionId);
        }

        // 初始化侧边栏调整大小功能
        initSidebarResize();
    }

    // 初始化侧边栏调整大小功能
    function initSidebarResize() {
        const sidebar = document.querySelector('.sidebar');
        const handle = document.querySelector('.resize-handle');
        const menuBtn = document.querySelector('.menu-btn');
        let isResizing = false;

        // --- 1. 侧边栏折叠/展开逻辑 ---
        menuBtn.addEventListener('click', () => {
            if (sidebar.classList.contains('collapsed')) {
                sidebar.classList.remove('collapsed');
                // 恢复宽度
                sidebar.style.padding = ''; // 恢复 CSS 默认
                sidebar.style.minWidth = ''; // 恢复 CSS 默认
                const savedWidth = localStorage.getItem('sidebarWidth') || '260px';
                sidebar.style.width = savedWidth;
            } else {
                sidebar.classList.add('collapsed');
                sidebar.style.width = '0px';
                sidebar.style.padding = '0px'; // 确保彻底消失
                sidebar.style.minWidth = '0px';
                sidebar.style.maxWidth = '0px';
            }
        });

        // --- 2. 侧边栏调整大小逻辑 ---
        // 恢复保存的宽度
        const savedWidth = localStorage.getItem('sidebarWidth');
        if (savedWidth) {
            sidebar.style.width = savedWidth;
            sidebar.style.minWidth = savedWidth;
        }

        handle.addEventListener('mousedown', (e) => {
            if (sidebar.classList.contains('collapsed')) return;
            isResizing = true;
            handle.classList.add('active');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;

            let newWidth = e.clientX;

            // 响应式限制：如果窗口很窄，允许侧边栏占满更多空间
            const maxAllowedRatio = window.innerWidth < 600 ? 0.8 : 0.5;
            const maxAllowed = window.innerWidth * maxAllowedRatio;
            const minAllowed = 150; // 稍微降低最小限制以适应窄屏

            if (newWidth < minAllowed) newWidth = minAllowed;
            if (newWidth > maxAllowed) newWidth = maxAllowed;

            sidebar.style.width = `${newWidth}px`;
            sidebar.style.minWidth = `${newWidth}px`;
            sidebar.style.maxWidth = `${newWidth}px`;
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                handle.classList.remove('active');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';

                // 保存宽度
                localStorage.setItem('sidebarWidth', sidebar.style.width);
            }
        });
    }

    // [New Feature] Stop Specific Worker function
    window.stopWorker = async function (workerPort, workerSessionId) {
        if (!confirm(`Confirm to force stop Worker-${workerPort}?`)) return;

        console.log(`[Stop Worker] Port: ${workerPort}, Session: ${workerSessionId}`);

        try {
            // Retrieve current user ID dynamically
            const currentUserId = getUserId();

            const response = await fetch('/api/stop_worker', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    worker_port: workerPort,
                    worker_session_id: workerSessionId,
                    app_name: APP_NAME,
                    user_id: currentUserId
                })
            });

            const res = await response.json();
            if (res.status === 'success') {
                // Manually update the card UI to show stopped (optional, as backend might not push fail event immediately if cancelling)
                // note: msgId is not available here, relying on backend event stream

                alert(`Instruction sent to stop Worker-${workerPort}.`);
            } else {
                alert(`Failed to stop worker: ${res.error || res.message}`);
            }
        } catch (e) {
            console.error("Stop worker error:", e);
            alert("Error stopping worker.");
        }
    };

    // 调用初始化
    initializePage();
});
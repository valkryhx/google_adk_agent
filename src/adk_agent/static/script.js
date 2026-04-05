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
        // Skill dropdown trigger
        const val = this.value;
        const slashMatch = val.match(/^\/([\w-]*)$/);
        if (slashMatch) {
            showSkillDropdown(slashMatch[1]);
        } else {
            hideSkillDropdown();
        }
    });

    // Handle Enter key
    userInput.addEventListener('keydown', (e) => {
        const dropdown = document.getElementById('skillDropdown');
        if (dropdown && dropdown.style.display !== 'none') {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                skillDropdownMove(1);
                return;
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                skillDropdownMove(-1);
                return;
            } else if (e.key === 'Enter') {
                e.preventDefault();
                skillDropdownSelect();
                return;
            } else if (e.key === 'Escape') {
                hideSkillDropdown();
                return;
            }
        }
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // ==========================================
    // Skill Dropdown
    // ==========================================
    let _skillCache = null;
    let _skillActiveIdx = -1;

    async function fetchSkills() {
        if (_skillCache) return _skillCache;
        try {
            const res = await fetch('/api/skills');
            const data = await res.json();
            _skillCache = data.skills || [];
        } catch (e) {
            _skillCache = [];
        }
        return _skillCache;
    }

    async function showSkillDropdown(filter) {
        const skills = await fetchSkills();
        const filtered = filter
            ? skills.filter(s => s.id.includes(filter) || s.name.toLowerCase().includes(filter.toLowerCase()))
            : skills;
        const dropdown = document.getElementById('skillDropdown');
        if (!filtered.length) { hideSkillDropdown(); return; }
        _skillActiveIdx = -1;
        dropdown.innerHTML = filtered.map((s, i) =>
            `<div class="skill-dropdown-item" data-id="${s.id}" data-idx="${i}">
                <span class="skill-name">${s.name || s.id}</span>
                <span class="skill-desc">${s.description || ''}</span>
            </div>`
        ).join('');
        dropdown.querySelectorAll('.skill-dropdown-item').forEach(item => {
            item.addEventListener('mousedown', (e) => {
                e.preventDefault();
                userInput.value = item.dataset.id + ' ';
                userInput.style.height = 'auto';
                userInput.style.height = (userInput.scrollHeight) + 'px';
                hideSkillDropdown();
                userInput.focus();
            });
        });
        // Position using fixed coords relative to textarea
        const rect = userInput.getBoundingClientRect();
        dropdown.style.display = 'block';
        const ddHeight = Math.min(dropdown.scrollHeight, 280);
        dropdown.style.left = rect.left + 'px';
        dropdown.style.width = rect.width + 'px';
        dropdown.style.top = (rect.top - ddHeight - 6) + 'px';
    }

    function hideSkillDropdown() {
        const dropdown = document.getElementById('skillDropdown');
        if (dropdown) dropdown.style.display = 'none';
        _skillActiveIdx = -1;
    }

    function skillDropdownMove(dir) {
        const dropdown = document.getElementById('skillDropdown');
        const items = dropdown.querySelectorAll('.skill-dropdown-item');
        if (!items.length) return;
        items[_skillActiveIdx]?.classList.remove('active');
        _skillActiveIdx = (_skillActiveIdx + dir + items.length) % items.length;
        items[_skillActiveIdx].classList.add('active');
        items[_skillActiveIdx].scrollIntoView({ block: 'nearest' });
    }

    function skillDropdownSelect() {
        const dropdown = document.getElementById('skillDropdown');
        const items = dropdown.querySelectorAll('.skill-dropdown-item');
        const idx = _skillActiveIdx >= 0 ? _skillActiveIdx : 0;
        if (items[idx]) {
            userInput.value = items[idx].dataset.id + ' ';
            userInput.style.height = 'auto';
            userInput.style.height = (userInput.scrollHeight) + 'px';
            hideSkillDropdown();
            userInput.focus();
        }
    }

    document.addEventListener('click', (e) => {
        if (!e.target.closest('#skillDropdown') && e.target !== userInput) {
            hideSkillDropdown();
        }
    });

    sendBtn.addEventListener('click', sendMessage);

    const stopBtn = document.getElementById('stopBtn');

    // ==========================================
    // [多模态] 图片上传逻辑
    // ==========================================
    let currentImages = [];
    const fileInput = document.getElementById('fileInput');
    const uploadBtn = document.getElementById('uploadBtn');
    const previewContainer = document.getElementById('imagePreviewContainer');

    if (uploadBtn && fileInput) {
        uploadBtn.addEventListener('click', () => {
            fileInput.value = '';
            fileInput.click();
        });

        fileInput.addEventListener('change', async (e) => {
            const files = Array.from(e.target.files);
            if (files.length === 0) return;

            for (const file of files) {
                if (!file.type.startsWith('image/')) continue;
                try {
                    const base64 = await fileToBase64(file);
                    currentImages.push(base64);
                } catch (err) {
                    console.error('[Multimodal] Failed to read image:', err);
                }
            }
            renderPreview();
        });
    }

    function fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.readAsDataURL(file);
            reader.onload = () => resolve(reader.result);
            reader.onerror = error => reject(error);
        });
    }

    function renderPreview() {
        previewContainer.innerHTML = '';
        if (currentImages.length === 0) return;

        currentImages.forEach((imgSrc, index) => {
            const item = document.createElement('div');
            item.className = 'preview-item';

            const img = document.createElement('img');
            img.src = imgSrc;

            const removeBtn = document.createElement('div');
            removeBtn.className = 'remove-btn';
            removeBtn.onclick = (e) => {
                e.stopPropagation();
                currentImages.splice(index, 1);
                renderPreview();
            };

            item.appendChild(img);
            item.appendChild(removeBtn);
            previewContainer.appendChild(item);
        });
    }

    function clearImages() {
        currentImages = [];
        renderPreview();
    }

    // Session Constants (Should match backend defaults)
    const APP_NAME = "dynamic_expert";

    // 动态获取当前 user_id (必须是函数，不能是常量！)
    // ⚠️ 优先从 localStorage 读取，为了兼容各种移动端浏览器的 reload() 行为
    function getUserId() {
        return localStorage.getItem('user_id_override') || "user_001";
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
        // [新增] 每次发送新消息时，重置 Swarm 事件的早期刷新标记
        window._hasTriggeredEarlyRefreshForSwarm = false;

        const text = userInput.value.trim();
        // [多模态] 有文本或有图片就可以发送
        if (!text && currentImages.length === 0) return;

        // Hide welcome screen on first message
        if (welcomeScreen && welcomeScreen.style.display !== 'none') {
            welcomeScreen.style.display = 'none';
            document.body.classList.remove('welcome-mode');
            document.body.classList.add('chat-mode');
        }

        // [多模态] 暂存图片副本用于发送和回显
        const imagesToSend = [...currentImages];

        // Add User Message (with images)
        const userMsgId = appendMessage('user', text, false, 'Ciri', imagesToSend);
        userInput.value = '';
        userInput.style.height = 'auto';
        clearImages();

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

            // 动态确定 app_name（如果是 Swarm 会话，使用对应的 app_name）
            let appName = APP_NAME;
            const storedIsSwarm = sessionStorage.getItem('current_is_swarm');
            const storedLeaderPort = sessionStorage.getItem('current_leader_port');
            if (storedIsSwarm === 'true' && storedLeaderPort) {
                appName = `swarm_from_${storedLeaderPort}`;
            }

            console.log('[发送请求] user_id:', currentUserId, 'session_id:', currentSessionId, 'app_name:', appName);

            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: text,
                    images: imagesToSend.length > 0 ? imagesToSend : undefined,
                    app_name: appName,
                    user_id: currentUserId,
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

                            // [新增] 专门针对会话状态更新（如打标签）事件：无视标记强制刷新，因为此时后端刚好写入完成
                            if (evt.sub_type === 'update_session_state') {
                                setTimeout(() => loadSessions().catch(e => console.warn('state update load failed:', e)), 200);
                            }
                            // [新增] 发现后台开始执行 Agent 任务时，提早触发左侧列表刷新，以免长时间等待
                            else if (!window._hasTriggeredEarlyRefreshForSwarm) {
                                window._hasTriggeredEarlyRefreshForSwarm = true;
                                setTimeout(() => loadSessions().catch(e => console.warn('early loadSessions failed:', e)), 500);
                            }

                            // [Fix] Chronological Ordering:
                            // When 'init' event arrives, insert a placeholder block into the stream.
                            if (evt.sub_type === 'init') {
                                const roundInfo = evt.data.meeting_round;
                                const role = evt.data.meeting_role;

                                // Meeting mode: insert Round Header before first card of each round
                                if (roundInfo) {
                                    const roundContainerId = `swarm-round-${loadingId}-${roundInfo}`;
                                    const alreadyHasRoundHeader = responseBlocks.some(
                                        b => b.type === 'round_header' && b.round === roundInfo && b.msgId === loadingId
                                    );
                                    if (!alreadyHasRoundHeader) {
                                        responseBlocks.push({
                                            type: 'round_header',
                                            msgId: loadingId,
                                            round: roundInfo,
                                            totalRounds: evt.data.meeting_total_rounds,
                                            role: role
                                        });
                                    }
                                }

                                // Use round-aware suffix for placeholder ID (include role to avoid secretary/participant collision)
                                const rolePrefix = role === 'secretary' ? 'sec-' : '';
                                let placeholderSuffix = `${evt.data.worker_port}`;
                                if (roundInfo) {
                                    placeholderSuffix = `R${roundInfo}-${rolePrefix}${evt.data.worker_port}`;
                                } else if (evt.data.session_id) {
                                    placeholderSuffix = `${evt.data.session_id}-${evt.data.worker_port}`;
                                }
                                responseBlocks.push({
                                    type: 'swarm_placeholder',
                                    msgId: loadingId,
                                    port: evt.data.worker_port,
                                    round: roundInfo || null,
                                    role: role || null,
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
                                    // [新增] 发现普通 tool_call 时，也提早触发左侧列表刷新
                                    if (chunk.type === 'tool_call' && !window._hasTriggeredEarlyRefreshForSwarm) {
                                        window._hasTriggeredEarlyRefreshForSwarm = true;
                                        setTimeout(() => loadSessions().catch(e => console.warn('early loadSessions failed:', e)), 500);
                                    }

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

            // [新增] 流式响应完成后刷新左侧会话列表（标题、task_type 标记更新）
            // 延迟 800ms 等后端 save_session 写入 DB 完成
            setTimeout(() => loadSessions().catch(e => console.warn('loadSessions after chat failed:', e)), 800);

            // [新增] 刷新最新用户消息的 invocation_id
            try {
                const currentSessionId = getCurrentSessionId();
                if (currentSessionId) {
                    // 与 sendMessage 中保持一致的 app_name 获取逻辑
                    let currentAppName = APP_NAME;
                    const _isSwarm = sessionStorage.getItem('current_is_swarm');
                    const _leaderPort = sessionStorage.getItem('current_leader_port');
                    if (_isSwarm === 'true' && _leaderPort) {
                        currentAppName = `swarm_from_${_leaderPort}`;
                    }
                    const historyRes = await fetch(`/api/sessions/${currentSessionId}/history?app_name=${currentAppName}&user_id=${getUserId()}`);
                    const historyData = await historyRes.json();
                    if (historyData.messages && historyData.messages.length > 0) {
                        // 找到最后一个 role === 'user' 的消息
                        let lastUserMsg = null;
                        for (let i = historyData.messages.length - 1; i >= 0; i--) {
                            if (historyData.messages[i].role === 'user') {
                                lastUserMsg = historyData.messages[i];
                                break;
                            }
                        }
                        if (lastUserMsg && lastUserMsg.invocation_id) {
                            const userMsgEl = document.getElementById(userMsgId);
                            if (userMsgEl && !userMsgEl.dataset.invocationId) {
                                userMsgEl.dataset.invocationId = lastUserMsg.invocation_id;
                                let actionHtml = `
                                    <div class="msg-actions">
                                        <button class="icon-btn rewind-btn" title="回退到此处并重新编辑" onclick="window.triggerRewind('${lastUserMsg.invocation_id}', '${userMsgId}')">
                                            <span class="material-symbols-outlined">edit</span>
                                        </button>
                                    </div>
                                `;
                                const contentDiv = userMsgEl.querySelector('.message-content');
                                if (contentDiv) {
                                    contentDiv.insertAdjacentHTML('beforeend', actionHtml);
                                }
                            }
                        }
                    }
                }
            } catch (e) {
                console.error('Failed to fetch history for invocation_id update', e);
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
        const round = data.meeting_round;
        const role = data.meeting_role || data.deep_think_role;
        const totalRounds = data.meeting_total_rounds;

        // Round-aware ID: prevent same worker across rounds from overwriting
        // Also include role to prevent secretary/participant collision on same round+port
        const rolePrefix = role === 'secretary' ? 'sec-' : '';
        let cardSuffix = `${workerPort}`;
        if (round) {
            cardSuffix = `R${round}-${rolePrefix}${workerPort}`;
        } else if (data.session_id) {
            cardSuffix = `${data.session_id}-${workerPort}`;
        }

        const cardId = `swarm-card-${msgId}-${cardSuffix}`;
        const placeholderId = `swarm-placeholder-${msgId}-${cardSuffix}`;

        let card = document.getElementById(cardId);

        // 1. Init: create card
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

            // Build header info based on meeting or deep think context
            let workerLabel = data.worker_name || `Worker-${workerPort}`;
            let metaLabel = 'Running';
            let statusIcon = 'sync';

            if (round) {
                if (role === 'secretary') {
                    workerLabel = `[Secretary] Worker-${workerPort}`;
                    metaLabel = 'Summarizing';
                    statusIcon = 'edit_note';
                } else {
                    workerLabel = `[Round ${round}/${totalRounds || '?'}] Worker-${workerPort}`;
                    metaLabel = `Round ${round}/${totalRounds || '?'}`;
                }
            } else if (data.deep_think_role) {
                workerLabel = `[${data.deep_think_role}] Worker-${workerPort}`;
                metaLabel = data.deep_think_role;
                statusIcon = 'psychology';
            }

            card.innerHTML = `
                <div class="swarm-card-header">
                    <div class="swarm-status-icon"><span class="material-symbols-outlined spin">${statusIcon}</span></div>
                    <div class="swarm-info">
                        <div class="swarm-worker-id">${workerLabel}</div>
                        <div class="swarm-task-preview" title="${data.task_preview}">${data.task_preview || 'Task Started...'}</div>
                    </div>
                    <div class="swarm-meta">${metaLabel}</div>
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
                // 对于 OpenCode，由于后端已经在 accumulated_text 里累加了，这里如果一直是 += 会导致文本重复或者太长
                // 需要区分是否是 OpenCode。或者后端改了，前端就用赋值。
                // 既然我们在工具里做了 += 累加，前端应该用 = （直接覆盖）。但是之前的 Swarm 任务可能是片段流。
                // 为了兼容，如果内容是包含前面内容的累加字符串，前端用 = 替换。
                if (data.worker_port === 'opencode') {
                    terminal.textContent = data.content;
                } else {
                    terminal.textContent += data.content;
                }
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

        // 5. Retry: 标记跳过（节点忙碌，正在切换到其他节点）
        if (subType === 'retry') {
            card.classList.remove('running');
            card.classList.add('skipped');
            meta.textContent = data.retry_reason || 'Skipped';
            icon.innerHTML = '<span class="material-symbols-outlined">swap_horiz</span>';
            // 不自动展开日志（与 fail 不同），因为这不是真正的错误
        }
    }

    function markSwarmTasksFinished(msgId) {
        // 遍历所有还在 running 的卡片，强制标记为结束（防止 UI 卡在转圈）
        // 正常情况下 finish 事件会处理，但防止异常中断
        const msgEl = document.getElementById(msgId);
        if (!msgEl) return;
        const runningCards = msgEl.querySelectorAll('.swarm-card.running');
        runningCards.forEach(card => {
            // [Fix] Do not mark OpenCode background tasks as disconnected prematurely
            const workerIdEl = card.querySelector('.swarm-worker-id');
            if (workerIdEl && workerIdEl.textContent.includes('opencode')) {
                return; // Skip this card, let it finish via its own background thread events
            }

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
            const html = renderBlocks(blocks, isHistory);
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

    // [修改] 增加 invocationId 参数
    function appendMessage(role, text, isLoading = false, appName = 'Ciri', images = [], invocationId = null) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        // Use Date.now() + random to ensure uniqueness even if called rapidly
        const id = 'msg-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
        msgDiv.id = id;

        // [新增] 把原始文本和调用ID藏在 DOM 的 dataset 里，供回填使用
        msgDiv.dataset.rawText = encodeURIComponent(text || '');
        if (invocationId) msgDiv.dataset.invocationId = invocationId;

        let contentHtml = '';
        if (isLoading) {
            contentHtml = '<div class="typing-indicator"></div>';
        } else {
            // [多模态] 如果有图片，先渲染图片行
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

        // [新增] 生成悬浮的回退编辑按钮（仅对带有 ID 的用户消息渲染）
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
                ${actionHtml}
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

    function renderBlocks(blocks, isHistory = false) {
        // [Debug] Beacon to verify script update and execution
        console.log(`[Swarm Debug] renderBlocks called. Blocks: ${blocks.length}, isHistory: ${isHistory}`);

        let html = '';

        for (let i = 0; i < blocks.length; i++) {
            const block = blocks[i];
            // [Debug] Trace block types
            if (isHistory) console.log(`[Swarm Debug] Block ${i}: type=${block.type}, tool=${block.tool_name || block.function?.name}`);

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
                // Only render these when loading from history. 
                // In live mode, the Swarm Events (swarm_placeholder) will handle the UI.
                if (isHistory) {
                    if (block.tool_name === 'dispatch_task' && block.tool_args) {
                        const args = block.tool_args;
                        const taskPreview = args.task_instruction ? (args.task_instruction.substring(0, 50) + '...') : 'Swarm Task';
                        const workerInfo = args.target_port ? `Worker-${args.target_port}` : 'Swarm-Auto';

                        // Try to peek next block for result to display inside card too
                        let resultHtml = '';
                        if (i + 1 < blocks.length && (blocks[i + 1].type === 'tool_result' || blocks[i + 1].type === 'function_response')) {
                            const resultBlock = blocks[i + 1];
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

                    } else if (block.tool_name === 'opencode_delegate' && block.tool_args) {
                        // === opencode_delegate History Cards (Simulate Swarm Card) ===
                        const args = block.tool_args;
                        const taskPreview = args.prompt ? (args.prompt.substring(0, 50) + '...') : 'OpenCode Task';

                        // Peek next block for result (the full accumulated log)
                        let resultHtml = '';
                        if (i + 1 < blocks.length && (blocks[i + 1].type === 'tool_result' || blocks[i + 1].type === 'function_response')) {
                            const resultBlock = blocks[i + 1];
                            resultHtml = `<details class="swarm-logs-wrapper" open>
                                             <summary>Execution Logs (Final)</summary>
                                             <pre class="swarm-terminal">${resultBlock.content}</pre>
                                           </details>`;
                        }

                        html += `<div class="swarm-card success" style="margin: 10px 0;">
                                    <div class="swarm-card-header">
                                        <div class="swarm-status-icon"><span class="material-symbols-outlined">code_blocks</span></div>
                                        <div class="swarm-info">
                                            <div class="swarm-worker-id">Worker-OpenCode</div>
                                            <div class="swarm-task-preview" title="${args.prompt}">${taskPreview}</div>
                                        </div>
                                        <div class="swarm-meta">Completed</div>
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
                            let content = nextBlock.tool_result_clean || nextBlock.content || '';

                            // [Fix] Normalize escaped newlines to real newlines for regex matching
                            content = content.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n').replace(/\\r/g, '\n');

                            // Regex now expects CLEAN string with newlines
                            const regex = /--- \u4efb\u52a1 (\d+) \u7ed3\u679c ---[\r\n]+([\s\S]*?)(?=[\r\n]+--- \u4efb\u52a1|[\r\n]*$)/g;
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
                    } else if (block.tool_name === 'dag_execute' && block.tool_args) {
                        // === dag_execute History Cards ===
                        let dagResultContent = '';
                        if (i + 1 < blocks.length && (blocks[i + 1].type === 'tool_result' || blocks[i + 1].type === 'function_response')) {
                            dagResultContent = blocks[i + 1].tool_result_clean || blocks[i + 1].content || '';
                        }
                        const dagSummaryMatch = dagResultContent.match(/Tasks: ([0-9]+\/[0-9]+[^\n]*)/);
                        const dagSummary = dagSummaryMatch ? dagSummaryMatch[1] : 'DAG Executed';

                        // Parse [TASK] lines to render individual worker cards
                        const taskLines = dagResultContent.split('\n').filter(l => l.startsWith('[TASK]'));
                        if (taskLines.length > 0) {
                            taskLines.forEach(line => {
                                // [TASK] ✓ 任务名 | owner=worker_8003@adk_swarm | status=completed | id=xxx
                                const nameMatch = line.match(/\] [✓✗⋯○?] (.+?) \|/);
                                const ownerMatch = line.match(/owner=([^|]+)/);
                                const statusMatch = line.match(/status=([^|]+)/);
                                const taskName = nameMatch ? nameMatch[1].trim() : 'Task';
                                const workerName = ownerMatch ? ownerMatch[1].trim() : 'unknown';
                                const taskStatus = statusMatch ? statusMatch[1].trim() : 'unknown';
                                const cardClass = taskStatus === 'completed' ? 'success' : taskStatus === 'failed' ? 'failed' : 'success';
                                const iconName = taskStatus === 'completed' ? 'check_circle' : taskStatus === 'failed' ? 'cancel' : 'history';
                                html += `<div class="swarm-card ${cardClass}" style="margin: 10px 0;">
                                    <div class="swarm-card-header">
                                        <div class="swarm-status-icon"><span class="material-symbols-outlined">${iconName}</span></div>
                                        <div class="swarm-info">
                                            <div class="swarm-worker-id">${workerName}</div>
                                            <div class="swarm-task-preview">${taskName}</div>
                                        </div>
                                        <div class="swarm-meta">History</div>
                                    </div>
                                </div>`;
                            });
                        } else {
                            // Fallback: single summary card
                            const dagResultHtml = dagResultContent ? '<details class="swarm-logs-wrapper"><summary>Execution Summary</summary><pre class="swarm-terminal">' + dagResultContent + '</pre></details>' : '';
                            html += '<div class="swarm-card success" style="margin: 10px 0;"><div class="swarm-card-header"><div class="swarm-status-icon"><span class="material-symbols-outlined">account_tree</span></div><div class="swarm-info"><div class="swarm-worker-id">DAG Execute</div><div class="swarm-task-preview">' + dagSummary + '</div></div><div class="swarm-meta">History</div></div>' + dagResultHtml + '</div>';
                        }

                    } else if (block.tool_name === 'hold_meeting' && block.tool_args) {
                        // === hold_meeting History Cards ===
                        const meetingTopic = args.topic || 'Meeting';
                        const maxRounds = args.max_rounds || '?';
                        const participantCount = args.participant_count || '?';

                        // Parse round_details from tool_result
                        let roundEntries = [];
                        if (i + 1 < blocks.length && (blocks[i + 1].type === 'tool_result' || blocks[i + 1].type === 'function_response')) {
                            let resultContent = blocks[i + 1].tool_result_clean || blocks[i + 1].content || '';
                            // Normalize escaped newlines
                            resultContent = resultContent.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n').replace(/\\r/g, '\n');

                            // Robust Line-by-Line Parsing with Multi-line Support
                            console.groupCollapsed(`[Meeting History Debug] Parsing rounds for topic: ${meetingTopic}`);

                            const lines = resultContent.split('\n');
                            let currentRound = null;
                            let currentEntry = null;

                            for (const line of lines) {
                                // Match: --- Round 1 (3 participants) ---
                                const roundMatch = line.match(/Round (\d+) \((\d+) participants\)/);
                                if (roundMatch) {
                                    console.log(`✅ Found Round: ${roundMatch[1]}`);
                                    currentRound = {
                                        round: parseInt(roundMatch[1]),
                                        participants: parseInt(roundMatch[2]),
                                        entries: []
                                    };
                                    roundEntries.push(currentRound);
                                    currentEntry = null; // Reset entry focus
                                    continue;
                                }

                                // Match: [P1-Port8003]: content or [Secretary-Port8003]: content
                                const entryMatch = line.match(/^\s*\[(P\d+|Secretary)-Port(\d+|\?)\]:\s*(.*)/);
                                if (entryMatch) {
                                    if (currentRound) {
                                        console.log(`  ✅ Found Entry: ${entryMatch[1]} (Port ${entryMatch[2]})`);
                                        currentEntry = {
                                            role: entryMatch[1].startsWith('Secretary') ? 'secretary' : 'participant',
                                            label: entryMatch[1],
                                            port: entryMatch[2],
                                            preview: entryMatch[3].trim() // Start of content
                                        };
                                        currentRound.entries.push(currentEntry);
                                    } else {
                                        console.warn(`  ⚠️ Orphan Entry (no round): ${line.substring(0, 50)}...`);
                                    }
                                    continue;
                                }

                                // Multi-line Content Append
                                if (currentEntry) {
                                    const trimLine = line.trim();
                                    // Only append if line has content (or if we want to preserve empty lines)
                                    // For now, let's just append non-empty lines with a newline separator
                                    if (trimLine) {
                                        if (currentEntry.preview) {
                                            currentEntry.preview += "\n" + trimLine;
                                        } else {
                                            currentEntry.preview = trimLine;
                                        }
                                    }
                                }
                            }
                            console.log(`Total Rounds Parsed: ${roundEntries.length}`);
                            console.groupEnd();
                        }

                        // Render meeting overview header
                        html += `<div class="swarm-round-header" style="margin: 12px 0 6px 0;">
                                    <span class="round-badge" style="background:#e65100;">Meeting</span>
                                    <span class="round-label">${meetingTopic.substring(0, 40)} (${maxRounds} rounds, ${participantCount} per round)</span>
                                 </div>`;

                        // Render each round
                        if (roundEntries.length > 0) {
                            roundEntries.forEach(round => {
                                // Round header
                                html += `<div class="swarm-round-header" style="margin: 8px 0 4px 0;">
                                            <span class="round-badge">R${round.round}</span>
                                            <span class="round-label">${round.participants} participants</span>
                                         </div>`;

                                // Participant and Secretary cards
                                round.entries.forEach(entry => {
                                    const isSecretary = entry.role === 'Secretary';
                                    const icon = isSecretary ? 'edit_note' : 'history';
                                    const label = isSecretary ? `Secretary (Port ${entry.port})` : `${entry.role} (Port ${entry.port})`;
                                    const roleTag = isSecretary ? '<span style="background:#e65100;color:#fff;padding:1px 6px;border-radius:4px;font-size:11px;margin-left:6px;">Secretary</span>' : '';

                                    html += `<div class="swarm-card success" style="margin: 6px 0;">
                                                <div class="swarm-card-header">
                                                    <div class="swarm-status-icon"><span class="material-symbols-outlined">${icon}</span></div>
                                                    <div class="swarm-info">
                                                        <div class="swarm-worker-id">${label}${roleTag}</div>
                                                        <div class="swarm-task-preview" title="${entry.preview.substring(0, 500)}">${entry.preview.length > 60 ? entry.preview.substring(0, 60) + "..." : entry.preview}</div>
                                                    </div>
                                                    <div class="swarm-meta">History</div>
                                                </div>
                                                <details class="swarm-logs-wrapper">
                                                    <summary>Show History Logs</summary>
                                                    <div class="swarm-logs-content">
                                                        <pre class="swarm-terminal">${entry.preview}</pre>
                                                    </div>
                                                </details>
                                             </div>`;
                                });
                            });
                        } else {
                            // Fallback: no structured details parsed, show basic info
                            html += `<div class="swarm-card success" style="margin: 10px 0;">
                                        <div class="swarm-card-header">
                                            <div class="swarm-status-icon"><span class="material-symbols-outlined">groups</span></div>
                                            <div class="swarm-info">
                                                <div class="swarm-worker-id">Meeting: ${meetingTopic.substring(0, 30)}</div>
                                                <div class="swarm-task-preview">${maxRounds} rounds, ${participantCount} participants per round</div>
                                            </div>
                                            <div class="swarm-meta">History</div>
                                        </div>
                                     </div>`;
                        }
                    } else if (block.tool_name === 'deep_think' && block.tool_args) {
                        // === deep_think (Aletheia GVR) History Cards ===
                        const args = block.tool_args;
                        const taskPreview = args.task_instruction ? args.task_instruction.substring(0, 60) + '...' : 'Deep Think Task';
                        const mPaths = args.m_paths || '?';
                        const nRounds = args.n_rounds || '?';

                        // Parse result content
                        let resultContent = '';

                        if (i + 1 < blocks.length && (blocks[i + 1].type === 'tool_result' || blocks[i + 1].type === 'function_response')) {
                            resultContent = blocks[i + 1].tool_result_clean || blocks[i + 1].content || '';
                            resultContent = resultContent.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n').replace(/\\r/g, '\n');
                        }

                        // Detect success/failure from report title
                        const isSuccess = resultContent.includes('\u6162\u601d\u8003\u5b8c\u6210');

                        // Parse PHASE_LOGS for per-phase detail
                        let phaseLogs = {};
                        const phaseLogsMatch = resultContent.match(/<!-- PHASE_LOGS_START -->\n([\s\S]*?)\n<!-- PHASE_LOGS_END -->/);
                        if (phaseLogsMatch) {
                            const logMatches = [...phaseLogsMatch[1].matchAll(/\[PHASE_LOG\]\s*([^|]+?)\s*\|\s*Status:\s*(\w+)\s*\|\s*([\s\S]*?)(?=\n\[PHASE_LOG\]|$)/g)];
                            for (const m of logMatches) {
                                phaseLogs[m[1].trim()] = { status: m[2], detail: m[3].trim() };
                            }
                        }
                        console.log('[DeepThink History Debug] phaseLogs parsed:', Object.keys(phaseLogs).length, 'entries');

                        // Render overview header
                        const statusColor = isSuccess ? '#2e7d32' : '#c62828';
                        const statusText = isSuccess ? 'GVR Success' : 'GVR Failed';
                        html += `<div class="swarm-round-header" style="margin: 12px 0 6px 0;">
                                    <span class="round-badge" style="background:${statusColor};">${statusText}</span>
                                    <span class="round-label">Aletheia Deep Think (${mPaths} paths, ${nRounds} max rounds)</span>
                                 </div>`;

                        // Phase 1: QA Tester
                        const qaLog = phaseLogs['QA Tester'];
                        const qaDetail = qaLog ? qaLog.detail : '';
                        html += `<div class="swarm-card success" style="margin: 6px 0;">
                                    <div class="swarm-card-header">
                                        <div class="swarm-status-icon"><span class="material-symbols-outlined">psychology</span></div>
                                        <div class="swarm-info">
                                            <div class="swarm-worker-id">[QA Tester] Phase 1</div>
                                            <div class="swarm-task-preview">Generated ground-truth test script</div>
                                        </div>
                                        <div class="swarm-meta">Done</div>
                                    </div>
                                    ${qaDetail ? `<details class="swarm-logs-wrapper"><summary>Test Script Path</summary><pre class="swarm-terminal">${qaDetail}</pre></details>` : ''}
                                 </div>`;

                        // Phase 2: Solver cards - status from PHASE_LOG
                        const numPaths = parseInt(mPaths) || 0;
                        for (let p = 1; p <= numPaths; p++) {
                            const solverLog = phaseLogs[`Solver Path ${p}`];

                            let pathStatus = 'Unknown';
                            let cardClass = 'running';
                            let pathIcon = 'help';
                            let solverDetail = '';
                            let solverFile = '';
                            let solverExecOutput = '';
                            let roundsInfo = '';

                            if (solverLog) {
                                pathStatus = solverLog.status;
                                cardClass = pathStatus === 'Passed' ? 'success' : 'fail';
                                pathIcon = pathStatus === 'Passed' ? 'check_circle' : 'cancel';

                                const roundsMatch = solverLog.detail.match(/Rounds:\s*(\d+\/\d+)/);
                                if (roundsMatch) roundsInfo = roundsMatch[1];
                                const fileMatch = solverLog.detail.match(/SolutionFile:\s*([^\n|]*?)(?:\s*\||$)/);
                                if (fileMatch && fileMatch[1].trim()) solverFile = fileMatch[1].trim();
                                const execMatch = solverLog.detail.match(/ExecOutput:\s*([\s\S]*?)(?:\s*\|\s*LastError:|$)/);
                                if (execMatch && execMatch[1].trim()) solverExecOutput = execMatch[1].trim();
                                const errorMatch = solverLog.detail.match(/LastError:\s*([\s\S]*)/);
                                if (errorMatch && errorMatch[1].trim()) solverDetail = errorMatch[1].trim();
                            }

                            const roundsLabel = roundsInfo ? ` (Round ${roundsInfo})` : ` (max ${nRounds} rounds)`;

                            let solverExpandHtml = '';
                            if (solverDetail) {
                                solverExpandHtml += `<details class="swarm-logs-wrapper"><summary>Last Error Log</summary><pre class="swarm-terminal">${solverDetail}</pre></details>`;
                            }
                            if (solverFile) {
                                solverExpandHtml += `<details class="swarm-logs-wrapper"><summary>Solution Details</summary><pre class="swarm-terminal">File: ${solverFile}${solverExecOutput ? '\n\nTest Output:\n' + solverExecOutput : ''}</pre></details>`;
                            }

                            html += `<div class="swarm-card ${cardClass}" style="margin: 6px 0;">
                                        <div class="swarm-card-header">
                                            <div class="swarm-status-icon"><span class="material-symbols-outlined">${pathIcon}</span></div>
                                            <div class="swarm-info">
                                                <div class="swarm-worker-id">[Solver] Path ${p}</div>
                                                <div class="swarm-task-preview">${pathStatus} sandbox verification${roundsLabel}</div>
                                            </div>
                                            <div class="swarm-meta">${pathStatus}</div>
                                        </div>
                                        ${solverExpandHtml}
                                     </div>`;

                            // Reviser cards for this path (rendered after Solver card)
                            const maxRoundsInt = parseInt(nRounds) || 3;
                            for (let r = 1; r < maxRoundsInt; r++) {
                                const reviserLog = phaseLogs[`Reviser Path ${p} Round ${r}`];
                                if (!reviserLog) continue;

                                let reviserFile = '';
                                let reviserError = '';
                                if (reviserLog.detail) {
                                    const fMatch = reviserLog.detail.match(/SolutionFile:\s*([^\n|]*?)(?:\s*\||$)/);
                                    if (fMatch && fMatch[1].trim()) reviserFile = fMatch[1].trim();
                                    const eMatch = reviserLog.detail.match(/ErrorInput:\s*([\s\S]*)/);
                                    if (eMatch && eMatch[1].trim()) reviserError = eMatch[1].trim();
                                }

                                let reviserExpandHtml = '';
                                if (reviserFile) {
                                    reviserExpandHtml += `<details class="swarm-logs-wrapper"><summary>Revised File</summary><pre class="swarm-terminal">${reviserFile}</pre></details>`;
                                }
                                if (reviserError) {
                                    const errorDisplay = reviserError.length > 2000 ? reviserError.substring(0, 2000) + '\n...(Truncated)' : reviserError;
                                    reviserExpandHtml += `<details class="swarm-logs-wrapper"><summary>Error Input (Traceback)</summary><pre class="swarm-terminal">${errorDisplay}</pre></details>`;
                                }

                                html += `<div class="swarm-card running" style="margin: 6px 0 6px 20px;">
                                            <div class="swarm-card-header">
                                                <div class="swarm-status-icon"><span class="material-symbols-outlined">build</span></div>
                                                <div class="swarm-info">
                                                    <div class="swarm-worker-id">[Reviser] Path ${p} Round ${r}</div>
                                                    <div class="swarm-task-preview">Code revision based on test failure</div>
                                                </div>
                                                <div class="swarm-meta">${reviserLog.status}</div>
                                            </div>
                                            ${reviserExpandHtml}
                                         </div>`;
                            }
                        }

                        // Phase 3: Arbiter - show whenever PHASE_LOG exists
                        const arbiterLog = phaseLogs['Arbiter'];
                        if (arbiterLog) {
                            let arbiterContent = arbiterLog.detail || 'Evaluation complete.';
                            // Extract just the Reason portion from detail
                            const reasonMatch = arbiterContent.match(/Reason:\s*([\s\S]*)/);
                            if (reasonMatch) arbiterContent = reasonMatch[1].trim();

                            const displayContent = arbiterContent.length > 3000 ? arbiterContent.substring(0, 3000) + '\n...(Truncated)' : arbiterContent;

                            html += `<div class="swarm-card success" style="margin: 6px 0;">
                                        <div class="swarm-card-header">
                                            <div class="swarm-status-icon"><span class="material-symbols-outlined">psychology</span></div>
                                            <div class="swarm-info">
                                                <div class="swarm-worker-id">[Arbiter] Final Evaluation</div>
                                                <div class="swarm-task-preview">Click to view analysis</div>
                                            </div>
                                            <div class="swarm-meta">Done</div>
                                        </div>
                                        <details class="swarm-logs-wrapper" open>
                                            <summary>Arbiter Analysis</summary>
                                            <pre class="swarm-terminal">${displayContent}</pre>
                                        </details>
                                     </div>`;
                        }
                    }
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
            } else if (block.type === 'round_header') {
                // [Meeting] Render round header for meeting round grouping
                const roleLabel = block.role === 'secretary' ? ' - Secretary Summarizing' : '';
                html += `<div id="swarm-round-${block.msgId}-${block.round}" class="swarm-round-header">
                    <span class="round-badge">Round ${block.round}/${block.totalRounds}</span>
                    <span class="round-label">${roleLabel}</span>
                </div>`;
            } else if (block.type === 'swarm_placeholder') {
                // [New] Render placeholder for inline swarm card
                // Use round-aware suffix if meeting_round is present
                // Include role to prevent secretary/participant collision
                const rolePrefix = block.role === 'secretary' ? 'sec-' : '';
                let suffix = `${block.port}`;
                if (block.round) {
                    suffix = `R${block.round}-${rolePrefix}${block.port}`;
                } else if (block.data && block.data.session_id) {
                    suffix = `${block.data.session_id}-${block.port}`;
                }
                html += `<div id="swarm-placeholder-${block.msgId}-${suffix}" class="swarm-placeholder" data-port="${block.port}" style="margin: 10px 0;"></div>`;
            }
        }

        return html;
    }

    // ==========================================
    // [新增] 触发rewind与重新编辑核心逻辑
    // ==========================================
    window.triggerRewind = async function (invocationId, msgId) {
        if (!confirm('确定要修改这条消息吗？此节点之后的对话记忆将被抹除')) return;

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
            // 与 sendMessage 保持一致的 app_name 获取逻辑（兼容 Swarm 模式）
            let rewindAppName = APP_NAME;
            const _rewindIsSwarm = sessionStorage.getItem('current_is_swarm');
            const _rewindLeaderPort = sessionStorage.getItem('current_leader_port');
            if (_rewindIsSwarm === 'true' && _rewindLeaderPort) {
                rewindAppName = `swarm_from_${_rewindLeaderPort}`;
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

                // rewind 后始终保持 chat-mode（用户还需要重新输入）
                // 隐藏 welcomeScreen 但不切换到 welcome-mode
                const welcomeScreenEl = document.getElementById('welcomeScreen');
                if (welcomeScreenEl) welcomeScreenEl.style.display = 'none';
                document.body.classList.remove('welcome-mode');
                document.body.classList.add('chat-mode');

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
            const currentUserId = getUserId();

            // 同时查询个人对话和 Swarm 任务会话
            const personalResponse = await fetch(
                `/api/sessions?app_name=${APP_NAME}&user_id=${currentUserId}`
            );
            const personalData = await personalResponse.json();

            console.log('[会话列表] 个人会话数:', personalData.sessions?.length || 0);

            // 查询 Swarm 会话（尝试常见的 Leader 端口）
            const swarmSessions = [];
            const possibleLeaderPorts = [8000, 8001, 8002, 8003, 8004];

            for (const port of possibleLeaderPorts) {
                try {
                    const swarmAppName = `swarm_from_${port}`;
                    const swarmResponse = await fetch(
                        `/api/sessions?app_name=${swarmAppName}&user_id=${currentUserId}`
                    );
                    const swarmData = await swarmResponse.json();

                    if (swarmData.sessions && swarmData.sessions.length > 0) {
                        console.log(`[会话列表] 找到 ${swarmData.sessions.length} 个 Swarm 会话 (app_name=${swarmAppName})`);

                        // 标记为 Swarm 会话，leaderPort 从 app_name 解析
                        swarmData.sessions.forEach(s => {
                            s.isSwarm = true;
                            s.leaderPort = port;  // 从 swarm_from_<port> 解析出的端口
                        });
                        swarmSessions.push(...swarmData.sessions);
                    }
                } catch (e) {
                    // 忽略错误，继续查询下一个端口
                    console.warn(`[会话列表] 查询 swarm_from_${port} 失败:`, e);
                }
            }

            console.log('[会话列表] Swarm 会话总数:', swarmSessions.length);

            // 合并会话列表
            const allSessions = [
                ...(personalData.sessions || []),
                ...swarmSessions
            ];

            console.log('[会话列表] 总会话数:', allSessions.length);

            renderSessionList(allSessions);
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

            // 如果是 Swarm 会话，添加标记
            if (session.isSwarm) {
                const swarmBadge = document.createElement('span');
                swarmBadge.textContent = '[Agent-Team-TASK] ';
                swarmBadge.style.marginRight = '4px';
                swarmBadge.style.color = '#ff9800'; // Add orange color to make it distinct
                swarmBadge.style.fontWeight = 'bold';
                swarmBadge.title = `来自 Leader Port ${session.leaderPort || 'Unknown'}`;
                titleSpan.appendChild(swarmBadge);
            }

            // [Fix] 不使用 else if，允许同时显示 Leader 标记
            if (session.task_type === 'swarm_leader') {
                const leaderBadge = document.createElement('span');
                leaderBadge.textContent = '[Agent-Team-LEADER] ';
                leaderBadge.style.marginRight = '4px';
                leaderBadge.style.color = '#9c27b0'; // Purple for Leader
                leaderBadge.style.fontWeight = 'bold';
                titleSpan.appendChild(leaderBadge);
            }

            const titleText = document.createTextNode(session.title || '新对话');
            titleSpan.appendChild(titleText);

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
                    await deleteSession(session.session_id, session.isSwarm, session.leaderPort);
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
            item.dataset.isSwarm = session.isSwarm || false;
            item.dataset.leaderPort = session.leaderPort || '';

            item.addEventListener('click', () => {
                switchSession(session.session_id, session.isSwarm, session.leaderPort);
            });

            container.appendChild(item);
        });
    }

    // 切换会话
    async function switchSession(sessionId, isSwarm = false, leaderPort = null) {
        const currentSessionId = getCurrentSessionId();
        if (sessionId === currentSessionId) return;

        console.log('切换会话:', sessionId, isSwarm ? `(Swarm from ${leaderPort})` : '(个人对话)');

        // 清空聊天容器
        while (chatContainer.firstChild) {
            chatContainer.removeChild(chatContainer.firstChild);
        }

        // 更新状态
        setCurrentSessionId(sessionId);

        // 存储 Swarm 会话信息到 sessionStorage
        if (isSwarm && leaderPort) {
            sessionStorage.setItem('current_is_swarm', 'true');
            sessionStorage.setItem('current_leader_port', leaderPort);
        } else {
            sessionStorage.removeItem('current_is_swarm');
            sessionStorage.removeItem('current_leader_port');
        }

        // 刷新列表高亮
        await loadSessions();

        // 加载历史消息
        await loadSessionHistory(sessionId, isSwarm, leaderPort);
    }

    // 辅助函数: 检查 blocks 是否包含有效内容
    function hasValidContent(blocks) {
        if (!blocks || blocks.length === 0) return false;
        // 只要有一个 block 内容不为空(trim后),就视为有效
        return blocks.some(b => b.content && b.content.trim().length > 0);
    }

    // 加载会话历史
    async function loadSessionHistory(sessionId, isSwarm = false, leaderPort = null) {
        try {
            // 动态确定 app_name
            let appName = APP_NAME;
            if (isSwarm && leaderPort) {
                appName = `swarm_from_${leaderPort}`;
            } else {
                // 尝试从 sessionStorage 恢复
                const storedIsSwarm = sessionStorage.getItem('current_is_swarm');
                const storedLeaderPort = sessionStorage.getItem('current_leader_port');
                if (storedIsSwarm === 'true' && storedLeaderPort) {
                    appName = `swarm_from_${storedLeaderPort}`;
                    isSwarm = true;
                }
            }

            console.log(`[加载历史] session=${sessionId}, app_name=${appName}`);

            const response = await fetch(
                `/api/sessions/${sessionId}/history?app_name=${appName}&user_id=${getUserId()}`
            );
            const data = await response.json();

            // 关键修复：历史重载前先清空旧 DOM，避免同一 session 的历史被重复追加
            while (chatContainer.firstChild) {
                chatContainer.removeChild(chatContainer.firstChild);
            }

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
            for (let i = 0; i < data.messages.length; i++) {
                const msg = data.messages[i];

                if (msg.role === 'user') {
                    // 用户消息渲染 text + images
                    const hasText = msg.text && msg.text.trim();
                    const hasImages = msg.images && msg.images.length > 0;
                    if (hasText || hasImages) {
                        // [修改] 最后一个参数传入后端的 msg.invocation_id
                        appendMessage('user', msg.text || '', false, 'Ciri', msg.images || [], msg.invocation_id);
                    }
                } else if (msg.role === 'model') {
                    // 优先处理 blocks 结构
                    if (msg.blocks && hasValidContent(msg.blocks)) {

                        // [Fix] Merge Logic: Check if next message is a tool_result for this tool_call
                        // This fixes the issue where hold_meeting history card couldn't see the result logs
                        if (i + 1 < data.messages.length) {
                            const nextMsg = data.messages[i + 1];
                            if (nextMsg.role === 'model' && nextMsg.blocks && hasValidContent(nextMsg.blocks)) {
                                // Simple heuristic:
                                // Current has tool_call/tool_use?
                                // Next has tool_result?
                                const hasToolCall = msg.blocks.some(b => b.type === 'tool_call' || b.type === 'tool_use');
                                const hasToolResult = nextMsg.blocks.some(b => b.type === 'tool_result' || b.type === 'function_response');

                                if (hasToolCall && hasToolResult) {
                                    console.log(`[History] Merging tool_call (msg ${i}) with tool_result (msg ${i + 1})`);
                                    // Append next message blocks to current
                                    msg.blocks = msg.blocks.concat(nextMsg.blocks);
                                    // Skip next message
                                    i++;
                                }
                            }
                        }

                        const msgId = appendMessage('model', '', false);
                        updateMessage(msgId, msg.blocks, true);
                    }
                    // 兼容旧的文本格式 (只有 text 没有 blocks)
                    else if (msg.text && msg.text.trim()) {
                        appendMessage('model', msg.text, false);
                    }
                    else {
                        // 真的没有内容,忽略
                        // console.warn('[前端调试] 忽略空消息:', msg);
                    }
                }
            }

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
    async function deleteSession(sessionId, isSwarm = false, leaderPort = null) {
        try {
            // 动态确定 app_name
            let appName = APP_NAME;
            if (isSwarm && leaderPort) {
                appName = `swarm_from_${leaderPort}`;
            }

            console.log(`[删除会话] sessionId=${sessionId}, appName=${appName}`);

            const response = await fetch(
                `/api/sessions/${sessionId}?app_name=${appName}&user_id=${getUserId()}`,  // 动态获取
                { method: 'DELETE' }
            );

            if (!response.ok) {
                throw new Error('删除失败');
            }

            // 如果删除的是当前会话, 清除状态并返回欢迎页面
            if (sessionId === getCurrentSessionId()) {
                sessionStorage.removeItem('current_session_id');
                // 清空界面
                while (chatContainer.firstChild) {
                    chatContainer.removeChild(chatContainer.firstChild);
                }
                showWelcomeScreen();
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
        // 设置初始选中值 (改为 localStorage 以兼容所有手机浏览器刷新)
        const currentUserId = localStorage.getItem('user_id_override') || 'user_001';

        // 如果当前 ID 不在预设选项中，动态添加它
        const presetValues = Array.from(userSelector.options).map(opt => opt.value);
        if (!presetValues.includes(currentUserId)) {
            const newOpt = document.createElement('option');
            newOpt.value = currentUserId;
            newOpt.textContent = `用户: ${currentUserId}`;
            // 插入到“自定义”之前
            userSelector.insertBefore(newOpt, userSelector.querySelector('option[value="custom"]'));
        }
        userSelector.value = currentUserId;

        // 监听切换事件
        userSelector.addEventListener('change', (e) => {
            let newUserId = e.target.value;

            if (newUserId === 'custom') {
                const customName = prompt('请输入自定义用户名 (例如: Jack):');
                if (!customName || customName.trim() === '') {
                    // 取消选择，恢复原值
                    userSelector.value = currentUserId;
                    return;
                }
                newUserId = customName.trim();
            }

            console.log(`[切换用户] ${currentUserId} -> ${newUserId}`);

            // 更新用户ID (localStorage更稳定)
            localStorage.setItem('user_id_override', newUserId);

            // ⚠️ 关键修复：清除旧的 session_id，强制为新用户创建新会话
            sessionStorage.removeItem('current_session_id');
            console.log('[清除会话] 已清除旧会话，将为新用户创建新会话');

            // 延迟一点刷新，给手机浏览器IO写入时间
            setTimeout(() => {
                location.reload();
            }, 100);
        });
    }

    // ========================================
    // Settings Functionality
    // ========================================
    function initSettings() {
        const settingsBtn = document.getElementById('settingsBtn');
        const settingsModal = document.getElementById('settingsModal');
        const closeSettings = document.getElementById('closeSettings');
        const cancelSettings = document.getElementById('cancelSettings');
        const saveSettingsBtn = document.getElementById('saveSettingsBtn');
        const modelPreset = document.getElementById('modelPreset');

        if (!settingsBtn) return;

        settingsBtn.addEventListener('click', openSettings);
        closeSettings.addEventListener('click', () => settingsModal.classList.remove('visible'));
        cancelSettings.addEventListener('click', () => settingsModal.classList.remove('visible'));

        saveSettingsBtn.addEventListener('click', saveSettings);
        modelPreset.addEventListener('change', handlePresetChange);

        // Click outside to close
        settingsModal.addEventListener('click', (e) => {
            if (e.target === settingsModal) settingsModal.classList.remove('visible');
        });
    }

    // ==========================================
    // KAIROS Modal Logic
    // ==========================================
    function formatKairosTrackedTasks(tasks) {
        if (!tasks || tasks.length === 0) return '无';
        return tasks.map(task => {
            const summary = task.result_summary || task.error_summary || task.result || '';
            return [
                `- ${task.task_id} [${task.status}]`,
                `  desc: ${task.description || ''}`,
                `  created: ${task.created_at || '-'}`,
                `  completed: ${task.completed_at || '-'}`,
                `  summary: ${summary || '-'}`,
                `  log: ${task.log_path || '-'}`
            ].join('\n');
        }).join('\n\n');
    }

    function formatKairosWorkflow(workflow) {
        if (!workflow) return '无';
        const stages = (workflow.stages || []).map(stage => (
            `- ${stage.stage_id} [${stage.status}] ${stage.label} | tasks: ${(stage.task_ids || []).join(', ') || '-'} | artifacts: ${(stage.artifacts || []).join(', ') || '-'}`
        )).join('\n');
        return [
            `workflow_id: ${workflow.workflow_id || '-'}`,
            `goal: ${workflow.goal || '-'}`,
            `status: ${workflow.status || '-'}`,
            `current_stage: ${workflow.current_stage || '-'}`,
            `metadata: ${JSON.stringify(workflow.metadata || {}, null, 2)}`,
            `stages:\n${stages || '无'}`
        ].join('\n');
    }

    function formatKairosPlannedActions(actions) {
        if (!actions || actions.length === 0) return '无';
        return actions.map(action => [
            `- ${action.action_id || '-'}`,
            `  kind: ${action.kind || '-'}`,
            `  reason: ${action.reason || '-'}`,
            `  status: ${action.status || '-'}`,
            `  payload: ${JSON.stringify(action.payload || {}, null, 2)}`
        ].join('\n')).join('\n\n');
    }

    function formatKairosEvents(events) {
        if (!events || events.length === 0) return '无';
        return events.map(event => {
            const timestamp = event.ts || event.timestamp || '-';
            const kind = event.kind || event.event || 'event';
            const message = event.message || event.reason || '';
            return `[${timestamp}] ${kind}: ${message}`;
        }).join('\n');
    }

    function formatKairosResultSummaries(summaries) {
        if (!summaries || summaries.length === 0) return '无';
        return summaries.map(item => [
            `- ${item.task_id || '-' } [${item.status || '-'}]`,
            `  summary: ${item.summary_text || '-'}`,
            `  artifacts: ${item.artifact_status || '-'}`,
            `  result: ${item.result_summary || '-'}`,
            `  error: ${item.error_summary || '-'}`,
            `  log: ${item.log_hint || '-'}`
        ].join('\n')).join('\n\n');
    }

    function formatKairosConditionTree(tree) {
        if (!tree) return '无';
        const satisfied = (tree.satisfied || []).map(item => `  - ${item.kind || '-'}: ${item.target || '-'}${item.reason ? ` (${item.reason})` : ''}`).join('\n') || '  - 无';
        const missing = (tree.missing || []).map(item => `  - ${item.kind || '-'}: ${item.target || '-'}${item.reason ? ` (${item.reason})` : ''}`).join('\n') || '  - 无';
        return [
            `stage: ${tree.stage_id || '-'}`,
            `label: ${tree.stage_label || '-'}`,
            'satisfied:',
            satisfied,
            'missing:',
            missing
        ].join('\n');
    }

    function formatKairosStatus(kairos) {
        return [
            `enabled: ${kairos.enabled}`,
            `running: ${kairos.running}`,
            `busy: ${kairos.busy}`,
            `mode: ${kairos.mode}`,
            `last_tick_at: ${kairos.last_tick_at || '-'}`,
            `sleep_until: ${kairos.sleep_until || '-'}`,
            `pending_wake_reason: ${kairos.pending_wake_reason || '-'}`,
            `blocked_reason: ${kairos.blocked_reason || '-'}`,
            `tracked_dex_task_ids: ${(kairos.tracked_dex_task_ids || []).join(', ') || '-'}`,
            `active_trigger: ${kairos.active_trigger ? JSON.stringify(kairos.active_trigger, null, 2) : '-'}`,
            `pending_triggers: ${JSON.stringify(kairos.pending_triggers || [], null, 2)}`,
            `schedules: ${JSON.stringify(kairos.schedules || [], null, 2)}`,
            `active_workflow: ${kairos.active_workflow ? kairos.active_workflow.workflow_id : '-'}`,
            `planned_actions: ${(kairos.planned_actions || []).length}`
        ].join('\n');
    }

    async function kairosRequest(path, method = 'GET', body = null) {
        const sessionId = getCurrentSessionId();
        if (!sessionId) {
            throw new Error('请先选择或创建一个对话');
        }
        const url = `/api/sessions/${sessionId}${path}`;
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' }
        };
        if (body) {
            options.body = JSON.stringify(body);
        }
        const response = await fetch(url, options);
        if (!response.ok) {
            throw new Error(`KAIROS request failed: ${response.status}`);
        }
        return response.json();
    }

    function initKairosModal() {
        const kairosBtn = document.getElementById('kairosBtn');
        const kairosModal = document.getElementById('kairosModal');
        const closeKairos = document.getElementById('closeKairos');
        const kairosStartBtn = document.getElementById('kairosStartBtn');
        const kairosStopBtn = document.getElementById('kairosStopBtn');
        const kairosWakeBtn = document.getElementById('kairosWakeBtn');
        const kairosRefreshBtn = document.getElementById('kairosRefreshBtn');
        const kairosAddSchedBtn = document.getElementById('kairosAddSchedBtn');
        const kairosDelSchedBtn = document.getElementById('kairosDelSchedBtn');
        const kairosDexRegBtn = document.getElementById('kairosDexRegBtn');

        if (!kairosBtn) return;

        kairosBtn.addEventListener('click', openKairosModal);
        closeKairos.addEventListener('click', () => kairosModal.classList.remove('visible'));
        kairosModal.addEventListener('click', (e) => {
            if (e.target === kairosModal) kairosModal.classList.remove('visible');
        });

        kairosStartBtn.addEventListener('click', startKairos);
        kairosStopBtn.addEventListener('click', stopKairos);
        kairosWakeBtn.addEventListener('click', wakeKairos);
        kairosRefreshBtn.addEventListener('click', refreshKairosStatus);
        kairosAddSchedBtn.addEventListener('click', addKairosSchedule);
        kairosDelSchedBtn.addEventListener('click', deleteKairosSchedule);
        kairosDexRegBtn.addEventListener('click', registerDexHandoff);
    }

    async function openKairosModal() {
        const kairosModal = document.getElementById('kairosModal');
        const kairosNoSession = document.getElementById('kairosNoSession');
        const kairosPanel = document.getElementById('kairosPanel');

        kairosModal.classList.add('visible');

        const sessionId = getCurrentSessionId();
        if (!sessionId) {
            kairosNoSession.style.display = 'block';
            kairosPanel.style.display = 'none';
            return;
        }

        kairosNoSession.style.display = 'none';
        kairosPanel.style.display = 'block';
        await refreshKairosStatus();
    }

    async function refreshKairosStatus() {
        const sessionId = getCurrentSessionId();
        const noSession = document.getElementById('kairosNoSession');
        const panel = document.getElementById('kairosPanel');
        const statusEl = document.getElementById('kairosStatus');
        const eventsEl = document.getElementById('kairosEvents');
        const trackedEl = document.getElementById('kairosTrackedDexTasks');
        const workflowEl = document.getElementById('kairosWorkflow');
        const plannedActionsEl = document.getElementById('kairosPlannedActions');
        const blockedReasonEl = document.getElementById('kairosBlockedReason');
        const resultSummaryEl = document.getElementById('kairosResultSummary');

        if (!sessionId) {
            if (noSession) noSession.style.display = 'block';
            if (panel) panel.style.display = 'none';
            return;
        }

        if (noSession) noSession.style.display = 'none';
        if (panel) panel.style.display = 'block';

        try {
            const params = new URLSearchParams({
                app_name: APP_NAME,
                user_id: getUserId()
            });
            const response = await fetch(`/api/sessions/${sessionId}/kairos/status?${params.toString()}`);
            if (!response.ok) {
                throw new Error(`KAIROS status failed: ${response.status}`);
            }
            const data = await response.json();
            const kairos = data.kairos || {};
            if (statusEl) statusEl.textContent = formatKairosStatus(kairos);
            if (eventsEl) eventsEl.textContent = formatKairosEvents(kairos.recent_events || []);
            if (trackedEl) trackedEl.textContent = formatKairosTrackedTasks(kairos.tracked_dex_tasks || []);
            if (workflowEl) workflowEl.textContent = formatKairosWorkflow(kairos.active_workflow || data.active_workflow || null);
            if (plannedActionsEl) plannedActionsEl.textContent = formatKairosPlannedActions(kairos.planned_actions || data.planned_actions || []);
            if (blockedReasonEl) blockedReasonEl.textContent = formatKairosConditionTree(kairos.condition_tree || data.condition_tree) || kairos.blocked_reason || data.blocked_reason || '无';
            if (resultSummaryEl) resultSummaryEl.textContent = formatKairosResultSummaries(kairos.task_summaries || data.task_summaries || []);
        } catch (e) {
            console.error('[KAIROS] 刷新状态失败:', e);
            if (statusEl) statusEl.textContent = `加载失败: ${e.message}`;
            if (eventsEl) eventsEl.textContent = '无';
            if (trackedEl) trackedEl.textContent = '无';
            if (workflowEl) workflowEl.textContent = '无';
            if (plannedActionsEl) plannedActionsEl.textContent = '无';
            if (blockedReasonEl) blockedReasonEl.textContent = '无';
            if (resultSummaryEl) resultSummaryEl.textContent = '无';
        }
    }

    async function startKairos() {
        const sessionId = getCurrentSessionId();
        if (!sessionId) return;

        try {
            const data = await kairosRequest('/kairos/start', 'POST', { app_name: APP_NAME, user_id: getUserId() });
            if (data.status === 'ok') {
                alert('KAIROS 启动成功');
                await refreshKairosStatus();
            } else {
                alert('启动失败: ' + (data.error || '未知错误'));
            }
        } catch (e) {
            console.error('[KAIROS] 启动失败:', e);
            alert('启动失败: ' + e.message);
        }
    }

    async function stopKairos() {
        const sessionId = getCurrentSessionId();
        if (!sessionId) return;

        try {
            const data = await kairosRequest('/kairos/stop', 'POST', { app_name: APP_NAME, user_id: getUserId() });
            if (data.status === 'ok') {
                alert('KAIROS 已停止');
                await refreshKairosStatus();
            } else {
                alert('停止失败: ' + (data.error || '未知错误'));
            }
        } catch (e) {
            console.error('[KAIROS] 停止失败:', e);
            alert('停止失败: ' + e.message);
        }
    }

    async function wakeKairos() {
        const sessionId = getCurrentSessionId();
        if (!sessionId) return;

        const reason = document.getElementById('kairosWakeReason').value || 'manual_wake';

        try {
            const data = await kairosRequest('/kairos/wake', 'POST', { app_name: APP_NAME, user_id: getUserId(), reason });
            if (data.status === 'ok') {
                alert('唤醒请求已发送');
                await refreshKairosStatus();

                // 修复：唤醒后重新加载历史消息，避免累积的 kairos 事件在下次切换会话时突然出现
                const storedIsSwarm = sessionStorage.getItem('current_is_swarm');
                const storedLeaderPort = sessionStorage.getItem('current_leader_port');
                await loadSessionHistory(
                    sessionId,
                    storedIsSwarm === 'true',
                    storedLeaderPort
                );
            } else {
                alert('唤醒失败: ' + (data.error || '未知错误'));
            }
        } catch (e) {
            console.error('[KAIROS] 唤醒失败:', e);
            alert('唤醒失败: ' + e.message);
        }
    }

    async function addKairosSchedule() {
        const sessionId = getCurrentSessionId();
        if (!sessionId) return;

        const schedule_id = document.getElementById('kairosSchedId').value;
        const cron = document.getElementById('kairosSchedCron').value;
        const reason = document.getElementById('kairosSchedReason').value;

        if (!schedule_id || !cron || !reason) {
            alert('请填写完整的 schedule 信息');
            return;
        }

        try {
            const data = await kairosRequest('/kairos/schedules', 'POST', {
                app_name: APP_NAME,
                user_id: getUserId(),
                schedule_id,
                cron,
                reason,
                enabled: true
            });
            if (data.status === 'ok') {
                alert('Schedule 添加成功');
                await refreshKairosStatus();
            } else {
                alert('添加失败: ' + (data.error || '未知错误'));
            }
        } catch (e) {
            console.error('[KAIROS] 添加 schedule 失败:', e);
            alert('添加失败: ' + e.message);
        }
    }

    async function deleteKairosSchedule() {
        const sessionId = getCurrentSessionId();
        if (!sessionId) return;

        const schedule_id = document.getElementById('kairosSchedId').value;
        if (!schedule_id) {
            alert('请填写 schedule_id');
            return;
        }

        try {
            const params = new URLSearchParams({ app_name: APP_NAME, user_id: getUserId() });
            const response = await fetch(
                `/api/sessions/${sessionId}/kairos/schedules/${encodeURIComponent(schedule_id)}?${params.toString()}`,
                { method: 'DELETE' }
            );
            if (!response.ok) {
                throw new Error(`Delete schedule failed: ${response.status}`);
            }
            const data = await response.json();
            if (data.status === 'ok') {
                alert('Schedule 删除成功');
                await refreshKairosStatus();
            } else {
                alert('删除失败: ' + (data.error || '未知错误'));
            }
        } catch (e) {
            console.error('[KAIROS] 删除 schedule 失败:', e);
            alert('删除失败: ' + e.message);
        }
    }

    async function registerDexHandoff() {
        const sessionId = getCurrentSessionId();
        if (!sessionId) return;

        const task_id = document.getElementById('kairosDexTaskId').value;
        const description = document.getElementById('kairosDexDesc').value;

        if (!task_id || !description) {
            alert('请填写 task_id 和 description');
            return;
        }

        try {
            const data = await kairosRequest('/kairos/dex/register', 'POST', {
                app_name: APP_NAME,
                user_id: getUserId(),
                task_id,
                description
            });
            if (data.status === 'ok') {
                alert('Dex handoff 注册成功');
                await refreshKairosStatus();
            } else {
                alert('注册失败: ' + (data.error || '未知错误'));
            }
        } catch (e) {
            console.error('[KAIROS] 注册 dex handoff 失败:', e);
            alert('注册失败: ' + e.message);
        }
    }

    let currentPresets = {}; // 全局变量存储从后端获取的预设

    async function openSettings() {
        const settingsModal = document.getElementById('settingsModal');
        const settingModel = document.getElementById('settingModel');
        const settingApiBase = document.getElementById('settingApiBase');
        const settingApiKey = document.getElementById('settingApiKey');
        const modelPreset = document.getElementById('modelPreset');

        try {
            const response = await fetch('/api/settings');
            const config = await response.json();

            if (config.error) {
                console.error('Backend error:', config.error);
                alert(`获取设置失败: ${config.error}`);
                return;
            }

            // 动态填充预设下拉菜单
            // 填充预设
            modelPreset.innerHTML = '<option value="">-- 选择预设模型 --</option>';
            if (config.presets) {
                currentPresets = config.presets; // 统一使用全局变量名
                Object.keys(config.presets).forEach(id => {
                    const preset = config.presets[id];
                    const option = document.createElement('option');
                    option.value = id; // 逻辑标签 (项名)
                    option.textContent = preset.label || id;
                    modelPreset.appendChild(option);
                });
                console.log('[Settings] Presets loaded:', Object.keys(currentPresets));
                if (config.active_config) {
                    modelPreset.value = config.active_config;
                }
            }

            settingModel.value = config.model || '';
            settingApiBase.value = config.api_base || '';
            settingApiKey.value = '';
            settingApiKey.placeholder = config.api_key || 'sk-...';

            settingsModal.classList.add('visible');
        } catch (e) {
            console.error('Failed to fetch settings:', e);
            alert('获取设置失败');
        }
    }

    async function saveSettings() {
        const settingsModal = document.getElementById('settingsModal');
        const saveSettingsBtn = document.getElementById('saveSettingsBtn');
        const settingModel = document.getElementById('settingModel');
        const settingApiBase = document.getElementById('settingApiBase');
        const settingApiKey = document.getElementById('settingApiKey');
        const modelPreset = document.getElementById('modelPreset');

        const data = {
            model: settingModel.value.trim(),
            api_base: settingApiBase.value.trim(),
            api_key: settingApiKey.value.trim() || undefined,
            config_name: modelPreset.value, // 修正：必须保存预设标签名，而非物理模型名
            session_id: getCurrentSessionId()
        };
        console.log('[Settings] Saving data package:', data);

        try {
            saveSettingsBtn.disabled = true;
            saveSettingsBtn.textContent = '应用中...';

            const response = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (response.ok) {
                settingsModal.classList.remove('visible');
                console.log('Settings saved successfully');
            } else {
                alert('保存失败');
            }
        } catch (e) {
            console.error('Save settings error:', e);
            alert('网络请求出错');
        } finally {
            saveSettingsBtn.disabled = false;
            saveSettingsBtn.textContent = '保存并应用';
        }
    }

    function handlePresetChange() {
        const modelPreset = document.getElementById('modelPreset');
        const settingModel = document.getElementById('settingModel');
        const settingApiBase = document.getElementById('settingApiBase');
        const settingApiKey = document.getElementById('settingApiKey');

        const preset = modelPreset.value;
        console.log('[Settings] Preset changed to:', preset);

        if (preset === '' || preset === 'custom') return;

        // 使用全局变量 currentPresets 查找
        if (currentPresets && currentPresets[preset]) {
            const detail = currentPresets[preset];
            console.log('[Settings] Applying preset detail:', detail);
            settingModel.value = detail.model || preset;
            settingApiBase.value = detail.base || '';

            if (detail.api_key) {
                settingApiKey.value = '';
                settingApiKey.placeholder = detail.api_key;
            } else {
                settingApiKey.placeholder = 'sk-...';
            }
        } else {
            console.warn('[Settings] No detail found for preset:', preset);
        }
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

        // 初始化设置功能
        initSettings();

        // 初始化 KAIROS 功能
        initKairosModal();
    }

    // 初始化侧边栏调整大小功能
    function initSidebarResize() {
        const sidebar = document.querySelector('.sidebar');
        const handle = document.querySelector('.resize-handle');
        const menuBtn = document.querySelector('.menu-btn');
        const mobileMenuBtn = document.getElementById('mobileMenuBtn');
        const overlay = document.getElementById('mobileOverlay');
        let isResizing = false;

        // 判断是否为手机端
        const isMobile = () => window.innerWidth <= 768;

        // --- 手机端：关闭侧边栏 ---
        function closeMobileSidebar() {
            sidebar.classList.remove('mobile-open');
            if (overlay) {
                overlay.classList.remove('visible');
            }
        }

        // --- 手机端：打开侧边栏 ---
        function openMobileSidebar() {
            sidebar.classList.add('mobile-open');
            if (overlay) {
                overlay.classList.add('visible');
            }
        }

        // --- 1. 菜单按钮点击 ---
        menuBtn.addEventListener('click', () => {
            if (isMobile()) {
                // 手机端：切换 drawer 模式
                if (sidebar.classList.contains('mobile-open')) {
                    closeMobileSidebar();
                } else {
                    openMobileSidebar();
                }
            } else {
                // 桌面端：折叠/展开原逻辑
                if (sidebar.classList.contains('collapsed')) {
                    sidebar.classList.remove('collapsed');
                    const savedWidth = localStorage.getItem('sidebarWidth_v2') || '300px';
                    sidebar.style.width = savedWidth;
                    sidebar.style.minWidth = savedWidth;
                    sidebar.style.maxWidth = savedWidth;
                } else {
                    sidebar.classList.add('collapsed');
                    sidebar.style.width = '';
                    sidebar.style.minWidth = '';
                    sidebar.style.maxWidth = '';
                }
            }
        });

        // --- 2. 手机端：点击遮罩关闭侧边栏 ---
        if (overlay) {
            overlay.addEventListener('click', closeMobileSidebar);
        }

        // --- 2b. 手机端：top-bar 里的汉堡按钮 ---
        if (mobileMenuBtn) {
            mobileMenuBtn.addEventListener('click', () => {
                if (sidebar.classList.contains('mobile-open')) {
                    closeMobileSidebar();
                } else {
                    openMobileSidebar();
                }
            });
        }

        // --- 3. 桌面端：拖拽调整大小 ---
        // 恢复保存的宽度（仅桌面）
        if (!isMobile()) {
            const savedWidth = localStorage.getItem('sidebarWidth_v2');
            if (savedWidth) {
                sidebar.style.width = savedWidth;
                sidebar.style.minWidth = savedWidth;
            }
        }

        handle.addEventListener('mousedown', (e) => {
            if (isMobile()) return; // 手机端不支持拖拽
            if (sidebar.classList.contains('collapsed')) return;
            isResizing = true;
            handle.classList.add('active');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;

            let newWidth = e.clientX;

            const maxAllowedRatio = window.innerWidth < 600 ? 0.8 : 0.5;
            const maxAllowed = window.innerWidth * maxAllowedRatio;
            const minAllowed = 150;

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
                localStorage.setItem('sidebarWidth_v2', sidebar.style.width);
            }
        });

        // --- 4. 窗口大小变化时重置状态 ---
        window.addEventListener('resize', () => {
            if (!isMobile()) {
                // 切换回桌面：移除手机端样式
                closeMobileSidebar();
                const savedWidth = localStorage.getItem('sidebarWidth_v2') || '300px';
                sidebar.style.width = savedWidth;
                sidebar.style.minWidth = savedWidth;
            } else {
                // 切换回手机：清除桌面内联宽度
                sidebar.style.width = '';
                sidebar.style.minWidth = '';
                sidebar.style.maxWidth = '';
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

    // ==========================================
    // [Real-time] 实时语音输入逻辑
    // ==========================================
    let audioContext = null;
    let scriptProcessor = null;
    let mediaStreamSource = null;
    let websocket = null;
    let isRecording = false;

    const micBtn = document.getElementById('micBtn');

    if (micBtn) {
        micBtn.addEventListener('click', toggleRecording);
    }

    async function toggleRecording() {
        if (!isRecording) {
            startRecording();
        } else {
            stopRecording();
        }
    }

    async function startRecording() {
        try {
            // 1. 获取麦克风流
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            // 2. 初始化 WebSocket
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            // [Fix] 动态获取协议和主机，兼容 HTTPS (Cloudflare)
            const host = window.location.host;
            const wsUrl = `${protocol}//${host}/ws/audio`;

            websocket = new WebSocket(wsUrl);

            websocket.onopen = () => {
                console.log('[WS] 连接已建立');
                initAudioProcessing(stream);
            };

            websocket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                const text = data.text;

                if (text) {
                    // 实时更新输入框
                    if (userInput) {
                        userInput.value = text;
                        userInput.style.height = 'auto';
                        userInput.style.height = (userInput.scrollHeight) + 'px';
                    }
                }

                // if (data.is_final) {
                //     // 自动发送？还是让用户确认？让用户确认比较好。
                // }
            };

            // UI 更新
            isRecording = true;
            if (micBtn) {
                micBtn.style.color = '#ea4335';
                micBtn.style.backgroundColor = '#fce8e6';
                const span = micBtn.querySelector('span');
                if (span) span.textContent = 'mic_off';
            }

        } catch (err) {
            console.error('[STT] 无法获取麦克风权限', err);
            alert('无法获取麦克风权限');
        }
    }

    function initAudioProcessing(stream) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        mediaStreamSource = audioContext.createMediaStreamSource(stream);

        // 创建 ScriptProcessor
        scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);

        scriptProcessor.onaudioprocess = (event) => {
            if (!isRecording || !websocket || websocket.readyState !== WebSocket.OPEN) return;

            const inputData = event.inputBuffer.getChannelData(0); // 单通道 Float32Array

            // 浏览器录音一般是 44100Hz 或 48000Hz, 重采样到 16000Hz 给模型
            const resampledData = downsampleBuffer(inputData, audioContext.sampleRate, 16000);

            // 发送给后端
            websocket.send(resampledData.buffer);
        };

        mediaStreamSource.connect(scriptProcessor);
        scriptProcessor.connect(audioContext.destination);
    }

    function stopRecording() {
        isRecording = false;

        if (scriptProcessor) {
            scriptProcessor.disconnect();
            scriptProcessor = null;
        }
        if (mediaStreamSource) {
            mediaStreamSource.disconnect();
            mediaStreamSource = null;
        }
        if (audioContext) {
            audioContext.close();
            audioContext = null;
        }
        if (websocket) {
            websocket.close();
            websocket = null;
        }

        // UI 恢复
        if (micBtn) {
            micBtn.style.color = '';
            micBtn.style.backgroundColor = '';
            const span = micBtn.querySelector('span');
            if (span) span.textContent = 'mic';
        }
    }

    // 简单降采样算法
    function downsampleBuffer(buffer, sampleRate, outSampleRate) {
        if (outSampleRate === sampleRate) {
            return buffer;
        }
        if (outSampleRate > sampleRate) {
            throw 'downsampling rate should be smaller than original sample rate';
        }
        var sampleRateRatio = sampleRate / outSampleRate;
        var newLength = Math.round(buffer.length / sampleRateRatio);
        var result = new Float32Array(newLength);
        var offsetResult = 0;
        var offsetBuffer = 0;
        while (offsetResult < result.length) {
            var nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
            var accum = 0, count = 0;
            for (var i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
                accum += buffer[i];
                count++;
            }
            result[offsetResult] = accum / count;
            offsetResult++;
            offsetBuffer = nextOffsetBuffer;
        }
        return result;
    }

    // 调用初始化
    initializePage();
});
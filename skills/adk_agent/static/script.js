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
    const SESSION_ID = "session_001";

    stopBtn.addEventListener('click', async () => {
        try {
            console.log("Sending cancel request...");
            await fetch('/api/cancel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    app_name: APP_NAME,
                    user_id: USER_ID,
                    session_id: SESSION_ID
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
        if (welcomeScreen.style.display !== 'none') {
            welcomeScreen.style.display = 'none';
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
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: text,
                    app_name: APP_NAME,
                    user_id: USER_ID,
                    session_id: SESSION_ID
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

    function updateMessage(id, blocks) {
        const el = document.getElementById(id);
        if (el) {
            const messageContent = el.querySelector('.message-content');

            // 1. 记录当前所有 details 标签的展开状态 (open 属性)
            const detailsStates = Array.from(messageContent.querySelectorAll('details')).map(d => d.open);

            // 2. 渲染新内容 (+ cursor)
            const html = renderBlocks(blocks);
            messageContent.innerHTML = html + '<span class="streaming-cursor"></span>';

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

            scrollToBottom();
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
});
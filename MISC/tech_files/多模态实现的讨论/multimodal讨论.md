这是我的项目的main后端代码和 前端代码 ，请你完整阅读 ，然后针对我的目前的前后端代码，给出实现支持我们讨论的本地图片上传后输入给agent的特性的具体的修改位置，以及原因，注意图片在前端上传时要按照我们讨论的上传按钮和小图预览以及预览图右上角叉号删除，以及可以上传多张图片。先在开始

Gemini said
这是一个非常完整且合理的修改计划。我已经仔细阅读了你的 main_web_start_steering.py (后端), index.html (前端结构), script.js (前端逻辑) 和 style.css (样式)。

为了实现你想要的 "Gemini 风格多图上传"（点击加号选图、圆角缩略图预览、右上角叉号删除、多图混合发送），我们需要按照以下步骤修改代码。

第一步：修改前端样式 (style.css)
位置：在文件末尾添加以下 CSS。
原因：实现圆角预览图、横向排列容器以及那个关键的“悬浮在右上角的删除按钮”。

CSS
/* =========================================
   多模态图片预览样式 (Gemini 风格)
   ========================================= */

/* 1. 调整输入框外层容器，使其包含预览区 */
.input-area-wrapper {
    /* 确保容器有背景色，像一个整体卡片 */
    background: #f0f4f9; 
    border-radius: 24px; 
    padding: 8px 8px 16px 8px; /* 调整内边距 */
    /* 之前的样式可能需要覆盖或调整 */
    display: flex;
    flex-direction: column;
}

/* 2. 预览容器 (位于输入框上方) */
.image-preview-container {
    display: flex;
    gap: 12px;
    padding: 8px 12px 0 12px; /* 上方留白 */
    overflow-x: auto; /* 支持横向滚动 */
    white-space: nowrap;
    scrollbar-width: none; /* Firefox 隐藏滚动条 */
    min-height: 0; /* 防止 Flex 子元素溢出 */
    margin-bottom: 4px; /* 与输入框的间距 */
}

.image-preview-container:empty {
    display: none; /* 没有图片时隐藏 */
    margin-bottom: 0;
}

/* Chrome/Safari 隐藏滚动条 */
.image-preview-container::-webkit-scrollbar {
    display: none;
}

/* 3. 单张预览卡片 */
.preview-item {
    position: relative;
    width: 60px;
    height: 60px;
    flex-shrink: 0;
    border-radius: 8px;
    background-color: #e1e3e1;
    border: 1px solid rgba(0,0,0,0.05);
}

/* 4. 图片本体 */
.preview-item img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 8px;
    display: block;
}

/* 5. 删除按钮 (右上角悬浮叉号) */
.preview-item .remove-btn {
    position: absolute;
    top: -6px;
    right: -6px;
    width: 20px;
    height: 20px;
    background-color: rgba(60, 64, 67, 0.8); /* 深灰色半透明 */
    color: white;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    font-size: 14px;
    z-index: 10;
    border: 2px solid #f0f4f9; /* 加个白边，与背景融合更自然 */
    transition: transform 0.1s;
}

.preview-item .remove-btn:hover {
    background-color: #cf142b; /* 悬停变红 */
    transform: scale(1.1);
}
.preview-item .remove-btn::before {
    content: '×'; 
    line-height: 1;
    font-weight: bold;
    margin-top: -2px;
}

/* 微调原有的输入区域，去掉背景色，因为外层已经有了 */
.input-area {
    background-color: transparent !important; 
    padding: 4px 8px !important;
    border-radius: 0 !important;
}
.input-area textarea {
    padding: 10px 5px !important;
}
第二步：修改前端结构 (index.html)
位置：找到 <div class="input-area-wrapper"> 及其内部。
修改内容：

插入 <div id="imagePreviewContainer">。

给上传按钮添加 ID uploadBtn。

添加隐藏的 <input type="file">。

HTML
<div class="input-area-wrapper">
    
    <div id="imagePreviewContainer" class="image-preview-container"></div>

    <div class="input-area">
        <button class="icon-btn" id="uploadBtn">
            <span class="material-symbols-outlined">add_circle</span>
        </button>

        <input type="file" id="fileInput" multiple accept="image/*" style="display: none;">

        <textarea id="userInput" placeholder="问问 Ciri" rows="1"></textarea>
        ```

---

### 第三步：修改前端逻辑 (`script.js`)

**位置**：`document.addEventListener('DOMContentLoaded', () => { ... })` 内部，建议放在 `const stopBtn` 定义之后。

**修改内容**：添加图片状态管理、选择逻辑、预览渲染逻辑，并修改 `sendMessage` 函数。

```javascript
    // ... 原有代码 ...
    const stopBtn = document.getElementById('stopBtn');

    // ==========================================
    // [新增] 多模态图片上传逻辑
    // ==========================================
    let currentImages = []; // 存储 Base64 字符串
    const fileInput = document.getElementById('fileInput');
    const uploadBtn = document.getElementById('uploadBtn');
    const previewContainer = document.getElementById('imagePreviewContainer');

    // 1. 点击加号 -> 触发文件选择
    if (uploadBtn && fileInput) {
        uploadBtn.addEventListener('click', () => {
            fileInput.value = ''; // 重置，允许重复选同一张图
            fileInput.click();
        });

        // 2. 监听文件变化 -> 转Base64并存储
        fileInput.addEventListener('change', async (e) => {
            const files = Array.from(e.target.files);
            if (files.length === 0) return;

            for (const file of files) {
                if (!file.type.startsWith('image/')) continue;
                try {
                    const base64 = await fileToBase64(file);
                    currentImages.push(base64);
                } catch (err) {
                    console.error("图片读取失败:", err);
                }
            }
            renderPreview();
        });
    }

    // 工具：转 Base64
    function fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.readAsDataURL(file); // 自动带 data:image/... 前缀
            reader.onload = () => resolve(reader.result);
            reader.onerror = error => reject(error);
        });
    }

    // 3. 渲染预览图 (Gemini 样式)
    function renderPreview() {
        previewContainer.innerHTML = '';
        
        if (currentImages.length === 0) {
            // CSS :empty 会自动隐藏，这里也可以手动控制
            return;
        }

        currentImages.forEach((imgSrc, index) => {
            const item = document.createElement('div');
            item.className = 'preview-item';

            const img = document.createElement('img');
            img.src = imgSrc;

            const removeBtn = document.createElement('div');
            removeBtn.className = 'remove-btn';
            removeBtn.onclick = (e) => {
                e.stopPropagation(); // 防止冒泡
                currentImages.splice(index, 1); // 移除数据
                renderPreview(); // 重绘
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

    // ==========================================
    // [修改] sendMessage 函数
    // ==========================================
    async function sendMessage() {
        const text = userInput.value.trim();
        
        // 修改判断逻辑：只要有文本 或者 有图片 就可以发送
        if (!text && currentImages.length === 0) return;

        // ... 原有的 UI 切换逻辑 (Hide welcome screen, appendUserMessage) ...
        if (welcomeScreen && welcomeScreen.style.display !== 'none') {
            welcomeScreen.style.display = 'none';
            document.body.classList.remove('welcome-mode');
            document.body.classList.add('chat-mode');
        }

        // 1. 在 UI 上显示用户消息（需要处理图片回显）
        appendUserMessageUI(text, [...currentImages]); // 传入图片副本

        // 清空输入和状态
        userInput.value = '';
        userInput.style.height = 'auto';
        const imagesToSend = [...currentImages]; // 暂存用于发送
        clearImages(); // 清空预览区

        // ... 按钮状态切换 (sendBtn hide, stopBtn show) ...
        sendBtn.style.display = 'none';
        stopBtn.style.display = 'inline-flex';

        const loadingId = appendMessage('model', '', true);

        // ... Session 获取逻辑 ...
        let currentSessionId = getCurrentSessionId();
        // ... (省略 Session 创建代码，保持原样) ...

        const currentUserId = getUserId();
        // ... appName 逻辑 ...

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,     // 哪怕为空字符串也没关系，因为有 images
                    images: imagesToSend, // <--- [关键] 新增字段
                    app_name: appName, // 使用前面逻辑获取的 appName
                    user_id: currentUserId,
                    session_id: currentSessionId
                })
            });

            // ... 后续流式处理逻辑保持不变 ...
        } 
        // ... catch / finally 保持不变 ...
    }

    // [新增] 专门用于 UI 显示用户消息的辅助函数
    // 替换原本简单的 appendMessage('user', text)
    function appendUserMessageUI(text, images) {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message user';
        
        // 构造图片 HTML
        let imagesHtml = '';
        if (images && images.length > 0) {
            imagesHtml = `<div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px; justify-content:flex-end;">
                ${images.map(src => `<img src="${src}" style="height:100px; border-radius:8px; border:1px solid #eee;">`).join('')}
            </div>`;
        }

        let textHtml = '';
        if (text) {
            textHtml = marked.parse(text);
        }

        msgDiv.innerHTML = `
            <div class="message-content">
                ${imagesHtml}
                ${textHtml}
            </div>
        `;
        chatContainer.appendChild(msgDiv);
        scrollToBottom();
    }
第四步：修改后端 API (main_web_start_steering.py)
位置 1：修改 ChatRequest 类。
原因：允许 API 接收 images 字段。

Python
class ChatRequest(BaseModel):
    message: str
    # [新增] 支持多模态输入，列表元素是 Base64 字符串
    images: Optional[List[str]] = None 
    
    app_name: str = DEFAULT_APP_NAME
    user_id: str = DEFAULT_USER_ID
    session_id: str = DEFAULT_SESSION_ID
位置 2：修改 SteeringSession 类中的 run_task 方法。
原因：解析 Base64 并构建 Google ADK 的多模态输入 (Content + Part)。

Python
    # [修改] 增加 images 参数
    async def run_task(self, task: str, images: List[str] = None):
        """
        执行任务主逻辑
        """
        was_interrupted = False
        
        try:
            from google.adk.runners import Runner
            from google.adk.agents import RunConfig
            from google.adk.agents.run_config import StreamingMode
            import base64 # [新增] 导入 base64

            runner = Runner(agent=self.agent, app_name=self.app_name, session_service=self.session_service)
            
            # ... (获取/创建 session 的代码保持不变) ...
            
            # ... (自动标题生成代码保持不变) ...

            # ... (上下文压缩代码保持不变) ...

            # 启动前检票
            self.interruption_guard()
            
            # === [核心修改] 构建多模态输入 ===
            input_parts = []
            
            # 1. 只有当文本不为空时才添加文本 Part
            if task and task.strip():
                input_parts.append(types.Part(text=task))
            
            # 2. 处理图片
            if images:
                print(f"[Steering] 收到 {len(images)} 张图片输入")
                for img_str in images:
                    try:
                        # 格式通常是: data:image/png;base64,iVBORw0K...
                        if img_str.startswith("data:image"):
                            header, encoded = img_str.split(",", 1)
                            # 从 header 提取 mime_type (如 image/png)
                            mime_type = header.split(";")[0].split(":")[1]
                            
                            image_bytes = base64.b64decode(encoded)
                            # 创建 Image Part
                            input_parts.append(types.Part.from_data(data=image_bytes, mime_type=mime_type))
                        elif img_str.startswith("http"):
                             input_parts.append(types.Part.from_uri(file_uri=img_str, mime_type="image/jpeg"))
                    except Exception as e:
                        print(f"[Error] 图片解析失败: {e}")

            # 如果既没文本也没图片 (理论上前端已拦截，但后端要做兜底)
            if not input_parts:
                input_parts.append(types.Part(text="...")) # 防止空请求报错

            user_query = types.Content(role='user', parts=input_parts)
            
            run_config = RunConfig(streaming_mode=StreamingMode.SSE)
            
            logger.task_start(task)
            print(f"\n[任务] {task[:50]}... (Images: {len(images) if images else 0})")
            
            # ... (后续 try/except 代码保持不变，使用 user_query 变量) ...
            # ... 注意 check_and_compact_context 调用 ...
            # ... 注意 runner.run_async 调用中传入 new_message=user_query ...
位置 3：修改 run_agent 和 chat_endpoint 以透传参数。

Python
# 修改 run_agent 签名
async def run_agent(task: str, app_name: str, user_id: str, session_id: str, images: List[str] = None):
    # ... session_manager init check ...
    session = session_manager.get_or_create(app_name, user_id, session_id)
    
    # [修改] 传递 images
    async for chunk in session.run_task(task, images=images):
        yield chunk

# 修改 chat_endpoint
@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest, response: Response):
    # ... (检查忙碌状态代码不变) ...

    # ...
    async def generate():
        try:
            # [修改] 传递 request.images
            async for chunk in run_agent(
                request.message, 
                request.app_name, 
                request.user_id, 
                request.session_id,
                images=request.images # <--- 新增
            ):
                yield json.dumps({"chunk": chunk}) + "\n"
        # ... (后续不变) ...
总结
这套修改方案：

CSS 负责把界面变成你截图里的样子（预览图悬浮、圆角、右上角删除）。

JS 负责把文件输入框 (input type=file) 和 UI 按钮联动，并把图片转成后端能读懂的 Base64 字符串。

Python 负责接收这些 Base64 字符串，解码成二进制，然后封装成 Google ADK 的 Part 对象，从而让 Agent 真正拥有“视觉”。
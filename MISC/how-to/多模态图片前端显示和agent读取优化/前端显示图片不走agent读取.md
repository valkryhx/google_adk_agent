好的，为了实现 方案 A：浏览器直接展示本地图片，你需要修改两个文件。请按照以下步骤操作：

第一步：修改 main_web_start_steering.py
我们需要在后端增加一个 API 接口，允许前端通过 URL 访问本地图片文件。

1. 确认导入 (Imports)
虽然你的代码中已经导入了 FileResponse，为了保险起见，请检查文件头部（约第 43 行）：

Python
# 确保包含 FileResponse
from fastapi.responses import FileResponse, StreamingResponse
2. 添加 API 路由
在文件末尾，在 start_web_server 函数定义之前（大约第 1360 行附近，@app.on_event("shutdown") 之后），插入以下代码：

Python
# ==========================================
# [新增] 本地图片代理接口 (用于前端直接渲染本地图)
# ==========================================
@app.get("/api/local_image")
async def get_local_image(path: str):
    """
    代理本地图片文件，供前端 Markdown 渲染使用。
    用法: ![alt](/api/local_image?path=绝对路径)
    """
    # 1. 安全/存在性检查
    if not os.path.exists(path):
        return Response(content="File not found", status_code=404)
    
    # 2. 简单的扩展名过滤，防止读取非图片文件
    valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')
    if not path.lower().endswith(valid_extensions):
        return Response(content="Not a valid image file", status_code=400)
    
    # 3. 直接返回文件流
    return FileResponse(path)
第二步：修改 config.py
我们需要修改系统提示词，告诉 Agent 不要读取图片二进制数据，而是直接输出上面那个 API 的链接。

1. 找到 SYSTEM_PROMPT_TEMPLATE
在 config.py 文件中，找到 SYSTEM_PROMPT_TEMPLATE = """...""" 定义的部分。

2. 插入新指令
建议在 ### 6. 输出格式 这一节内容的后面，插入新的 ### 7. 本地图片展示 章节。

请将原来的：

Python
### 6. 输出格式
- 简洁清晰，避免冗余
- 引用具体的文件路径和行号
- 代码块使用正确的语法高亮

### 7. 主动资源管理 (Proactive Compaction)
修改为：

Python
### 6. 输出格式
- 简洁清晰，避免冗余
- 引用具体的文件路径和行号
- 代码块使用正确的语法高亮

### 7. 本地图片展示 (Display Local Images) 🖼️
当你在本地生成或找到图片文件（如 .png, .jpg, .svg）时，**为了让用户能直接在聊天界面看到图片**，请遵循以下规则：
1. **不要读取**图片的二进制内容（不要 print base64）。
2. **直接输出**以下 Markdown 格式的图片链接：
   `![图片描述](/api/local_image?path=文件的绝对路径)`
   
   **示例**：
   - 用户："画个图" -> 你生成了 `D:/data/plot.png`
   - 你的回复："图表已生成：\n![销售趋势图](/api/local_image?path=D:/data/plot.png)"

### 8. 主动资源管理 (Proactive Compaction)
完成后的验证
保存两个文件。

重启服务：python -m src.adk_agent.main_web_start_steering

在前端对话框输入："请生成一个简单的红色圆形的图片 test_circle.png，并展示给我看。"

如果你看到一个红色的圆直接显示在聊天气泡里，说明修改成功！


===后续优化 实现成工具===
第二步：修改 tools.py (新增工具)
这是核心。我们要给 Agent 一个名为 view_local_image 的“假”视觉工具。它不读文件，只生成链接。

位置：tools.py 末尾。
修改：新增函数并注册。

Python
# ... (现有代码) ...

# 1. 新增工具函数
async def view_local_image(path: str) -> str:
    """
    [UI Tool] 专门用于在聊天界面向用户展示本地图片。
    当用户要求"看图"、"显示图片"、"展示结果"时，必须优先使用此工具。
    它不会读取文件内容，而是生成一个特殊的显示链接，消耗 Token 极少。
    
    Args:
        path: 图片文件的路径 (可以是相对路径或绝对路径)
    """
    # 这里不做复杂的路径检查，交给后端 API 去容错
    # 直接返回 Markdown 图片语法
    # 使用 quote 处理路径中的空格等特殊字符，但这里简单拼接通常也够用
    return f"![Image View](/api/local_image?path={path})"

# 2. 修改 get_tools 函数，加入新工具
def get_tools(*args, **kwargs) -> List:
    # 确保列表中包含 view_local_image
    return [file_editor, view_local_image] 
第三步：修改 config.py (系统提示词)
我们要明确告诉 Agent：看图 = 调用 view_local_image。

位置：config.py 中的 SYSTEM_PROMPT_TEMPLATE 变量。
修改：更新或添加 “本地图片展示” 相关的指令部分。

Python
# ... (在 "6. 输出格式" 之后) ...

### 7. 本地图片展示 (Display Local Images) 🖼️
当需要向用户展示本地图片（如 .png, .jpg, .svg）时，请严格遵守以下规则：

1. ✅ **必须调用工具**：使用 `view_local_image(path=...)`。
   - 这是展示图片的唯一正确方式。
   - 即使是刚生成的图片，也请调用此工具来展示。

2. 🚫 **严禁读取内容**：
   - 不要使用 `file_editor` 读取图片内容。
   - 不要使用 `bash` 或 `python` 编写脚本读取图片。
   - 不要输出 Base64 字符串。

**示例**：
User: "把生成的图表给我看看"
Assistant: (调用工具) `view_local_image(path="output/chart.png")`

### 8. 主动资源管理...
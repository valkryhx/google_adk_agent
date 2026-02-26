好的，为了让 Agent 具备**“真正看懂本地图片”**的能力（即功能点 2），我们需要在代码和提示词层面进行明确的区分和实现。

这是完整的修改方案，请依次操作：

第一步：修改 tools.py (核心实现)
我们需要引入图像处理库，并新增 analyze_local_image 工具。

1. 修改头部导入
在 tools.py 文件最顶部，确保包含以下导入：

Python
import os
import asyncio
import base64      # [新增]
import mimetypes   # [新增]
from typing import Any, Literal, Optional, List, Dict
from pathlib import Path
from dataclasses import dataclass
2. 添加 analyze_local_image 函数
在 tools.py 的末尾（get_tools 函数之前），插入以下代码。
(注：为了完整性，我同时也列出了 view_local_image，如果你之前已经加过，请确保两个都在)

Python
# ==========================================
# [新增] 视觉能力工具组
# ==========================================

async def view_local_image(path: str) -> str:
    """
    [UI Tool] 仅用于向【人类用户】展示图片。
    场景：用户说"给我看看图"、"显示结果"、"画好了吗"。
    行为：生成前端可渲染的 Markdown 链接。
    注意：此工具不会让 Agent 看到图片内容，仅仅是搬运工。
    """
    import os
    from urllib.parse import quote
    
    # 简单路径检查与修正
    if not os.path.exists(path):
        # 尝试相对路径
        cwd_path = os.path.join(os.getcwd(), path)
        if os.path.exists(cwd_path):
            path = cwd_path
        else:
            return f"Error: 文件不存在 {path}"
            
    # 返回纯文本链接 (让前端去渲染)
    # 这里的 path 建议转义一下，防止空格报错，但在本地环境简单拼接通常也没问题
    return f"![Image Display](/api/local_image?path={path})"


async def analyze_local_image(path: str) -> List[Dict[str, Any]]:
    """
    [Vision Tool] 仅用于让【Agent 你自己】看懂并分析图片内容。
    场景：用户说"图里有什么"、"检查图片是否画错了"、"分析数据趋势"、"提取截图文字"。
    行为：读取文件二进制数据，消耗 Vision Token 进行视觉理解。
    
    Args:
        path: 图片文件的路径
    """
    p = Path(path)
    # 相对路径兼容
    if not p.is_absolute():
        p = Path(os.getcwd()) / p
        
    if not p.exists():
        return [{"type": "text", "text": f"Error: 文件 {path} 不存在"}]
    
    # 识别 MIME 类型
    mime_type, _ = mimetypes.guess_type(p)
    if not mime_type or not mime_type.startswith('image'):
        # 兜底默认为 png
        mime_type = 'image/png'

    try:
        # 读取并转 Base64
        with open(p, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode('utf-8')
            
        # 返回多模态数据结构 (OpenAI/LiteLLM 标准格式)
        # 注意：这里返回的是 List，Agent 框架会将其作为 content 传入 LLM
        return [
            {
                "type": "text", 
                "text": f"我已读取图片 {path} 的视觉数据，正在分析其内容..."
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{b64_data}"
                }
            }
        ]
    except Exception as e:
        return [{"type": "text", "text": f"读取图片失败: {str(e)}"}]
3. 修改 get_tools 注册函数
修改文件末尾的 get_tools，确保新工具被注册。

Python
# 适配 ADK 加载协议
def get_tools(*args, **kwargs) -> List:
    # 注册所有工具：文件编辑、给用户看图、自己看图
    return [file_editor, view_local_image, analyze_local_image]
第二步：修改 config.py (大脑指令)
我们需要在 System Prompt 中明确两个工具的分工，防止 Agent 混淆。

位置：在 config.py 中找到 SYSTEM_PROMPT_TEMPLATE = """..."""。
操作：更新或替换 第 7 点（如果你之前还没加第 7 点，就加在“输出格式”后面）。

Python
### 7. 视觉能力与图片处理 (Visual Capabilities) 👁️

你拥有两个处理本地图片的核心工具，请根据**用户意图**严格区分使用：

#### 场景 A：用户想看 (Display)
- **用户指令示例**："把图发给我"、"展示一下结果"、"画完了吗？让我看看"。
- **你的行动**：必须调用 `view_local_image(path=...)`。
- **禁止**：不要读取文件内容，不要分析，直接展示。

#### 场景 B：你需要看 (Analyze/Verify)
- **用户指令示例**："分析这张图的趋势"、"检查图片里有没有乱码"、"图里画的是猫还是狗"。
- **你的行动**：必须调用 `analyze_local_image(path=...)`。
- **原理**：这会将图片传入你的视觉神经进行理解，会消耗 Token。

#### 场景 C：自查与纠错 (Self-Correction)
- **自动触发**：当你编写代码生成了一张图片后，**建议主动**调用 `analyze_local_image` 检查图片是否符合要求（如是否有空白、乱码），确认无误后再调用 `view_local_image` 展示给用户。

---
第三步：验证流程
完成上述修改后：

重启后端服务 (python -m ...)。

刷新前端页面 并 发起新对话。

测试指令 1 (展示)：

"请显示 session_length_distribution.png 给我看。"
预期：Agent 调用 view_local_image，图片直接显示。

测试指令 2 (分析)：

"请分析 session_length_distribution.png 里展示的数据趋势是什么？"
预期：Agent 调用 analyze_local_image，然后回答：“这张图展示了一个柱状图，数值集中在...”

这样你就拥有了一个既能省流展示，又能深度看图的强力 Agent 了！
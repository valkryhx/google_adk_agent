import os
import asyncio
import base64
import mimetypes
from typing import Any, Literal, Optional, List, Dict
from pathlib import Path
from dataclasses import dataclass

# ==========================================
# 1. 移植自 base.py 和缺失的 run.py 的核心组件
# ==========================================

class ToolError(Exception):
    """Raised when a tool encounters an error."""
    def __init__(self, message):
        self.message = message

@dataclass
class ToolResult:
    output: str | None = None
    error: str | None = None
    
    def __str__(self):
        if self.error:
            return f"ERROR: {self.error}"
        return self.output or "Success"

def maybe_truncate(content: str, max_len: int = 16000) -> str:
    """模拟缺失的 maybe_truncate，防止 Token 爆炸"""
    if len(content) > max_len:
        return content[:max_len] + f"\n... (truncated {len(content)-max_len} chars)"
    return content

# ==========================================
# 2. 移植自 edit.py (已修改移除依赖)
# ==========================================

SNIPPET_LINES: int = 4

class EditTool:
    """
    移植版 Anthropic File Editor
    移除 anthropic SDK 依赖，使用 Python 原生路径操作替代 shell command
    """
    
    def __init__(self, allowed_root: str):
        # 安全沙箱检查
        self.root = Path(allowed_root).resolve()

    def validate_path(self, command: str, path: Path):
        """安全路径校验"""
        # 1. 强制解析为绝对路径
        if not path.is_absolute():
            # 如果是相对路径，拼接到 root 下
            path = (self.root / path).resolve()
        else:
            path = path.resolve()
            
        # 2. 沙箱逃逸检查 (防止访问 /etc/passwd 等) - 已禁用
        # if not str(path).startswith(str(self.root)):
        #      raise ToolError(f"Access denied: Path {path} is outside the allowed workspace {self.root}")

        # 3. 检查文件是否存在
        if not path.exists() and command != "create":
             raise ToolError(f"The path {path} does not exist.")
        
        if path.exists() and command == "create":
             raise ToolError(f"File already exists at: {path}. Cannot overwrite using `create`.")
             
        if path.is_dir() and command != "view":
             raise ToolError(f"The path {path} is a directory and only `view` command is allowed.")
             
        return path

    async def execute(
        self,
        command: Literal["view", "create", "str_replace", "insert"],
        path: str,
        file_text: Optional[str] = None,
        view_range: Optional[List[int]] = None,
        old_str: Optional[str] = None,
        new_str: Optional[str] = None,
        insert_line: Optional[int] = None,
        insert_text: Optional[str] = None
    ):
        try:
            # 路径预处理
            _path = Path(path)
            if not _path.is_absolute():
                _path = self.root / _path
            
            # 验证并获取绝对路径
            _path = self.validate_path(command, _path)

            if command == "view":
                return await self.view(_path, view_range)
            elif command == "create":
                if file_text is None:
                    raise ToolError("Parameter `file_text` is required for command: create")
                self.write_file(_path, file_text)
                return ToolResult(output=f"File created successfully at: {_path}")
            elif command == "str_replace":
                if old_str is None:
                    raise ToolError("Parameter `old_str` is required for command: str_replace")
                return self.str_replace(_path, old_str, new_str)
            elif command == "insert":
                if insert_line is None:
                    raise ToolError("Parameter `insert_line` is required for command: insert")
                if insert_text is None:
                    raise ToolError("Parameter `insert_text` is required for command: insert")
                return self.insert(_path, insert_line, insert_text)
            
            raise ToolError(f"Unrecognized command {command}")

        except ToolError as e:
            return ToolResult(error=e.message)
        except Exception as e:
            return ToolResult(error=f"System Error: {str(e)}")

    async def view(self, path: Path, view_range: List[int] | None = None):
        """查看文件或目录"""
        # 1. 如果是目录，列出内容 (替代原版 run("find ...") 逻辑)
        if path.is_dir():
            if view_range:
                raise ToolError("`view_range` is not allowed for directories.")
            
            # 使用 Python 原生 walk 替代 Linux find 命令，兼容 Windows
            files_list = []
            try:
                # 模拟 find . -maxdepth 2
                base_depth = len(path.parts)
                for root, dirs, files in os.walk(path):
                    depth = len(Path(root).parts) - base_depth
                    if depth >= 2: # maxdepth 2
                        del dirs[:] # 停止递归
                        continue
                    
                    # 排除隐藏文件
                    if any(p.startswith('.') for p in Path(root).name):
                        continue

                    level_indent = "  " * depth
                    files_list.append(f"{level_indent}{Path(root).name}/")
                    for f in files:
                        if not f.startswith('.'):
                            files_list.append(f"{level_indent}  {f}")
                
                stdout = "\n".join(files_list)
                return ToolResult(output=f"Files in {path} (depth 2):\n{stdout}\n")
            except Exception as e:
                return ToolResult(error=f"Error listing directory: {e}")

        # 2. 如果是文件，读取内容
        file_content = self.read_file(path)
        init_line = 1
        
        if view_range:
            if len(view_range) != 2:
                raise ToolError("Invalid `view_range`. It should be a list of two integers.")
            file_lines = file_content.split("\n")
            init_line, final_line = view_range
            
            # 边界检查逻辑 (原版保留)
            if init_line < 1 or init_line > len(file_lines):
                raise ToolError(f"Invalid start line {init_line}")
            
            if final_line == -1:
                # file_content = "\n".join(file_lines[init_line - 1 :])
                 # 修复原版逻辑可能的越界（切片宽容度高，但 range 检查要细心）
                 file_content = "\n".join(file_lines[init_line - 1 :])
            else:
                file_content = "\n".join(file_lines[init_line - 1 : final_line])

        return ToolResult(output=self._make_output(file_content, str(path), init_line=init_line))

    def str_replace(self, path: Path, old_str: str, new_str: str | None):
        """精准字符串替换"""
        file_content = self.read_file(path).expandtabs()
        old_str = old_str.expandtabs()
        new_str = new_str.expandtabs() if new_str is not None else ""

        occurrences = file_content.count(old_str)
        if occurrences == 0:
            raise ToolError(f"No replacement performed. '{old_str[:50]}...' not found in {path}.")
        elif occurrences > 1:
            raise ToolError(f"No replacement performed. '{old_str[:50]}...' occurs {occurrences} times. Must be unique.")

        new_file_content = file_content.replace(old_str, new_str)
        self.write_file(path, new_file_content)

        # 生成 snippet 预览
        replacement_line = file_content.split(old_str)[0].count("\n")
        start_line = max(0, replacement_line - SNIPPET_LINES)
        
        # 计算新内容的行数
        new_str_lines_count = new_str.count("\n")
        # end_line = replacement_line + SNIPPET_LINES + new_str_lines_count
        # 修正: 上下文展示不宜过长
        end_line = start_line + (SNIPPET_LINES * 2) + new_str_lines_count + 1
        
        snippet = "\n".join(new_file_content.split("\n")[start_line : end_line + 1])

        msg = f"Edited {path}.\n" + self._make_output(snippet, "snippet", start_line + 1)
        return ToolResult(output=msg)

    def insert(self, path: Path, insert_line: int, new_str: str):
        """指定行插入"""
        file_text = self.read_file(path).expandtabs()
        new_str = new_str.expandtabs()
        lines = file_text.split("\n")
        
        # 行号检查 (insert_line 是 1-based 还是 0-based? 通常编辑器是 1-based)
        # 逻辑上，在此处 insert_line 是用户输入的行号。
        # 如果是 1，代表插入到第1行之前（成为新的第1行）
        # 如果是 len+1，代表追加到末尾
        if insert_line < 0 or insert_line > len(lines) + 1:
             raise ToolError(f"Invalid insert_line {insert_line}. File has {len(lines)} lines.")
             
        # 转换为 0-based index
        idx = max(0, insert_line - 1)

        new_str_lines = new_str.split("\n")
        new_lines = lines[:idx] + new_str_lines + lines[idx:]
        self.write_file(path, "\n".join(new_lines))
        
        return ToolResult(output=f"Inserted text at line {insert_line} in {path}.")

    def read_file(self, path: Path):
        try:
            return path.read_text(encoding='utf-8')
        except Exception as e:
            raise ToolError(f"Read error: {e}")

    def write_file(self, path: Path, content: str):
        try:
            # 自动创建父目录
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        except Exception as e:
            raise ToolError(f"Write error: {e}")

    def _make_output(self, file_content: str, file_descriptor: str, init_line: int = 1):
        file_content = maybe_truncate(file_content)
        lines = [f"{i + init_line:6}\t{line}" for i, line in enumerate(file_content.split("\n"))]
        return f"Result for {file_descriptor}:\n" + "\n".join(lines) + "\n"


# ==========================================
# 3. 适配 ADK 的入口函数
# ==========================================

# 实例化一个全局工具对象，根目录设为当前工作目录
# 你也可以从环境变量读取，例如 os.getenv("AGENT_WORKSPACE", ".")
_editor = EditTool(allowed_root=os.getcwd())

async def file_editor(
    command: Literal["view", "create", "str_replace", "insert"],
    path: str,
    file_text: Optional[str] = None,
    view_range: Optional[List[int]] = None,
    old_str: Optional[str] = None,
    new_str: Optional[str] = None,
    insert_line: Optional[int] = None,
    insert_text: Optional[str] = None
) -> str:
    """
    Anthropic 标准文件编辑工具 (移植版) - 强大的文件读取与编辑能力
    
    Args:
        command: 操作指令 (view, create, str_replace, insert)
            - view: 查看文件内容或目录列表
            - create: 创建新文件
            - str_replace: 精确字符串替换
            - insert: 指定行插入
        path: 文件或目录的路径 (绝对路径或相对路径)
        file_text: [create] 文件内容
        view_range: [view] 查看行号范围 [start, end] (1-based)
        old_str: [str_replace] 被替换的旧字符串 (必须唯一)
        new_str: [str_replace] 新字符串
        insert_line: [insert] 插入行号 (1-based)
        insert_text: [insert] 插入文本
    """
    result = await _editor.execute(
        command=command,
        path=path,
        file_text=file_text,
        view_range=view_range,
        old_str=old_str,
        new_str=new_str,
        insert_line=insert_line,
        insert_text=insert_text
    )
    
    if result.error:
        return f"ERROR: {result.error}"
    return result.output

# 适配 ADK 加载协议
#def get_tools(agent, session_service, app_info):

async def view_local_image(path: str) -> str:
    """
    [UI Tool] 仅用于向【人类用户】展示图片。
    场景：用户说"给我看看图"、"显示结果"、"画好了吗"。
    行为：生成前端可渲染的 Markdown 链接。
    注意：此工具不会让 Agent 看到图片内容，仅仅是搬运工。
    """
    import os
    from urllib.parse import quote
    
    # 如果是网络图片 URL，直接返回 Markdown 格式让前端渲染
    if path.startswith("http://") or path.startswith("https://"):
        return f"![Image Display]({path})"
    
    # 简单路径检查与修正
    if not os.path.exists(path):
        # 尝试相对路径
        cwd_path = os.path.join(os.getcwd(), path)
        if os.path.exists(cwd_path):
            path = cwd_path
        else:
            return f"Error: 文件不存在 {path}"
            
    # 返回纯文本链接 (让前端去渲染)
    # 对路径进行 URL 编码，解决路径中有空格等特殊字符导致前端无法渲染的问题
    encoded_path = quote(path)
    return f"![Image Display](/api/local_image?path={encoded_path})"


from google.adk.events.event import Event
from google.genai import types as genai_types
from google.adk.tools.tool_context import ToolContext

async def analyze_local_image(path: str, tool_context: ToolContext = None) -> str:
    """
    [Vision Tool] 仅用于让【Agent 你自己】看懂并分析图片内容。
    场景：用户说"图里有什么"、"检查图片是否画错了"、"分析数据趋势"、"提取截图文字"。
    行为：读取文件二进制数据或从网络URL直接读取，消耗 Vision Token 进行视觉理解。
    
    Args:
        path: 图片文件的路径或网络 URL (如 http:// 或 https://)
        tool_context: (Auto-injected) 工具执行上下文
    """
    if not tool_context or not tool_context.session:
        return "Error: ToolContext or Session is missing. This tool must be called within an active agent session."

    import mimetypes
    import traceback

    # 识别 MIME 类型和加载图片 Part
    try:
        if path.startswith("http://") or path.startswith("https://"):
            image_part = genai_types.Part.from_uri(file_uri=path, mime_type="image/jpeg") # Default to jpeg for URIs
        else:
            p = Path(path)
            if not p.is_absolute():
                p = Path(os.getcwd()) / p
            if not p.exists():
                return f"Error: 文件 {path} 不存在"
            
            mime_type, _ = mimetypes.guess_type(p)
            if not mime_type or not mime_type.startswith('image'):
                mime_type = 'image/png'
            
            with open(p, "rb") as f:
                image_data = f.read()
            image_part = genai_types.Part.from_bytes(data=image_data, mime_type=mime_type)

        # Prevent multiple injections of the same image in the same turn
        # We check the events for an existing injection with the same path or image data
        for event in tool_context.session.events:
            if event.author == "user" and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text and f"image from {path}" in part.text:
                        return f"The image {path} is already in the conversation history above. Please analyze it directly."

        # 构造 Injection Event（注入为 User 消息）
        # 我们在这里使用更强烈的语气和明确的标记
        image_event = Event(
            author="user",
            invocation_id=tool_context._invocation_context.invocation_id,
            content=genai_types.Content(
                role="user",
                parts=[
                    genai_types.Part.from_text(text=f"### [USER_ATTACHMENT: IMAGE] ###\nI am providing the image file from: {path}\n\n[IMAGE_CONTENT_START]"),
                    image_part,
                    genai_types.Part.from_text(text="[IMAGE_CONTENT_END]\n\nAbove is the image you requested to analyze. Please examine it carefully and provide a detailed analysis based on the actual visual content you see.")
                ]
            )
        )

        # 持久化该事件到 SessionService
        # 注意：append_event 会将其添加到 events 列表的末尾
        await tool_context._invocation_context.session_service.append_event(
            tool_context.session, image_event
        )

        # 为了满足 LiteLLM 校验（tool_call 必须紧跟 tool_response），
        # 我们寻找当前工具调用的位置，并将新注入的 user 事件移动到它之前。
        tool_call_idx = -1
        for i, event in enumerate(tool_context.session.events):
            if tool_context.function_call_id and any(fc.id == tool_context.function_call_id for fc in event.get_function_calls()):
                tool_call_idx = i
                break
        
        # 如果找到了当前的 tool_call 事件，且刚刚 append 的事件在最后，则移动它
        if tool_call_idx != -1 and tool_context.session.events[-1] == image_event:
            ev = tool_context.session.events.pop()
            tool_context.session.events.insert(tool_call_idx, ev)
            logger_info = f"Successfully injected and PERSISTED image event before tool call for {path}"
        else:
            logger_info = f"Appended and PERSISTED image event for {path}"
        
        print(logger_info)
        
        return f"SUCCESS: The image data for {path} has been PERSISTED to the database and injected as a NEW User Message immediately BEFORE this tool response. ACTION: Please look at the message content titled '### [USER_ATTACHMENT: IMAGE] ###' in your conversation history and use its visual parts to answer the user's request. DO NOT hallucinate based on the filename."

    except Exception as e:
        error_msg = f"Error processing image {path}: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return error_msg

def get_tools(*args, **kwargs) -> List:
    return [file_editor, view_local_image, analyze_local_image]

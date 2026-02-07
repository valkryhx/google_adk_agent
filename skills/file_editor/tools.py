import os
import asyncio
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
            
        # 2. 沙箱逃逸检查 (防止访问 /etc/passwd 等)
        if not str(path).startswith(str(self.root)):
             raise ToolError(f"Access denied: Path {path} is outside the allowed workspace {self.root}")

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
def get_tools(agent, session_service, app_info):
    return [file_editor]

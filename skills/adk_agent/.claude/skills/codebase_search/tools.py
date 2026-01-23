"""
Codebase Search Skill - 代码库搜索工具集

基于 ripgrep 的高性能文本检索，用于 Agentic RAG。
"""

import subprocess
import os
from typing import Optional, List


def execute_ripgrep(
    pattern: str, 
    path: str = ".", 
    context_lines: int = 2,
    ignore_case: bool = True,
    file_type: Optional[str] = None,
    max_results: int = 50
) -> str:
    """
    使用 ripgrep 进行高性能文本检索
    
    Args:
        pattern: 搜索模式（支持正则表达式）
        path: 搜索路径，默认当前目录
        context_lines: 显示匹配行的上下文行数
        ignore_case: 是否忽略大小写
        file_type: 限制文件类型（如 'py', 'md', 'js'）
        max_results: 最大结果数
        
    Returns:
        搜索结果或错误信息
    """
    try:
        cmd = [
            "rg", "--color", "never", "-n",
            "-A", str(context_lines), 
            "-B", str(context_lines),
            "-m", str(max_results),
        ]
        
        if ignore_case:
            cmd.append("-i")
        if file_type:
            cmd.extend(["-t", file_type])
            
        cmd.extend([pattern, path])
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            timeout=30
        )
        
        if result.returncode == 0:
            output = result.stdout
            # 限制输出长度
            if len(output) > 5000:
                lines = output.split('\n')
                output = '\n'.join(lines[:100])
                output += f"\n\n... [结果已截断，共匹配更多内容，请使用更精确的搜索条件]"
            return output if output else "匹配成功但无输出。"
        elif result.returncode == 1:
            return "[WARN] 未找到匹配内容。建议：尝试简化关键词或使用通配符如 `.*`"
        else:
            return f"[ERROR] Ripgrep 错误: {result.stderr}"
            
    except FileNotFoundError:
        return "[ERROR] 系统未安装 ripgrep (rg)。请先安装：\n  Windows: choco install ripgrep\n  macOS: brew install ripgrep\n  Linux: apt install ripgrep"
    except subprocess.TimeoutExpired:
        return "[ERROR] 搜索超时，请缩小搜索范围或简化正则表达式。"
    except Exception as e:
        return f"[ERROR] 执行异常: {type(e).__name__}: {str(e)}"


def read_file_content(
    file_path: str, 
    start_line: int = 1, 
    end_line: Optional[int] = None,
    max_chars: int = 10000
) -> str:
    """
    读取文件内容
    
    Args:
        file_path: 文件路径
        start_line: 起始行号（1-indexed）
        end_line: 结束行号（可选，不指定则读到文件末尾）
        max_chars: 最大字符数
        
    Returns:
        文件内容或错误信息
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        
        # 处理行号范围
        start_idx = max(0, start_line - 1)
        end_idx = end_line if end_line else total_lines
        
        selected_lines = lines[start_idx:end_idx]
        
        # 添加行号
        numbered_content = []
        for i, line in enumerate(selected_lines, start=start_line):
            numbered_content.append(f"{i:4d}: {line.rstrip()}")
        
        content = '\n'.join(numbered_content)
        
        # 限制长度
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n... [内容已截断，文件共 {total_lines} 行]"
        
        header = f"[文件] {file_path} (第 {start_line}-{min(end_idx, total_lines)} 行，共 {total_lines} 行)\n"
        return header + "=" * 50 + "\n" + content
        
    except FileNotFoundError:
        return f"[ERROR] 文件不存在: {file_path}"
    except UnicodeDecodeError:
        return f"[ERROR] 无法读取二进制文件: {file_path}"
    except Exception as e:
        return f"[ERROR] 读取失败: {type(e).__name__}: {str(e)}"


def list_files(
    path: str = ".", 
    pattern: str = "*", 
    max_depth: int = 3,
    file_type: Optional[str] = None
) -> str:
    """
    列出目录下的文件
    
    Args:
        path: 目录路径
        pattern: 文件名 glob 模式
        max_depth: 最大搜索深度
        file_type: 文件类型过滤
        
    Returns:
        文件列表
    """
    try:
        cmd = ["rg", "--files", "--max-depth", str(max_depth)]
        
        if pattern != "*":
            cmd.extend(["--glob", pattern])
        if file_type:
            cmd.extend(["-t", file_type])
            
        cmd.append(path)
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            timeout=10
        )
        
        if result.returncode == 0 and result.stdout:
            files = result.stdout.strip().split('\n')
            output = f"📁 目录: {path} (找到 {len(files)} 个文件)\n"
            output += "=" * 50 + "\n"
            
            if len(files) > 50:
                output += '\n'.join(files[:50])
                output += f"\n\n... [仅显示前 50 个，共 {len(files)} 个文件]"
            else:
                output += '\n'.join(files)
            return output
        else:
            return f"[WARN] 未找到匹配文件"
            
    except FileNotFoundError:
        # 如果 rg 不可用，使用 os.walk 作为备选
        try:
            files = []
            for root, dirs, filenames in os.walk(path):
                depth = root.replace(path, '').count(os.sep)
                if depth >= max_depth:
                    dirs[:] = []
                    continue
                for f in filenames:
                    files.append(os.path.join(root, f))
            
            output = f"📁 目录: {path} (找到 {len(files)} 个文件)\n"
            output += "=" * 50 + "\n"
            output += '\n'.join(files[:50])
            if len(files) > 50:
                output += f"\n\n... [仅显示前 50 个]"
            return output
        except Exception as e:
            return f"[ERROR] 列出文件失败: {str(e)}"
    except Exception as e:
        return f"[ERROR] 列出文件失败: {type(e).__name__}: {str(e)}"


def search_and_read(
    pattern: str, 
    path: str = ".",
    read_first_match: bool = True
) -> str:
    """
    搜索并自动读取第一个匹配文件的内容（便捷方法）
    
    Args:
        pattern: 搜索模式
        path: 搜索路径
        read_first_match: 是否自动读取第一个匹配的文件
        
    Returns:
        搜索结果和文件内容
    """
    # 先执行搜索
    search_result = execute_ripgrep(pattern, path, context_lines=0, max_results=10)
    
    if "未找到" in search_result or "错误" in search_result:
        return search_result
    
    output = ["[搜索结果]", search_result]
    
    if read_first_match:
        # 提取第一个文件路径
        lines = search_result.strip().split('\n')
        if lines:
            first_line = lines[0]
            if ':' in first_line:
                file_path = first_line.split(':')[0]
                output.append("\n" + "=" * 50)
                output.append(f"\n[读取] 自动读取文件: {file_path}\n")
                file_content = read_file_content(file_path)
                output.append(file_content)
    
    return '\n'.join(output)


# 工具函数字典
CODEBASE_SEARCH_TOOLS = {
    "execute_ripgrep": execute_ripgrep,
    "read_file_content": read_file_content,
    "list_files": list_files,
    "search_and_read": search_and_read,
}


def get_tools() -> List:
    """返回所有代码搜索工具函数列表"""
    return list(CODEBASE_SEARCH_TOOLS.values())

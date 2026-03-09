"""
Memory Retrieval System Skill - 记忆检索引擎

基于 ripgrep 和精准文件读取，实现高性能的 L0 (全库扫描) -> L2 (精准读取) 两级检索策略。
专门针对 Swarm 日志结构的归档格式进行优化。
"""

import subprocess
import os
from typing import Optional, List


def search_memory(
    pattern: str, 
    user_id: str,
    month: Optional[str] = None,
    max_results: int = 100
) -> str:
    """
    [L0] 在记忆库中广度扫描线索 (基于 ripgrep)
    
    返回按文件聚合的紧凑索引（文件名 + 匹配行号列表），不返回具体内容。
    Agent 根据索引结果，使用 read_memory 精确读取感兴趣的文件和行范围。
    
    Args:
        pattern: 搜索模式 (关键词或正则)
        user_id: 用户的 ID
        month: 可选过滤月份，如 "2026-03"
        max_results: 每个文件最大匹配数
        
    Returns:
        按文件分组的匹配行号索引
    """
    try:
        _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        memory_base = os.path.join(_PROJECT_ROOT, "memory_archive", user_id)
        
        if not os.path.exists(memory_base):
            return f"[WARN] 用户 {user_id} 尚无记忆库"
        
        # 使用 ripgrep 只输出 文件名:行号 格式（不输出匹配内容，极度紧凑）
        cmd = [
            "rg", "--color", "never",
            "-n",           # 显示行号
            "--no-heading",  # 每行都带文件路径
            "-m", str(max_results),
            "-i",           # 忽略大小写
        ]
        
        if month:
            cmd.extend(["-g", f"*{month}*"])
            
        cmd.extend([pattern, memory_base])
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            timeout=30
        )
        
        if result.returncode == 1:
            return f"[L0] 未找到包含 '{pattern}' 的记忆。尝试更换关键词。"
        elif result.returncode != 0:
            return f"[ERROR] Ripgrep 执行失败: {result.stderr}"
        
        # 聚合：按文件分组，只保留文件名和匹配行号
        file_matches = {}
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            # ripgrep 输出格式 (Windows): d:\path\file.md:42:匹配内容
            # 注意 Windows 路径自带一个冒号 (d:)
            # 我们应该从右边分割或者用正则提取
            import re
            # 寻找最后一个路径:行号:内容的模式
            match = re.search(r'^(.*?):(\d+):(.*)$', line)
            if match:
                filepath = match.group(1)
                try:
                    line_no = int(match.group(2))
                except ValueError:
                    continue
                basename = os.path.basename(filepath)
                if basename not in file_matches:
                    file_matches[basename] = []
                file_matches[basename].append(line_no)
        
        if not file_matches:
            return f"[L0] 未找到包含 '{pattern}' 的记忆。"
        
        # 构建紧凑索引输出
        total_matches = sum(len(v) for v in file_matches.values())
        output = [f"[L0] 搜索 \"{pattern}\" 找到 {len(file_matches)} 个文件，共 {total_matches} 处匹配：\n"]
        
        for i, (fname, lines) in enumerate(file_matches.items(), 1):
            line_nums = ','.join(f"L{n}" for n in sorted(lines))
            output.append(f"  {i}. {fname} ({len(lines)}处匹配: {line_nums})")
        
        output.append(f"\n提示: 使用 read_memory(file_path=\"<文件名>\", start_line=N, end_line=M, user_id=\"{user_id}\") 读取具体内容。")
        
        return '\n'.join(output)
            
    except Exception as e:
         return f"[ERROR] 搜索异常: {type(e).__name__}: {str(e)}"



def maybe_truncate(content: str, max_len: int = 15000) -> str:
    """防止 Token 爆炸的截断保护"""
    if len(content) > max_len:
        return content[:max_len] + f"\n\n... [内容过长已触发自我保护截断，省略后 {len(content)-max_len} 字符。请减小 end_line 重新读取剩余部分]"
    return content

def read_memory(
    file_path: str,
    start_line: int,
    end_line: int,
    user_id: str
) -> str:
    """
    [L2] 精准定位读取指定记忆行范围
    
    Args:
        file_path: 从 L0 获取到的目标记忆文件 (相对/绝对路径)
        start_line: 起始读取行
        end_line: 结束读取行
        user_id: 防止越权读取的安全校验
        
    Returns:
        包含精确行号的具体记忆内容
    """
    try:
        # 强制行数限制保护：一次最多读 300 行
        if end_line - start_line > 300:
            end_line = start_line + 300
            
        _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # 处理可能的相对路径
        if not os.path.isabs(file_path):
            # 文件名格式: 2026-03-09_app_session.md → 月份目录: 2026-03
            # 先尝试直接拼接（含月份目录）
            basename = os.path.basename(file_path)
            month_prefix = basename[:7] if len(basename) >= 7 else ""
            candidate = os.path.join(_PROJECT_ROOT, "memory_archive", user_id, month_prefix, basename)
            if os.path.exists(candidate):
                file_path = candidate
            else:
                # 兜底：直接拼接不含月份目录
                file_path = os.path.join(_PROJECT_ROOT, "memory_archive", user_id, file_path)
             
        # 安全校验: 确保读取的目标文件包含 user_id (极其简化的沙箱)
        if user_id not in file_path:
             return f"❌ [ERROR] 安全拦截: 无权读取其他用户的记忆档案"
        
        if not os.path.exists(file_path):
             return f"❌ [ERROR] 档案不存在: {file_path}"
             
             
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        total = len(lines)
        start = max(0, start_line - 1)
        end = min(total, end_line)
        
        selected = lines[start:end]
        
        result_lines = []
        for i, line in enumerate(selected, start=start_line):
           result_lines.append(f"{i:4d}: {line.rstrip()}")
           
        content = "\n".join(result_lines)
        content = maybe_truncate(content)  # 字符级硬截断保护
        
        header = f"📖 **[L2 Read] {os.path.basename(file_path)}** (Lines {start_line}-{end}):\n"
        if end < end_line:
            header += f"   *Notice: Auto-capped at 300 lines for safety.*\n"
            
        return header + "-"*40 + "\n" + content + "\n" + "-"*40
        
    except Exception as e:
         return f"❌ [ERROR] 读取异常: {str(e)}"


MEMORY_TOOLS = {
    "search_memory": search_memory,
    "read_memory": read_memory
}

def get_tools(*args, **kwargs) -> List:
    return list(MEMORY_TOOLS.values())


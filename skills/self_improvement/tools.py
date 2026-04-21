"""
Self-Improvement Skill - Tools Module

Provides log_learning and log_error tools for structured knowledge capture.
Also provides after_tool_callback and after_model_callback factory functions
for ADK native hook integration.
"""
import os
import datetime
import secrets
import traceback
import logging
from typing import Optional, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

# 项目根目录 (由 _init_paths 动态设置)
_PROJECT_ROOT: str = ""
_LEARNINGS_DIR: str = ""

# 错误检测模式列表 (移植自 error-detector.sh)
ERROR_PATTERNS = [
    "error:", "Error:", "ERROR:",
    "failed", "FAILED",
    "command not found", "No such file",
    "Permission denied", "fatal:",
    "Exception", "Traceback",
    "npm ERR!", "ModuleNotFoundError",
    "SyntaxError", "TypeError",
    "exit code", "non-zero",
    "is not recognized",  # Windows command not found
    "无法完成", "失败", "错误",       # Chinese errors
]


def _init_paths(project_root: str = "") -> None:
    """初始化路径 (幂等: 无参调用时若已初始化则跳过)"""
    global _PROJECT_ROOT, _LEARNINGS_DIR
    if not project_root and _LEARNINGS_DIR:
        # 已初始化且未指定新路径，跳过
        return
    if not project_root:
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    _PROJECT_ROOT = project_root
    _LEARNINGS_DIR = os.path.join(_PROJECT_ROOT, ".learnings")
    os.makedirs(_LEARNINGS_DIR, exist_ok=True)


def _generate_id(prefix: str) -> str:
    """生成唯一 ID: LRN-20260421-A3F"""
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    rand_suffix = secrets.token_hex(2)[:3].upper()
    return f"{prefix}-{date_str}-{rand_suffix}"


async def log_learning(
    category: str,
    summary: str,
    details: str = "",
    priority: str = "medium",
    area: str = "backend",
    related_files: str = "",
    tags: str = "",
) -> str:
    """
    Record a learning entry to .learnings/LEARNINGS.md.

    Use this when you discover something non-obvious, find a better approach,
    or learn a project-specific convention.

    Args:
        category: Type of learning (correction, knowledge_gap, best_practice, workaround)
        summary: One-line description of what was learned
        details: Full context - what happened, what was wrong, what's correct
        priority: low | medium | high | critical
        area: frontend | backend | infra | tests | docs | config
        related_files: Comma-separated list of related file paths
        tags: Comma-separated tags for filtering
    """
    _init_paths()
    entry_id = _generate_id("LRN")
    timestamp = datetime.datetime.now().isoformat()

    entry = f"""
## [{entry_id}] {category}

**Logged**: {timestamp}
**Priority**: {priority}
**Status**: pending
**Area**: {area}

### Summary
{summary}

### Details
{details or 'N/A'}

### Suggested Action
Review and apply this learning in future tasks.

### Metadata
- Source: agent_session
- Related Files: {related_files or 'N/A'}
- Tags: {tags or category}

---
"""
    learnings_file = os.path.join(_LEARNINGS_DIR, "LEARNINGS.md")
    try:
        with open(learnings_file, "a", encoding="utf-8") as f:
            f.write(entry)
        return f"[OK] Learning logged: {entry_id} ({category}: {summary})"
    except Exception as e:
        error_msg = f"[ERROR] Failed to write learning: {e}\n{traceback.format_exc()}"
        logger.error(error_msg, exc_info=True)
        return error_msg


async def log_error(
    tool_name: str,
    error_msg: str,
    context: str = "",
    priority: str = "high",
    area: str = "backend",
    related_files: str = "",
) -> str:
    """
    Record an error entry to .learnings/ERRORS.md.

    Use this when a tool or command fails unexpectedly, especially if it
    required investigation to resolve.

    Args:
        tool_name: Name of the tool or command that failed
        error_msg: The actual error message or output
        context: What was being attempted and environment details
        priority: low | medium | high | critical
        area: frontend | backend | infra | tests | docs | config
        related_files: Comma-separated list of related file paths
    """
    _init_paths()
    entry_id = _generate_id("ERR")
    timestamp = datetime.datetime.now().isoformat()

    entry = f"""
## [{entry_id}] {tool_name}

**Logged**: {timestamp}
**Priority**: {priority}
**Status**: pending
**Area**: {area}

### Summary
Error in {tool_name}

### Error
```
{error_msg}
```

### Context
{context or 'N/A'}

### Suggested Fix
Investigate the root cause and apply a fix.

### Metadata
- Reproducible: unknown
- Related Files: {related_files or 'N/A'}

---
"""
    errors_file = os.path.join(_LEARNINGS_DIR, "ERRORS.md")
    try:
        with open(errors_file, "a", encoding="utf-8") as f:
            f.write(entry)
        return f"[OK] Error logged: {entry_id} ({tool_name})"
    except Exception as e:
        error_detail = f"[ERROR] Failed to write error log: {e}\n{traceback.format_exc()}"
        logger.error(error_detail, exc_info=True)
        return error_detail


def detect_error_in_output(output_text: str) -> bool:
    """检查输出文本是否包含错误模式 (移植自 error-detector.sh)"""
    for pattern in ERROR_PATTERNS:
        if pattern in output_text:
            return True
    return False


def build_after_tool_callback(loaded_skills_getter=None):
    """
    工厂函数: 创建 after_tool_callback (常驻系统监控版)
    返回 None = 不修改结果; 返回 dict = 替换工具结果
    """
    def _after_tool_callback(tool, args, tool_context, tool_response):
        # [Self-Improvement] 现在是常驻功能，默认始终执行监控
        response_text = str(tool_response)
        if detect_error_in_output(response_text):
            tool_name = getattr(tool, "name", getattr(tool, "__name__", str(tool)))
            logger.info(
                "[SelfImprovement] Error detected in tool %s output, injecting reminder",
                tool_name,
            )
            reminder = (
                "\n\n<error-detected>"
                "\nA tool error was detected. Consider logging to .learnings/ERRORS.md "
                "using the `log_error` tool if this error was unexpected or required investigation."
                "\n</error-detected>"
            )
            if isinstance(tool_response, dict):
                modified = dict(tool_response)
                for key in ("result", "output", "content"):
                    if key in modified:
                        modified[key] = str(modified[key]) + reminder
                        return modified
                # fallback: 追加到第一个字符串值
                for key, val in modified.items():
                    if isinstance(val, str):
                        modified[key] = val + reminder
                        return modified
            # tool_response 不是 dict, 无法安全修改
            return None
        return None

    return _after_tool_callback


def build_after_model_callback(loaded_skills_getter=None):
    """
    工厂函数: 创建 after_model_callback (常驻系统监控版)
    功能: LLM 回复后标记 session state, 提醒下一轮评估 learning
    """
    def _after_model_callback(callback_context, llm_response):
        # [Self-Improvement] 在 session state 中设置标记 (常驻执行)
        try:
            if hasattr(callback_context, "state") and callback_context.state is not None:
                callback_context.state["_si_pending_eval"] = True
        except Exception as e:
            logger.error("[SelfImprovement] Failed to set state marker: %s", e, exc_info=True)

        return None  # 不修改 LLM 响应

    return _after_model_callback


def get_tools(*args, **kwargs) -> List:
    """ADK skill 加载协议入口"""
    # 初始化路径
    if args and hasattr(args[0], "tools"):
        # args[0] 是 agent 对象, 从它推断项目根目录
        pass
    _init_paths()
    return [log_learning, log_error]

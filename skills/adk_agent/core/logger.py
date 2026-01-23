"""
日志工具模块

提供结构化的日志记录功能（纯日志，不追踪状态）。
"""

import sys
from datetime import datetime
from typing import Optional
from enum import Enum


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    TOOL = "TOOL"


class AgentLogger:
    """Agent 日志记录器（纯日志功能）"""
    
    def __init__(self, verbose: bool = True, log_tool_calls: bool = True):
        self.verbose = verbose
        self.log_tool_calls = log_tool_calls
        self.history = []
    
    def _format_message(self, level: LogLevel, message: str, **kwargs) -> str:
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        icons = {
            LogLevel.DEBUG: "[DEBUG]",
            LogLevel.INFO: "[INFO]",
            LogLevel.WARN: "[WARN]",
            LogLevel.ERROR: "[ERROR]",
            LogLevel.TOOL: "[TOOL]",
        }
        
        icon = icons.get(level, "")
        formatted = f"[{timestamp}] {icon} {message}"
        
        if kwargs:
            details = " | ".join(f"{k}={v}" for k, v in kwargs.items())
            formatted += f" ({details})"
        
        return formatted
    
    def _log(self, level: LogLevel, message: str, **kwargs):
        formatted = self._format_message(level, message, **kwargs)
        self.history.append((level, formatted))
        
        if self.verbose or level in [LogLevel.ERROR, LogLevel.WARN]:
            print(formatted, file=sys.stderr if level == LogLevel.ERROR else sys.stdout)
    
    def debug(self, message: str, **kwargs):
        if self.verbose:
            self._log(LogLevel.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log(LogLevel.INFO, message, **kwargs)
    
    def warn(self, message: str, **kwargs):
        self._log(LogLevel.WARN, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log(LogLevel.ERROR, message, **kwargs)
    
    def tool_call(self, tool_name: str, args: dict, result: Optional[str] = None):
        if self.log_tool_calls:
            args_str = ", ".join(f"{k}={repr(v)}" for k, v in args.items())
            self._log(LogLevel.TOOL, f"调用 {tool_name}({args_str})")
            if result:
                self._log(LogLevel.TOOL, f"返回: {result}")
    
    def skill_loaded(self, skill_id: str, tools: list):
        tool_names = [t.__name__ if hasattr(t, '__name__') else str(t) for t in tools]
        self._log(LogLevel.INFO, f"技能已加载: {skill_id}", tools=tool_names)
    
    def task_start(self, task: str):
        self._log(LogLevel.INFO, f"任务启动: {task}")
    
    def task_complete(self, result: str):
        self._log(LogLevel.INFO, f"任务完成: {result}")
    
    def thought(self, content: str):
        self._log(LogLevel.DEBUG, f"思考: {content}")
    
    def get_history(self) -> list:
        return self.history.copy()
    
    def clear_history(self):
        self.history.clear()


# 全局日志实例 (默认关闭 verbose 以避免与 main.py 中的自定义输出重复)
logger = AgentLogger(verbose=False)

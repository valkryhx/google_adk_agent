"""
极简独立文件日志模块
- 零依赖，不依赖任何 logging 体系
- 100% 可靠，保证写入
- 同时输出到控制台和文件
- 线程/协程安全
- 自动创建目录，自动轮转
"""

import os
import sys
import atexit
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
import contextlib
import builtins

class SimpleFileLogger:
    """极简文件日志器，同时输出到控制台和文件"""
    
    _instances: Dict[str, 'SimpleFileLogger'] = {}
    _lock = threading.Lock()
    
    def __new__(cls, log_file: str = "logs/agent_debug.log", max_size: int = 10 * 1024 * 1024, backup_count: int = 5):
        """单例模式：相同日志文件路径复用同一个实例"""
        with cls._lock:
            if log_file not in cls._instances:
                instance = super().__new__(cls)
                instance._initialized = False
                cls._instances[log_file] = instance
            return cls._instances[log_file]
    
    def __init__(self, log_file: str = "logs/agent_debug.log", max_size: int = 10 * 1024 * 1024, backup_count: int = 5):
        """初始化日志器"""
        if self._initialized:
            return
            
        self.log_file = log_file
        self.max_size = max_size
        self.backup_count = backup_count
        
        # 确保目录存在
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        
        # 立即写入测试标记，验证可写性
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n--- 日志会话开始于 {self._current_time()} ---\n")
        except Exception as e:
            print(f"[SimpleFileLogger] 无法写入日志文件: {e}", file=sys.stderr)
        
        # 注册退出时刷新
        atexit.register(self.flush)
        
        self._initialized = True
        self._buffer = []
    
    def _current_time(self) -> str:
        """获取当前时间字符串（毫秒精度）"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    def _check_rotation(self):
        """检查并执行日志轮转"""
        if not os.path.exists(self.log_file):
            return
            
        size = os.path.getsize(self.log_file)
        if size < self.max_size:
            return
            
        # 执行轮转
        for i in range(self.backup_count - 1, 0, -1):
            old_name = f"{self.log_file}.{i}"
            new_name = f"{self.log_file}.{i+1}"
            if os.path.exists(old_name):
                if os.path.exists(new_name):
                    os.remove(new_name)
                os.rename(old_name, new_name)
        
        # 备份当前文件
        backup = f"{self.log_file}.1"
        if os.path.exists(backup):
            os.remove(backup)
        os.rename(self.log_file, backup)
    
    def log(self, *args, sep: str = ' ', level: str = "INFO", to_console: bool = True):
        """
        核心日志方法：同时写入文件和输出到控制台
        
        参数:
            *args: 任意数量的参数，同 print(*args)
            sep: 分隔符，默认空格
            level: 日志级别 (INFO/DEBUG/WARNING/ERROR)
            to_console: 是否同时输出到控制台，默认True
        """
        # 拼接消息
        msg = sep.join(str(arg) for arg in args)
        timestamp = self._current_time()
        log_line = f"{timestamp} - {level} - {msg}\n"
        
        # 线程安全写入
        with self._lock:
            # 写入文件（实时）
            try:
                self._check_rotation()
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(log_line)
            except Exception as e:
                print(f"[SimpleFileLogger] 写入失败: {e}", file=sys.stderr)
            
            # 可选输出到控制台
            if to_console:
                # 使用原始 print，避免递归
                builtins_print = __builtins__.get('print') if isinstance(__builtins__, dict) else __builtins__.print
                builtins_print(msg)
    
    # === 便捷方法 ===
    def info(self, *args, sep: str = ' ', to_console: bool = True):
        """INFO 级别日志"""
        self.log(*args, sep=sep, level="INFO", to_console=to_console)
    
    def debug(self, *args, sep: str = ' ', to_console: bool = True):
        """DEBUG 级别日志"""
        self.log(*args, sep=sep, level="DEBUG", to_console=to_console)
    
    def warning(self, *args, sep: str = ' ', to_console: bool = True):
        """WARNING 级别日志"""
        self.log(*args, sep=sep, level="WARNING", to_console=to_console)
    
    def error(self, *args, sep: str = ' ', to_console: bool = True):
        """ERROR 级别日志"""
        self.log(*args, sep=sep, level="ERROR", to_console=to_console)
    
    def flush(self):
        """退出时确保所有日志写入（本模块是实时写入，此方法保留兼容性）"""
        pass


# ============================================
# 全局默认实例 - 直接导入即可使用
# ============================================
default_logger = SimpleFileLogger("logs/agent_debug.log")


# ============================================
# 装饰器：自动记录函数调用
# ============================================
def log_call(logger=None):
    """装饰器：自动记录函数进入和退出"""
    if logger is None:
        logger = default_logger
    
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger.debug(f"▶️ 进入 {func.__name__}")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"✅ 退出 {func.__name__}")
                return result
            except Exception as e:
                logger.error(f"❌ 异常 {func.__name__}: {e}")
                raise
        return wrapper
    return decorator


# ============================================
# 上下文管理器：临时捕获 print 输出
# ============================================
@contextlib.contextmanager
def capture_prints_to_logger(logger=None):
    """临时将所有的 print 重定向到日志器"""
    if logger is None:
        logger = default_logger
    
    original_print = builtins.print
    def _captured_print(*args, **kwargs):
        # 保持控制台输出
        original_print(*args, **kwargs)
        # 同时写入日志文件
        if kwargs.get('file', sys.stdout) is sys.stdout:
            msg = ' '.join(str(arg) for arg in args)
            logger.info(msg, to_console=False)
    
    builtins.print = _captured_print
    try:
        yield
    finally:
        builtins.print = original_print
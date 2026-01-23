"""
Executor - 物理执行器

负责实际的代码执行、会话管理和工具卸载操作。
"""

import sys
import io
from typing import Any


def execute_python_code(code: str) -> str:
    """
    真实 Python 执行器：捕获输出与报错
    
    这个函数会动态执行传入的 Python 代码，并捕获所有输出。
    支持 pandas 和 matplotlib，适用于数据分析任务。
    
    Args:
        code: 要执行的 Python 代码字符串
        
    Returns:
        执行输出或错误信息
    """
    # 尝试导入可能需要的库
    try:
        import pandas as pd
        import matplotlib
        matplotlib.use('Agg')  # 使用非交互式后端
        import matplotlib.pyplot as plt
        available_libs = {"pd": pd, "plt": plt}
    except ImportError:
        available_libs = {}

    # 清理代码中的 markdown 标记
    clean_code = code.replace("```python", "").replace("```", "").strip()
    
    # 捕获标准输出
    output_capture = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = output_capture

    # 准备执行环境
    loc = {**available_libs}
    
    try:
        exec(clean_code, globals(), loc)
        sys.stdout = old_stdout
        output = output_capture.getvalue()
        return output if output else "执行完成（无打印输出）。"
    except Exception as e:
        sys.stdout = old_stdout
        return f"运行时报错: {type(e).__name__}: {str(e)}"
    finally:
        output_capture.close()


async def execute_context_compact(agent_instance: Any, session_service: Any, app_name: str, user_id: str, session_id: str) -> str:
    """
    卸载动作：清空 Session 历史，并将 Agent 工具集重置为仅含网关
    
    这个函数用于在任务完成后重置 Agent 状态，实现：
    1. 清空对话历史，释放 Token
    2. 卸载所有动态加载的工具
    
    Args:
        agent_instance: Agent 实例
        session_service: 会话服务实例
        app_name: 应用名称
        user_id: 用户 ID
        session_id: 会话 ID
        
    Returns:
        操作结果消息
    """
    try:
        # 尝试清空会话
        if hasattr(session_service, 'clear_session'):
            await session_service.clear_session(session_id)
        elif hasattr(session_service, 'delete_session'):
            await session_service.delete_session(app_name=app_name, user_id=user_id, session_id=session_id)
        
        # 动态卸载所有通过 skill_load 挂载的工具
        # 保留第一个工具（skill_load 网关）
        if hasattr(agent_instance, 'tools') and len(agent_instance.tools) > 1:
            agent_instance.tools = [agent_instance.tools[0]]
            
        return "[OK] 历史已重置。临时工具已卸载。当前状态：轻量化初始态。"
    except Exception as e:
        return f"[WARN] 重置过程中出现问题: {type(e).__name__}: {str(e)}"


def create_tool_function(tool_name: str, tool_description: str):
    """
    动态创建工具函数的工厂方法
    
    Args:
        tool_name: 工具名称
        tool_description: 工具描述
        
    Returns:
        新创建的工具函数
    """
    def dynamic_tool(**kwargs) -> str:
        return f"工具 {tool_name} 被调用，参数: {kwargs}"
    
    dynamic_tool.__name__ = tool_name
    dynamic_tool.__doc__ = tool_description
    return dynamic_tool


async def execute_async_python_code(code: str, context: dict = None) -> str:
    """
    异步 Python 执行器：支持 await 和上下文注入
    
    Args:
        code: Python 代码字符串
        context: 注入到执行环境的变量字典 (如 call_tool)
        
    Returns:
        执行结果或错误
    """
    import sys
    import io
    import asyncio
    
    # 尝试导入分析库
    try:
        import pandas as pd
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        available_libs = {"pd": pd, "plt": plt, "asyncio": asyncio}
    except ImportError:
        available_libs = {"asyncio": asyncio}

    # 代码清理
    clean_code = code.replace("```python", "").replace("```", "").strip()
    
    # 构建执行环境
    # CRITICAL FIX: 函数定义(async def)会绑定到 globals。
    # 如果我们将工具只放在 locals (loc) 中，函数内部将无法通过 global scope 访问它们。
    # 因此，我们需要构建一个合并的 globals 字典。
    exec_globals = globals().copy()
    exec_globals.update(available_libs)
    # 确保脚本内的 if __name__ == "__main__": 能够正确触发
    exec_globals['__name__'] = '__main__'
    if context:
        exec_globals.update(context)

    # 捕获输出
    output_capture = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = output_capture

    try:
        # 如果代码没有被 async def 包裹，我们尝试执行它
        # 更好的方式是让 Agent 定义一个 entry point，或者我们包裹它
        # 这里使用一种通用模式：包裹在 main 函数中执行
        
        # 检查代码是否有 await，如果有，必须包裹在 async 函数中
        wrapped_code = f"""
async def _async_main_():
    try:
{'\n'.join(['        ' + line for line in clean_code.splitlines()])}
    except Exception as e:
        print(f"执行出错: {{e}}")
        raise e
"""
        # 1. 编译 async wrapper
        # 使用相同的字典作为 globals 和 locals，模拟模块级执行
        exec(wrapped_code, exec_globals, exec_globals)
        
        # 2. 执行并等待
        if "_async_main_" in exec_globals:
            await exec_globals["_async_main_"]()
        
        sys.stdout = old_stdout
        return output_capture.getvalue() or "执行完成（无打印输出）。"

    except Exception as e:
        sys.stdout = old_stdout
        # 尝试回退到同步执行 (如果是简单的 print)
        if "await" not in clean_code:
             return execute_python_code(code)
        return f"异步执行报错: {type(e).__name__}: {str(e)}"
    finally:
        output_capture.close()


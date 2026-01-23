import sys
import os
import asyncio
import inspect
from typing import List, Any

# Adapt path to import from core
current_dir = os.path.dirname(os.path.abspath(__file__))
# 假设 agent_root 是 skills/adk_agent 的父目录
# 目录结构: skills/adk_agent/.claude/skills/programmatic-tool-calling/tools.py
# 需要回退4层到 skills/ 前面，或者是直接找到 adk_agent 的位置
agent_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if agent_root not in sys.path:
    sys.path.insert(0, agent_root)

# Import the new async executor
from core.executor import execute_async_python_code

# Global references to injected services
_AGENT_REF = None

async def run_programmatic_task(code: str) -> str:
    """
    通过编写 Python 代码来执行任务。
    可以在代码中使用 `await call_tool("工具名", 参数=值)` 来调用 Agent 的其他工具。
    
    Args:
        code: 要执行的 Python 代码。
              支持 pandas, matplotlib, asyncio。
              如果需要调用其他工具，请务必使用 `await call_tool(...)`。
              
    Returns:
        执行输出 (stdout)
    """
    global _AGENT_REF
    
    # === 定义 Bridge 函数 ===
    async def call_tool_bridge(tool_name: str, **kwargs) -> Any:
        """
        Injected bridge to call other tools from within the sandbox.
        """
        print(f"[Sandbox] Requesting tool: {tool_name} with {kwargs}")
        
        if not _AGENT_REF:
            # 尝试回退：检查是否有 bash (Hack for standalone testing)
            # 但在 Agent 环境中应该总是有 _AGENT_REF
            return "[Error] Agent reference lost."
            
        # 1. Find the tool
        target_tool = None
        # _AGENT_REF.tools 应该是一个工具列表
        if hasattr(_AGENT_REF, 'tools'):
            for tool in _AGENT_REF.tools:
                t_name = getattr(tool, '__name__', str(tool))
                if t_name == tool_name:
                    target_tool = tool
                    break
        
        if not target_tool:
            return f"[Error] Tool '{tool_name}' not found."

        # 2. Execute the tool
        try:
            # Check if it's a coroutine
            if inspect.iscoroutinefunction(target_tool):
                return await target_tool(**kwargs)
            else:
                return target_tool(**kwargs)
        except Exception as e:
            return f"[Error executing {tool_name}] {e}"

    # === 执行代码 ===
    context = {
        "call_tool": call_tool_bridge
    }
    
    return await execute_async_python_code(code, context)


def get_tools(agent, session_service, app_info) -> List:
    """
    Factory method to initialize the tool with Agent access.
    """
    global _AGENT_REF
    _AGENT_REF = agent
    return [run_programmatic_task]

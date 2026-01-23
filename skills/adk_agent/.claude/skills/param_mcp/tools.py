"""
参数 MCP Integration Skill - Model Context Protocol 工具集成

提供与外部参数 MCP 服务的集成，通过 HTTP 连接使用 MCP 工具。

注意：MCP toolset 的初始化是异步的，但在 skills 框架中，工具加载是同步的。
因此，我们使用延迟初始化的方式：创建一个包装对象，在首次使用时初始化。
"""

import os
import asyncio
from typing import Optional, List
from urllib.parse import urlparse

# 全局变量，存储 MCP toolset 实例
_mcp_toolset = None
_mcp_url = os.environ.get("MCP_URL", "http://localhost:9014/mcp")


def _create_mcp_toolset():
    """
    创建 MCP toolset 实例
    
    注意：这是一个同步包装函数，实际的初始化是异步的。
    在 skills 框架中，McpToolset 对象可以直接添加到 tools 列表。
    """
    global _mcp_toolset
    
    # 如果已经创建，直接返回
    if _mcp_toolset is not None:
        return _mcp_toolset
    
    try:
        from google.adk.tools.mcp_tool import McpToolset
        from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
        
        # 创建 MCP toolset 实例
        # 注意：McpToolset 的初始化本身是同步的，但连接验证是异步的
        # ADK 会在实际使用时处理异步连接
        _mcp_toolset = McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=_mcp_url
            )
        )
        
        return _mcp_toolset
    except Exception as e:
        # 如果导入失败或创建失败，返回 None
        # 系统会在运行时处理错误
        print(f"[参数 MCP Integration] 警告: 无法创建 MCP toolset: {e}")
        return None


def get_mcp_toolset():
    """
    获取 MCP toolset 实例
    
    这是一个同步函数，返回 McpToolset 对象。
    McpToolset 对象可以直接添加到 Agent 的 tools 列表中。
    """
    toolset = _create_mcp_toolset()
    if toolset is None:
        # 如果创建失败，返回一个占位函数
        # 这个函数会在被调用时返回错误信息
        def mcp_unavailable():
            """MCP 工具集不可用（服务可能未启动）"""
            return "MCP 工具集当前不可用，请检查服务是否启动。确保 MCP_URL 环境变量正确设置，且 MCP 服务正在运行。"
        return mcp_unavailable
    return toolset


def get_tools() -> List:
    """
    返回 MCP 集成工具列表
    
    注意：McpToolset 对象本身就是一个工具容器，ADK 会自动识别其中的工具。
    因此，我们直接返回 toolset 对象本身。
    """
    toolset = get_mcp_toolset()
    
    # 如果 toolset 是 None 或占位函数，返回空列表（或占位函数）
    if toolset is None:
        return []
    
    # 如果 toolset 是一个占位函数，将其包装在列表中返回
    if callable(toolset) and not hasattr(toolset, 'get_tools'):
        # 这是一个占位函数，返回它
        return [toolset]
    
    # 否则，返回 toolset 对象本身
    # ADK 会识别 McpToolset 对象并提取其中的工具
    return [toolset]


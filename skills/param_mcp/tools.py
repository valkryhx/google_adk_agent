"""
参数 MCP Integration Skill - Model Context Protocol 工具集成

提供与外部参数 MCP 服务的集成，通过 HTTP 连接使用 MCP 工具。

注意：MCP toolset 的初始化是异步的，但在 skills 框架中，工具加载是同步的。
因此，我们使用延迟初始化的方式：创建一个包装对象，在首次使用时初始化。
"""

import os
import logging
from typing import List

logger = logging.getLogger(__name__)

# 全局变量，存储 MCP toolset 实例
_mcp_toolset = None
_mcp_init_failed = False  # 标志：是否已尝试初始化且失败，避免重复无效尝试
_mcp_url = os.environ.get("MCP_URL", "http://localhost:9014/mcp")


def _create_mcp_toolset():
    """
    创建 MCP toolset 实例

    注意：这是一个同步包装函数，实际的初始化是异步的。
    在 skills 框架中，McpToolset 对象可以直接添加到 tools 列表。
    """
    global _mcp_toolset, _mcp_init_failed

    # 如果已经创建，直接返回
    if _mcp_toolset is not None:
        return _mcp_toolset

    # 如果已经失败过，不再重试
    if _mcp_init_failed:
        logger.warning("[参数 MCP Integration] 跳过重试：上次初始化已失败")
        return None

    try:
        from google.adk.tools.mcp_tool import McpToolset
        from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

        logger.info(f"[参数 MCP Integration] 正在连接 MCP 服务: {_mcp_url}")

        _mcp_toolset = McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=_mcp_url
            )
        )
        logger.info("[参数 MCP Integration] MCP toolset 创建成功")
        return _mcp_toolset

    except Exception as e:
        _mcp_init_failed = True
        logger.error(
            f"[参数 MCP Integration] 无法创建 MCP toolset，URL={_mcp_url}，错误: {e}",
            exc_info=True
        )
        return None


def get_mcp_toolset():
    """
    获取 MCP toolset 实例

    这是一个同步函数，返回 McpToolset 对象。
    McpToolset 对象可以直接添加到 Agent 的 tools 列表中。
    """
    toolset = _create_mcp_toolset()
    if toolset is None:
        def mcp_unavailable():
            """MCP 工具集不可用（服务可能未启动）"""
            msg = (
                f"MCP 工具集当前不可用，请检查：\n"
                f"  1. MCP 服务是否已启动（当前配置 URL: {_mcp_url}）\n"
                f"  2. 环境变量 MCP_URL 是否正确设置\n"
                f"  3. 查看日志中的具体错误信息"
            )
            return msg
        mcp_unavailable._is_placeholder = True
        return mcp_unavailable
    return toolset


def get_tools(*args, **kwargs) -> List:
    """
    返回 MCP 集成工具列表

    注意：McpToolset 对象本身就是一个工具容器，ADK 会自动识别其中的工具。
    因此，我们直接返回 toolset 对象本身。
    """
    toolset = get_mcp_toolset()

    if toolset is None:
        return []

    # 通过 _is_placeholder 标志判断是否为占位函数
    if getattr(toolset, "_is_placeholder", False):
        return [toolset]

    # 返回 McpToolset 对象，ADK 会自动提取其中的工具
    return [toolset]

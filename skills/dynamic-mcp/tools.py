"""
Dynamic MCP Loader Skill - 动态 MCP 工具加载器

提供运行时动态加载 MCP 服务的能力，支持远程 HTTP/SSE 连接和本地进程启动。
Agent 可以根据搜索结果自主发现并加载新的 MCP 工具，实现能力的即时扩展。
"""

import os
import shutil
import asyncio
from typing import List, Optional, Dict, Literal, Tuple
from urllib.parse import urlparse

# ADK 核心组件
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioServerParameters,
    StreamableHTTPConnectionParams
)


def get_tools(agent, session_service, app_info) -> List:
    """
    返回动态 MCP 加载工具
    
    利用 ADK 的依赖注入机制，获取当前 agent 实例，从而能够在运行时
    修改 agent.tools 列表，实现动态工具挂载。
    """
    
    # --- 安全配置 ---
    ALLOWED_LOCAL_COMMANDS = {"npx", "npx.cmd", "uvx", "node", "python", "python3"}
    
    def _is_safe_arg(arg: str) -> bool:
        """防止 Shell 注入攻击"""
        dangerous_chars = ['|', '>', '<', ';', '&', '`', '$(']
        return not any(char in arg for char in dangerous_chars)
    
    # async def _wrap_mcp_tool(original_tool, mcp_identifier: str):
    #     """
    #     包装 MCP 工具,提供断线检测和友好错误提示
        
    #     Args:
    #         original_tool: 原始 MCP 工具函数
    #         mcp_identifier: MCP 服务标识符(用于错误提示)
        
    #     Returns:
    #         包装后的工具函数
    #     """
    #     async def wrapped(*args, **kwargs):
    #         try:
    #             # 调用原始工具
    #             return await original_tool(*args, **kwargs)
    #         except Exception as e:
    #             err_msg = str(e)
    #             # 检测常见的断线错误特征
    #             disconnect_keywords = [
    #                 "all connection attempts failed",
    #                 "session termination failed",
    #                 "connection closed",
    #                 "disconnect",
    #                 "shutdown",
    #                 "connection error",
    #                 "not connected"
    #             ]
                
    #             if any(keyword in err_msg.lower() for keyword in disconnect_keywords):
    #                 # 返回友好的断线提示,而非抛出异常
    #                 return (
    #                     f"[MCP 连接已断开] {mcp_identifier} 服务不可用。\n\n"
    #                     f"可能原因:\n"
    #                     f"1. 浏览器进程已关闭\n"
    #                     f"2. MCP 服务意外退出\n"
    #                     f"3. 网络连接中断\n\n"
    #                     f"建议操作: 使用 connect_mcp 重新连接"
    #                 )
    #             # 其他异常正常抛出
    #             raise
        
    #     # 保持原函数的元数据
    #     wrapped.__name__ = getattr(original_tool, '__name__', 'unknown_tool')
    #     wrapped.__doc__ = getattr(original_tool, '__doc__', '')
    #     return wrapped
    
    async def _verify_mcp_connection(toolset: McpToolset, timeout: int = 10) -> Tuple[bool, str]:
        """
        验证 MCP 连接并主动触发工具发现
        
        Args:
            toolset: McpToolset 实例
            timeout: 超时时间（秒）
        
        Returns:
            (成功标志, 消息)
        """
        try:
            # 【关键修复】直接调用 get_tools() 而非等待后检查属性
            # 这与测试脚本的成功方式一致
            tools = await asyncio.wait_for(toolset.get_tools(), timeout=timeout)
            
            if tools:
                # 优先使用 name 属性(MCPTool的标准属性),其次才是 __name__
                tool_names = [getattr(t, 'name', getattr(t, '__name__', str(t))) for t in tools]
                return True, f"成功发现 {len(tools)} 个工具: {', '.join(tool_names[:3])}{'...' if len(tools) > 3 else ''}"
            
            # 理论上不会到达这里（get_tools 应该返回列表或抛出异常）
            return False, "未发现工具，连接可能失败"
        
        except asyncio.TimeoutError:
            return False, f"连接超时（{timeout}秒内未响应），请检查服务地址和端口"
        except ConnectionError as e:
            # 捕获我们主动抛出的连接错误
            return False, f"无法连接到 MCP 服务: {str(e)}"
        except BaseException as e:
            error_msg = str(e)
            # 友好化错误消息
            if "401" in error_msg or "Unauthorized" in error_msg:
                return False, "认证失败，请检查 API Key 是否正确"
            elif "403" in error_msg or "Forbidden" in error_msg:
                return False, "访问被拒绝，请确认 API Key 权限"
            elif "ConnectError" in error_msg or "connection" in error_msg.lower():
                return False, "无法连接到 MCP 服务，请确认服务地址和端口是否正确"
            elif "network" in error_msg.lower():
                return False, f"网络连接失败: {error_msg}"
            else:
                return False, f"连接失败: {error_msg}"

    async def connect_mcp(
        mode: Literal["remote", "local"],
        source: str,
        args: Optional[List[str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        api_key: Optional[str] = None
    ) -> str:
        """
        [全能加载器] 连接远程 MCP 服务或启动本地 MCP 进程，以动态扩展 Agent 能力。

        Args:
            mode: 连接模式。
                  - 'remote': 连接 HTTP/SSE 服务 (如 Context7, Exa)。
                  - 'local': 启动本地命令行工具 (如 npx, python)。
            source: 
                  - 当 mode='remote' 时，填写 URL (如 'https://mcp.context7.com/mcp')。
                  - 当 mode='local' 时，填写基础命令 (如 'npx', 'python')。
            args: 
                  - 当 mode='local' 时必填。参数列表 (如 ['-y', '@modelcontextprotocol/server-git'])。
                  - 当 mode='remote' 时忽略。
            env_vars: 
                  - (可选) 本地模式专用。需要注入的环境变量 (例如 {'BRAVE_API_KEY': '...'})。
            api_key:
                  - (可选) 远程模式专用。API Key，用于远程服务认证。
                  - 智能检测服务类型：
                    * Context7 (context7.com): 使用 'CONTEXT7_API_KEY' header
                    * 其他服务: 使用 'Authorization: Bearer {api_key}' header
                  - 格式示例：'ctx7sk-xxx' (Context7) 或 'mcp_sk_xxx' (标准服务)
        
        Returns:
            执行结果信息字符串
        """
        
        # 1. 初始化变量
        connection_params = None
        if args is None: 
            args = []
        if env_vars is None: 
            env_vars = {}

        # 2. 分支逻辑处理
        try:
            # ============================
            # 分支 A: 远程 HTTP/SSE 模式
            # ============================
            if mode == "remote":
                if not source.startswith("http"):
                    return f"[Error] 远程模式下 source 必须是 HTTP/HTTPS URL，收到: {source}"
                
                target_url = source
                
                # A-1. 远程去重检查
                for tool in agent.tools:
                    if isinstance(tool, McpToolset) and hasattr(tool, 'connection_params'):
                        if isinstance(tool.connection_params, StreamableHTTPConnectionParams):
                            # 简单的 URL 比较 (忽略末尾斜杠)
                            if tool.connection_params.url.rstrip('/') == target_url.rstrip('/'):
                                return f"无需重复连接：已连接到远程服务 {target_url}"
                
                # A-2. 配置参数（支持 API Key 认证）
                headers = {
                    # 必需的 MCP SSE headers（很多服务器要求这两个）
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json"
                }
                
                # 添加认证 header
                if api_key:
                    # 智能检测服务类型并使用对应的 header
                    if "context7.com" in target_url.lower():
                        # Context7 使用自定义 header
                        headers["CONTEXT7_API_KEY"] = api_key
                        print(f"[DynamicMCP] 连接远程（Context7 认证）: {target_url}")
                    else:
                        # 标准 MCP 服务使用 Bearer token
                        headers["Authorization"] = f"Bearer {api_key}"
                        print(f"[DynamicMCP] 连接远程（Bearer 认证）: {target_url}")
                else:
                    print(f"[DynamicMCP] 连接远程（无认证）: {target_url}")
                
                connection_params = StreamableHTTPConnectionParams(
                    url=target_url,
                    headers=headers
                )


            # ============================
            # 分支 B: 本地 Process 模式
            # ============================
            elif mode == "local":
                command = source
                
                # B-1. 安全校验
                if command not in ALLOWED_LOCAL_COMMANDS:
                    return f"[Security] 拒绝执行：命令 '{command}' 不在白名单中 ({ALLOWED_LOCAL_COMMANDS})。"
                for arg in args:
                    if not _is_safe_arg(arg):
                        return f"[Security] 参数 '{arg}' 含非法字符，拒绝执行。"
                if not shutil.which(command):
                    return f"[System] 找不到命令 '{command}'。请确保已安装 Node.js/Python 环境。"

                # B-2. 本地去重检查
                for tool in agent.tools:
                    if isinstance(tool, McpToolset) and hasattr(tool, 'connection_params'):
                        if isinstance(tool.connection_params, StdioServerParameters):
                            cp = tool.connection_params
                            if cp.command == command and cp.args == args:
                                return f"无需重复启动：本地服务 '{command} {args}' 已在运行。"

                # B-3. 配置参数
                final_env = os.environ.copy()
                final_env.update(env_vars)
                
                connection_params = StdioServerParameters(
                    command=command,
                    args=args,
                    env=final_env
                )
                print(f"[DynamicMCP] 启动本地: {command} {args}")

            else:
                return f"[Error] 未知的模式 '{mode}'，仅支持 'remote' 或 'local'。"

            # 3. 统一执行挂载与验证
            if connection_params:
                new_toolset = McpToolset(connection_params=connection_params)
                
                # 【关键优化】主动验证连接并等待工具发现
                print(f"[DynamicMCP] 正在验证连接...")
                success, message = await _verify_mcp_connection(new_toolset, timeout=15)
                
                if not success:
                    # 验证失败,不添加到 agent.tools
                    return f"[Error] {message}"
                
                # 【关键修复】验证成功后,将 toolset 添加到 agent.tools
                # 这一步是必需的,否则工具无法被 Agent 调用
                agent.tools.append(new_toolset)
                print(f"[DynamicMCP] 已将 MCP toolset 添加到 agent.tools")
                
                # 【用户体验优化】构建详细的工具列表信息
                tools = await new_toolset.get_tools()
                display_limit = 1000
                tool_lines = []
                
                for i, tool in enumerate(tools[:display_limit], 1):
                    name = getattr(tool, 'name', 'unknown')
                    desc = getattr(tool, 'description', '')
                    # 只取描述的第一行,可以限制长度
                    desc = desc.strip().split('\n')[0][:]
                    tool_lines.append(f"  {i}. `{name}` - {desc}")
                
                if len(tools) > display_limit:
                    tool_lines.append(f"  ... 还有 {len(tools) - display_limit} 个工具")
                
                tools_list_text = '\n'.join(tool_lines)
                
                # 返回格式化消息
                return f"""✅ **{mode.upper()} MCP 连接成功**

📦 已加载 **{len(tools)}** 个工具到当前会话

🔧 **工具列表**:
{tools_list_text}

💡 现在可以直接调用这些工具了。"""

        except BaseException as e:
            return f"[Error] 加载 MCP 失败: {str(e)}"

        return "[Error] 未知逻辑错误"

    return [connect_mcp]

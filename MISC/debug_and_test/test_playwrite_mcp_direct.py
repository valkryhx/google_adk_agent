import asyncio
import os
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioServerParameters 

async def test_connection():
    # 环境变量配置
    env_vars = {
        # 你的 Token
        "PLAYWRIGHT_MCP_EXTENSION_TOKEN": "your_playwright_extension_token_in_chrome",
        # 强制 Python 和 Node 尽可能使用 UTF-8，减少编码错误风险
        "PYTHONUTF8": "1",
        "NODE_OPTIONS": "--no-warnings", # 抑制 Node 的警告信息输出到 stderr (虽然 MCP 读取 stdout，但保持干净是个好习惯)
    }
    final_env = os.environ.copy()
    final_env.update(env_vars)
    
    print("=== 修正方案: 使用 'npx.cmd' 直接调用 ===")
    
    # 核心修正 1: Windows 下必须带 .cmd 后缀
    # 核心修正 2: 确保 -y 参数在最前面，防止交互式提示
    params = StdioServerParameters(
        command="npx.cmd", 
        args=["-y", "@playwright/mcp@latest", "--extension"],
        env=final_env
    )
    
    try:
        # 创建 Toolset
        toolset = McpToolset(connection_params=params)
        print("McpToolset 对象创建成功")
        
        print("正在建立连接并获取工具列表 (timeout=30s)...")
        # 这里会触发实际的进程启动和握手
        tools = await asyncio.wait_for(toolset.get_tools(), timeout=30)
        
        print(f"✅ 连接成功！发现 {len(tools)} 个工具")
        for i, tool in enumerate(tools[:10], 1):
            name = getattr(tool, 'name', 'unknown')
            print(f"  {i}. {name}")
            
    except Exception as e:
        print(f"❌ 依然失败: {type(e).__name__}: {e}")
        # 如果是解码错误，通常意味着 stdout 还是混入了非 JSON 文本
        if "UnicodeDecodeError" in str(e):
            print("\n⚠️ 提示: 请先在终端手动运行 'npx -y @playwright/mcp@latest' 确保包已安装且无额外日志输出。")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connection())
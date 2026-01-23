import sys
import os
import asyncio
from unittest.mock import MagicMock

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
# project_root (d:\git_codes\google_adk_helloworld\skills\adk_agent)
agent_root = os.path.join(current_dir, 'skills', 'adk_agent') 
sys.path.append(agent_root)

from core.executor import execute_async_python_code

async def test_async_injection():
    print("Testing async context injection...")
    
    # 1. Define a mock tool
    async def mock_call_tool(name, **kwargs):
        return f"Mock Tool Result: {name} called with {kwargs}"
    
    context = {"call_tool": mock_call_tool}
    
    # 2. Define user code that uses 'await call_tool'
    code = """
import asyncio
print("Starting code execution...")
# Call the injected tool
res = await call_tool('test_tool', param=123)
print(f"Tool returned: {res}")
"""

    # 3. Execute
    try:
        output = await execute_async_python_code(code, context)
        print("Execution Output:\n", output)
        
        if "Mock Tool Result" in output:
            print("[PASS] Context injection successful.")
        else:
            print("[FAIL] Output did not contain expected result.")
            
    except Exception as e:
        print(f"[FAIL] Execution failed: {e}")

if __name__ == "__main__":
    # Adjust path if running from a different location
    # But for simplicity, we mock the path setup above or rely on the environment
    # Let's try running it directly.
    import asyncio
    try:
        # Need to re-add the correct path for 'core' module
        # Assuming we are running this script from the project root d:\git_codes\google_adk_helloworld
        sys.path.append(r"d:\git_codes\google_adk_helloworld\skills\adk_agent")
        from core.executor import execute_async_python_code
        asyncio.run(test_async_injection())
    except ImportError:
        print("Could not import core.executor. Please check paths.")


import sys
import os
import importlib.util
import traceback

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
# Add the directory containing skills/adk_agent to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("--- Step 1: Check psutil ---")
try:
    import psutil
    print(f"psutil version: {psutil.__version__}")
    print(f"psutil path: {psutil.__file__}")
except ImportError:
    print("ERROR: psutil not installed!")
except Exception as e:
    print(f"ERROR importing psutil: {e}")

print("\n--- Step 2: Simulate tool loading ---")
try:
    from skills.adk_agent.config import AgentConfig
    config = AgentConfig()
    
    # Construct path to bash tools.py
    # skills_path: .../adk_agent/.claude/skills
    skill_id = "bash"
    tools_path = os.path.join(config.skills_path, skill_id, "tools.py")
    
    print(f"Target tools path: {tools_path}")
    
    if not os.path.exists(tools_path):
        print(f"ERROR: tools.py not found at {tools_path}")
    else:
        print("tools.py exists.")
        
        try:
            spec = importlib.util.spec_from_file_location(f"skills.{skill_id}", tools_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            print("Module loaded successfully.")
            
            if hasattr(module, 'get_tools'):
                print("get_tools function found.")
                tools = module.get_tools()
                print(f"get_tools returned: {tools}")
                print(f"Count: {len(tools)}")
            else:
                print("ERROR: get_tools function NOT found in module.")
                
        except Exception as e:
            print(f"ERROR loading module: {e}")
            traceback.print_exc()

except Exception as e:
    print(f"General Error: {e}")
    traceback.print_exc()

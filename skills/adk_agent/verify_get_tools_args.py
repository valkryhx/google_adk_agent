
import sys
import os
import importlib.util
import traceback

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
# Add the directory containing skills/adk_agent to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


try:
    from skills.adk_agent.config import AgentConfig
    config = AgentConfig()
    
    skill_id = "bash"
    tools_path = os.path.join(config.skills_path, skill_id, "tools.py")
    
    print(f"Target tools path: {tools_path}")
    
    spec = importlib.util.spec_from_file_location(f"skills.{skill_id}", tools_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print("Module loaded successfully.")
    
    if hasattr(module, 'get_tools'):
        print("get_tools function found.")
        
        # Simulate call with arguments as main_web_start_steering.py does
        common_args = (None, None, {
            "app_name": "test",
            "user_id": "test",
            "session_id": "test"
        })

        try:
            print("Attempting to call get_tools with args...")
            # Simulate except block behavior
            try:
                module.get_tools(*common_args, status_reporter=None)
            except TypeError as e:
                print(f"Caught first TypeError: {e}")
                module.get_tools(*common_args)
                
            print("Successfully called get_tools.")
        except TypeError as e:
            print(f"TypeError caught during retry: {e}")
            print("Confirmed failure: get_tools() does not accept arguments.")
        except Exception as e:
            print(f"Other error caught: {e}")
            
    else:
        print("ERROR: get_tools function NOT found in module.")

except Exception as e:
    print(f"General Error: {e}")
    traceback.print_exc()

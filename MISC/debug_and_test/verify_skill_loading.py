
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
# Add the directory containing skills/adk_agent to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


print(f"Current working directory: {os.getcwd()}")
print(f"sys.path: {sys.path}")
try:
    print(f"Contents of project root: {os.listdir(sys.path[0])}")
except Exception as e:
    print(f"Error listing root: {e}")

try:
    from src.adk_agent.core.manager import SkillManager
    from src.adk_agent.config import AgentConfig
    
    config = AgentConfig()
    print(f"Skills path: {config.skills_path}")
    
    sm = SkillManager(base_path=config.skills_path)
    
    # Get all subdirectories in skills_path
    if not os.path.exists(config.skills_path):
        print(f"ERROR: Skills path does not exist: {config.skills_path}")
    else:
        skill_dirs = [d for d in os.listdir(config.skills_path) 
                      if os.path.isdir(os.path.join(config.skills_path, d)) 
                      and not d.startswith("__") and not d.startswith(".")]
        
        print(f"Found {len(skill_dirs)} potential skills: {skill_dirs}")
        
        success_count = 0
        fail_count = 0
        
        for skill_id in skill_dirs:
            print(f"\n--- Checking skill: {skill_id} ---")
            if sm.skill_exists(skill_id):
                try:
                    body = sm.load_full_sop(skill_id)
                    if body and body != "无法加载技能详情。":
                        # Check if tools.py exists and can be loaded (optional, but good for completeness)
                        tools_path = os.path.join(config.skills_path, skill_id, "tools.py")
                        tools_status = "No tools.py"
                        if os.path.exists(tools_path):
                            tools_status = "tools.py exists"
                            
                        print(f"  [PASS] SOP Loaded. ({len(body)} chars). {tools_status}")
                        success_count += 1
                    else:
                        print(f"  [FAIL] SOP Load Failed (Empty or Error Message).")
                        fail_count += 1
                except Exception as e:
                    print(f"  [FAIL] Exception loading SOP: {e}")
                    fail_count += 1
            else:
                print(f"  [FAIL] SkillManager.skill_exists() returned False.")
                fail_count += 1
        
        print(f"\nSummary: {success_count} Passed, {fail_count} Failed.")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

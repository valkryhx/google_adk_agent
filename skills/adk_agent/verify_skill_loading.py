
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
# Add the directory containing skills/adk_agent to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


try:
    from skills.adk_agent.core.manager import SkillManager
    from skills.adk_agent.config import AgentConfig
    
    config = AgentConfig()
    print(f"Skills path: {config.skills_path}")
    
    sm = SkillManager(base_path=config.skills_path)
    
    print(f"Checking bash skill...")
    if sm.skill_exists("bash"):
        print("Bash skill exists.")
        body = sm.load_full_sop("bash")
        if body and body != "无法加载技能详情。":
            print("Successfully loaded bash instructions!")
            print(f"Body preview: {body[:100]}...")
        else:
            print("Failed to load bash instructions.")
    else:
        print("Bash skill not found.")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

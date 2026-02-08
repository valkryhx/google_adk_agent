import sys
import os
import platform

# Add src to path
current_dir = os.path.dirname(os.path.abspath(__file__))
# MISC/debug_and_test/../../src -> src
src_path = os.path.abspath(os.path.join(current_dir, "..", "..", "src"))
sys.path.append(src_path)

try:
    from adk_agent.config import AgentConfig, build_system_prompt
except ImportError as e:
    print(f"ImportError: {e}")
    print(f"sys.path: {sys.path}")
    sys.exit(1)

def test_prompt_injection():
    print(f"Testing on {platform.system()}...")
    
    # Mock yaml config if needed, but AgentConfig has defaults
    config = AgentConfig()
    prompt = build_system_prompt(config, "SKILL MANIFEST PLACEHOLDER")
    
    print("\n--- Generated Prompt Hint ---\n")
    if "## 🖥️ 系统环境感知 (OS Context)" in prompt:
        print("✅ OS Context section found.")
        
        # Extract the section
        start = prompt.find("## 🖥️ 系统环境感知 (OS Context)")
        end = prompt.find("## 运行环境", start)
        context_content = prompt[start:end]
        print(f"Context Content:\n{context_content}")
        
        if platform.system() == "Windows":
            if "当前环境为 Windows" in context_content:
                print("✅ Correct Windows context detected.")
            else:
                print("❌ Windows context missing or incorrect.")
        elif platform.system() in ["Linux", "Darwin"]:
            if "Unix-like" in context_content:
                print("✅ Correct Unix-like context detected.")
            else:
                print("❌ Unix-like context missing or incorrect.")
    else:
        print("❌ OS Context section NOT found.")

if __name__ == "__main__":
    test_prompt_injection()

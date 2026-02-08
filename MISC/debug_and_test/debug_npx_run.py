import subprocess
import shutil
import os
import sys
import time

# Env setup
env_vars = {
    "PLAYWRIGHT_MCP_EXTENSION_TOKEN": "toekn_of_your_playwrite_extension_in_chrome"
}
final_env = os.environ.copy()
final_env.update(env_vars)

npx_path = shutil.which("npx")
print(f"Resolved npx: {npx_path}")

def run_test(name, cmd_list, wait_time=5):
    print(f"\n=== Test: {name} ===")
    print(f"Command: {cmd_list}")
    try:
        proc = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            env=final_env,
            text=True
        )
        print(f"Started PID: {proc.pid}")
        
        try:
            out, err = proc.communicate(timeout=wait_time)
            print(f"Exited with code: {proc.returncode}")
            print(f"STDOUT: {out.strip()[:500]}") # Truncate
            print(f"STDERR: {err.strip()[:500]}")
        except subprocess.TimeoutExpired:
            print("TIMEOUT (Process is running!)")
            proc.kill()
            out, err = proc.communicate()
            print(f"Captured Output: {out.strip()[:200]}... / {err.strip()[:200]}...")
            
    except Exception as e:
        print(f"Failed to run: {e}")

# 1. Base check
run_test("npx --version (Shell=False, FullPath)", [npx_path, "--version"], wait_time=2)

# 2. cmd /c approach (Simulate Shell=True behavior)
run_test("cmd /c npx ... --extension", ["cmd", "/c", "npx", "-y", "@playwright/mcp@latest", "--extension"], wait_time=5)

# 3. Direct approach without --extension
run_test("npx ... (No Extension)", [npx_path, "-y", "@playwright/mcp@latest"], wait_time=5)

# 4. Help
run_test("npx ... --help", [npx_path, "-y", "@playwright/mcp@latest", "--help"], wait_time=5)

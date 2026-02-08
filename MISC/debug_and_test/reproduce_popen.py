import subprocess
import shutil
import os

print("--- Test 1: npx directly ---")
try:
    # On Windows, shell=False by default for Popen
    proc = subprocess.Popen(["npx", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    print(f"Success. Exit code: {proc.returncode}")
    print(f"Out: {out.strip()}")
    print(f"Err: {err.strip()}")
except Exception as e:
    print(f"Failed: {e}")

print("\n--- Test 2: Full path ---")
try:
    cmd = shutil.which("npx")
    if cmd:
        print(f"Using path: {cmd}")
        proc = subprocess.Popen([cmd, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = proc.communicate()
        print(f"Success. Exit code: {proc.returncode}")
        print(f"Out: {out.strip()}")
        print(f"Err: {err.strip()}")
    else:
        print("Could not find npx via shutil.which")
except Exception as e:
    print(f"Failed: {e}")

print("\n--- Test 3: cmd /c npx ---")
try:
    # This is what the user said works (in terminal), simulating it via Popen
    proc = subprocess.Popen(["cmd", "/c", "npx", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    print(f"Success. Exit code: {proc.returncode}")
    print(f"Out: {out.strip()}")
    print(f"Err: {err.strip()}")
except Exception as e:
    print(f"Failed: {e}")

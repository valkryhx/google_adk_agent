
import sys
# 将项目根目录添加到路径 (3层目录向上)
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from google.adk.agents import RunConfig
import inspect

try:
    print(inspect.signature(RunConfig))
except Exception as e:
    print(f"Error: {e}")


import sys
# 将项目根目录添加到路径 (3层目录向上)
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from google.adk.agents.run_config import StreamingMode

for member in StreamingMode:
    print(f"{member.name}: {member.value}")

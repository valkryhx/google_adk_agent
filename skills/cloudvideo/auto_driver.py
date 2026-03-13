import sys
import time
import os
import win32clipboard
import subprocess
import uuid

# 强制 UTF-8
if sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH = os.path.join(CURRENT_DIR, "cloudvideo_ultimate_agent_v10.py")
# 待分析队列文件
PENDING_FILE = os.path.join(CURRENT_DIR, "pending_analysis.txt")

def get_clipboard_text():
    try:
        win32clipboard.OpenClipboard()
        data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return data
    except: return None

def start_smart_driver():
    print("=" * 70)
    print("🚀 移动会议 - AI 智能驾驶模式 [V11.0] 已启动")
    print("=" * 70)
    print("逻辑：")
    print("1. 您在会议中复制一段消息。")
    print("2. 脚本捕获并将其标记为【待分析】。")
    print("3. Agent (Gemini CLI) 将自动读取并判断是否需要回复。")
    print("-" * 70)

    last_content = get_clipboard_text()
    
    try:
        while True:
            current_content = get_clipboard_text()
            if current_content and current_content != last_content:
                # 过滤掉太短的内容（通常不是问题）
                if len(current_content.strip()) > 5:
                    print(f"\n[📡 捕获新线索] 内容: {current_content[:50]}...")
                    # 写入待分析文件，通知 Agent
                    with open(PENDING_FILE, 'w', encoding='utf-8') as f:
                        f.write(current_content)
                    print(">>> 已同步至 Agent 决策中心，等待分析...")
                
                last_content = current_content
                time.sleep(2.0)
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[🛑] 智能驾驶已关闭。")

if __name__ == "__main__":
    start_smart_driver()

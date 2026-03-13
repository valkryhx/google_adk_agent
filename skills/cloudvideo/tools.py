import os
import subprocess
import sys
import uuid
import win32clipboard
from typing import List

# ==========================================
# 1. 路径配置
# ==========================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH = os.path.join(CURRENT_DIR, "cloudvideo_ultimate_agent_v10.py")
DRIVER_PATH = os.path.join(CURRENT_DIR, "auto_driver.py")

def get_current_clipboard() -> str:
    """读取当前系统剪切板中的文本"""
    try:
        win32clipboard.OpenClipboard()
        data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return data
    except Exception as e:
        return ""

def start_auto_delivery_service() -> str:
    """
    【V10.5 核心工具】: 启动剪切板自动驾驶服务 (后台运行)。

    【功能描述】:
    启动后，Agent 将实时监控系统剪切板。用户只要执行 Ctrl+C (复制)，
    新内容就会被自动投送到当前会议聊天框中，实现 0 点击投送。
    """
    try:
        # 使用 Popen 后台启动监听进程
        subprocess.Popen([sys.executable, "-X", "utf8", DRIVER_PATH], creationflags=subprocess.CREATE_NEW_CONSOLE)
        return "🚀 剪切板【自动驾驶模式】已在独立窗口启动。现在您可以开始复制内容进行自动投送了。"
    except Exception as e:
        return f"❌ 启动自动驾驶服务失败: {e}"

def send_meeting_message(message: str, meeting_id: str = "370478229", password: str = "123456") -> str:
    """
    移动会议 (CloudVideo) 自动化消息投送工具 (并发安全版)。

    Args:
        message: 投送内容。传入 "[CLIPBOARD]" 则投送当前剪切板一次。
        meeting_id: 会议 ID。
        password: 会议密码。
    """
    # 逻辑处理略 (同 V10.4)
    is_from_clip = False
    if message == "[CLIPBOARD]":
        message = get_current_clipboard()
        is_from_clip = True
        if not message:
            return "❌ 剪切板中未发现文本内容。"

    payload_filename = f"payload_{uuid.uuid4().hex[:8]}.txt"
    payload_path = os.path.join(CURRENT_DIR, payload_filename)
    
    with open(payload_path, 'w', encoding='utf-8') as f:
        f.write(message)

    cmd = [sys.executable, "-X", "utf8", SCRIPT_PATH, meeting_id, password, payload_filename]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=45)
        status = "✅ 投送成功" if result.returncode == 0 else f"❌ 失败 (Code {result.returncode})"
        source_hint = " (来自系统剪切板)" if is_from_clip else ""
        return f"[cloudvideo_skill] 任务完毕{source_hint}\n{status}\n\n输出摘要:\n{result.stdout[-300:]}"
    except Exception as e:
        return f"❌ 发生错误: {e}"

def get_tools(*args, **kwargs) -> List:
    """ADK 标准工具导出接口"""
    return [send_meeting_message, start_auto_delivery_service]

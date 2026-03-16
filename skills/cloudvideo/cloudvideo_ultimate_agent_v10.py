import sys
import time
import os
import win32api
import win32con
import win32gui
import win32clipboard
from pywinauto import Desktop, Application
from pywinauto.keyboard import send_keys

# 强制 UTF-8 编码
if sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

def set_clipboard(text):
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
    except: pass

def smart_delivery_v15(message):
    """
    智能投送引擎 V15: 全场景自适应 (独立窗/标准窗/气泡窗)
    """
    print(f">>> 启动智能投送引擎 V15 | 消息长度: {len(message)}")
    orig_pos = win32api.GetCursorPos()
    orig_hwnd = win32gui.GetForegroundWindow()
    
    # 1. 探测独立聊天窗 (最优先)
    hwnd_standalone = win32gui.FindWindow("Conf Chat", "ChatWnd")
    # 2. 探测标准会议窗
    hwnd_standard = win32gui.FindWindow("FrameWorkWnd", None)
    # 3. 探测气泡窗 (共享屏幕)
    hwnd_bubble = win32gui.FindWindow("AwarenessDlg", None)

    if hwnd_standalone and win32gui.IsWindowVisible(hwnd_standalone):
        print("✅ 检测到独立聊天窗口 (Conf Chat)。")
        deliver_standalone(hwnd_standalone, message)
    elif hwnd_standard and win32gui.IsWindowVisible(hwnd_standard):
        print("✅ 检测到标准会议窗口 (FrameWorkWnd)。")
        deliver_standard(hwnd_standard, message)
    elif hwnd_bubble and win32gui.IsWindowVisible(hwnd_bubble):
        print("✅ 检测到共享屏幕气泡窗 (AwarenessDlg)。")
        deliver_bubble_v6_fixed(hwnd_bubble, message)
    else:
        print("❌ 未发现任何有效的会议聊天入口。")
        return

    # 还原现场
    print("🔄 正在还原鼠标与焦点...")
    win32api.SetCursorPos(orig_pos)
    if orig_hwnd and win32gui.IsWindow(orig_hwnd):
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
            win32gui.SetForegroundWindow(orig_hwnd)
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
        except: pass

def deliver_standalone(hwnd, message):
    """独立窗投送"""
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    rect = win32gui.GetWindowRect(hwnd)
    # 点击底部激活输入
    in_x = (rect[0] + rect[2]) // 2
    in_y = rect[3] - 50
    win32api.SetCursorPos((in_x, in_y))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.2)
    # 投送
    set_clipboard(message)
    send_keys("^a{BACKSPACE}^v{ENTER}")
    print("✅ 独立窗投送成功。")

def deliver_standard(hwnd, message):
    """标准窗投送"""
    desktop = Desktop(backend="uia")
    meeting_win = desktop.window(handle=hwnd)
    chat_panel = next((c for c in meeting_win.descendants(control_type="Pane") if c.window_text() == "ChatWnd"), None)
    if not chat_panel:
        r = meeting_win.rectangle()
        meeting_win.click_input(coords=(int(r.width() * 0.58), r.height() - 40))
        time.sleep(1.2)
        chat_panel = next((c for c in meeting_win.descendants(control_type="Pane") if c.window_text() == "ChatWnd"), None)
    
    if chat_panel:
        pr = chat_panel.rectangle()
        mr = meeting_win.rectangle()
        tx, ty = (pr.left + pr.right) // 2 - mr.left, pr.bottom - 50 - mr.top
        meeting_win.click_input(coords=(tx, ty), double=True)
        time.sleep(0.2)
        set_clipboard(message)
        send_keys("^a{BACKSPACE}^v{ENTER}~^{ENTER}")
        print("✅ 标准窗投送成功。")

def deliver_bubble_v6_fixed(hwnd, message):
    """气泡窗 V6 成功逻辑"""
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    rect = win32gui.GetWindowRect(hwnd)
    l, t, r, b = rect
    w, h = r - l, b - t
    cy = t + h // 2
    # 多点触控展开
    for ratio in [0.1, 0.25]:
        win32api.SetCursorPos((l + int(w * ratio), cy))
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.1)
    time.sleep(1.5)
    # 输入并发送
    win32api.SetCursorPos((l + int(w * 0.7), cy))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.2)
    set_clipboard(message)
    send_keys("^a{BACKSPACE}^v{ENTER}")
    print("✅ 气泡窗投送成功。")

if __name__ == "__main__":
    payload_file = sys.argv[3] if len(sys.argv) > 3 else "meeting_payload.txt"
    payload_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), payload_file)
    if os.path.exists(payload_path):
        with open(payload_path, 'r', encoding='utf-8') as f:
            msg = f.read().strip()
        if msg:
            smart_delivery_v15(msg)
            try: os.remove(payload_path)
            except: pass

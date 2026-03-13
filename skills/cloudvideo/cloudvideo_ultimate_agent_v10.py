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

def v9_core_delivery_with_focus_restore(message):
    print(">>> 模式：【多租户并发安全版】")
    orig_pos = win32api.GetCursorPos()
    orig_hwnd = win32gui.GetForegroundWindow()
    
    desktop = Desktop(backend="uia")
    meeting_win = next((w for w in desktop.windows(visible_only=True) if w.class_name() == "FrameWorkWnd"), None)
    if not meeting_win:
        print("❌ 未发现运行中的会议窗口 (FrameWorkWnd)。")
        return

    chat_panel = next((c for c in meeting_win.descendants(control_type="Pane") if c.window_text() == "ChatWnd"), None)
    if not chat_panel:
        r = meeting_win.rectangle()
        w, h = r.width(), r.height()
        meeting_win.click_input(coords=(int(w * 0.58), h - 40))
        time.sleep(1.2)
        chat_panel = next((c for c in meeting_win.descendants(control_type="Pane") if c.window_text() == "ChatWnd"), None)

    if chat_panel:
        print("✅ 锁定 ChatWnd。正在注入...")
        pr = chat_panel.rectangle()
        mr = meeting_win.rectangle()
        tx, ty = (pr.left + pr.right) // 2 - mr.left, pr.bottom - 50 - mr.top
        meeting_win.click_input(coords=(tx, ty), double=True)
        time.sleep(0.2)
        set_clipboard(message)
        send_keys("^a{BACKSPACE}^v")
        time.sleep(0.5) 
        send_keys("{ENTER}~^{ENTER}")
        print("✅ 投送完成！")
    else:
        print("❌ 无法定位聊天面板。")

    print("🔄 正在还原焦点与鼠标位置...")
    win32api.SetCursorPos(orig_pos)
    if orig_hwnd and win32gui.IsWindow(orig_hwnd):
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0) # Alt down
            win32gui.SetForegroundWindow(orig_hwnd)
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0) # Alt up
        except: pass

if __name__ == "__main__":
    m_id = sys.argv[1] if len(sys.argv) > 1 else "370478229"
    m_pwd = sys.argv[2] if len(sys.argv) > 2 else "123456"
    # 核心改动：支持从指定文件读取
    payload_file = sys.argv[3] if len(sys.argv) > 3 else "meeting_payload.txt"
    payload_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), payload_file)

    if os.path.exists(payload_path):
        with open(payload_path, 'r', encoding='utf-8') as f:
            msg = f.read().strip()
        
        if msg:
            print("=" * 60)
            print(f"🚀 会议投送工具启动 | 文件: {payload_file} | 长度: {len(msg)}")
            print("=" * 60)
            v9_core_delivery_with_focus_restore(msg)
            
            # 【核心安全】投送完立即物理删除
            try:
                os.remove(payload_path)
                print(f"🗑️ 临时 Payload 已销毁: {payload_file}")
            except: pass
        else:
            print("⚠️ 负载为空，跳过。")
    else:
        print(f"❌ 找不到 Payload 文件: {payload_file}")

import pywinauto
from pywinauto import Desktop
import sys
import os
import win32gui
import win32process

# 强制 UTF-8
if sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

def capture_all_cloudvideo_windows():
    print(">>> 正在对 CloudVideo 进程进行地毯式窗口搜索...")
    
    output_dir = "skills/cloudvideo/screenshots"
    os.makedirs(output_dir, exist_ok=True)
    
    # 查找进程名为 CloudVideo.exe 的 PID
    import psutil
    target_pids = [p.info['pid'] for p in psutil.process_iter(['name', 'pid']) if 'cloudvideo' in p.info['name'].lower()]
    
    if not target_pids:
        print("❌ 未发现 CloudVideo.exe 进程。")
        return

    print(f"[*] 锁定 PID: {target_pids}")
    
    all_hwnds = []
    def enum_cb(hwnd, _):
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid in target_pids:
            all_hwnds.append(hwnd)
    
    win32gui.EnumWindows(enum_cb, None)
    
    count = 0
    for hwnd in all_hwnds:
        try:
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            
            # 过滤掉尺寸过小的窗口（可能是系统组件）
            if w < 10 or h < 10:
                continue
                
            count += 1
            safe_title = "".join([c for c in title if c.isalnum()]).rstrip() or "NoTitle"
            filename = f"ALL_{cls}_{safe_title}_{hwnd}_{count}.png"
            filepath = os.path.join(output_dir, filename)
            
            print(f"[*] 捕捉到窗口: Hwnd={hex(hwnd)} | Class={cls} | Title={title} | Rect={rect} -> {filename}")
            
            # 使用 win32 接口尝试截图，如果 pywinauto 失败则跳过
            try:
                app = pywinauto.Application(backend="win32").connect(handle=hwnd)
                img = app.window(handle=hwnd).capture_as_image()
                img.save(filepath)
            except:
                # 尝试 UIA 后端作为备选
                try:
                    app = pywinauto.Application(backend="uia").connect(handle=hwnd)
                    img = app.window(handle=hwnd).capture_as_image()
                    img.save(filepath)
                except:
                    print(f"  [!] 无法对窗口 {hex(hwnd)} 进行截图")
            
        except Exception as e:
            continue
            
    print(f"\n>>> 扫描完成，共尝试捕捉 {count} 个窗口。")

if __name__ == "__main__":
    capture_all_cloudvideo_windows()

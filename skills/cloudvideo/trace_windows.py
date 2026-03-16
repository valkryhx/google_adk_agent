import pywinauto
from pywinauto import Desktop
import json
import sys
import win32gui

# 强制 UTF-8 输出
if sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

def get_all_windows_win32():
    results = []
    def callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            results.append({
                "handle": hex(hwnd),
                "class": cls,
                "title": title,
                "engine": "win32"
            })
    win32gui.EnumWindows(callback, None)
    return results

def trace_windows():
    print(">>> 正在扫描系统窗口 (Win32 + UIA)...")
    
    # 1. Win32 扫描
    results = get_all_windows_win32()
    
    # 2. UIA 扫描 (尝试不带 visible_only)
    try:
        desktop = Desktop(backend="uia")
        uia_windows = desktop.windows()
        for w in uia_windows:
            try:
                results.append({
                    "class": w.class_name(),
                    "title": w.window_text(),
                    "control_type": w.control_type(),
                    "engine": "uia"
                })
            except: continue
    except Exception as e:
        print(f"UIA 扫描失败: {e}")

    # 过滤掉完全没信息的
    final_results = [r for r in results if r["title"] or r["class"]]

    output_path = "skills/cloudvideo/window_trace.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)
    
    # 实时打印疑似目标
    print("\n--- 疑似 CloudVideo 相关窗口 ---")
    for r in final_results:
        t = r["title"].lower()
        c = r["class"].lower()
        if "cloudvideo" in t or "会议" in t or "chat" in c or "bubble" in c or "float" in c:
            print(f"[{r['engine'].upper()}] Class: {r['class']} | Title: {r['title']}")

if __name__ == "__main__":
    trace_windows()

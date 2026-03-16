import pywinauto
from pywinauto import Desktop
import sys

# 强制 UTF-8
if sys.stdout.encoding != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

def dump_node(node, depth=0):
    indent = "  " * depth
    try:
        title = node.window_text()
        cls = node.class_name()
        ctype = node.control_type()
        print(f"{indent}[{ctype}] Title: '{title}' | Class: {cls}")
        
        for child in node.children():
            dump_node(child, depth + 1)
    except:
        pass

def inspect_awareness_dlg():
    print(">>> 正在深入分析 AwarenessDlg 窗口结构...")
    desktop = Desktop(backend="uia")
    try:
        # 获取窗口包装器
        target_win = next((w for w in desktop.windows() if w.class_name() == "AwarenessDlg"), None)
        
        if not target_win:
            # 尝试 win32 后端
            print("uia 未发现，尝试 win32 查找...")
            from pywinauto import Application
            app = Application(backend="win32").connect(class_name="AwarenessDlg")
            target_win = app.window(class_name="AwarenessDlg")

        if not target_win:
            print("❌ 未发现 AwarenessDlg 窗口。")
            return

        print(f"✅ 锁定窗口: {target_win.window_text()} | Class: AwarenessDlg")
        print("-" * 60)
        
        # 尝试使用 pywinauto 的 print_control_identifiers (修正之前的错误)
        try:
            target_win.print_control_identifiers()
        except:
            dump_node(target_win)
        
    except Exception as e:
        print(f"探测失败: {e}")

if __name__ == "__main__":
    inspect_awareness_dlg()

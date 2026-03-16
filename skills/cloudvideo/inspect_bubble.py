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

def inspect_bubble():
    print(">>> 正在深入分析 DVSmallContainerListWnd 窗口结构 (Manual Dump)...")
    desktop = Desktop(backend="uia")
    try:
        # 获取窗口包装器
        bubble_win = next((w for w in desktop.windows() if w.class_name() == "DVSmallContainerListWnd"), None)
        
        if not bubble_win:
            print("❌ 未发现 DVSmallContainerListWnd 窗口。")
            return

        print(f"✅ 锁定窗口: {bubble_win.window_text()}")
        print("-" * 60)
        
        dump_node(bubble_win)
        
    except Exception as e:
        print(f"探测失败: {e}")

if __name__ == "__main__":
    inspect_bubble()

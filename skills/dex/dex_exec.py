
import sys
import os
import subprocess
import time
import platform
from datetime import datetime
# Update: DexManager moved to tools.py to solve import issues
try:
    from tools import DexManager
except ImportError:
    # Fallback if tools.py is not found immediately (e.g. not in path)
    # Add current dir to path
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from tools import DexManager

def main():
    if len(sys.argv) < 3:
        # Expected: python dex_exec.py <TASK_ID> <USER_ID> <CMD_PART_1> ...
        # (old version was <TASK_ID> <CMD>...)
        print("Usage: python dex_exec.py <TASK_ID> <USER_ID> <COMMAND...>")
        sys.exit(1)
        
    task_id = sys.argv[1]
    user_id_arg = sys.argv[2]
    
    user_id = None
    if user_id_arg and user_id_arg != "__NO_USER__":
        user_id = user_id_arg
        
    command_parts = sys.argv[3:]
    
    # 1. 准备环境 (带 user_id)
    dex = DexManager(user_id=user_id) 
    
    # 日志文件位置
    # 在 Windows 上，通常用 TEMP；Linux 用 /tmp
    # 或者直接放在 .dex/logs/ 下更好管理
    
    # 注意：DexManager现在可能指向 .dex/tasks/<user_id>/
    # 我们希望 log 也隔离吗？暂时保持全局 logs 或者 ../../logs
    # .dex (root) is 2 levels up if user_id is present
    
    # Calculate log directory based on user_id to ensure isolation
    if user_id:
        # Structure: .dex/logs/<user_id>/
        # dex.dex_dir is .dex/tasks/<user_id>/
        # So we go up 3 levels (.dex/tasks/<user>/ -> .dex/tasks/ -> .dex/) 
        # Actually easier to rebuild based on dex.base_dir logic but dex object encapsulates it.
        # Let's derive it from dex.dex_dir structure.
        
        # dex.dex_dir = base/.dex/tasks/user_id
        tasks_dir = os.path.dirname(dex.dex_dir) # base/.dex/tasks
        dex_base = os.path.dirname(tasks_dir)    # base/.dex
        log_dir = os.path.join(dex_base, "logs", user_id)
    else:
        # dex.dex_dir = base/.dex/tasks
        dex_base = os.path.dirname(dex.dex_dir)
        log_dir = os.path.join(dex_base, "logs", "global") # Use 'global' subdir for cleaner structure
    
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except:
            pass # 如果无法创建日志目录，就无法记录日志
            
    log_file = os.path.join(log_dir, f"{task_id}.log")
    
    # 开始记录
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(f"=== dex task started at {datetime.now().isoformat()} ===\n")
        f.write(f"Task ID: {task_id}\n")
        f.write(f"User ID: {user_id}\n")
        f.write(f"Command: {command_parts}\n")
        f.write("-" * 40 + "\n")
    
    # 2. 执行命令
    exit_code = -1
    output_summary = ""
    
    try:
        # 用 subprocess.run 执行，并重定向 stdout/stderr 到日志文件
        # 注意：这里是阻塞执行，因为本脚本本身已经是后台进程了
        with open(log_file, 'a', encoding='utf-8') as f_log:
            # 如果 command_parts 是列表，shell=False (更安全，但不支持管道)
            # 如果需要支持管道 (e.g. "echo hello | grep h"), 用户传入的通常应该是一个字符串
            # 但我们的 dex.py 传递的是 list.
            # 策略：如果只有一个参数且包含空格/管道符，可能需要 shell=True
            # 简单起见，这里直接执行 list 形式 (不支持管道)，或者拼接成字符串用 shell=True (支持管道)
            
            # 为了最大兼容性，我们尝试拼接命令字符串并用 shell=True
            # 这样用户可以用 "python a.py > out.txt" 这种写法
            full_cmd_str = subprocess.list2cmdline(command_parts)
            
            # 再次记录实际执行的命令串
            f_log.write(f"Executing: {full_cmd_str}\n\n")
            f_log.flush()
            
            # Prepare environment with UTF-8 enforcement to prevent garbled logs on Windows
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"

            proc = subprocess.run(
                full_cmd_str,
                shell=True,
                stdout=f_log,
                stderr=subprocess.STDOUT,
                env=env
            )
            exit_code = proc.returncode
            
        # 读取最后 N 行作为摘要
        try:
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f_read:
                lines = f_read.readlines()
                tail_lines = lines[-20:] if len(lines) > 20 else lines
                output_summary = "".join(tail_lines).strip()
        except:
            output_summary = "(Unable to read log file)"

    except Exception as e:
        exit_code = 999
        output_summary = f"Execution Exception: {str(e)}"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{output_summary}\n")

    # 3. 更新 Dex 状态 (Complete)
    status_msg = "SUCCESS" if exit_code == 0 else f"FAILED (Code {exit_code})"
    final_result_text = f"[{status_msg}]\nLog: {log_file}\nOutput Tail:\n{output_summary}"
    
    try:
        dex.complete_task(task_id, final_result_text)
        
        # 4. (可选) 桌面通知
        pass 
            
    except Exception as e:
        # 如果连更新状态都失败了... 真的没办法了
        msg = f"\nFATAL: Failed to update dex status: {e}\nDex Dir: {dex.dex_dir}\n"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(msg)
            print(msg) # print to stderr (captured mainly by OS if detached)

if __name__ == "__main__":
    main()

import os
import subprocess
import sys
from datetime import datetime

try:
    from tools import DexManager
    from summary import summarize_output
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from tools import DexManager
    from summary import summarize_output


def main():
    if len(sys.argv) < 3:
        print("Usage: python dex_exec.py <TASK_ID> <USER_ID> <COMMAND...>")
        sys.exit(1)

    task_id = sys.argv[1]
    user_id_arg = sys.argv[2]
    user_id = user_id_arg if user_id_arg and user_id_arg != "__NO_USER__" else None
    command_parts = sys.argv[3:]

    dex = DexManager(user_id=user_id, allow_global=(user_id is None))
    store = dex.store
    store._ensure_dirs()
    log_file = store.log_path(task_id)

    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"=== dex task started at {datetime.now().isoformat()} ===\n")
        f.write(f"Task ID: {task_id}\n")
        f.write(f"User ID: {user_id}\n")
        f.write(f"Command: {command_parts}\n")
        f.write("-" * 40 + "\n")

    try:
        store.mark_running(task_id, command=list(command_parts), pid=os.getpid())
    except Exception:
        pass

    exit_code = -1
    output_text = ""

    try:
        with open(log_file, "a", encoding="utf-8") as f_log:
            full_cmd_str = subprocess.list2cmdline(command_parts)
            f_log.write(f"Executing: {full_cmd_str}\n\n")
            f_log.flush()

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"

            use_shell = len(command_parts) == 1 and any(
                token in command_parts[0] for token in ("|", ">", "<", "&&", "||")
            )
            cmd_to_run = command_parts[0] if use_shell else command_parts

            proc = subprocess.run(
                cmd_to_run,
                shell=use_shell,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )
            exit_code = proc.returncode
            output_bytes = proc.stdout or b""
            for enc in ("utf-8", "gbk"):
                try:
                    output_text = output_bytes.decode(enc)
                    break
                except Exception:
                    output_text = output_bytes.decode("utf-8", errors="replace")
            f_log.write(output_text)
            f_log.flush()
    except Exception as e:
        exit_code = 999
        output_text = f"Execution Exception: {str(e)}"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n{output_text}\n")

    summary = summarize_output(exit_code, output_text)

    try:
        store.mark_finished(
            task_id,
            status=summary["status"],
            exit_code=exit_code,
            result_summary=summary["result_summary"],
            error_summary=summary["error_summary"],
        )
    except Exception as e:
        msg = f"\nFATAL: Failed to update dex status: {e}\nDex Dir: {dex.dex_dir}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(msg)
            print(msg)


if __name__ == "__main__":
    main()

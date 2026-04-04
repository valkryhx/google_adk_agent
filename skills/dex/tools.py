import json
import os
import shlex
import subprocess
import sys
from typing import Any, Dict, List

try:
    from .models import DexTask, DexTaskStatus
    from .store import DexStore
except ImportError:  # pragma: no cover - script import fallback
    from models import DexTask, DexTaskStatus
    from store import DexStore


def _strip_matching_outer_quotes(value: str) -> str:
    normalized = value.strip()
    while len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in ('"', "'"):
        normalized = normalized[1:-1].strip()
    return normalized


def _normalize_command_args(command: str) -> list[str]:
    is_posix = sys.platform != "win32"
    args_list = shlex.split(command, posix=is_posix)

    if len(args_list) >= 3 and args_list[0].lower() == "python" and args_list[1] == "-c":
        code_arg = " ".join(args_list[2:]).strip()
        code_arg = _strip_matching_outer_quotes(code_arg)
        args_list = [args_list[0], args_list[1], code_arg]

    return args_list


class DexManager:
    def __init__(self, base_dir=None, user_id=None, allow_global=False):
        self.base_dir = base_dir if base_dir else os.getcwd()
        self.user_id = user_id
        self.allow_global = allow_global
        if not self.user_id and not self.allow_global:
            raise ValueError(
                "DexManager requires user_id unless allow_global=True is passed explicitly."
            )
        self.store = DexStore(base_dir=self.base_dir, user_id=self.user_id)
        self.dex_dir = str(self.store.tasks_dir())

    def create_task(self, description, context=""):
        return self.store.create_task(description, context).to_dict()

    def load_task(self, task_id):
        return self.store.load_task(task_id).to_dict()

    def save_task(self, task):
        if isinstance(task, dict):
            task = DexTask.from_dict(task)
        self.store.save_task(task)

    def list_tasks(self, show_all=False):
        return [task.to_dict() for task in self.store.list_tasks(show_all=show_all)]

    def complete_task(self, task_id, result):
        return self.store.mark_finished(
            task_id,
            status=DexTaskStatus.COMPLETED,
            exit_code=0,
            result_summary=result,
            error_summary=None,
        ).to_dict()

    def update_context(self, task_id, context):
        return self.store.update_context(task_id, context).to_dict()

    def delete_task(self, task_id):
        return self.store.delete_task(task_id)

    def start_background_process(self, task_id, command_parts):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        dex_exec_path = os.path.join(current_dir, "dex_exec.py")

        user_id_arg = str(self.user_id) if self.user_id else "__NO_USER__"
        cmd_args = [sys.executable, dex_exec_path, task_id, user_id_arg] + command_parts

        if sys.platform == "win32":
            detached_process = 0x00000008
            create_no_window = 0x08000000
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            proc = subprocess.Popen(
                cmd_args,
                creationflags=detached_process | create_no_window,
                close_fds=True,
                cwd=self.base_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
        else:
            proc = subprocess.Popen(
                cmd_args,
                start_new_session=True,
                cwd=self.base_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        self.store.mark_running(task_id, command=list(command_parts), pid=proc.pid)


def get_tools(agent=None, session_service=None, app_info: Dict = None) -> List[Any]:
    user_id = app_info.get("user_id") if app_info else None

    def dex_create_task(description: str, context: str = "") -> str:
        dex = DexManager(user_id=user_id)
        try:
            task = dex.create_task(description, context)
            return json.dumps(task, indent=2, ensure_ascii=False)
        except Exception as e:
            return f"[ERROR] Failed to create task: {str(e)}"

    def dex_start_task(task_id: str, command: str) -> str:
        dex = DexManager(user_id=user_id)
        try:
            args_list = _normalize_command_args(command)
            dex.start_background_process(task_id, args_list)
            task = dex.store.load_task(task_id)
            return json.dumps(task.to_dict(), indent=2, ensure_ascii=False)
        except Exception as e:
            return f"[ERROR] Failed to start task: {str(e)}"

    def dex_list_tasks(show_all: bool = False) -> str:
        dex = DexManager(user_id=user_id)
        try:
            tasks = dex.list_tasks(show_all)
            if not tasks:
                return "[]"
            return json.dumps(tasks, indent=2, ensure_ascii=False)
        except Exception as e:
            return f"[ERROR] {str(e)}"

    def dex_get_task_details(task_id: str) -> str:
        dex = DexManager(user_id=user_id)
        try:
            task = dex.load_task(task_id)
            return json.dumps(task, indent=2, ensure_ascii=False)
        except Exception as e:
            return f"[ERROR] {str(e)}"

    return [dex_create_task, dex_start_task, dex_list_tasks, dex_get_task_details]

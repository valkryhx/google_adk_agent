import os
import json
import sys
import shlex
import glob
import uuid
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Optional

# 配置存储路径
DEX_DIR_NAME = ".dex"
TASKS_DIR_NAME = "tasks"

class DexManager:
    def __init__(self, base_dir=None, user_id=None):
        self.base_dir = base_dir if base_dir else os.getcwd()
        self.user_id = user_id
        
        # 路径逻辑
        if self.user_id:
            cleaned_user_id = self._clean_path_segment(str(self.user_id))
            self.dex_dir = os.path.join(self.base_dir, DEX_DIR_NAME, TASKS_DIR_NAME, cleaned_user_id)
        else:
            self.dex_dir = os.path.join(self.base_dir, DEX_DIR_NAME, TASKS_DIR_NAME)

    def _clean_path_segment(self, segment):
        """简单的清理以防止路径穿越"""
        return "".join(c for c in segment if c.isalnum() or c in ('-', '_'))

    def _ensure_dex_dir(self):
        """确保存储目录存在"""
        if not os.path.exists(self.dex_dir):
            os.makedirs(self.dex_dir)

    def _get_task_path(self, task_id):
        """根据ID获取完整文件路径"""
        return os.path.join(self.dex_dir, f"{task_id}.json")

    def _generate_id(self):
        """生成短ID (8位)"""
        return str(uuid.uuid4())[:8]

    def create_task(self, description, context=""):
        """创建新任务"""
        self._ensure_dex_dir()
        task_id = self._generate_id()
        task = {
            "id": task_id,
            "user_id": self.user_id,
            "description": description,
            "context": context,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "result": ""
        }
        self.save_task(task)
        return task

    def load_task(self, task_id):
        """加载特定任务，支持模糊匹配前缀"""
        self._ensure_dex_dir()
        
        # 直接匹配
        path = self._get_task_path(task_id)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # 尝试匹配前缀
        files = glob.glob(os.path.join(self.dex_dir, f"{task_id}*.json"))
        if len(files) == 1:
            with open(files[0], 'r', encoding='utf-8') as f:
                return json.load(f)
        elif len(files) > 1:
            raise ValueError(f"Error: ID '{task_id}' is ambiguous, matches multiple tasks.")
        
        raise FileNotFoundError(f"Error: Task '{task_id}' not found.")

    def save_task(self, task):
        """保存任务到文件"""
        self._ensure_dex_dir()
        path = self._get_task_path(task['id'])
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(task, f, indent=2, ensure_ascii=False)

    def list_tasks(self, show_all=False):
        """列出任务"""
        if not os.path.exists(self.dex_dir):
            return []

        files = glob.glob(os.path.join(self.dex_dir, "*.json"))
        tasks = []
        for fpath in files:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    tasks.append(json.load(f))
            except:
                continue

        # 排序：未完成的在前
        tasks.sort(key=lambda x: (x.get('status') == 'completed', x.get('created_at')), reverse=False)
        
        if not show_all:
            tasks = [t for t in tasks if t.get('status') != 'completed']
            
        return tasks

    def complete_task(self, task_id, result):
        """完成任务"""
        task = self.load_task(task_id)
        task['status'] = 'completed'
        task['result'] = result
        task['completed_at'] = datetime.now().isoformat()
        self.save_task(task)
        return task

    def update_context(self, task_id, context):
        """更新任务上下文"""
        task = self.load_task(task_id)
        task['context'] = context
        self.save_task(task)
        return task

    def delete_task(self, task_id):
        """删除任务"""
        task = self.load_task(task_id)
        path = self._get_task_path(task['id'])
        os.remove(path)
        return True

    def start_background_process(self, task_id, command_parts):
        """启动后台进程（底层实现）"""
        # 获取 dex_exec.py 的路径 (同目录)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        dex_exec_path = os.path.join(current_dir, "dex_exec.py")
        
        user_id_arg = str(self.user_id) if self.user_id else "__NO_USER__"
        cmd_args = [sys.executable, dex_exec_path, task_id, user_id_arg] + command_parts
        
        if sys.platform == "win32":
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(
                cmd_args,
                creationflags=DETACHED_PROCESS,
                close_fds=True,
                cwd=self.base_dir
            )
        else:
            subprocess.Popen(
                cmd_args,
                start_new_session=True, # setsid
                cwd=self.base_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
        try:
            task = self.load_task(task_id)
            task['status'] = 'running'
            self.save_task(task)
        except Exception as e:
            print(f"Warning: Failed to update status: {e}")

def get_tools(agent=None, session_service=None, app_info: Dict = None) -> List[Any]:
    """
    动态生成绑定了用户上下文的工具函数。
    由 main_web_start_steering.py 自动调用。
    """
    user_id = app_info.get("user_id") if app_info else None
    
    # Define wrappers that capture user_id
    
    def dex_create_task(description: str, context: str = "") -> str:
        """
        创建一个新的异步长耗时任务。
        
        Args:
            description: 任务的一句话描述 (e.g. "训练 Llama3 模型")
            context: 任务的详细上下文、目标、完成标准等
            
        Returns:
            JSON 字符串，包含新创建的任务 ID 和详细信息
        """
        # 使用闭包捕获的 user_id 初始化 Manager
        dex = DexManager(user_id=user_id)
        try:
            task = dex.create_task(description, context)
            return json.dumps(task, indent=2, ensure_ascii=False)
        except Exception as e:
            return f"[ERROR] Failed to create task: {str(e)}"

    def dex_start_task(task_id: str, command: str) -> str:
        """
        启动一个已创建的任务（后台执行）。
        
        Args:
            task_id: 任务 ID
            command: 要在后台执行的完整命令字符串 (e.g. "python train.py --epochs 10")
            
        Returns:
            启动结果信息
        """
        dex = DexManager(user_id=user_id)
        try:
            # 使用 shlex.split 正确解析命令行字符串
            # posix=False 模式下，Windows 路径的反斜杠不会被当作转义符
            is_posix = sys.platform != 'win32'
            args_list = shlex.split(command, posix=is_posix)
            
            dex.start_background_process(task_id, args_list)
            return f"[OK] Task {task_id} started in background. Command: {command}"
        except Exception as e:
            return f"[ERROR] Failed to start task: {str(e)}"

    def dex_list_tasks(show_all: bool = False) -> str:
        """
        列出当前用户的所有任务。
        
        Args:
            show_all: 是否显示已完成的任务 (默认 False)
        """
        dex = DexManager(user_id=user_id)
        try:
            tasks = dex.list_tasks(show_all)
            if not tasks:
                return "[]"
            return json.dumps(tasks, indent=2, ensure_ascii=False)
        except Exception as e:
            return f"[ERROR] {str(e)}"

    def dex_get_task_details(task_id: str) -> str:
        """
        获取特定任务的详细信息，包括执行结果或最新的日志片段。
        
        Args:
            task_id: 任务 ID
        """
        dex = DexManager(user_id=user_id)
        try:
            task = dex.load_task(task_id)
            return json.dumps(task, indent=2, ensure_ascii=False)
        except Exception as e:
            return f"[ERROR] {str(e)}"
    
    # Return the bound functions
    return [dex_create_task, dex_start_task, dex_list_tasks, dex_get_task_details]

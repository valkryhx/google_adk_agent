from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

try:
    from .models import DexTask, DexTaskArtifact, DexTaskEvent, DexTaskStatus
except ImportError:  # pragma: no cover - script import fallback
    from models import DexTask, DexTaskArtifact, DexTaskEvent, DexTaskStatus


class DexStore:
    def __init__(self, base_dir, user_id=None):
        self.base_dir = Path(base_dir)
        self.user_id = user_id

    def _user_segment(self) -> str:
        if not self.user_id:
            return "global"
        cleaned = "".join(c for c in str(self.user_id) if c.isalnum() or c in ("-", "_"))
        return cleaned or "global"

    def tasks_dir(self) -> Path:
        return self.base_dir / ".dex" / "tasks" / self._user_segment()

    def logs_dir(self) -> Path:
        return self.base_dir / ".dex" / "logs" / self._user_segment()

    def task_path(self, task_id: str) -> Path:
        return self.tasks_dir() / f"{task_id}.json"

    def log_path(self, task_id: str) -> Path:
        return self.logs_dir() / f"{task_id}.log"

    def _ensure_dirs(self) -> None:
        self.tasks_dir().mkdir(parents=True, exist_ok=True)
        self.logs_dir().mkdir(parents=True, exist_ok=True)

    def _generate_id(self) -> str:
        return str(uuid.uuid4())[:8]

    def _resolve_task_path(self, task_id: str) -> Path:
        direct = self.task_path(task_id)
        if direct.exists():
            return direct
        matches = list(self.tasks_dir().glob(f"{task_id}*.json"))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"Error: ID '{task_id}' is ambiguous, matches multiple tasks.")
        raise FileNotFoundError(f"Error: Task '{task_id}' not found.")

    def save_task(self, task: DexTask) -> DexTask:
        self._ensure_dirs()
        self.task_path(task.id).write_text(
            json.dumps(task.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return task

    def load_task(self, task_id: str) -> DexTask:
        raw = json.loads(self._resolve_task_path(task_id).read_text(encoding="utf-8"))
        return DexTask.from_dict(raw)

    def create_task(self, description: str, context: str) -> DexTask:
        task = DexTask.new(self._generate_id(), self.user_id, description, context)
        task.artifacts.append(
            DexTaskArtifact(kind="log", path=str(self.log_path(task.id)), label="task log")
        )
        task.events.append(
            DexTaskEvent(kind="status", message="task created", ts=datetime.now(UTC).isoformat())
        )
        return self.save_task(task)

    def list_tasks(self, show_all: bool = False) -> list[DexTask]:
        if not self.tasks_dir().exists():
            return []
        tasks: list[DexTask] = []
        for path in self.tasks_dir().glob("*.json"):
            try:
                tasks.append(DexTask.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
        tasks.sort(key=lambda task: (task.status is DexTaskStatus.COMPLETED, task.created_at))
        if not show_all:
            tasks = [task for task in tasks if task.status is not DexTaskStatus.COMPLETED]
        return tasks

    def update_context(self, task_id: str, context: str) -> DexTask:
        task = self.load_task(task_id)
        task.context = context
        return self.save_task(task)

    def delete_task(self, task_id: str) -> bool:
        self._resolve_task_path(task_id).unlink()
        return True

    def mark_running(self, task_id: str, command: list[str], pid: int | None) -> DexTask:
        task = self.load_task(task_id)
        task.status = DexTaskStatus.RUNNING
        task.command = command
        task.pid = pid
        task.started_at = datetime.now(UTC).isoformat()
        task.events.append(DexTaskEvent(kind="status", message="task started", ts=task.started_at))
        return self.save_task(task)

    def mark_finished(
        self,
        task_id: str,
        status: DexTaskStatus,
        exit_code: int,
        result_summary: str | None,
        error_summary: str | None,
    ) -> DexTask:
        task = self.load_task(task_id)
        task.status = status
        task.exit_code = exit_code
        task.result_summary = result_summary
        task.error_summary = error_summary
        task.completed_at = datetime.now(UTC).isoformat()
        task.events.append(
            DexTaskEvent(kind="status", message=f"task {status.value}", ts=task.completed_at)
        )
        return self.save_task(task)

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

from filelock import FileLock


class KairosActivityLog:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)

    def append_entry(
        self,
        user_id: str,
        app_name: str,
        session_id: str,
        kind: str,
        message: str,
        ts: str,
    ) -> Path:
        dt = datetime.fromisoformat(ts)
        month_str = dt.strftime("%Y-%m")
        date_str = dt.strftime("%Y-%m-%d")
        safe_app_name = app_name.replace("/", "_").replace("\\", "_")

        log_dir = self.project_root / "memory_archive" / user_id / month_str
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{date_str}_{safe_app_name}_{session_id}_kairos.md"

        is_new_file = not log_path.exists()
        buffer: list[str] = []

        if is_new_file:
            buffer.extend(
                [
                    "---\n",
                    f"user_id: {user_id}\n",
                    f"app_name: {app_name}\n",
                    f"session_id: {session_id}\n",
                    "kind: kairos_activity\n",
                    "---\n\n",
                ]
            )

        buffer.extend(
            [
                f"## {ts}\n",
                f"kind: {kind}\n",
                f"message: {message}\n\n",
            ]
        )

        lock_path = str(log_path) + ".lock"
        with FileLock(lock_path, timeout=5):
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write("".join(buffer))

        try:
            Path(lock_path).unlink()
        except OSError:
            pass

        return log_path

    def read_session_history(
        self,
        user_id: str,
        app_name: str,
        session_id: str,
        descending: bool = True,
    ) -> list[dict[str, Any]]:
        safe_app_name = app_name.replace("/", "_").replace("\\", "_")
        root = self.project_root / "memory_archive" / user_id
        if not root.exists():
            return []

        pattern = f"**/*_{safe_app_name}_{session_id}_kairos.md"
        matches = sorted(root.glob(pattern))
        entries: list[dict[str, Any]] = []
        for path in matches:
            entries.extend(self._parse_history_file(path))
        entries.sort(key=lambda item: item["ts"], reverse=descending)
        return entries

    def _parse_history_file(self, path: Path) -> list[dict[str, Any]]:
        text = path.read_text(encoding="utf-8")
        if "---\n\n" in text:
            _, body = text.split("---\n\n", 1)
        else:
            body = text

        chunks = [chunk.strip() for chunk in body.split("## ") if chunk.strip()]
        entries: list[dict[str, Any]] = []
        for chunk in chunks:
            lines = chunk.splitlines()
            if not lines:
                continue
            ts = lines[0].strip()
            fields: dict[str, str] = {}
            for line in lines[1:]:
                if ": " in line:
                    key, value = line.split(": ", 1)
                    fields[key.strip()] = value.strip()
            entries.append(self._to_timeline_entry(ts, fields.get("kind", "brief"), fields.get("message", "")))
        return entries

    def _to_timeline_entry(self, ts: str, kind: str, message: str) -> dict[str, Any]:
        entry_kind = kind
        title = "Kairos event"
        task_id = self._extract_task_id(message)

        if "auto-created dex task" in message:
            entry_kind = "follow_up"
            title = "Auto-created follow-up"
        elif " completed:" in message or message.startswith("completed "):
            entry_kind = "task_completion"
            title = "Completed task"
        elif "blocked" in message or "waiting_input" in message:
            entry_kind = "guardrail"
            title = "Guardrail update"
        elif kind == "status":
            title = "Status update"
        elif kind == "brief":
            title = "Brief"

        return {
            "ts": ts,
            "kind": entry_kind,
            "title": title,
            "message": message,
            "workflow": self._extract_workflow_id(message),
            "stage": self._extract_stage_id(message),
            "task_id": task_id,
            "metadata": {
                "raw_kind": kind,
                "raw_message": message,
            },
        }

    def _extract_task_id(self, message: str) -> str | None:
        auto_created = re.search(r"auto-created dex task\s+([^:]+):", message)
        if auto_created:
            return auto_created.group(1).strip()
        inline_task = re.search(r"task(?:[_ ]id)?[=:]\s*([\w.-]+)", message)
        if inline_task:
            return inline_task.group(1)
        completed = re.match(r"([\w.-]+) completed:", message)
        if completed:
            return completed.group(1)
        return None

    def _extract_workflow_id(self, message: str) -> str | None:
        match = re.search(r"workflow(?:[_ ]id)?[=:]\s*([\w.-]+)", message)
        return match.group(1) if match else None

    def _extract_stage_id(self, message: str) -> str | None:
        match = re.search(r"stage(?:[_ ]id)?[=:]\s*([\w.-]+)", message)
        return match.group(1) if match else None

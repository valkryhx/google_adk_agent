from __future__ import annotations

from datetime import datetime
from pathlib import Path

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

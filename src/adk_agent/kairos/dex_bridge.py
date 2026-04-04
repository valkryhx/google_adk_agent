from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skills.dex.tools import DexManager


@dataclass
class DexTaskSnapshot:
    task_id: str
    status: str
    description: str
    result: str = ""
    result_summary: str | None = None
    error_summary: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    log_path: str | None = None


class KairosDexBridge:
    def __init__(self, base_dir: str, user_id: str):
        self.manager = DexManager(base_dir=base_dir, user_id=user_id)

    def _extract_log_path(self, raw: dict) -> str | None:
        for artifact in raw.get("artifacts", []):
            if artifact.get("kind") == "log":
                return artifact.get("path")
        return None

    def get_task(self, task_id: str) -> DexTaskSnapshot | None:
        try:
            raw = self.manager.load_task(task_id)
        except FileNotFoundError:
            return None
        return DexTaskSnapshot(
            task_id=raw["id"],
            status=raw.get("status", "pending"),
            description=raw.get("description", ""),
            result=raw.get("result", ""),
            result_summary=raw.get("result_summary"),
            error_summary=raw.get("error_summary"),
            created_at=raw.get("created_at"),
            completed_at=raw.get("completed_at"),
            log_path=self._extract_log_path(raw),
        )

    def get_tasks(self, task_ids: Iterable[str]) -> list[DexTaskSnapshot]:
        result: list[DexTaskSnapshot] = []
        for task_id in task_ids:
            snap = self.get_task(task_id)
            if snap is not None:
                result.append(snap)
        return result

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


class KairosDexBridge:
    def __init__(self, base_dir: str, user_id: str):
        self.manager = DexManager(base_dir=base_dir, user_id=user_id)

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
        )

    def get_tasks(self, task_ids: Iterable[str]) -> list[DexTaskSnapshot]:
        result: list[DexTaskSnapshot] = []
        for task_id in task_ids:
            snap = self.get_task(task_id)
            if snap is not None:
                result.append(snap)
        return result

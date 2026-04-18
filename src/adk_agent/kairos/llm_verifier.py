from __future__ import annotations

from typing import Any

from .llm_planner import KairosPlanner


class KairosVerifier:
    def __init__(self, planner: KairosPlanner):
        self._planner = planner

    async def verify_attempt(self, **kwargs):
        return await self._planner.verify_attempt(**kwargs)

    async def replan_from_failure(self, **kwargs):
        return await self._planner.replan_from_failure(**kwargs)

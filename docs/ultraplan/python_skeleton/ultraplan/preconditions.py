from __future__ import annotations

from typing import Protocol


class UltraplanPreconditionChecker(Protocol):
    async def check(self) -> tuple[bool, list[str]]: ...


class AllowAllPreconditionChecker:
    async def check(self) -> tuple[bool, list[str]]:
        return True, []

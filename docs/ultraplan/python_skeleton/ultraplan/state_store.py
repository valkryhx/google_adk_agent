from __future__ import annotations

from copy import deepcopy
from typing import Callable, Protocol

from .models import UltraplanAppState


class UltraplanStateStore(Protocol):
    def get_state(self) -> UltraplanAppState: ...
    def update(self, updater: Callable[[UltraplanAppState], UltraplanAppState]) -> None: ...


class InMemoryUltraplanStateStore:
    def __init__(self):
        self._state = UltraplanAppState()

    def get_state(self) -> UltraplanAppState:
        return deepcopy(self._state)

    def update(self, updater: Callable[[UltraplanAppState], UltraplanAppState]) -> None:
        self._state = updater(deepcopy(self._state))

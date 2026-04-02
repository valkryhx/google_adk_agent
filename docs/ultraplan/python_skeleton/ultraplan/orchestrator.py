from __future__ import annotations

from .models import LaunchUltraplanRequest


class UltraplanOrchestrator:
    def __init__(self, *, trigger, service):
        self.trigger = trigger
        self.service = service

    async def handle_input(self, text: str):
        if not self.trigger.has_keyword(text):
            return None
        rewritten = self.trigger.replace_keyword(text).strip()
        return await self.service.launch(LaunchUltraplanRequest(blurb=rewritten))

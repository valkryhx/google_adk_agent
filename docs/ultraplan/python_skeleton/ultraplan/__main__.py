from __future__ import annotations

import asyncio
import json
import sys

from .cli import run_demo
from .notifier import StdoutNotifier
from .phase import UltraplanPhaseResolver
from .preconditions import AllowAllPreconditionChecker
from .prompt_builder import UltraplanPromptBuilder
from .remote_api import RemoteSessionApi
from .service import UltraplanService
from .state_store import InMemoryUltraplanStateStore


def build_default_service() -> UltraplanService:
    return UltraplanService(
        state_store=InMemoryUltraplanStateStore(),
        remote_api=RemoteSessionApi(),
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )


async def main_async(argv: list[str] | None = None, *, service=None) -> tuple[int, dict]:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return 2, {
            "status": "usage_error",
            "message": "usage: python -m ultraplan <blurb>",
        }
    selected_service = build_default_service() if service is None else service
    payload = await run_demo(service=selected_service, blurb=" ".join(argv))
    exit_code = 1 if payload["status"] == "rejected" else 0
    return exit_code, payload


def main(argv: list[str] | None = None) -> int:
    exit_code, payload = asyncio.run(main_async(argv))
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

import pytest

from ultraplan.errors import UltraplanPollError
from ultraplan.models import ExecutionTarget
from ultraplan.notifier import StdoutNotifier
from ultraplan.phase import UltraplanPhaseResolver
from ultraplan.preconditions import AllowAllPreconditionChecker
from ultraplan.prompt_builder import UltraplanPromptBuilder
from ultraplan.remote_api import RemoteSessionApi
from ultraplan.service import UltraplanService
from ultraplan.state_store import InMemoryUltraplanStateStore


@pytest.mark.asyncio
async def test_poll_once_returns_approved_result_when_plan_is_approved():
    store = InMemoryUltraplanStateStore()
    service = UltraplanService(
        state_store=store,
        remote_api=RemoteSessionApi(),
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )

    result = await service.poll_once(
        session_id="session-1",
        new_events=[
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "tool-1", "name": "ExitPlanMode"}
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-1",
                            "is_error": False,
                            "content": "## Approved Plan:\nship it",
                        }
                    ]
                },
            },
        ],
        session_status="running",
    )

    assert result.execution_target == ExecutionTarget.REMOTE
    assert result.plan == "ship it"


@pytest.mark.asyncio
async def test_poll_once_returns_teleport_result_when_sentinel_is_present():
    store = InMemoryUltraplanStateStore()
    service = UltraplanService(
        state_store=store,
        remote_api=RemoteSessionApi(),
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )

    result = await service.poll_once(
        session_id="session-1",
        new_events=[
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "tool-1", "name": "ExitPlanMode"}
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-1",
                            "is_error": True,
                            "content": "__ULTRAPLAN_TELEPORT_LOCAL__\nbring plan back",
                        }
                    ]
                },
            },
        ],
        session_status="running",
    )

    assert result.execution_target == ExecutionTarget.LOCAL
    assert result.plan == "bring plan back"


@pytest.mark.asyncio
async def test_poll_once_raises_poll_error_when_remote_is_terminated():
    store = InMemoryUltraplanStateStore()
    service = UltraplanService(
        state_store=store,
        remote_api=RemoteSessionApi(),
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )

    with pytest.raises(UltraplanPollError, match="remote session ended"):
        await service.poll_once(
            session_id="session-1",
            new_events=[{"type": "result", "subtype": "error_max_turns"}],
            session_status="running",
        )

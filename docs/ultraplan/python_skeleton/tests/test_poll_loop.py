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


class ScriptedRemoteSessionApi(RemoteSessionApi):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)
        self.calls = []

    async def poll_remote_session_events(self, session_id: str, after_id: str | None = None, skip_metadata: bool = False):
        self.calls.append(after_id)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_poll_until_terminal_returns_remote_result_and_tracks_cursor():
    from ultraplan.models import PollRemoteSessionResponse

    api = ScriptedRemoteSessionApi([
        PollRemoteSessionResponse(new_events=[], last_event_id="cursor-1", session_status="running"),
        PollRemoteSessionResponse(
            new_events=[
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "tool_use", "id": "tool-1", "name": "ExitPlanMode"}]},
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
            last_event_id="cursor-2",
            session_status="running",
        ),
    ])
    service = UltraplanService(
        state_store=InMemoryUltraplanStateStore(),
        remote_api=api,
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )

    result = await service.poll_until_terminal(session_id="session-1", timeout_seconds=1, poll_interval_seconds=0)

    assert result.execution_target == ExecutionTarget.REMOTE
    assert result.plan == "ship it"
    assert api.calls == [None, "cursor-1"]


@pytest.mark.asyncio
async def test_poll_until_terminal_stores_pending_choice_for_local_handoff():
    from ultraplan.models import PollRemoteSessionResponse

    store = InMemoryUltraplanStateStore()
    api = ScriptedRemoteSessionApi([
        PollRemoteSessionResponse(
            new_events=[
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "tool_use", "id": "tool-1", "name": "ExitPlanMode"}]},
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
            last_event_id="cursor-1",
            session_status="running",
        ),
    ])
    service = UltraplanService(
        state_store=store,
        remote_api=api,
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )

    result = await service.poll_until_terminal(
        session_id="session-1",
        task_id="task-1",
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    state = store.get_state()
    assert result.execution_target == ExecutionTarget.LOCAL
    assert state.pending_choice is not None
    assert state.pending_choice.plan == "bring plan back"
    assert state.pending_choice.task_id == "task-1"


@pytest.mark.asyncio
async def test_poll_until_terminal_raises_after_repeated_failures():
    api = ScriptedRemoteSessionApi([
        RuntimeError("boom-1"),
        RuntimeError("boom-2"),
    ])
    service = UltraplanService(
        state_store=InMemoryUltraplanStateStore(),
        remote_api=api,
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )

    with pytest.raises(UltraplanPollError, match="boom-2"):
        await service.poll_until_terminal(
            session_id="session-1",
            timeout_seconds=1,
            poll_interval_seconds=0,
            max_consecutive_failures=2,
        )

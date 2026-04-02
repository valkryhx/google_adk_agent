import pytest

from ultraplan.models import ExecutionTarget, PollRemoteSessionResponse
from ultraplan.notifier import StdoutNotifier
from ultraplan.phase import UltraplanPhaseResolver
from ultraplan.preconditions import AllowAllPreconditionChecker
from ultraplan.prompt_builder import UltraplanPromptBuilder
from ultraplan.remote_api import HttpxRemoteSessionTransport, RemoteSessionApi
from ultraplan.service import UltraplanService
from ultraplan.state_store import InMemoryUltraplanStateStore


class ScriptedRemoteSessionApi(RemoteSessionApi):
    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)

    async def poll_remote_session_events(self, session_id: str, after_id: str | None = None, skip_metadata: bool = False):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_poll_until_terminal_marks_remote_task_completed():
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
                                "is_error": False,
                                "content": "## Approved Plan:\nship it",
                            }
                        ]
                    },
                },
            ],
            last_event_id="cursor-1",
            session_status="running",
        )
    ])
    service = UltraplanService(
        state_store=store,
        remote_api=api,
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )

    launch = await service.launch_request("please plan this")
    result = await service.poll_until_terminal(
        session_id="session-1",
        task_id=launch.task_id,
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    state = store.get_state()
    assert result.execution_target == ExecutionTarget.REMOTE
    assert state.tasks[launch.task_id].status == "completed"
    assert state.tasks[launch.task_id].end_time is not None


@pytest.mark.asyncio
async def test_poll_until_terminal_updates_task_phase_on_non_terminal_poll():
    store = InMemoryUltraplanStateStore()
    api = ScriptedRemoteSessionApi([
        PollRemoteSessionResponse(new_events=[], last_event_id="cursor-1", session_status="idle"),
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
        state_store=store,
        remote_api=api,
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )

    launch = await service.launch_request("please plan this")
    await service.poll_until_terminal(
        session_id="session-1",
        task_id=launch.task_id,
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    state = store.get_state()
    assert state.tasks[launch.task_id].phase is not None
    assert state.tasks[launch.task_id].phase.value == "needs_input"


def test_httpx_transport_builds_session_payload_with_control_request():
    transport = HttpxRemoteSessionTransport(base_url="https://example.invalid")
    payload = transport.build_create_session_payload(
        initial_message="hello remote",
        description="Refine local plan",
        model="claude-opus-4-6",
        permission_mode="plan",
        ultraplan=True,
    )

    assert payload["title"] == "ultraplan: Refine local plan"
    assert payload["session_context"]["model"] == "claude-opus-4-6"
    assert payload["events"][0]["data"]["request"]["subtype"] == "set_permission_mode"
    assert payload["events"][0]["data"]["request"]["ultraplan"] is True
    assert payload["events"][1]["data"]["message"]["content"] == "hello remote"

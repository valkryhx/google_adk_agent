import pytest

from ultraplan.models import LaunchUltraplanRequest
from ultraplan.notifier import StdoutNotifier
from ultraplan.phase import UltraplanPhaseResolver
from ultraplan.preconditions import AllowAllPreconditionChecker
from ultraplan.prompt_builder import UltraplanPromptBuilder
from ultraplan.remote_api import RemoteSessionApi
from ultraplan.service import UltraplanService
from ultraplan.state_store import InMemoryUltraplanStateStore


@pytest.mark.asyncio
async def test_remote_api_builds_initial_events_with_set_permission_mode_and_user_message():
    api = RemoteSessionApi()
    events = api.build_initial_events(
        initial_message="hello remote",
        permission_mode="plan",
        ultraplan=True,
    )

    assert events[0]["data"]["request"]["subtype"] == "set_permission_mode"
    assert events[0]["data"]["request"]["mode"] == "plan"
    assert events[0]["data"]["request"]["ultraplan"] is True
    assert events[1]["data"]["message"]["content"] == "hello remote"


@pytest.mark.asyncio
async def test_remote_api_titles_ultraplan_sessions_with_prefix():
    api = RemoteSessionApi()
    assert api.build_title("Refine local plan", ultraplan=True) == "ultraplan: Refine local plan"
    assert api.build_title("Refine local plan", ultraplan=False) == "Refine local plan"


@pytest.mark.asyncio
async def test_stop_clears_active_session_and_marks_task_killed():
    store = InMemoryUltraplanStateStore()
    service = UltraplanService(
        state_store=store,
        remote_api=RemoteSessionApi(),
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )

    launch = await service.launch(LaunchUltraplanRequest(blurb="please plan this"))
    assert launch.task_id is not None

    await service.stop(task_id=launch.task_id, session_id="session-override")

    state = store.get_state()
    assert state.session_url is None
    assert state.launching is False
    assert state.pending_choice is None
    assert state.tasks[launch.task_id].status == "killed"

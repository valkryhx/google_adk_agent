import pytest

from ultraplan.models import LaunchUltraplanRequest
from ultraplan.notifier import StdoutNotifier
from ultraplan.phase import UltraplanPhaseResolver
from ultraplan.preconditions import AllowAllPreconditionChecker
from ultraplan.prompt_builder import UltraplanPromptBuilder
from ultraplan.remote_api import RemoteSessionApi
from ultraplan.service import UltraplanService
from ultraplan.state_store import InMemoryUltraplanStateStore


class FailingRemoteSessionApi(RemoteSessionApi):
    async def create_ultraplan_session(self, **kwargs):  # pragma: no cover - behavior under test
        raise RuntimeError("boom")


class RejectingPreconditionChecker:
    async def check(self):
        return False, ["missing login"]


@pytest.mark.asyncio
async def test_launch_resets_launching_flag_when_remote_creation_fails():
    store = InMemoryUltraplanStateStore()
    service = UltraplanService(
        state_store=store,
        remote_api=FailingRemoteSessionApi(),
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await service.launch(LaunchUltraplanRequest(blurb="please plan this"))

    assert store.get_state().launching is False


@pytest.mark.asyncio
async def test_launch_rejects_when_preconditions_fail():
    store = InMemoryUltraplanStateStore()
    service = UltraplanService(
        state_store=store,
        remote_api=RemoteSessionApi(),
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=RejectingPreconditionChecker(),
    )

    result = await service.launch(LaunchUltraplanRequest(blurb="please plan this"))

    assert result.accepted is False
    assert result.message == "missing login"
    assert store.get_state().launching is False


@pytest.mark.asyncio
async def test_poll_once_returns_phase_when_no_approved_plan_exists():
    store = InMemoryUltraplanStateStore()
    service = UltraplanService(
        state_store=store,
        remote_api=RemoteSessionApi(),
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )

    phase = await service.poll_once(
        session_id="session-1",
        new_events=[],
        session_status="idle",
    )

    assert phase.value == "needs_input"

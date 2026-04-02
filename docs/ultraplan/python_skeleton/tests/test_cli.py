import asyncio

from ultraplan.cli import run_demo
from ultraplan.models import ExecutionTarget, PollResult, UltraplanPhase


class StubService:
    def __init__(self, *, launch_result, poll_result):
        self.launch_result = launch_result
        self.poll_result = poll_result
        self.launch_calls = []
        self.poll_calls = []

    async def launch_request(self, blurb: str, seed_plan: str | None = None):
        self.launch_calls.append((blurb, seed_plan))
        return self.launch_result

    async def poll_until_terminal(self, *, session_id: str, task_id: str | None = None, timeout_seconds: float = 1800, poll_interval_seconds: float = 3.0):
        self.poll_calls.append((session_id, task_id, timeout_seconds, poll_interval_seconds))
        return self.poll_result


class LaunchResult:
    def __init__(self, *, accepted: bool, message: str, session_url: str | None = None, task_id: str | None = None):
        self.accepted = accepted
        self.message = message
        self.session_url = session_url
        self.task_id = task_id


def test_run_demo_returns_launch_rejection_without_polling():
    service = StubService(
        launch_result=LaunchResult(accepted=False, message="missing login"),
        poll_result=None,
    )

    result = asyncio.run(run_demo(service=service, blurb="please plan this"))

    assert result["status"] == "rejected"
    assert result["message"] == "missing login"
    assert service.poll_calls == []


def test_run_demo_returns_remote_plan_result():
    service = StubService(
        launch_result=LaunchResult(
            accepted=True,
            message="ultraplan launching",
            session_url="https://console.example.invalid/sessions/session-1",
            task_id="task-1",
        ),
        poll_result=PollResult(plan="ship it", reject_count=0, execution_target=ExecutionTarget.REMOTE),
    )

    result = asyncio.run(run_demo(service=service, blurb="please plan this", session_id="session-1"))

    assert result["status"] == "completed"
    assert result["execution_target"] == "remote"
    assert result["plan"] == "ship it"
    assert result["session_url"] == "https://console.example.invalid/sessions/session-1"


def test_run_demo_extracts_session_id_from_session_url():
    service = StubService(
        launch_result=LaunchResult(
            accepted=True,
            message="ultraplan launching",
            session_url="https://console.example.invalid/sessions/session-1",
            task_id="task-1",
        ),
        poll_result=PollResult(plan="ship it", reject_count=0, execution_target=ExecutionTarget.LOCAL),
    )

    result = asyncio.run(run_demo(service=service, blurb="please plan this"))

    assert result["execution_target"] == "local"
    assert service.poll_calls[0][0] == "session-1"


def test_run_demo_returns_phase_snapshot_when_service_yields_phase():
    service = StubService(
        launch_result=LaunchResult(
            accepted=True,
            message="ultraplan launching",
            session_url="https://console.example.invalid/sessions/session-1",
            task_id="task-1",
        ),
        poll_result=UltraplanPhase.NEEDS_INPUT,
    )

    result = asyncio.run(run_demo(service=service, blurb="please plan this", session_id="session-1"))

    assert result["status"] == "phase"
    assert result["phase"] == "needs_input"

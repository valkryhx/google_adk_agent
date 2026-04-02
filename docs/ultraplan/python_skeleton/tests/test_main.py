import asyncio

from ultraplan.__main__ import main_async
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


def test_main_async_returns_rejection_exit_code_and_payload():
    service = StubService(
        launch_result=LaunchResult(accepted=False, message="missing login"),
        poll_result=None,
    )

    exit_code, payload = asyncio.run(main_async(argv=["please plan this"], service=service))

    assert exit_code == 1
    assert payload["status"] == "rejected"
    assert payload["message"] == "missing login"


def test_main_async_returns_zero_for_completed_remote_result():
    service = StubService(
        launch_result=LaunchResult(
            accepted=True,
            message="ultraplan launching",
            session_url="https://console.example.invalid/sessions/session-1",
            task_id="task-1",
        ),
        poll_result=PollResult(plan="ship it", reject_count=0, execution_target=ExecutionTarget.REMOTE),
    )

    exit_code, payload = asyncio.run(main_async(argv=["please plan this"], service=service))

    assert exit_code == 0
    assert payload["status"] == "completed"
    assert payload["execution_target"] == "remote"


def test_main_async_returns_zero_for_phase_snapshot():
    service = StubService(
        launch_result=LaunchResult(
            accepted=True,
            message="ultraplan launching",
            session_url="https://console.example.invalid/sessions/session-1",
            task_id="task-1",
        ),
        poll_result=UltraplanPhase.NEEDS_INPUT,
    )

    exit_code, payload = asyncio.run(main_async(argv=["please plan this"], service=service))

    assert exit_code == 0
    assert payload["status"] == "phase"
    assert payload["phase"] == "needs_input"

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from .constants import DEFAULT_REMOTE_DESCRIPTION
from .errors import UltraplanPollError
from .models import ExecutionTarget, LaunchUltraplanRequest, LaunchUltraplanResponse, PendingChoice, PollFailReason, PollResult, UltraplanTaskState
from .scanner import ExitPlanModeScanner


class UltraplanService:
    def __init__(
        self,
        *,
        state_store,
        remote_api,
        prompt_builder,
        phase_resolver,
        notifier,
        precondition_checker,
        model: str = "claude-opus-4-6",
    ):
        self.state_store = state_store
        self.remote_api = remote_api
        self.prompt_builder = prompt_builder
        self.phase_resolver = phase_resolver
        self.notifier = notifier
        self.precondition_checker = precondition_checker
        self.model = model

    async def launch(self, request: LaunchUltraplanRequest) -> LaunchUltraplanResponse:
        state = self.state_store.get_state()
        if state.launching or state.session_url:
            return LaunchUltraplanResponse(
                accepted=False,
                message="ultraplan already active",
                session_url=state.session_url,
            )

        self.state_store.update(lambda s: self._set_launching(s, True))
        allowed, errors = await self.precondition_checker.check()
        if not allowed:
            self.state_store.update(lambda s: self._set_launching(s, False))
            message = "\n".join(errors) if errors else "ultraplan preconditions failed"
            self.notifier.error(message)
            return LaunchUltraplanResponse(
                accepted=False,
                message=message,
            )

        try:
            prompt = self.prompt_builder.build(request.blurb, request.seed_plan)
            session = await self.remote_api.create_ultraplan_session(
                initial_message=prompt,
                description=request.blurb or DEFAULT_REMOTE_DESCRIPTION,
                model=self.model,
                permission_mode="plan",
                ultraplan=True,
            )
        except Exception:
            self.state_store.update(lambda s: self._set_launching(s, False))
            raise
        task_id = str(uuid4())
        self.state_store.update(lambda s: self._attach_session(s, session.url, task_id, session.session_id, request.blurb))
        self.notifier.info(f"ultraplan session created: {session.url}")
        return LaunchUltraplanResponse(
            accepted=True,
            message="ultraplan launching",
            session_url=session.url,
            task_id=task_id,
        )

    async def launch_request(self, blurb: str, seed_plan: str | None = None) -> LaunchUltraplanResponse:
        return await self.launch(LaunchUltraplanRequest(blurb=blurb, seed_plan=seed_plan))

    async def stop(self, *, task_id: str, session_id: str) -> None:
        await self.remote_api.archive_remote_session(session_id)
        self.state_store.update(lambda s: self._mark_task_killed(s, task_id))
        self.notifier.info(f"ultraplan stopped: {session_id}")

    async def poll_once(
        self,
        *,
        session_id: str,
        new_events: list[dict] | None = None,
        session_status: str | None = None,
        after_id: str | None = None,
    ):
        if new_events is None:
            response = await self.remote_api.poll_remote_session_events(
                session_id=session_id,
                after_id=after_id,
                skip_metadata=False,
            )
            new_events = response.new_events
            session_status = response.session_status
        scanner = ExitPlanModeScanner()
        scan_result = scanner.ingest(new_events)
        if scan_result.kind.value == "approved":
            return PollResult(
                plan=scan_result.plan or "",
                reject_count=scanner.reject_count,
                execution_target=ExecutionTarget.REMOTE,
            )
        if scan_result.kind.value == "teleport":
            return PollResult(
                plan=scan_result.plan or "",
                reject_count=scanner.reject_count,
                execution_target=ExecutionTarget.LOCAL,
            )
        if scan_result.kind.value == "terminated":
            raise UltraplanPollError(
                f"remote session ended ({scan_result.terminated_subtype})",
                PollFailReason.TERMINATED.value,
                scanner.reject_count,
            )
        phase = self.phase_resolver.resolve(
            scanner=scanner,
            session_status=session_status,
            new_events=new_events,
        )
        return phase

    async def poll_until_terminal(
        self,
        *,
        session_id: str,
        task_id: str | None = None,
        timeout_seconds: float = 30 * 60,
        poll_interval_seconds: float = 3.0,
        max_consecutive_failures: int = 5,
    ):
        deadline = time.monotonic() + timeout_seconds
        after_id: str | None = None
        failures = 0

        while time.monotonic() < deadline:
            try:
                response = await self.remote_api.poll_remote_session_events(
                    session_id=session_id,
                    after_id=after_id,
                    skip_metadata=False,
                )
                failures = 0
            except Exception as exc:
                failures += 1
                if failures >= max_consecutive_failures:
                    raise UltraplanPollError(
                        str(exc),
                        PollFailReason.NETWORK_OR_UNKNOWN.value,
                        0,
                        cause=exc,
                    )
                if poll_interval_seconds:
                    await asyncio.sleep(poll_interval_seconds)
                continue

            result = await self.poll_once(
                session_id=session_id,
                new_events=response.new_events,
                session_status=response.session_status,
                after_id=after_id,
            )
            after_id = response.last_event_id

            if isinstance(result, PollResult):
                if task_id is not None:
                    if result.execution_target == ExecutionTarget.LOCAL:
                        self.state_store.update(lambda s: self._set_pending_choice(s, task_id, session_id, result.plan))
                    else:
                        self.state_store.update(lambda s: self._mark_task_completed(s, task_id))
                return result

            if task_id is not None:
                self.state_store.update(lambda s: self._set_task_phase(s, task_id, result))

            if poll_interval_seconds:
                await asyncio.sleep(poll_interval_seconds)

        raise UltraplanPollError(
            "poll timed out before terminal result",
            PollFailReason.TIMEOUT_NO_PLAN.value,
            0,
        )

    @staticmethod
    def _set_launching(state, value: bool):
        state.launching = value
        return state

    @staticmethod
    def _attach_session(state, session_url: str, task_id: str, session_id: str, blurb: str):
        state.launching = False
        state.session_url = session_url
        state.tasks[task_id] = UltraplanTaskState(
            task_id=task_id,
            session_id=session_id,
            session_url=session_url,
            command=blurb,
            start_time=time.time(),
        )
        return state

    @staticmethod
    def _mark_task_killed(state, task_id: str):
        state.launching = False
        state.session_url = None
        state.pending_choice = None
        task = state.tasks.get(task_id)
        if task is not None:
            task.status = "killed"
            task.end_time = time.time()
        return state

    @staticmethod
    def _mark_task_completed(state, task_id: str):
        task = state.tasks.get(task_id)
        if task is not None:
            task.status = "completed"
            task.end_time = time.time()
        return state

    @staticmethod
    def _set_task_phase(state, task_id: str, phase):
        task = state.tasks.get(task_id)
        if task is not None:
            task.phase = phase
        return state

    @staticmethod
    def _set_pending_choice(state, task_id: str, session_id: str, plan: str):
        state.pending_choice = PendingChoice(
            plan=plan,
            session_id=session_id,
            task_id=task_id,
        )
        return state

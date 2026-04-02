from __future__ import annotations

from urllib.parse import urlparse

from .models import PollResult


def extract_session_id(session_url: str | None) -> str | None:
    if not session_url:
        return None
    path = urlparse(session_url).path.rstrip("/")
    if not path:
        return None
    session_id = path.split("/")[-1]
    return session_id or None


async def run_demo(
    *,
    service,
    blurb: str,
    seed_plan: str | None = None,
    session_id: str | None = None,
    timeout_seconds: float = 30 * 60,
    poll_interval_seconds: float = 3.0,
) -> dict:
    launch = await service.launch_request(blurb, seed_plan=seed_plan)
    if not launch.accepted:
        return {
            "status": "rejected",
            "message": launch.message,
            "session_url": launch.session_url,
        }

    resolved_session_id = session_id or extract_session_id(launch.session_url)
    if resolved_session_id is None:
        return {
            "status": "launch_only",
            "message": launch.message,
            "session_url": launch.session_url,
        }

    result = await service.poll_until_terminal(
        session_id=resolved_session_id,
        task_id=launch.task_id,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    if isinstance(result, PollResult):
        return {
            "status": "completed",
            "message": launch.message,
            "session_url": launch.session_url,
            "plan": result.plan,
            "reject_count": result.reject_count,
            "execution_target": result.execution_target.value,
        }
    return {
        "status": "phase",
        "message": launch.message,
        "session_url": launch.session_url,
        "phase": result.value,
    }

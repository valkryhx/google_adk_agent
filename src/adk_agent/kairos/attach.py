from __future__ import annotations

from pathlib import Path

from src.adk_agent.kairos.activity_log import KairosActivityLog


def build_runtime_summary(app_name: str, user_id: str, session_id: str, runtime) -> dict:
    status = runtime.get_status()
    project_root = Path(__file__).resolve().parents[3]
    has_history = bool(
        KairosActivityLog(project_root).read_session_history(
            user_id=user_id,
            app_name=app_name,
            session_id=session_id,
            descending=True,
        )[:1]
    )
    return {
        "app_name": app_name,
        "user_id": user_id,
        "session_id": session_id,
        "mode": status.get("mode"),
        "running": status.get("running"),
        "recent_events": status.get("recent_events", [])[-5:],
        "has_history": has_history,
    }


def list_runtime_summaries(session_manager, user_id: str) -> list[dict]:
    result: list[dict] = []
    for (app_name, uid, session_id), session in getattr(session_manager, "_sessions", {}).items():
        if uid != user_id:
            continue
        runtime = getattr(session, "kairos_runtime", None) or getattr(session, "runtime", None)
        if runtime is None:
            continue
        result.append(build_runtime_summary(app_name, uid, session_id, runtime))
    return result

from __future__ import annotations


def build_runtime_summary(app_name: str, user_id: str, session_id: str, runtime) -> dict:
    status = runtime.get_status()
    return {
        "app_name": app_name,
        "user_id": user_id,
        "session_id": session_id,
        "mode": status.get("mode"),
        "running": status.get("running"),
        "recent_events": status.get("recent_events", [])[-5:],
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

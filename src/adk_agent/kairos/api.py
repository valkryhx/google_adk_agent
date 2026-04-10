from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from .activity_log import KairosActivityLog
from .attach import build_runtime_summary, list_runtime_summaries
from .models import KairosSchedule


class KairosSessionRequest(BaseModel):
    app_name: str
    user_id: str
    reason: str | None = None


class KairosScheduleRequest(BaseModel):
    app_name: str
    user_id: str
    schedule_id: str
    cron: str
    reason: str
    enabled: bool = True


class KairosDexRegisterRequest(BaseModel):
    app_name: str
    user_id: str
    task_id: str
    description: str


def _get_session_manager(session_manager):
    return session_manager() if callable(session_manager) else session_manager


def register_kairos_routes(app, session_manager):
    router = APIRouter()

    @router.post("/api/sessions/{session_id}/kairos/start")
    async def start_kairos(session_id: str, req: KairosSessionRequest):
        manager = _get_session_manager(session_manager)
        session = manager.get_or_create(req.app_name, req.user_id, session_id)
        runtime = session.get_or_create_kairos_runtime()
        await runtime.start()
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}

    @router.post("/api/sessions/{session_id}/kairos/stop")
    async def stop_kairos(session_id: str, req: KairosSessionRequest):
        manager = _get_session_manager(session_manager)
        session = manager.get_or_create(req.app_name, req.user_id, session_id)
        runtime = session.get_or_create_kairos_runtime()
        await runtime.stop()
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}

    @router.post("/api/sessions/{session_id}/kairos/wake")
    async def wake_kairos(session_id: str, req: KairosSessionRequest):
        manager = _get_session_manager(session_manager)
        session = manager.get_or_create(req.app_name, req.user_id, session_id)
        runtime = session.get_or_create_kairos_runtime()
        await runtime.wake(req.reason or "manual")
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}

    @router.get("/api/sessions/{session_id}/kairos/status")
    async def kairos_status(session_id: str, app_name: str, user_id: str):
        manager = _get_session_manager(session_manager)
        session = manager.get_or_create(app_name, user_id, session_id)
        runtime = session.get_or_create_kairos_runtime()
        status = runtime.get_status()
        return {
            "status": "ok",
            "session_id": session_id,
            "kairos": status,
            "active_workflow": status.get("active_workflow"),
            "planned_actions": status.get("planned_actions", []),
            "blocked_reason": status.get("blocked_reason"),
            "task_summaries": status.get("task_summaries", []),
            "decision_explanation": status.get("decision_explanation"),
            "condition_tree": status.get("condition_tree"),
            "unfinished_work_items": status.get("unfinished_work_items", []),
            "proactive_candidates": status.get("proactive_candidates", []),
            "last_proactive_scan": status.get("last_proactive_scan", {}),
            "last_guardrail_block": status.get("last_guardrail_block", {}),
            "last_planning_result": status.get("last_planning_result", {}),
        }

    @router.get("/api/sessions/{session_id}/kairos/history")
    async def kairos_history(
        session_id: str,
        app_name: str,
        user_id: str,
        descending: bool = True,
    ):
        project_root = Path(__file__).resolve().parents[3]
        history = KairosActivityLog(project_root).read_session_history(
            user_id=user_id,
            app_name=app_name,
            session_id=session_id,
            descending=descending,
        )
        return {
            "status": "ok",
            "session_id": session_id,
            "history": history,
        }

    # --- Phase 2: Schedule routes ---

    @router.post("/api/sessions/{session_id}/kairos/schedules")
    async def add_schedule(session_id: str, req: KairosScheduleRequest):
        manager = _get_session_manager(session_manager)
        session = manager.get_or_create(req.app_name, req.user_id, session_id)
        runtime = session.get_or_create_kairos_runtime()
        await runtime.add_schedule(
            KairosSchedule(
                schedule_id=req.schedule_id,
                cron=req.cron,
                reason=req.reason,
                enabled=req.enabled,
            )
        )
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}

    @router.delete("/api/sessions/{session_id}/kairos/schedules/{schedule_id}")
    async def delete_schedule(session_id: str, schedule_id: str, app_name: str, user_id: str):
        manager = _get_session_manager(session_manager)
        session = manager.get_or_create(app_name, user_id, session_id)
        runtime = session.get_or_create_kairos_runtime()
        await runtime.delete_schedule(schedule_id)
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}

    # --- Phase 2: Dex handoff route ---

    @router.post("/api/sessions/{session_id}/kairos/dex/register")
    async def register_dex_task(session_id: str, req: KairosDexRegisterRequest):
        manager = _get_session_manager(session_manager)
        session = manager.get_or_create(req.app_name, req.user_id, session_id)
        runtime = session.get_or_create_kairos_runtime()
        await runtime.register_dex_task(req.task_id, req.description)
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}

    # --- Phase 2: Attach/List routes ---

    @router.get("/api/kairos/sessions")
    async def list_kairos_sessions(user_id: str):
        manager = _get_session_manager(session_manager)
        return {"sessions": list_runtime_summaries(manager, user_id)}

    @router.get("/api/sessions/{session_id}/kairos/attach")
    async def attach_kairos(session_id: str, app_name: str, user_id: str):
        manager = _get_session_manager(session_manager)
        session = manager.get_or_create(app_name, user_id, session_id)
        runtime = session.get_or_create_kairos_runtime()
        return {
            "status": "ok",
            "session_id": session_id,
            "kairos": runtime.get_status(),
            "attach": build_runtime_summary(app_name, user_id, session_id, runtime),
        }

    app.include_router(router)

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel


class KairosSessionRequest(BaseModel):
    app_name: str
    user_id: str
    reason: str | None = None


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
        return {"status": "ok", "session_id": session_id, "kairos": runtime.get_status()}

    app.include_router(router)

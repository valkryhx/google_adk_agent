import asyncio
import os
import tempfile

import pytest
from google.adk.events import Event

from src.shared.db.custom_table_db_service import FullyCustomDbService


@pytest.mark.asyncio
async def test_save_session_state_does_not_rewrite_events():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    try:
        service = FullyCustomDbService(
            f"sqlite+aiosqlite:///{path}",
            session_table_name="test_sessions",
            event_table_name="test_events",
        )
        await service.init_db()

        session = await service.create_session("app", "user", "sid")
        session.events = [
            Event.model_validate({
                "invocation_id": "u1",
                "author": "user",
                "content": {"role": "user", "parts": [{"text": "hi"}]},
            }),
            Event.model_validate({
                "invocation_id": "m1",
                "author": "model",
                "content": {"role": "model", "parts": [{"text": "hello"}]},
            }),
        ]
        await service.save_session(session)

        for i in range(5):
            await service.save_session_state(
                app_name="app",
                user_id="user",
                session_id="sid",
                state={"kairos": {"tick": i}},
            )

        loaded = await service.get_session("app", "user", "sid")
        assert loaded is not None
        assert len(loaded.events) == 2
        assert [event.invocation_id for event in loaded.events] == ["u1", "m1"]
        assert loaded.state == {"kairos": {"tick": 4}}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

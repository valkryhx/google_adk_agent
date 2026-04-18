import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from fastapi import Response

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adk_agent import main_web_start_steering as steering


class _FakeSession:
    async def draft_user_requirement_work_item(self, requirement):
        return SimpleNamespace(open_questions=[]), Path("requirements/session/work.md")


class _FakeSessionManager:
    def get_or_create(self, app_name, user_id, session_id):
        return _FakeSession()


async def _read_streaming_body(streaming_response):
    chunks = []
    async for raw in streaming_response.body_iterator:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        chunks.append(raw)
    return chunks


@pytest.mark.asyncio
async def test_chat_endpoint_keeps_normal_todo_request_on_run_agent_path(monkeypatch):
    observed = {"run_agent_called": False}

    async def fake_run_agent(task, app_name, user_id, session_id, images=None):
        observed["run_agent_called"] = True
        yield {"type": "text", "content": f"run_agent:{task}"}

    monkeypatch.setattr(steering, "run_agent", fake_run_agent)
    monkeypatch.setattr(steering, "session_manager", _FakeSessionManager())
    monkeypatch.setattr(steering, "WORKER_LOCK", asyncio.Lock())
    steering.worker_state.set_idle()

    request = steering.ChatRequest(
        message="开发一个 todolist demo",
        app_name="dynamic_expert",
        user_id="user_001",
        session_id="session_test",
    )

    response = await steering.chat_endpoint(request, Response())
    body_lines = await _read_streaming_body(response)
    payloads = [json.loads(line) for line in body_lines if line.strip()]

    assert observed["run_agent_called"] is True
    assert payloads == [{"chunk": {"type": "text", "content": "run_agent:开发一个 todolist demo"}}]

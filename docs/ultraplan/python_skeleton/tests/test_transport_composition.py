import pytest

from ultraplan.models import PollRemoteSessionResponse, RemoteSessionRef
from ultraplan.remote_api import HttpxRemoteSessionTransport, RemoteSessionApi


class StubTransport:
    def __init__(self):
        self.created_payload = None
        self.poll_calls = []
        self.archived_sessions = []

    def build_create_session_payload(self, **kwargs) -> dict:
        self.created_payload = {
            "title": "ultraplan: Refine local plan",
            "events": [
                {
                    "type": "event",
                    "data": {
                        "request": {
                            "subtype": "set_permission_mode",
                            "mode": kwargs["permission_mode"],
                            "ultraplan": kwargs["ultraplan"],
                        }
                    },
                }
            ],
            "session_context": {
                "model": kwargs["model"],
            },
        }
        return self.created_payload

    async def create_session(self, payload: dict) -> RemoteSessionRef:
        self.created_payload = payload
        return RemoteSessionRef(
            session_id="session-123",
            title=payload["title"],
            url="https://example.invalid/sessions/session-123",
        )

    async def poll_events(self, session_id: str, after_id: str | None = None, skip_metadata: bool = False) -> PollRemoteSessionResponse:
        self.poll_calls.append((session_id, after_id, skip_metadata))
        return PollRemoteSessionResponse(new_events=[], last_event_id="cursor-1", session_status="idle")

    async def archive_session(self, session_id: str) -> None:
        self.archived_sessions.append(session_id)


def test_httpx_transport_exposes_create_payload_builder():
    transport = HttpxRemoteSessionTransport(base_url="https://example.invalid")
    payload = transport.build_create_session_payload(
        initial_message="hello remote",
        description="Refine local plan",
        model="claude-opus-4-6",
        permission_mode="plan",
        ultraplan=True,
    )

    assert payload["title"] == "ultraplan: Refine local plan"
    assert payload["events"][0]["data"]["request"]["subtype"] == "set_permission_mode"


@pytest.mark.asyncio
async def test_remote_api_create_session_delegates_to_transport():
    transport = StubTransport()
    api = RemoteSessionApi(transport=transport)

    result = await api.create_ultraplan_session(
        initial_message="hello remote",
        description="Refine local plan",
        model="claude-opus-4-6",
        permission_mode="plan",
        ultraplan=True,
    )

    assert result.session_id == "session-123"
    assert transport.created_payload is not None
    assert transport.created_payload["session_context"]["model"] == "claude-opus-4-6"


@pytest.mark.asyncio
async def test_remote_api_poll_and_archive_delegate_to_transport():
    transport = StubTransport()
    api = RemoteSessionApi(transport=transport)

    response = await api.poll_remote_session_events("session-1", after_id="cursor-0", skip_metadata=True)
    await api.archive_remote_session("session-1")

    assert response.last_event_id == "cursor-1"
    assert transport.poll_calls == [("session-1", "cursor-0", True)]
    assert transport.archived_sessions == ["session-1"]

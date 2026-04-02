import pytest

from ultraplan.errors import (
    RemoteSessionAuthError,
    RemoteSessionNotFoundError,
    RemoteSessionRateLimitError,
    RemoteSessionResponseError,
    RemoteSessionServerError,
    RemoteSessionTransportError,
)
from ultraplan.models import PollRemoteSessionResponse, RemoteSessionRef
from ultraplan.remote_api import HttpxRemoteSessionTransport


class DummyResponse:
    def __init__(self, data=None, status_code=200, text=""):
        self._data = data or {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._data


class DummyHttpClient:
    def __init__(self):
        self.post_calls = []
        self.get_calls = []

    async def post(self, url, headers=None, json=None):
        self.post_calls.append((url, headers, json))
        if url.endswith("/archive"):
            return DummyResponse({})
        return DummyResponse({"id": "session-123", "title": json["title"]})

    async def get(self, url, headers=None, params=None):
        self.get_calls.append((url, headers, params))
        return DummyResponse(
            {
                "data": [],
                "last_id": "cursor-1",
                "first_id": None,
                "has_more": False,
                "session_status": "idle",
            }
        )


class DummyHttpClientWithCustomResponses:
    def __init__(self, *, post_response=None, get_response=None, post_error=None, get_error=None):
        self.post_calls = []
        self.get_calls = []
        self.post_response = post_response
        self.get_response = get_response
        self.post_error = post_error
        self.get_error = get_error

    async def post(self, url, headers=None, json=None):
        self.post_calls.append((url, headers, json))
        if self.post_error is not None:
            raise self.post_error
        return self.post_response if self.post_response is not None else DummyResponse({})

    async def get(self, url, headers=None, params=None):
        self.get_calls.append((url, headers, params))
        if self.get_error is not None:
            raise self.get_error
        return self.get_response if self.get_response is not None else DummyResponse({})


class FakeAsyncClient:
    def __init__(self, *, base_url, timeout, headers):
        self.base_url = base_url
        self.timeout = timeout
        self.headers = headers


class FakeHttpxModule:
    AsyncClient = FakeAsyncClient


class RuntimeFakeAsyncClient:
    instances = []

    def __init__(self, *, base_url, timeout, headers):
        self.base_url = base_url
        self.timeout = timeout
        self.headers = headers
        self.closed = False
        self.post_calls = []
        RuntimeFakeAsyncClient.instances.append(self)

    async def post(self, url, headers=None, json=None):
        self.post_calls.append((url, headers, json))
        return DummyResponse({"id": "session-runtime", "title": json["title"], "url": f"{self.base_url}/sessions/session-runtime"})

    async def aclose(self):
        self.closed = True

class RuntimeFakeHttpxModule:
    AsyncClient = RuntimeFakeAsyncClient


class FakeServerAsyncClient:
    instances = []
    shared_sessions = {}
    archived_session_ids = []
    last_after_id = None

    def __init__(self, *, base_url, timeout, headers):
        self.base_url = base_url
        self.timeout = timeout
        self.headers = headers
        self.closed = False
        self.post_calls = []
        self.get_calls = []
        FakeServerAsyncClient.instances.append(self)

    async def post(self, url, headers=None, json=None):
        self.post_calls.append((url, headers, json))
        if url == "https://example.invalid/v1/sessions":
            session_id = "session-fake-server"
            FakeServerAsyncClient.shared_sessions[session_id] = {
                "title": json["title"],
                "archived": False,
                "events": [{"type": "assistant", "message": {"content": []}}],
            }
            return DummyResponse(
                {
                    "id": session_id,
                    "title": json["title"],
                    "url": f"https://console.example.invalid/sessions/{session_id}",
                }
            )
        if url == "https://example.invalid/v1/sessions/session-fake-server/archive":
            FakeServerAsyncClient.shared_sessions["session-fake-server"]["archived"] = True
            FakeServerAsyncClient.archived_session_ids.append("session-fake-server")
            return DummyResponse({})
        return DummyResponse({}, status_code=404, text="missing")

    async def get(self, url, headers=None, params=None):
        self.get_calls.append((url, headers, params))
        FakeServerAsyncClient.last_after_id = None if params is None else params.get("after_id")
        if url == "https://example.invalid/v1/sessions/session-fake-server/events":
            return DummyResponse(
                {
                    "data": FakeServerAsyncClient.shared_sessions["session-fake-server"]["events"],
                    "last_id": "cursor-fake-server",
                    "branch": "main",
                    "session_status": "running",
                }
            )
        return DummyResponse({}, status_code=404, text="missing")

    async def aclose(self):
        self.closed = True


class FakeServerHttpxModule:
    AsyncClient = FakeServerAsyncClient


def test_transport_build_headers_and_urls():
    transport = HttpxRemoteSessionTransport(base_url="https://example.invalid", access_token="token-1", organization_uuid="org-1")

    headers = transport.build_headers()
    events_url = transport.build_events_url("session-1")
    archive_url = transport.build_archive_url("session-1")

    assert headers["Authorization"] == "Bearer token-1"
    assert headers["x-organization-uuid"] == "org-1"
    assert events_url == "https://example.invalid/v1/sessions/session-1/events"
    assert archive_url == "https://example.invalid/v1/sessions/session-1/archive"


@pytest.mark.asyncio
async def test_transport_create_session_uses_http_client():
    client = DummyHttpClient()
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token-1",
        organization_uuid="org-1",
        http_client=client,
    )

    payload = transport.build_create_session_payload(
        initial_message="hello remote",
        description="Refine local plan",
        model="claude-opus-4-6",
        permission_mode="plan",
        ultraplan=True,
    )
    result = await transport.create_session(payload)

    assert isinstance(result, RemoteSessionRef)
    assert result.session_id == "session-123"
    assert client.post_calls[0][0] == "https://example.invalid/v1/sessions"


@pytest.mark.asyncio
async def test_transport_create_session_prefers_backend_url():
    client = DummyHttpClientWithCustomResponses(
        post_response=DummyResponse({
            "id": "session-123",
            "title": "ultraplan: Refine local plan",
            "url": "https://console.example.invalid/sessions/session-123",
        })
    )
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token-1",
        organization_uuid="org-1",
        http_client=client,
    )

    payload = transport.build_create_session_payload(
        initial_message="hello remote",
        description="Refine local plan",
        model="claude-opus-4-6",
        permission_mode="plan",
        ultraplan=True,
    )
    result = await transport.create_session(payload)

    assert result.url == "https://console.example.invalid/sessions/session-123"


@pytest.mark.asyncio
async def test_transport_poll_and_archive_use_http_client():
    client = DummyHttpClient()
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token-1",
        organization_uuid="org-1",
        http_client=client,
    )

    response = await transport.poll_events("session-1", after_id="cursor-0", skip_metadata=True)
    await transport.archive_session("session-1")

    assert isinstance(response, PollRemoteSessionResponse)
    assert response.last_event_id == "cursor-1"
    assert client.get_calls[0][2] == {"after_id": "cursor-0"}
    assert client.post_calls[0][0] == "https://example.invalid/v1/sessions/session-1/archive"


@pytest.mark.asyncio
async def test_transport_poll_events_parses_branch_metadata():
    client = DummyHttpClientWithCustomResponses(
        get_response=DummyResponse(
            {"data": [], "last_id": "cursor-1", "branch": "main", "session_status": "idle"}
        )
    )
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token-1",
        organization_uuid="org-1",
        http_client=client,
    )

    response = await transport.poll_events("session-1")

    assert response.branch == "main"


def test_transport_can_build_runtime_httpx_client(monkeypatch):
    monkeypatch.setattr("ultraplan.remote_api.import_module", lambda name: FakeHttpxModule)
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token-1",
        organization_uuid="org-1",
        timeout_seconds=12.5,
        allow_stub_responses=False,
    )

    client = transport.build_runtime_http_client()

    assert isinstance(client, FakeAsyncClient)
    assert client.base_url == "https://example.invalid"
    assert client.timeout == 12.5
    assert client.headers["Authorization"] == "Bearer token-1"


@pytest.mark.asyncio
async def test_transport_create_session_with_runtime_client_closes_owned_client(monkeypatch):
    RuntimeFakeAsyncClient.instances.clear()
    monkeypatch.setattr("ultraplan.remote_api.import_module", lambda name: RuntimeFakeHttpxModule)
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token-1",
        organization_uuid="org-1",
        timeout_seconds=12.5,
        allow_stub_responses=False,
    )

    payload = transport.build_create_session_payload(
        initial_message="hello remote",
        description="Refine local plan",
        model="claude-opus-4-6",
        permission_mode="plan",
        ultraplan=True,
    )
    result = await transport.create_session(payload)

    assert result.session_id == "session-runtime"
    assert RuntimeFakeAsyncClient.instances[0].closed is True


@pytest.mark.asyncio
async def test_transport_create_session_rejects_missing_session_id():
    client = DummyHttpClientWithCustomResponses(post_response=DummyResponse({"title": "missing id"}))
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token-1",
        organization_uuid="org-1",
        http_client=client,
    )

    payload = transport.build_create_session_payload(
        initial_message="hello remote",
        description="Refine local plan",
        model="claude-opus-4-6",
        permission_mode="plan",
        ultraplan=True,
    )

    with pytest.raises(RemoteSessionResponseError, match="missing 'id'"):
        await transport.create_session(payload)


@pytest.mark.asyncio
async def test_transport_create_session_maps_auth_error():
    client = DummyHttpClientWithCustomResponses(post_response=DummyResponse({"message": "denied"}, status_code=401, text="denied"))
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token-1",
        organization_uuid="org-1",
        http_client=client,
    )

    payload = transport.build_create_session_payload(
        initial_message="hello remote",
        description="Refine local plan",
        model="claude-opus-4-6",
        permission_mode="plan",
        ultraplan=True,
    )

    with pytest.raises(RemoteSessionAuthError):
        await transport.create_session(payload)


@pytest.mark.asyncio
async def test_transport_poll_events_maps_not_found_error():
    client = DummyHttpClientWithCustomResponses(
        get_response=DummyResponse({"message": "missing"}, status_code=404, text="missing")
    )
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token-1",
        organization_uuid="org-1",
        http_client=client,
    )

    with pytest.raises(RemoteSessionNotFoundError):
        await transport.poll_events("session-1")


@pytest.mark.asyncio
async def test_transport_archive_session_maps_rate_limit_error():
    client = DummyHttpClientWithCustomResponses(
        post_response=DummyResponse({"message": "slow down"}, status_code=429, text="slow down")
    )
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token-1",
        organization_uuid="org-1",
        http_client=client,
    )

    with pytest.raises(RemoteSessionRateLimitError):
        await transport.archive_session("session-1")


@pytest.mark.asyncio
async def test_transport_archive_session_maps_server_error():
    client = DummyHttpClientWithCustomResponses(
        post_response=DummyResponse({"message": "server exploded"}, status_code=503, text="server exploded")
    )
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token-1",
        organization_uuid="org-1",
        http_client=client,
    )

    with pytest.raises(RemoteSessionServerError):
        await transport.archive_session("session-1")


@pytest.mark.asyncio
async def test_transport_poll_events_rejects_non_list_data():
    client = DummyHttpClientWithCustomResponses(
        get_response=DummyResponse({"data": {"not": "a list"}, "last_id": "cursor-1", "session_status": "idle"})
    )
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token-1",
        organization_uuid="org-1",
        http_client=client,
    )

    with pytest.raises(RemoteSessionResponseError, match="expected 'data' to be a list"):
        await transport.poll_events("session-1")




@pytest.mark.asyncio
async def test_transport_runtime_client_round_trip_fake_server(monkeypatch):
    FakeServerAsyncClient.instances.clear()
    FakeServerAsyncClient.shared_sessions.clear()
    FakeServerAsyncClient.archived_session_ids.clear()
    FakeServerAsyncClient.last_after_id = None
    monkeypatch.setattr("ultraplan.remote_api.import_module", lambda name: FakeServerHttpxModule)
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token-1",
        organization_uuid="org-1",
        timeout_seconds=12.5,
        allow_stub_responses=False,
    )

    payload = transport.build_create_session_payload(
        initial_message="hello remote",
        description="Refine local plan",
        model="claude-opus-4-6",
        permission_mode="plan",
        ultraplan=True,
    )
    session = await transport.create_session(payload)
    response = await transport.poll_events(session.session_id, after_id="cursor-0")
    await transport.archive_session(session.session_id)

    assert session.session_id == "session-fake-server"
    assert session.url == "https://console.example.invalid/sessions/session-fake-server"
    assert response.last_event_id == "cursor-fake-server"
    assert response.branch == "main"
    assert response.session_status == "running"
    assert FakeServerAsyncClient.last_after_id == "cursor-0"
    assert FakeServerAsyncClient.shared_sessions[session.session_id]["archived"] is True
    assert FakeServerAsyncClient.archived_session_ids == ["session-fake-server"]
    assert all(client.closed is True for client in FakeServerAsyncClient.instances)

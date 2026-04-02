from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from uuid import uuid4

from .errors import (
    RemoteSessionAuthError,
    RemoteSessionError,
    RemoteSessionNotFoundError,
    RemoteSessionRateLimitError,
    RemoteSessionResponseError,
    RemoteSessionServerError,
    RemoteSessionTransportError,
)
from .models import PollRemoteSessionResponse, RemoteSessionRef


@dataclass(slots=True)
class HttpxRemoteSessionTransport:
    base_url: str = "https://example.invalid"
    access_token: str = "token"
    organization_uuid: str = "org"
    http_client: object | None = None
    timeout_seconds: float = 30.0
    allow_stub_responses: bool = True

    def build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "x-organization-uuid": self.organization_uuid,
            "anthropic-beta": "ccr-byoc-2025-07-29",
        }

    def build_create_url(self) -> str:
        return f"{self.base_url}/v1/sessions"

    def build_events_url(self, session_id: str) -> str:
        return f"{self.base_url}/v1/sessions/{session_id}/events"

    def build_archive_url(self, session_id: str) -> str:
        return f"{self.base_url}/v1/sessions/{session_id}/archive"

    def build_runtime_http_client(self):
        httpx = import_module("httpx")
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            headers=self.build_headers(),
        )

    def build_create_session_payload(
        self,
        *,
        initial_message: str,
        description: str,
        model: str,
        permission_mode: str,
        ultraplan: bool,
    ) -> dict:
        api = RemoteSessionApi(base_url=self.base_url)
        return {
            "title": api.build_title(description, ultraplan=ultraplan),
            "events": api.build_initial_events(
                initial_message=initial_message,
                permission_mode=permission_mode,
                ultraplan=ultraplan,
            ),
            "session_context": {
                "model": model,
            },
        }

    def _resolve_http_client(self) -> tuple[object | None, bool]:
        if self.http_client is not None:
            return self.http_client, False
        if self.allow_stub_responses:
            return None, False
        return self.build_runtime_http_client(), True

    async def _close_http_client(self, client: object | None, owns_client: bool) -> None:
        if owns_client and client is not None and hasattr(client, "aclose"):
            await client.aclose()

    def _raise_for_http_status(self, response: object, operation: str) -> None:
        status_code = getattr(response, "status_code", 200) or 200
        if status_code < 400:
            return
        message = getattr(response, "text", "") or f"{operation} failed with status {status_code}"
        if status_code in (401, 403):
            raise RemoteSessionAuthError(message, status_code=status_code)
        if status_code == 404:
            raise RemoteSessionNotFoundError(message, status_code=status_code)
        if status_code == 429:
            raise RemoteSessionRateLimitError(message, status_code=status_code)
        if status_code >= 500:
            raise RemoteSessionServerError(message, status_code=status_code)
        raise RemoteSessionTransportError(message, status_code=status_code)

    def _parse_json_dict(self, response: object, operation: str) -> dict:
        try:
            data = response.json()
        except Exception as exc:
            raise RemoteSessionResponseError(f"{operation} returned invalid JSON", cause=exc) from exc
        if not isinstance(data, dict):
            raise RemoteSessionResponseError(f"{operation} expected a JSON object")
        return data

    async def create_session(self, payload: dict) -> RemoteSessionRef:
        client, owns_client = self._resolve_http_client()
        if client is None:
            session_id = str(uuid4())
            return RemoteSessionRef(
                session_id=session_id,
                title=payload["title"],
                url=f"{self.base_url}/sessions/{session_id}",
            )
        try:
            response = await client.post(
                self.build_create_url(),
                headers=self.build_headers(),
                json=payload,
            )
            self._raise_for_http_status(response, "create_session")
            data = self._parse_json_dict(response, "create_session")
            session_id = data.get("id")
            if not isinstance(session_id, str) or not session_id:
                raise RemoteSessionResponseError("create_session response missing 'id'")
            backend_url = data.get("url")
            if backend_url is not None and not isinstance(backend_url, str):
                raise RemoteSessionResponseError("create_session expected 'url' to be a string when present")
            return RemoteSessionRef(
                session_id=session_id,
                title=data.get("title", payload["title"]),
                url=backend_url or f"{self.base_url}/sessions/{session_id}",
            )
        except RemoteSessionError:
            raise
        except Exception as exc:
            raise RemoteSessionTransportError(str(exc), cause=exc) from exc
        finally:
            await self._close_http_client(client, owns_client)

    async def poll_events(
        self,
        session_id: str,
        after_id: str | None = None,
        skip_metadata: bool = False,
    ) -> PollRemoteSessionResponse:
        client, owns_client = self._resolve_http_client()
        if client is None:
            raise NotImplementedError("poll_events requires an HTTP client when stub responses are enabled")
        params = {"after_id": after_id} if after_id is not None else None
        try:
            response = await client.get(
                self.build_events_url(session_id),
                headers=self.build_headers(),
                params=params,
            )
            self._raise_for_http_status(response, "poll_events")
            data = self._parse_json_dict(response, "poll_events")
            new_events = data.get("data", [])
            if not isinstance(new_events, list):
                raise RemoteSessionResponseError("poll_events expected 'data' to be a list")
            last_event_id = data.get("last_id")
            if last_event_id is not None and not isinstance(last_event_id, str):
                raise RemoteSessionResponseError("poll_events expected 'last_id' to be a string or null")
            session_status = data.get("session_status")
            if session_status is not None and not isinstance(session_status, str):
                raise RemoteSessionResponseError("poll_events expected 'session_status' to be a string or null")
            branch = data.get("branch")
            if branch is not None and not isinstance(branch, str):
                raise RemoteSessionResponseError("poll_events expected 'branch' to be a string or null")
            return PollRemoteSessionResponse(
                new_events=new_events,
                last_event_id=last_event_id,
                branch=branch,
                session_status=None if skip_metadata else session_status,
            )
        except RemoteSessionError:
            raise
        except Exception as exc:
            raise RemoteSessionTransportError(str(exc), cause=exc) from exc
        finally:
            await self._close_http_client(client, owns_client)

    async def archive_session(self, session_id: str) -> None:
        client, owns_client = self._resolve_http_client()
        if client is None:
            return None
        try:
            response = await client.post(
                self.build_archive_url(session_id),
                headers=self.build_headers(),
                json={},
            )
            self._raise_for_http_status(response, "archive_session")
        except RemoteSessionError:
            raise
        except Exception as exc:
            raise RemoteSessionTransportError(str(exc), cause=exc) from exc
        finally:
            await self._close_http_client(client, owns_client)
        return None


@dataclass(slots=True)
class RemoteSessionApi:
    base_url: str = "https://example.invalid"
    transport: HttpxRemoteSessionTransport | None = field(default=None)

    def __post_init__(self) -> None:
        if self.transport is None:
            self.transport = HttpxRemoteSessionTransport(base_url=self.base_url)

    def build_title(self, description: str, *, ultraplan: bool) -> str:
        return f"ultraplan: {description}" if ultraplan else description

    def build_initial_events(
        self,
        *,
        initial_message: str,
        permission_mode: str,
        ultraplan: bool,
    ) -> list[dict]:
        return [
            {
                "type": "event",
                "data": {
                    "type": "control_request",
                    "request_id": f"set-mode-{uuid4()}",
                    "request": {
                        "subtype": "set_permission_mode",
                        "mode": permission_mode,
                        "ultraplan": ultraplan,
                    },
                },
            },
            {
                "type": "event",
                "data": {
                    "uuid": str(uuid4()),
                    "session_id": "",
                    "type": "user",
                    "parent_tool_use_id": None,
                    "message": {
                        "role": "user",
                        "content": initial_message,
                    },
                },
            },
        ]

    async def create_ultraplan_session(
        self,
        *,
        initial_message: str,
        description: str,
        model: str,
        permission_mode: str = "plan",
        ultraplan: bool = True,
    ) -> RemoteSessionRef:
        payload = self.transport.build_create_session_payload(
            initial_message=initial_message,
            description=description,
            model=model,
            permission_mode=permission_mode,
            ultraplan=ultraplan,
        )
        return await self.transport.create_session(payload)

    async def poll_remote_session_events(
        self,
        session_id: str,
        after_id: str | None = None,
        skip_metadata: bool = False,
    ) -> PollRemoteSessionResponse:
        return await self.transport.poll_events(
            session_id=session_id,
            after_id=after_id,
            skip_metadata=skip_metadata,
        )

    async def archive_remote_session(self, session_id: str) -> None:
        await self.transport.archive_session(session_id)

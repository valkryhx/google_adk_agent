from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.adk_agent.kairos.api import register_kairos_routes


class FakeRuntime:
    def __init__(self):
        self.started = False
        self.state = {
            "enabled": False,
            "mode": "stopped",
            "recent_events": [],
        }

    async def start(self):
        self.started = True
        self.state["enabled"] = True
        self.state["mode"] = "idle"

    async def stop(self):
        self.state["enabled"] = False
        self.state["mode"] = "stopped"

    async def wake(self, reason):
        self.state["recent_events"].append({"kind": "status", "message": reason})

    def get_status(self):
        return self.state


class FakeSession:
    def __init__(self):
        self.runtime = FakeRuntime()

    def get_or_create_kairos_runtime(self):
        return self.runtime


class FakeManager:
    def __init__(self):
        self.session = FakeSession()

    def get_or_create(self, app_name, user_id, session_id):
        return self.session


def test_start_and_status_routes_work():
    app = FastAPI()
    register_kairos_routes(app, FakeManager())
    client = TestClient(app)

    start_resp = client.post(
        "/api/sessions/session_1/kairos/start",
        json={"app_name": "demo", "user_id": "alice"},
    )
    assert start_resp.status_code == 200

    status_resp = client.get(
        "/api/sessions/session_1/kairos/status",
        params={"app_name": "demo", "user_id": "alice"},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["kairos"]["mode"] == "idle"

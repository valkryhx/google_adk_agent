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
            "schedules": [],
            "pending_triggers": [],
            "active_trigger": None,
            "last_tick_at": None,
            "tracked_dex_task_ids": [],
            "active_workflow": {
                "workflow_id": "demo_report_pipeline",
                "goal": "auto progress report stage",
                "status": "active",
                "current_stage": "phase1",
                "stages": [],
                "metadata": {},
            },
            "planned_actions": [
                {
                    "action_id": "create-report",
                    "kind": "create_dex_task",
                    "reason": "phase1_converged",
                    "payload": {"description": "generate final report"},
                    "status": "pending",
                }
            ],
            "task_summaries": [
                {
                    "task_id": "abc12345",
                    "status": "running",
                    "summary_text": "run report is still running",
                    "artifact_status": "pending",
                    "log_hint": ".dex/logs/alice/abc12345.log",
                    "result_summary": None,
                    "error_summary": None,
                }
            ],
            "decision_explanation": {
                "why_continued": "phase1_converged",
                "why_stopped": None,
                "missing_requirements": [],
            },
            "condition_tree": {
                "stage_id": "phase1",
                "stage_label": "prepare inputs",
                "satisfied": [],
                "missing": [],
            },
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

    async def add_schedule(self, schedule):
        self.state["schedules"] = [
            s for s in self.state["schedules"] if s["schedule_id"] != schedule.schedule_id
        ]
        self.state["schedules"].append(
            {"schedule_id": schedule.schedule_id, "cron": schedule.cron, "reason": schedule.reason}
        )

    async def delete_schedule(self, schedule_id):
        self.state["schedules"] = [
            s for s in self.state["schedules"] if s["schedule_id"] != schedule_id
        ]

    async def register_dex_task(self, task_id, description):
        self.state["tracked_dex_task_ids"].append(task_id)
        self.state["mode"] = "handoff"

    def get_status(self):
        return self.state


class FakeSession:
    def __init__(self, app_name="demo", user_id="alice", session_id="session_1"):
        self.app_name = app_name
        self.user_id = user_id
        self.session_id = session_id
        self.runtime = FakeRuntime()

    def get_or_create_kairos_runtime(self):
        return self.runtime

    async def ensure_kairos_runtime(self):
        return self.runtime


class FakeManager:
    def __init__(self):
        self.session = FakeSession()
        self._sessions = {
            ("demo", "alice", "session_1"): self.session,
        }

    def get_or_create(self, app_name, user_id, session_id):
        key = (app_name, user_id, session_id)
        if key not in self._sessions:
            self._sessions[key] = FakeSession(app_name, user_id, session_id)
        return self._sessions[key]


# === Phase 1 existing tests ===


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


def test_stop_route_works():
    app = FastAPI()
    register_kairos_routes(app, FakeManager())
    client = TestClient(app)

    client.post(
        "/api/sessions/session_1/kairos/start",
        json={"app_name": "demo", "user_id": "alice"},
    )
    stop_resp = client.post(
        "/api/sessions/session_1/kairos/stop",
        json={"app_name": "demo", "user_id": "alice"},
    )
    assert stop_resp.status_code == 200
    assert stop_resp.json()["kairos"]["mode"] == "stopped"


def test_wake_route_works():
    app = FastAPI()
    register_kairos_routes(app, FakeManager())
    client = TestClient(app)

    client.post(
        "/api/sessions/session_1/kairos/start",
        json={"app_name": "demo", "user_id": "alice"},
    )
    wake_resp = client.post(
        "/api/sessions/session_1/kairos/wake",
        json={"app_name": "demo", "user_id": "alice", "reason": "test_wake"},
    )
    assert wake_resp.status_code == 200
    events = wake_resp.json()["kairos"]["recent_events"]
    assert any(e["message"] == "test_wake" for e in events)


# === Phase 2 schedule route tests ===


def test_add_schedule_route_works():
    app = FastAPI()
    register_kairos_routes(app, FakeManager())
    client = TestClient(app)

    resp = client.post(
        "/api/sessions/session_1/kairos/schedules",
        json={
            "app_name": "demo",
            "user_id": "alice",
            "schedule_id": "morning",
            "cron": "*/5 * * * *",
            "reason": "morning_checkin",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["kairos"]["schedules"][0]["schedule_id"] == "morning"


def test_add_schedule_replaces_existing():
    app = FastAPI()
    register_kairos_routes(app, FakeManager())
    client = TestClient(app)

    client.post(
        "/api/sessions/session_1/kairos/schedules",
        json={
            "app_name": "demo",
            "user_id": "alice",
            "schedule_id": "morning",
            "cron": "*/5 * * * *",
            "reason": "old_reason",
        },
    )
    resp = client.post(
        "/api/sessions/session_1/kairos/schedules",
        json={
            "app_name": "demo",
            "user_id": "alice",
            "schedule_id": "morning",
            "cron": "*/10 * * * *",
            "reason": "new_reason",
        },
    )
    assert resp.status_code == 200
    schedules = resp.json()["kairos"]["schedules"]
    assert len(schedules) == 1
    assert schedules[0]["reason"] == "new_reason"


def test_delete_schedule_route_works():
    app = FastAPI()
    register_kairos_routes(app, FakeManager())
    client = TestClient(app)

    client.post(
        "/api/sessions/session_1/kairos/schedules",
        json={
            "app_name": "demo",
            "user_id": "alice",
            "schedule_id": "morning",
            "cron": "*/5 * * * *",
            "reason": "morning_checkin",
        },
    )
    resp = client.delete(
        "/api/sessions/session_1/kairos/schedules/morning",
        params={"app_name": "demo", "user_id": "alice"},
    )
    assert resp.status_code == 200
    assert resp.json()["kairos"]["schedules"] == []


def test_register_dex_route_works():
    app = FastAPI()
    register_kairos_routes(app, FakeManager())
    client = TestClient(app)

    resp = client.post(
        "/api/sessions/session_1/kairos/dex/register",
        json={
            "app_name": "demo",
            "user_id": "alice",
            "task_id": "abc12345",
            "description": "run report",
        },
    )
    assert resp.status_code == 200
    assert "abc12345" in resp.json()["kairos"]["tracked_dex_task_ids"]
    assert resp.json()["kairos"]["mode"] == "handoff"


def test_status_route_exposes_tracked_dex_task_details():
    app = FastAPI()
    manager = FakeManager()
    session = manager.get_or_create("demo", "alice", "session_1")
    session.runtime.state["tracked_dex_task_ids"] = ["abc12345"]
    session.runtime.state["tracked_dex_tasks"] = [
        {
            "task_id": "abc12345",
            "status": "running",
            "description": "run report",
            "result_summary": None,
            "error_summary": None,
            "created_at": "2026-04-04T00:00:00+00:00",
            "completed_at": None,
            "log_path": ".dex/logs/alice/abc12345.log",
        }
    ]
    register_kairos_routes(app, manager)
    client = TestClient(app)

    resp = client.get(
        "/api/sessions/session_1/kairos/status",
        params={"app_name": "demo", "user_id": "alice"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    tracked = payload["kairos"]["tracked_dex_tasks"]
    assert len(tracked) == 1
    assert tracked[0]["task_id"] == "abc12345"
    assert tracked[0]["log_path"] == ".dex/logs/alice/abc12345.log"
    assert payload["active_workflow"]["workflow_id"] == "demo_report_pipeline"
    assert payload["planned_actions"][0]["kind"] == "create_dex_task"
    assert payload["blocked_reason"] is None


def test_status_route_preserves_existing_fields_and_adds_reporting_fields():
    app = FastAPI()
    manager = FakeManager()
    register_kairos_routes(app, manager)
    client = TestClient(app)

    resp = client.get(
        "/api/sessions/session_1/kairos/status",
        params={"app_name": "demo", "user_id": "alice"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert "kairos" in payload
    assert "active_workflow" in payload
    assert "planned_actions" in payload
    assert "blocked_reason" in payload
    assert payload["kairos"]["task_summaries"][0]["task_id"] == "abc12345"
    assert payload["kairos"]["decision_explanation"]["why_continued"] == "phase1_converged"
    assert payload["kairos"]["condition_tree"]["stage_id"] == "phase1"
    assert payload["task_summaries"][0]["task_id"] == "abc12345"
    assert payload["decision_explanation"]["missing_requirements"] == []
    assert payload["condition_tree"]["missing"] == []


def test_status_route_exposes_todo_delivery_workflow_when_active():
    app = FastAPI()
    manager = FakeManager()
    session = manager.get_or_create("demo", "alice", "session_1")
    session.runtime.state["active_workflow"] = {
        "workflow_id": "todo_delivery_pipeline",
        "goal": "deliver todo app artifacts",
        "status": "active",
        "current_stage": "delivery_report",
        "stages": [
            {
                "stage_id": "delivery_report",
                "label": "delivery report",
                "status": "running",
                "task_ids": ["todo-report-task"],
                "artifacts": ["demo_delivery/todo_app/delivery_report.md"],
                "summary": None,
            }
        ],
        "metadata": {},
    }
    session.runtime.state["planned_actions"] = [
        {
            "action_id": "todo-report",
            "kind": "create_dex_task",
            "reason": "todo_delivery_ready",
            "payload": {"description": "generate todo delivery report"},
            "status": "pending",
        }
    ]
    register_kairos_routes(app, manager)
    client = TestClient(app)

    resp = client.get(
        "/api/sessions/session_1/kairos/status",
        params={"app_name": "demo", "user_id": "alice"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["kairos"]["active_workflow"]["workflow_id"] == "todo_delivery_pipeline"
    assert payload["kairos"]["planned_actions"][0]["payload"]["description"] == "generate todo delivery report"
    assert payload["active_workflow"]["stages"][0]["artifacts"][0] == "demo_delivery/todo_app/delivery_report.md"


# === Phase 2 attach/list route tests ===


def test_list_kairos_sessions_route_works():
    app = FastAPI()
    manager = FakeManager()
    # Ensure the session has a runtime
    session = manager.get_or_create("demo", "alice", "session_1")
    register_kairos_routes(app, manager)
    client = TestClient(app)

    resp = client.get("/api/kairos/sessions", params={"user_id": "alice"})
    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    assert len(sessions) >= 1
    assert sessions[0]["session_id"] == "session_1"


def test_list_kairos_sessions_filters_by_user():
    app = FastAPI()
    manager = FakeManager()
    manager.get_or_create("demo", "bob", "session_bob")
    register_kairos_routes(app, manager)
    client = TestClient(app)

    resp = client.get("/api/kairos/sessions", params={"user_id": "bob"})
    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    assert all(s["user_id"] == "bob" for s in sessions)


def test_attach_route_works():
    app = FastAPI()
    manager = FakeManager()
    register_kairos_routes(app, manager)
    client = TestClient(app)

    resp = client.get(
        "/api/sessions/session_1/kairos/attach",
        params={"app_name": "demo", "user_id": "alice"},
    )
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "session_1"
    assert "kairos" in resp.json()
    assert "attach" in resp.json()
    assert resp.json()["attach"]["session_id"] == "session_1"

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
            "document_work_items": [],
            "document_progress": {},
            "pending_requirements": [],
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






def test_history_route_supports_ascending_order(monkeypatch):
    app = FastAPI()
    manager = FakeManager()
    register_kairos_routes(app, manager)
    client = TestClient(app)

    class FakeHistory:
        def read_session_history(self, user_id, app_name, session_id, descending=True):
            assert descending is False
            return [
                {"ts": "2026-04-09T10:00:00", "kind": "brief", "title": "Brief", "message": "older", "workflow": None, "stage": None, "task_id": None, "metadata": {}},
                {"ts": "2026-04-09T10:05:00", "kind": "brief", "title": "Brief", "message": "newer", "workflow": None, "stage": None, "task_id": None, "metadata": {}},
            ]

    monkeypatch.setattr("src.adk_agent.kairos.api.KairosActivityLog", lambda *_args, **_kwargs: FakeHistory())

    resp = client.get(
        "/api/sessions/session_1/kairos/history",
        params={"app_name": "demo", "user_id": "alice", "descending": "false"},
    )

    assert resp.status_code == 200
    assert resp.json()["history"][0]["message"] == "older"


def test_attach_route_includes_has_history_hint(monkeypatch):
    app = FastAPI()
    manager = FakeManager()
    register_kairos_routes(app, manager)
    client = TestClient(app)

    class FakeHistory:
        def read_session_history(self, user_id, app_name, session_id, descending=True):
            return [{"ts": "2026-04-09T10:00:00"}]

    monkeypatch.setattr("src.adk_agent.kairos.attach.KairosActivityLog", lambda *_args, **_kwargs: FakeHistory())

    resp = client.get(
        "/api/sessions/session_1/kairos/attach",
        params={"app_name": "demo", "user_id": "alice"},
    )

    assert resp.status_code == 200
    assert resp.json()["attach"]["has_history"] is True


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


def test_status_route_exposes_proactive_scan_fields():
    app = FastAPI()
    manager = FakeManager()
    session = manager.get_or_create("demo", "alice", "session_1")
    session.runtime.state["unfinished_work_items"] = [{"work_id": "todo:codegen", "stage_id": "codegen"}]
    session.runtime.state["proactive_candidates"] = [{"candidate_id": "todo:codegen", "action": "continue_workflow"}]
    session.runtime.state["last_proactive_scan"] = {"result": "candidate_found"}
    session.runtime.state["last_guardrail_block"] = {"reason": "cooldown_active"}
    session.runtime.state["last_planning_result"] = {
        "ts": "2026-04-10T08:30:00+00:00",
        "goal": "advance todo delivery pipeline toward shippable report",
        "workflow_id": "todo_delivery_pipeline",
        "stage_id": "verification",
        "candidates_considered": [],
        "selected_candidate": {"action": "continue_workflow", "candidate_id": "todo:continue"},
        "rejected_candidates": [{"action": "sleep", "rejected_reason": "higher tier candidate selected"}],
        "final_action": {"kind": "continue_workflow_scan"},
        "policy_note": "winner retained under tiered-action policy",
        "replan": {"changed": False},
    }
    register_kairos_routes(app, manager)
    client = TestClient(app)

    resp = client.get(
        "/api/sessions/session_1/kairos/status",
        params={"app_name": "demo", "user_id": "alice"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["unfinished_work_items"][0]["stage_id"] == "codegen"
    assert payload["proactive_candidates"][0]["action"] == "continue_workflow"
    assert payload["last_proactive_scan"]["result"] == "candidate_found"
    assert payload["last_guardrail_block"]["reason"] == "cooldown_active"
    assert payload["last_planning_result"]["selected_candidate"]["action"] == "continue_workflow"
    assert payload["last_planning_result"]["final_action"]["kind"] == "continue_workflow_scan"
    assert payload["planning_winner"]["action"] == "continue_workflow"
    assert payload["planning_rejected_summary"][0]["action"] == "sleep"
    assert payload["planning_replan"]["changed"] is False


def test_attach_route_stays_lightweight_without_history_array(monkeypatch):
    app = FastAPI()
    manager = FakeManager()
    register_kairos_routes(app, manager)
    client = TestClient(app)

    class FakeHistory:
        def read_session_history(self, user_id, app_name, session_id, descending=True):
            return [{"ts": "2026-04-09T10:00:00"}]

    monkeypatch.setattr("src.adk_agent.kairos.attach.KairosActivityLog", lambda *_args, **_kwargs: FakeHistory())

    resp = client.get(
        "/api/sessions/session_1/kairos/attach",
        params={"app_name": "demo", "user_id": "alice"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["attach"]["has_history"] is True
    assert "history" not in payload["attach"]
    assert "last_planning_result" not in payload["attach"]




def test_status_route_exposes_spawned_work_items():
    app = FastAPI()
    manager = FakeManager()
    session = manager.get_or_create("demo", "alice", "session_1")
    session.runtime.state["document_work_items"] = [
        {
            "work_id": "work:session-123:follow-up",
            "goal": "verify generated todo delivery report",
            "status": "pending",
            "current_step": "verification",
            "next_actions": ["check delivery_report.md", "write follow-up note"],
            "blockers": [],
            "expected_artifacts": ["requirements/session-123/work.md", "demo_delivery/todo_app/delivery_report.md"],
            "open_questions": [],
            "human_input_required": False,
            "source_docs": ["requirements/session-123/work.md"],
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
    assert payload["kairos"]["document_work_items"][0]["work_id"] == "work:session-123:follow-up"
    assert payload["kairos"]["document_work_items"][0]["current_step"] == "verification"
    assert payload["kairos"]["document_work_items"][0]["source_docs"] == ["requirements/session-123/work.md"]
    assert payload["pending_requirements"] == []


def test_status_route_exposes_document_progress_and_attempts():
    app = FastAPI()
    manager = FakeManager()
    session = manager.get_or_create("demo", "alice", "session_1")
    session.runtime.state["document_work_items"] = [
        {
            "work_id": "work:python-cli",
            "goal": "build python cli",
            "status": "in_progress",
            "current_step": "design",
            "next_actions": ["write cli outline"],
            "blockers": [],
            "expected_artifacts": ["requirements/session-1/work.md"],
            "open_questions": [],
            "human_input_required": False,
            "source_docs": ["requirements/session-1/work.md"],
        }
    ]
    session.runtime.state["document_progress"] = {
        "document_work_count": 1,
        "active_attempt": {
            "attempt_id": "attempt-1",
            "work_id": "work:python-cli",
            "step_id": "design",
            "action_kind": "run_dex_task",
            "status": "started",
            "doc_fingerprint": "abc123",
            "created_at": "2026-04-14T00:00:00+00:00",
            "completed_at": None,
            "result_summary": "dex task created",
        },
        "step_attempts": [
            {
                "attempt_id": "attempt-1",
                "work_id": "work:python-cli",
                "step_id": "design",
                "action_kind": "run_dex_task",
                "status": "started",
                "doc_fingerprint": "abc123",
                "created_at": "2026-04-14T00:00:00+00:00",
                "completed_at": None,
                "result_summary": "dex task created",
            }
        ],
    }
    session.runtime.state["step_attempts"] = [
        {
            "attempt_id": "attempt-1",
            "work_id": "work:python-cli",
            "step_id": "design",
            "action_kind": "run_dex_task",
            "status": "started",
            "doc_fingerprint": "abc123",
            "created_at": "2026-04-14T00:00:00+00:00",
            "completed_at": None,
            "result_summary": "dex task created",
        }
    ]
    session.runtime.state["last_planning_result"] = {
        "ts": "2026-04-14T00:00:00+00:00",
        "goal": "build python cli",
        "workflow_id": None,
        "stage_id": "design",
        "candidates_considered": [],
        "selected_candidate": {"action": "continue_workflow", "candidate_id": "work:python-cli:design:continue_workflow"},
        "rejected_candidates": [],
        "final_action": {"kind": "run_dex_task", "payload": {"description": "write cli outline"}},
        "policy_note": "winner chosen under tiered-action policy",
        "replan": {"changed": False},
    }
    register_kairos_routes(app, manager)
    client = TestClient(app)

    resp = client.get(
        "/api/sessions/session_1/kairos/status",
        params={"app_name": "demo", "user_id": "alice"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["document_progress"]["document_work_count"] == 1
    assert payload["document_progress"]["document_work_count"] == 1
    assert payload["document_progress"]["active_attempt"]["attempt_id"] == "attempt-1"
    assert payload["document_progress"]["step_attempts"][0]["action_kind"] == "run_dex_task"
    assert payload["last_planning_result"]["final_action"]["kind"] == "run_dex_task"




def test_status_route_exposes_llm_autonomy_state_fields():
    app = FastAPI()
    manager = FakeManager()
    session = manager.get_or_create("demo", "alice", "session_1")
    session.runtime.state["current_understanding"] = {"goal": "build python cli", "constraints": ["use flask"]}
    session.runtime.state["current_execution_plan"] = {"plan_id": "plan-1", "steps": [{"step_id": "requirements", "action_kind": "spawn_dex_task"}]}
    session.runtime.state["last_verification_result"] = {"attempt_id": "attempt-1", "verdict": "partial"}
    session.runtime.state["last_replan_result"] = {"replan_reason": "verification gap", "retryable": True}
    session.runtime.state["current_action_payload"] = {"action_kind": "spawn_dex_task", "command_template_id": "generate_design_brief", "description": "generate design brief"}
    register_kairos_routes(app, manager)
    client = TestClient(app)

    resp = client.get(
        "/api/sessions/session_1/kairos/status",
        params={"app_name": "demo", "user_id": "alice"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["current_understanding"]["goal"] == "build python cli"
    assert payload["current_execution_plan"]["plan_id"] == "plan-1"
    assert payload["last_verification_result"]["verdict"] == "partial"
    assert payload["last_replan_result"]["replan_reason"] == "verification gap"
    assert payload["kairos"]["current_action_payload"]["command_template_id"] == "generate_design_brief"


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

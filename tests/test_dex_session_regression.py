import importlib.util
import types
from pathlib import Path

import pytest

from skills.dex.tools import DexManager
from src.adk_agent.kairos.models import DocumentReadResult
from src.adk_agent.main_web_start_steering import SteeringSession


_MODULE_PATH = Path(__file__).resolve().parents[1] / "skills" / "programmatic-tool-calling" / "tools.py"
_SPEC = importlib.util.spec_from_file_location("skills.programmatic_tool_calling.tools", _MODULE_PATH)
ptc_tools = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(ptc_tools)


class FakeSkillManager:
    def __init__(self, skills):
        self._skills = set(skills)

    def skill_exists(self, skill_id):
        return skill_id in self._skills

    def load_full_sop(self, skill_id):
        return f"SOP for {skill_id}"


class FakeAgent:
    def __init__(self, tools):
        self.tools = tools


def _make_named_tool(name):
    def _tool(**kwargs):
        return kwargs
    _tool.__name__ = name
    return _tool


@pytest.mark.asyncio
async def test_session_warn_then_reload_restores_dex_for_programmatic_calling(tmp_path):
    skill_root = tmp_path / "skills"
    dex_dir = skill_root / "dex"
    dex_dir.mkdir(parents=True, exist_ok=True)
    (dex_dir / "tools.py").write_text("# fake dex tools\n", encoding="utf-8")

    session = SteeringSession.__new__(SteeringSession)
    session.key = ("dynamic_expert", "user_001", "session_test")
    session.skill_manager = FakeSkillManager(["dex"])
    session._loaded_skills = []
    session._skill_tools_map = {}
    session.config = types.SimpleNamespace(skills_path=str(skill_root))

    async def _placeholder_skill_load(skill_id):
        return skill_id

    async def _placeholder_skill_reload(skill_id):
        return skill_id

    base_tools = [_placeholder_skill_load, _placeholder_skill_reload]
    base_tools[0].__name__ = "skill_load"
    base_tools[1].__name__ = "skill_reload"
    session.agent = FakeAgent(list(base_tools))

    def dex_list_tasks(show_all=False):
        return "[]" if show_all else "[pending]"

    dex_list_tasks.__name__ = "dex_list_tasks"

    def fake_load_skill_tools(skill_id, force_reload=False):
        if skill_id != "dex":
            return []

        if not force_reload:
            return []

        existing_names = {getattr(tool, "__name__", str(tool)) for tool in session.agent.tools}
        if "dex_list_tasks" not in existing_names:
            session.agent.tools.append(dex_list_tasks)
        if "dex" not in session._loaded_skills:
            session._loaded_skills.append("dex")
        session._skill_tools_map["dex"] = {"dex_list_tasks"}
        return [dex_list_tasks]

    session._load_skill_tools = fake_load_skill_tools

    warn_result = await session.skill_load("dex")
    assert warn_result.startswith("[WARN]")

    run_programmatic_task = ptc_tools.get_tools(session.agent, session_service=None)[0]
    session.agent.tools.append(run_programmatic_task)

    missing_output = await ptc_tools.run_programmatic_task(
        "print(await call_tool('dex_list_tasks', show_all=True))"
    )
    assert "[DIAG]" in missing_output
    assert "loaded_dex_tools=[]" in missing_output

    reload_result = await session.skill_reload("dex")
    assert reload_result.startswith("[OK]")
    assert "dex_list_tasks" in reload_result



def test_restore_dynamic_skills_records_recovery_diagnostics(tmp_path):
    session = SteeringSession.__new__(SteeringSession)
    session.key = ("dynamic_expert", "user_001", "session_test")
    session._loaded_skills = ["dex"]
    session._last_skill_load_diagnostics = {
        "dex": {
            "status": "loaded",
            "force_reload": False,
            "error_type": None,
            "error": None,
        }
    }

    logs = []
    session._append_debug_log = logs.append

    def skill_load(**kwargs):
        return kwargs

    skill_load.__name__ = "skill_load"
    session.agent = FakeAgent([skill_load])

    def dex_list_tasks(show_all=False):
        return "[]"

    dex_list_tasks.__name__ = "dex_list_tasks"

    def fake_load_skill_tools(skill_id, force_reload=False):
        session.agent.tools.append(dex_list_tasks)
        session._last_skill_load_diagnostics[skill_id] = {
            "status": "loaded",
            "force_reload": force_reload,
            "error_type": None,
            "error": None,
        }
        return [dex_list_tasks]

    session._load_skill_tools = fake_load_skill_tools

    session._restore_dynamic_skills()

    assert any("正在恢复动态技能工具" in line for line in logs)


def test_get_or_create_kairos_runtime_uses_real_project_root_for_path_checks(tmp_path):
    session = SteeringSession.__new__(SteeringSession)
    session.kairos_runtime = None
    session._current_session = types.SimpleNamespace(state={})
    session._save_kairos_state = lambda state: None
    session._emit_kairos_event = lambda event: None
    session._append_kairos_log = lambda event: None
    session.run_kairos_turn = lambda reason: None
    session.user_id = "alice"
    session.create_kairos_follow_up_task = lambda description, reason, payload=None: None

    runtime = session.get_or_create_kairos_runtime()

    assert runtime._path_exists("CLAUDE.md") is True
    assert runtime._path_exists("demo_outputs/this-file-should-not-exist.json") is False


@pytest.mark.asyncio
async def test_create_kairos_follow_up_task_supports_todo_delivery_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    todo_dir = tmp_path / "demo_delivery" / "todo_app"
    todo_dir.mkdir(parents=True, exist_ok=True)
    (todo_dir / "requirements.md").write_text("# req\n", encoding="utf-8")
    (todo_dir / "design.md").write_text("# design\n", encoding="utf-8")
    (todo_dir / "smoke_check.json").write_text('{"ready": true}', encoding="utf-8")

    session = SteeringSession.__new__(SteeringSession)
    session.user_id = "alice"
    saved_states = []
    recorded = []

    async def save_state(state):
        saved_states.append(state)

    async def record(kind, message):
        recorded.append((kind, message))

    runtime = types.SimpleNamespace(
        state=types.SimpleNamespace(
            planned_actions=[],
            active_workflow=types.SimpleNamespace(
                stages=[
                    types.SimpleNamespace(stage_id="requirements", task_ids=[], status="completed"),
                    types.SimpleNamespace(stage_id="design", task_ids=[], status="completed"),
                    types.SimpleNamespace(stage_id="codegen", task_ids=[], status="completed"),
                    types.SimpleNamespace(stage_id="verification", task_ids=[], status="completed"),
                    types.SimpleNamespace(stage_id="delivery_report", task_ids=["todo_delivery_report"], status="pending"),
                ]
            ),
        ),
        register_dex_task=None,
        _record=record,
    )

    async def register_dex_task(task_id, description):
        runtime.state.active_workflow.stages[4].task_ids = [task_id]
        runtime.state.active_workflow.stages[4].status = "running"

    runtime.register_dex_task = register_dex_task
    session.get_or_create_kairos_runtime = lambda: runtime
    session._save_kairos_state = save_state

    def fake_start_background_process(self, task_id, command_parts):
        report_path = tmp_path / "demo_delivery" / "todo_app" / "delivery_report.md"
        report_path.write_text(
            "# Todo Delivery Report\n\nReady: True\n",
            encoding="utf-8",
        )
        self.store.mark_running(task_id, command=list(command_parts), pid=12345)

    monkeypatch.setattr(DexManager, "start_background_process", fake_start_background_process)

    task = await session.create_kairos_follow_up_task(
        "generate todo delivery report",
        "todo_delivery_ready",
        {"workflow_id": "todo_delivery_pipeline", "description": "generate todo delivery report"},
    )

    report_path = tmp_path / "demo_delivery" / "todo_app" / "delivery_report.md"
    assert task["description"] == "generate todo delivery report"
    assert report_path.exists()
    assert "Ready: True" in report_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_create_kairos_follow_up_task_persists_spawned_work_to_requirement_doc(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    requirement_dir = tmp_path / "requirements" / "session-123"
    requirement_dir.mkdir(parents=True, exist_ok=True)
    work_doc = requirement_dir / "work.md"
    work_doc.write_text(
        "# Work Item: deliver todo app\n\n"
        "## Goal\ndeliver todo app\n\n"
        "## Current Status\nin_progress\n\n"
        "## Current Step\nverification\n\n"
        "## Steps\n- verify generated todo delivery report\n\n"
        "## Expected Artifacts\n- requirements/session-123/work.md\n\n"
        "## Blockers\n- none\n\n"
        "## Verification\n- confirm requirement scope with user\n\n"
        "## Replan Notes\n- no replans yet\n\n"
        "## Spawned Work\n- none yet\n",
        encoding="utf-8",
    )

    session = SteeringSession.__new__(SteeringSession)
    session.user_id = "alice"
    session.session_id = "session-123"
    saved_states = []
    recorded = []

    async def save_state(state):
        saved_states.append(state)

    async def record(kind, message):
        recorded.append((kind, message))

    runtime = types.SimpleNamespace(
        state=types.SimpleNamespace(
            planned_actions=[],
            active_workflow=types.SimpleNamespace(stages=[]),
            document_work_items=[],
        ),
        register_dex_task=None,
        _record=record,
        _continuation_engine=types.SimpleNamespace(refresh_unfinished_work=lambda state: None),
    )

    async def register_dex_task(task_id, description):
        return None

    runtime.register_dex_task = register_dex_task
    session.get_or_create_kairos_runtime = lambda: runtime
    session._save_kairos_state = save_state

    def fake_start_background_process(self, task_id, command_parts):
        self.store.mark_running(task_id, command=list(command_parts), pid=12345)

    monkeypatch.setattr(DexManager, "start_background_process", fake_start_background_process)
    monkeypatch.setattr("src.adk_agent.main_web_start_steering._PROJECT_ROOT", str(tmp_path))

    task = await session.create_kairos_follow_up_task(
        "generate todo delivery report",
        "todo_delivery_ready",
        {
            "workflow_id": "todo_delivery_pipeline",
            "description": "generate todo delivery report",
            "source_doc": "requirements/session-123/work.md",
            "work_id": "work:session-123:follow-up",
            "goal": "verify generated todo delivery report",
            "current_step": "verification",
            "expected_artifacts": [
                "requirements/session-123/work.md",
                "demo_delivery/todo_app/delivery_report.md",
            ],
            "next_actions": ["check delivery_report.md"],
        },
    )

    doc_text = work_doc.read_text(encoding="utf-8")
    assert task["description"] == "generate todo delivery report"
    assert "## Replan Notes" in doc_text
    assert "todo_delivery_ready" in doc_text
    assert "## Spawned Work" in doc_text
    assert "work:session-123:follow-up" in doc_text
    assert runtime.state.document_work_items
    assert isinstance(runtime.state.document_work_items[0], DocumentReadResult)
    assert runtime.state.document_work_items[0].work_id == "work:session-123:follow-up"
    assert runtime.state.document_work_items[0].source_docs == ["requirements/session-123/work.md"]
    assert saved_states
    assert any("spawned work persisted" in message for _, message in recorded)

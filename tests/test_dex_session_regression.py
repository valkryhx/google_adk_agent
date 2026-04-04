import importlib.util
import types
from pathlib import Path

import pytest

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
    assert any("动态技能恢复结果" in line and "skill=dex" in line for line in logs)
    assert any("new_tools=['dex_list_tasks']" in line for line in logs)

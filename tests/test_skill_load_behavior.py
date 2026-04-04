import types

import pytest

from src.adk_agent.main_web_start_steering import SteeringSession


class FakeSkillManager:
    def __init__(self, skills):
        self._skills = set(skills)

    def skill_exists(self, skill_id):
        return skill_id in self._skills

    def load_full_sop(self, skill_id):
        return f"SOP for {skill_id}"


def make_session(tmp_path, *, skills, loaded_skills=None, load_result=None, with_tools_py=False):
    session = SteeringSession.__new__(SteeringSession)
    session.key = ("dynamic_expert", "user_001", "session_test")
    session.skill_manager = FakeSkillManager(skills)
    session._loaded_skills = list(loaded_skills or [])
    session.config = types.SimpleNamespace(skills_path=str(tmp_path / "skills"))

    skill_root = tmp_path / "skills"
    skill_root.mkdir(parents=True, exist_ok=True)
    for skill_id in skills:
        skill_dir = skill_root / skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)
        if with_tools_py and skill_id == "dex":
            (skill_dir / "tools.py").write_text("# fake dex tools\n", encoding="utf-8")

    session._load_skill_tools = lambda skill_id: list(load_result or [])
    return session


@pytest.mark.asyncio
async def test_skill_load_warns_when_skill_has_tools_file_but_no_tools_loaded(tmp_path):
    session = make_session(
        tmp_path,
        skills=["dex"],
        loaded_skills=[],
        load_result=[],
        with_tools_py=True,
    )

    result = await session.skill_load("dex")

    assert result.startswith("[WARN]")
    assert "dex" in result
    assert "未成功加载" in result


@pytest.mark.asyncio
async def test_skill_load_keeps_ok_semantics_for_already_loaded_skill(tmp_path):
    session = make_session(
        tmp_path,
        skills=["dex"],
        loaded_skills=["dex"],
        load_result=[],
        with_tools_py=True,
    )

    result = await session.skill_load("dex")

    assert result.startswith("[OK]")
    assert "dex" in result


@pytest.mark.asyncio
async def test_skill_load_keeps_ok_for_instruction_only_skill_without_tools_file(tmp_path):
    session = make_session(
        tmp_path,
        skills=["guide_only"],
        loaded_skills=[],
        load_result=[],
        with_tools_py=False,
    )

    result = await session.skill_load("guide_only")

    assert result.startswith("[OK]")
    assert "guide_only" in result


@pytest.mark.asyncio
async def test_skill_load_warns_with_diagnostic_details_when_tools_import_fails(tmp_path):
    skill_root = tmp_path / "skills"
    dex_dir = skill_root / "dex"
    dex_dir.mkdir(parents=True, exist_ok=True)
    (dex_dir / "tools.py").write_text(
        "raise RuntimeError('boom from dex import')\n",
        encoding="utf-8",
    )

    session = SteeringSession.__new__(SteeringSession)
    session.key = ("dynamic_expert", "user_001", "session_test")
    session.app_name = "dynamic_expert"
    session.user_id = "user_001"
    session.session_id = "session_test"
    session.skill_manager = FakeSkillManager(["dex"])
    session._loaded_skills = []
    session.config = types.SimpleNamespace(skills_path=str(skill_root))
    session.session_service = None
    session.queue = None
    session.report_swarm_event = lambda *args, **kwargs: None
    session.agent = types.SimpleNamespace(tools=[])

    result = await session.skill_load("dex")



@pytest.mark.asyncio
async def test_skill_reload_warns_with_diagnostic_details_when_force_reload_import_fails(tmp_path):
    skill_root = tmp_path / "skills"
    dex_dir = skill_root / "dex"
    dex_dir.mkdir(parents=True, exist_ok=True)
    (dex_dir / "tools.py").write_text(
        "raise RuntimeError('boom during force reload')\n",
        encoding="utf-8",
    )

    session = SteeringSession.__new__(SteeringSession)
    session.key = ("dynamic_expert", "user_001", "session_test")
    session.app_name = "dynamic_expert"
    session.user_id = "user_001"
    session.session_id = "session_test"
    session.skill_manager = FakeSkillManager(["dex"])
    session._loaded_skills = ["dex"]
    session._skill_tools_map = {"dex": {"dex_list_tasks"}}
    session.config = types.SimpleNamespace(skills_path=str(skill_root))
    session.session_service = None
    session.queue = None
    session.report_swarm_event = lambda *args, **kwargs: None

    def dex_list_tasks(show_all=False):
        return "[]"

    dex_list_tasks.__name__ = "dex_list_tasks"
    session.agent = types.SimpleNamespace(tools=[dex_list_tasks])

    result = await session.skill_reload("dex")

    assert result.startswith("[WARN]")
    assert "RuntimeError" in result
    assert "boom during force reload" in result
    assert "force_reload: True" in result
    assert str(dex_dir / "tools.py") in result

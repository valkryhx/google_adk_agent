import types
from pathlib import Path

import pytest

from src.adk_agent.main_web_start_steering import SteeringSession


@pytest.mark.asyncio
async def test_dynamic_loader_can_import_real_dex_tools_from_repo():
    repo_root = Path(__file__).resolve().parents[1]

    session = SteeringSession.__new__(SteeringSession)
    session.key = ("dynamic_expert", "user_001", "session_test")
    session.app_name = "dynamic_expert"
    session.user_id = "user_001"
    session.session_id = "session_test"
    session.config = types.SimpleNamespace(skills_path=str(repo_root / "skills"))
    session.session_service = None
    session.queue = None
    session.report_swarm_event = lambda *args, **kwargs: None

    async def _placeholder_skill_load(skill_id):
        return skill_id

    async def _placeholder_skill_reload(skill_id):
        return skill_id

    _placeholder_skill_load.__name__ = "skill_load"
    _placeholder_skill_reload.__name__ = "skill_reload"
    session.agent = types.SimpleNamespace(tools=[_placeholder_skill_load, _placeholder_skill_reload])

    tools = session._load_skill_tools("dex")

    assert [tool.__name__ for tool in tools] == [
        "dex_create_task",
        "dex_start_task",
        "dex_list_tasks",
        "dex_get_task_details",
    ]

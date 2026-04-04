import importlib.util
from pathlib import Path

import pytest


_MODULE_PATH = Path(__file__).resolve().parents[1] / "skills" / "programmatic-tool-calling" / "tools.py"
_SPEC = importlib.util.spec_from_file_location("skills.programmatic_tool_calling.tools", _MODULE_PATH)
ptc_tools = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(ptc_tools)


class FakeAgent:
    def __init__(self, tools):
        self.tools = tools


def _make_named_tool(name):
    def _tool(**kwargs):
        return kwargs
    _tool.__name__ = name
    return _tool


@pytest.mark.asyncio
async def test_run_programmatic_task_reports_structured_dex_diagnostic_when_dex_tool_missing(monkeypatch):
    agent = FakeAgent([
        _make_named_tool("skill_load"),
        _make_named_tool("skill_reload"),
        _make_named_tool("run_programmatic_task"),
    ])
    ptc_tools.get_tools(agent, session_service=None)

    output = await ptc_tools.run_programmatic_task("print(await call_tool('dex_list_tasks', show_all=True))")

    assert "[DIAG]" in output
    assert "dex_list_tasks" in output
    assert "未加载" in output
    assert "DexManager" in output


@pytest.mark.asyncio
async def test_run_programmatic_task_still_calls_existing_dex_tool(monkeypatch):
    def dex_list_tasks(show_all=False):
        return "[]" if show_all else "[pending]"

    dex_list_tasks.__name__ = "dex_list_tasks"
    agent = FakeAgent([
        _make_named_tool("skill_load"),
        dex_list_tasks,
        _make_named_tool("run_programmatic_task"),
    ])
    ptc_tools.get_tools(agent, session_service=None)

    output = await ptc_tools.run_programmatic_task("print(await call_tool('dex_list_tasks', show_all=True))")

    assert "[]" in output

import json

import pytest

from src.adk_agent.kairos.kairos_config import KairosPromptConfig
from src.adk_agent.kairos.llm_planner import ALLOWED_ACTION_KINDS, KairosPlanner
from src.adk_agent.kairos.models import DocumentReadResult, KairosUnderstandingResult


@pytest.mark.asyncio
async def test_complete_json_falls_back_to_plain_text_json_extraction(monkeypatch):
    planner = KairosPlanner(model="test-model", api_key="k", api_base="http://example.com")

    calls = []

    class Message:
        def __init__(self, content):
            self.content = content

    class Choice:
        def __init__(self, content):
            self.message = Message(content)

    class Response:
        def __init__(self, content):
            self.choices = [Choice(content)]

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise TimeoutError("json mode timeout")
        return Response("```json\n{\"goal\": \"build cli\"}\n```")

    monkeypatch.setattr("src.adk_agent.kairos.llm_planner.litellm.acompletion", fake_acompletion)

    result = await planner._complete_json("system", "user")

    assert result == {"goal": "build cli"}
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in calls[1]
    assert calls[0]["timeout"] == planner._timeout_seconds
    assert calls[1]["timeout"] == planner._timeout_seconds


@pytest.mark.asyncio
async def test_complete_json_reads_reasoning_content_when_content_is_none(monkeypatch):
    planner = KairosPlanner(model="test-model", api_key="k", api_base="http://example.com")

    class Message:
        def __init__(self):
            self.content = None
            self.reasoning_content = "{\"goal\": \"from_reasoning\"}"

    class Choice:
        def __init__(self):
            self.message = Message()

    class Response:
        def __init__(self):
            self.choices = [Choice()]

    async def fake_acompletion(**_kwargs):
        return Response()

    monkeypatch.setattr("src.adk_agent.kairos.llm_planner.litellm.acompletion", fake_acompletion)

    result = await planner._complete_json("system", "user")

    assert result == {"goal": "from_reasoning"}


@pytest.mark.asyncio
async def test_complete_json_passes_dict_extra_body_when_empty(monkeypatch):
    planner = KairosPlanner(model="test-model", api_key="k", api_base="http://example.com", extra_body={})
    seen = {}

    class Message:
        def __init__(self, content):
            self.content = content

    class Choice:
        def __init__(self, content):
            self.message = Message(content)

    class Response:
        def __init__(self, content):
            self.choices = [Choice(content)]

    async def fake_acompletion(**kwargs):
        seen.update(kwargs)
        return Response("{\"goal\": \"ok\"}")

    monkeypatch.setattr("src.adk_agent.kairos.llm_planner.litellm.acompletion", fake_acompletion)

    result = await planner._complete_json("system", "user")

    assert result == {"goal": "ok"}
    assert seen["extra_body"] == {}
    assert isinstance(seen["extra_body"], dict)


def test_extract_json_object_supports_direct_json_and_fenced_json():
    planner = KairosPlanner(model="test-model", api_key="k", api_base="http://example.com")

    assert planner._extract_json_object('{"a": 1}') == {"a": 1}
    assert planner._extract_json_object('```json\n{"b": 2}\n```') == {"b": 2}


def test_timeout_seconds_normalization_handles_ms_and_bounds():
    planner_ms = KairosPlanner(
        model="test-model",
        api_key="k",
        api_base="http://example.com",
        timeout_seconds=600000,
    )
    planner_low = KairosPlanner(
        model="test-model",
        api_key="k",
        api_base="http://example.com",
        timeout_seconds=1,
    )
    planner_high = KairosPlanner(
        model="test-model",
        api_key="k",
        api_base="http://example.com",
        timeout_seconds=120,
    )

    assert planner_ms._timeout_seconds == 600
    assert planner_low._timeout_seconds == 15
    assert planner_high._timeout_seconds == 120


def test_max_retries_normalization_prefers_config_value_and_defaults_to_three():
    planner_none = KairosPlanner(model="test-model", api_key="k", api_base="http://example.com", max_retries=None)
    planner_zero = KairosPlanner(model="test-model", api_key="k", api_base="http://example.com", max_retries=0)
    planner_high = KairosPlanner(model="test-model", api_key="k", api_base="http://example.com", max_retries=5)
    planner_invalid = KairosPlanner(model="test-model", api_key="k", api_base="http://example.com", max_retries=-1)

    assert planner_none._max_retries == 3
    assert planner_zero._max_retries == 0
    assert planner_high._max_retries == 5
    assert planner_invalid._max_retries == 3


@pytest.mark.asyncio
async def test_build_execution_plan_raises_when_steps_still_empty_after_retry(monkeypatch):
    planner = KairosPlanner(model="test-model", api_key="k", api_base="http://example.com")
    calls = {"count": 0}

    async def fake_complete_json(_system_prompt, _user_prompt):
        calls["count"] += 1
        return {}

    monkeypatch.setattr(planner, "_complete_json", fake_complete_json)

    item = DocumentReadResult(
        work_id="work:test:todo",
        goal="build todo app",
        status="pending_requirements",
        current_step="requirements",
        next_actions=["draft requirements document"],
        expected_artifacts=["requirements/session/work.md"],
        source_docs=["requirements/session/work.md"],
    )
    understanding = KairosUnderstandingResult(goal="build todo app")

    with pytest.raises(ValueError, match="no steps"):
        await planner.build_execution_plan(
            item,
            understanding,
            candidate_actions=["update_document", "spawn_dex_task", "ask_user", "sleep"],
        )

    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_planner_reads_prompts_from_kairos_config(monkeypatch):
    custom = KairosPromptConfig(requirement_understanding_system="CUSTOM_UNDERSTANDING_PROMPT")
    planner = KairosPlanner(
        model="test-model",
        api_key="k",
        api_base="http://example.com",
        prompt_config=custom,
    )
    seen = {}

    async def fake_complete_json(system_prompt, _user_prompt):
        seen["system_prompt"] = system_prompt
        return {"goal": "ok"}

    monkeypatch.setattr(planner, "_complete_json", fake_complete_json)

    item = DocumentReadResult(
        work_id="work:test:prompt",
        goal="build todo app",
        status="pending_requirements",
        current_step="requirements",
        next_actions=["draft requirements document"],
        expected_artifacts=["requirements/session/work.md"],
        source_docs=["requirements/session/work.md"],
    )
    await planner.draft_requirement_understanding(item)

    assert seen["system_prompt"] == "CUSTOM_UNDERSTANDING_PROMPT"


@pytest.mark.asyncio
async def test_build_execution_plan_includes_available_skills_in_prompt(monkeypatch):
    planner = KairosPlanner(
        model="test-model",
        api_key="k",
        api_base="http://example.com",
        list_available_skill_catalog=lambda: [
            {"id": "codebase_search", "name": "代码库搜索专家", "description": "通过 ripgrep 定位代码"},
            {"id": "bash", "name": "Bash Tool", "description": "执行命令"},
        ],
    )
    seen = {}

    async def fake_complete_json(system_prompt, user_prompt):
        seen["system_prompt"] = system_prompt
        seen["user_prompt"] = json.loads(user_prompt)
        return {
            "plan_id": "plan-1",
            "work_id": "work:test",
            "steps": [
                {
                    "step_id": "s1",
                    "action_kind": "agent_execute",
                    "reason": "search code",
                    "exit_condition": "done",
                    "required_skills": ["codebase_search"],
                    "execution_prompt": "在仓库中定位实现文件并总结",
                }
            ],
        }

    monkeypatch.setattr(planner, "_complete_json", fake_complete_json)

    item = DocumentReadResult(
        work_id="work:test",
        goal="find implementation",
        status="pending_requirements",
        current_step="requirements",
        next_actions=["search code"],
        expected_artifacts=["requirements/session/work.md"],
        source_docs=["requirements/session/work.md"],
    )
    understanding = KairosUnderstandingResult(goal=item.goal)

    result = await planner.build_execution_plan(
        item,
        understanding,
        candidate_actions=["agent_execute", "ask_user", "sleep"],
    )

    assert result.steps
    assert seen["user_prompt"]["available_skill_ids"] == ["bash", "codebase_search"]
    assert seen["user_prompt"]["available_skills"][0]["id"] == "bash"
    assert any(
        item["preferred_skill_id"] == "codebase_search"
        for item in seen["user_prompt"]["skill_selection_hints"]
    )
    assert "available_skills" in seen["system_prompt"]


def test_allowed_action_kinds_include_agent_execute():
    assert "agent_execute" in ALLOWED_ACTION_KINDS


def test_sanitize_action_payload_keeps_agent_execute_args():
    planner = KairosPlanner(model="test-model", api_key="k", api_base="http://example.com")
    payload = planner._sanitize_action_payload(
        {
            "action_kind": "agent_execute",
            "args": {
                "required_skills": ["bash", "file_editor"],
                "execution_prompt": "生成并更新任务文档",
            },
            "brief": "execute",
        }
    )

    assert payload.action_kind == "agent_execute"
    assert payload.args["required_skills"] == ["bash", "file_editor"]
    assert payload.args["execution_prompt"] == "生成并更新任务文档"

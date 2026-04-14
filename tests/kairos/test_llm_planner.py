import pytest

from src.adk_agent.kairos.llm_planner import KairosPlanner


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


def test_extract_json_object_supports_direct_json_and_fenced_json():
    planner = KairosPlanner(model="test-model", api_key="k", api_base="http://example.com")

    assert planner._extract_json_object('{"a": 1}') == {"a": 1}
    assert planner._extract_json_object('```json\n{"b": 2}\n```') == {"b": 2}

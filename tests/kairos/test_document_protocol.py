from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "src" / "adk_agent" / "kairos" / "document_protocol.py"


def test_document_protocol_exposes_required_semantic_anchors():
    text = PROTOCOL.read_text(encoding="utf-8")

    assert "Goal" in text
    assert "Current Status" in text
    assert "Current Step" in text
    assert "Steps" in text
    assert "Expected Artifacts" in text
    assert "Blockers" in text
    assert "Verification" in text
    assert "Replan Notes" in text
    assert "Spawned Work" in text


def test_document_protocol_requires_markdown_not_json_only_output():
    text = PROTOCOL.read_text(encoding="utf-8")

    assert "markdown" in text.lower()
    assert "json-only" in text.lower()
    assert "open questions" in text.lower()

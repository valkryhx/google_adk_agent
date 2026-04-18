from pathlib import Path

from src.adk_agent.kairos.document_protocol import (
    append_spawned_work_update,
    append_user_guidance_update,
    build_requirement_work_item,
    write_work_document,
)
from src.adk_agent.kairos.models import DocumentReadResult

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


def test_document_protocol_exposes_spawned_work_append_helper():
    text = PROTOCOL.read_text(encoding="utf-8")

    assert "append_spawned_work_update" in text
    assert "Follow-up planned via" in text
    assert "source_doc=" in text


def test_append_spawned_work_update_writes_replan_and_spawned_sections(tmp_path):
    item = DocumentReadResult(
        work_id="work:test:todo",
        goal="build todo app",
        status="in_progress",
        current_step="design",
        next_actions=["draft ui flow"],
        expected_artifacts=["requirements/session-1/work.md"],
        source_docs=["/api/chat:session-1"],
    )
    doc_path = write_work_document(tmp_path, item)

    follow_up = DocumentReadResult(
        work_id="work:test:todo:codegen",
        goal="generate todo app code",
        status="pending",
        current_step="codegen",
    )

    updated = append_spawned_work_update(
        doc_path,
        trigger_reason="llm_action_payload",
        work_item=follow_up,
    )

    assert "## Replan Notes" in updated
    assert "Follow-up planned via llm_action_payload: work:test:todo:codegen (codegen)" in updated
    assert "## Spawned Work" in updated
    assert "work:test:todo:codegen: generate todo app code" in updated
    assert "source_doc=" in updated


def test_append_user_guidance_update_writes_response_into_replan_notes(tmp_path):
    item = DocumentReadResult(
        work_id="work:test:cli",
        goal="build python cli",
        status="blocked",
        current_step="requirements",
        next_actions=["draft requirements doc"],
        expected_artifacts=["requirements/session-1/work.md"],
        source_docs=["/kairos/work/register:session-1"],
    )
    doc_path = write_work_document(tmp_path, item)

    updated = append_user_guidance_update(
        doc_path,
        attention_id="attention-123",
        response="Keep CLI output in JSON and plain table modes.",
    )

    assert "## Replan Notes" in updated
    assert "User guidance [attention-123]" in updated
    assert "JSON and plain table modes" in updated


def test_build_requirement_work_item_defaults_to_autonomous_when_no_explicit_question():
    item = build_requirement_work_item(
        "请直接输出执行日志并持续推进，不需要额外确认",
        session_id="session-1",
        source_label="/kairos/work/register",
    )

    assert item.status == "pending_requirements"
    assert item.human_input_required is False
    assert item.blockers == []
    assert item.open_questions == []


def test_build_requirement_work_item_extracts_explicit_question_sentences():
    item = build_requirement_work_item(
        "请继续推进。你建议把日志输出到哪个目录？",
        session_id="session-1",
        source_label="/kairos/work/register",
    )

    assert item.human_input_required is True
    assert item.status == "blocked"
    assert item.open_questions
    assert item.open_questions[0].endswith("?")

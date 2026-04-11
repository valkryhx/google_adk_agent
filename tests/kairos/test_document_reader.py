from src.adk_agent.kairos.document_reader import read_work_document


def test_read_work_document_normalizes_runtime_fields_without_rigid_markdown_schema():
    result = read_work_document(
        {
            "work_id": "work:python-cli",
            "goal": "build python cli",
            "status": "in_progress",
            "current_step": "design",
            "next_actions": ["write CLI outline"],
            "blockers": [],
            "expected_artifacts": ["specs/python-cli/DESIGN.md"],
            "source_docs": ["specs/python-cli/PLAN.md"],
        }
    )

    assert result.work_id == "work:python-cli"
    assert result.goal == "build python cli"
    assert result.status == "in_progress"
    assert result.current_step == "design"
    assert result.next_actions == ["write CLI outline"]
    assert result.expected_artifacts == ["specs/python-cli/DESIGN.md"]
    assert result.source_docs == ["specs/python-cli/PLAN.md"]


def test_read_work_document_surfaces_open_questions_and_human_input():
    result = read_work_document(
        {
            "work_id": "work:python-cli",
            "goal": "build python cli",
            "status": "blocked",
            "open_questions": ["Which packaging target matters most?"],
            "human_input_required": True,
        }
    )

    assert result.open_questions == ["Which packaging target matters most?"]
    assert result.human_input_required is True

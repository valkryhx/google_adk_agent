from __future__ import annotations

from .models import DocumentReadResult


def read_work_document(payload: dict[str, object]) -> DocumentReadResult:
    return DocumentReadResult(
        work_id=str(payload["work_id"]),
        goal=str(payload["goal"]),
        status=str(payload["status"]),
        current_step=str(payload["current_step"]) if payload.get("current_step") is not None else None,
        next_actions=[str(item) for item in payload.get("next_actions", [])],
        blockers=[str(item) for item in payload.get("blockers", [])],
        expected_artifacts=[str(item) for item in payload.get("expected_artifacts", [])],
        open_questions=[str(item) for item in payload.get("open_questions", [])],
        human_input_required=bool(payload.get("human_input_required", False)),
        source_docs=[str(item) for item in payload.get("source_docs", [])],
    )

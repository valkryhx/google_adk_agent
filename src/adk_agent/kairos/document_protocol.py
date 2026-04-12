from __future__ import annotations

import re
import uuid
from pathlib import Path

from .models import DocumentReadResult

DOCUMENT_SEMANTIC_ANCHORS = (
    "Goal",
    "Current Status",
    "Current Step",
    "Steps",
    "Expected Artifacts",
    "Blockers",
    "Verification",
    "Replan Notes",
    "Spawned Work",
)


def build_generation_prompt() -> str:
    anchors = "\n".join(f"- {anchor}" for anchor in DOCUMENT_SEMANTIC_ANCHORS)
    return (
        "Write a human-readable markdown work document with the required semantic anchors.\n"
        "Do not respond with json-only output.\n"
        "If key information is missing, record it as open questions instead of omitting it.\n"
        "Required sections:\n"
        f"{anchors}\n"
    )


def build_update_prompt() -> str:
    anchors = ", ".join(DOCUMENT_SEMANTIC_ANCHORS)
    return (
        "Update the existing markdown work document while preserving the semantic anchors: "
        f"{anchors}. "
        "Keep the result readable for humans, avoid json-only rewrites, and surface missing details as open questions."
    )


def build_requirement_work_item(
    requirement: str,
    *,
    session_id: str,
    source_label: str = "/api/chat",
) -> DocumentReadResult:
    normalized = " ".join(requirement.strip().split())
    slug = _slugify(normalized) or f"requirement-{uuid.uuid4().hex[:8]}"
    work_id = f"work:{session_id}:{slug}"
    goal = normalized or "capture user requirement"
    open_questions = _extract_open_questions(normalized)
    human_input_required = bool(open_questions)
    status = "blocked" if human_input_required else "pending_requirements"
    blockers = ["Need answers before drafting executable plan"] if human_input_required else []
    next_actions = ["draft requirements document", "review scope and constraints"]
    expected_artifacts = [f"requirements/{session_id}/work.md"]
    source_docs = [f"{source_label}:{session_id}"]
    return DocumentReadResult(
        work_id=work_id,
        goal=goal,
        status=status,
        current_step="requirements",
        next_actions=next_actions,
        blockers=blockers,
        expected_artifacts=expected_artifacts,
        open_questions=open_questions,
        human_input_required=human_input_required,
        source_docs=source_docs,
    )


def render_work_document(item: DocumentReadResult) -> str:
    lines = [
        f"# Work Item: {item.goal}",
        "",
        f"## Goal\n{item.goal}",
        "",
        f"## Current Status\n{item.status}",
        "",
        f"## Current Step\n{item.current_step or 'requirements'}",
        "",
        "## Steps",
    ]
    if item.next_actions:
        lines.extend(f"- {action}" for action in item.next_actions)
    else:
        lines.append("- clarify next action")
    lines.extend(["", "## Expected Artifacts"])
    if item.expected_artifacts:
        lines.extend(f"- {artifact}" for artifact in item.expected_artifacts)
    else:
        lines.append("- none yet")
    lines.extend(["", "## Blockers"])
    if item.blockers:
        lines.extend(f"- {blocker}" for blocker in item.blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Verification", "- confirm requirement scope with user", "", "## Replan Notes"])
    if item.open_questions:
        lines.extend(f"- Open question: {question}" for question in item.open_questions)
    else:
        lines.append("- no replans yet")
    lines.extend(["", "## Spawned Work", "- none yet"])
    return "\n".join(lines) + "\n"


def write_work_document(base_dir: Path, item: DocumentReadResult) -> Path:
    path = base_dir / item.expected_artifacts[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_work_document(item), encoding="utf-8")
    return path


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]


def _extract_open_questions(text: str) -> list[str]:
    lower = text.lower()
    questions: list[str] = []
    if "todo" in lower and not any(token in lower for token in ("html", "react", "vue", "web", "app")):
        questions.append("Should this todo app be web-based, desktop, or another format?")
    if not any(token in lower for token in ("persist", "storage", "sqlite", "localstorage", "database")):
        questions.append("What persistence or storage requirement matters most?")
    return questions

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from typing import Callable

from .models import DocumentReadResult


@dataclass
class WorkProgressSnapshot:
    work_id: str
    goal: str
    current_step: str
    status: str
    next_actions: list[str]
    blockers: list[str]
    open_questions: list[str]
    expected_artifacts: list[str]
    verification_needs: list[str]
    source_docs: list[str]
    doc_fingerprint: str


@dataclass
class GateEvaluation:
    passed: bool
    requires_human: bool
    reason: str
    missing_artifacts: list[str]
    questions: list[str]
    verification_pending: bool


@dataclass
class ExecutableAction:
    kind: str
    reason: str
    payload: dict[str, object]


def build_progress_snapshot(item: DocumentReadResult) -> WorkProgressSnapshot:
    verification_needs = [question.removeprefix("Open question: ").strip() for question in item.open_questions]
    if item.human_input_required:
        verification_needs.extend(question for question in item.open_questions if question not in verification_needs)
    fingerprint_source = "|".join(
        [
            item.work_id,
            item.goal,
            item.status,
            item.current_step or "",
            *item.next_actions,
            *item.blockers,
            *item.expected_artifacts,
            *item.open_questions,
            *item.source_docs,
        ]
    )
    return WorkProgressSnapshot(
        work_id=item.work_id,
        goal=item.goal,
        current_step=item.current_step or "document_work",
        status=item.status,
        next_actions=list(item.next_actions),
        blockers=list(item.blockers),
        open_questions=list(item.open_questions),
        expected_artifacts=list(item.expected_artifacts),
        verification_needs=verification_needs,
        source_docs=list(item.source_docs),
        doc_fingerprint=sha1(fingerprint_source.encode("utf-8")).hexdigest(),
    )


def evaluate_document_gates(
    snapshot: WorkProgressSnapshot,
    runtime_state,
    path_exists: Callable[[str], bool],
) -> GateEvaluation:
    del runtime_state
    missing_artifacts = [path for path in snapshot.expected_artifacts if path and not path_exists(path)]
    questions = list(snapshot.open_questions)
    blockers = [blocker for blocker in snapshot.blockers if blocker.lower() != "none"]
    requires_human = bool(snapshot.open_questions) or snapshot.status == "blocked"
    verification_pending = bool(snapshot.verification_needs) and not snapshot.next_actions and not blockers
    if requires_human:
        return GateEvaluation(
            passed=False,
            requires_human=True,
            reason=questions[0] if questions else (blockers[0] if blockers else "document work requires user input"),
            missing_artifacts=missing_artifacts,
            questions=questions,
            verification_pending=verification_pending,
        )
    if blockers:
        return GateEvaluation(
            passed=False,
            requires_human=False,
            reason=blockers[0],
            missing_artifacts=missing_artifacts,
            questions=questions,
            verification_pending=verification_pending,
        )
    if snapshot.next_actions:
        return GateEvaluation(
            passed=True,
            requires_human=False,
            reason="document work has executable next action",
            missing_artifacts=missing_artifacts,
            questions=questions,
            verification_pending=verification_pending,
        )
    return GateEvaluation(
        passed=False,
        requires_human=False,
        reason="document work has no executable next action",
        missing_artifacts=missing_artifacts,
        questions=questions,
        verification_pending=verification_pending,
    )


def materialize_document_action(
    snapshot: WorkProgressSnapshot,
    gates: GateEvaluation,
    runtime_state,
) -> ExecutableAction:
    del runtime_state
    if gates.requires_human:
        return ExecutableAction(
            kind="ask_user",
            reason="document_work_waiting_input",
            payload={
                "work_id": snapshot.work_id,
                "step_id": snapshot.current_step,
                "message": gates.reason,
                "open_questions": list(gates.questions),
                "source_doc": snapshot.source_docs[0] if snapshot.source_docs else None,
                "doc_fingerprint": snapshot.doc_fingerprint,
            },
        )
    blockers = [blocker for blocker in snapshot.blockers if blocker.lower() != "none"]
    if blockers:
        return ExecutableAction(
            kind="record_blocked",
            reason="document_work_blocked",
            payload={
                "work_id": snapshot.work_id,
                "step_id": snapshot.current_step,
                "message": gates.reason,
                "blockers": blockers,
                "source_doc": snapshot.source_docs[0] if snapshot.source_docs else None,
                "doc_fingerprint": snapshot.doc_fingerprint,
            },
        )
    if gates.passed and snapshot.next_actions:
        description = snapshot.next_actions[0]
        return ExecutableAction(
            kind="run_dex_task",
            reason="document_work_ready",
            payload={
                "work_id": snapshot.work_id,
                "step_id": snapshot.current_step,
                "description": description,
                "goal": snapshot.goal,
                "current_step": snapshot.current_step,
                "next_actions": list(snapshot.next_actions),
                "expected_artifacts": list(snapshot.expected_artifacts),
                "open_questions": list(snapshot.open_questions),
                "human_input_required": False,
                "source_doc": snapshot.source_docs[0] if snapshot.source_docs else None,
                "doc_fingerprint": snapshot.doc_fingerprint,
            },
        )
    return ExecutableAction(
        kind="sleep_until_signal",
        reason="document_work_waiting_signal",
        payload={
            "work_id": snapshot.work_id,
            "step_id": snapshot.current_step,
            "message": gates.reason,
            "source_doc": snapshot.source_docs[0] if snapshot.source_docs else None,
            "doc_fingerprint": snapshot.doc_fingerprint,
        },
    )

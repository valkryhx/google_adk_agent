import json
import os
import re
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any


BASE_URL = os.environ.get("KAIROS_BASE_URL", "http://127.0.0.1:8000")
APP_NAME_PREFIX = os.environ.get("KAIROS_APP_NAME", "kairos_stepwise_e2e")
USER_ID_PREFIX = os.environ.get("KAIROS_USER_ID", "user_stepwise_e2e")
REPO_ROOT = Path(os.environ.get("KAIROS_REPO_ROOT", str(Path.cwd()))).resolve()


def _request(method: str, path: str, data: dict[str, Any] | None = None) -> Any:
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=300) as resp:
        text = resp.read().decode("utf-8")
    return json.loads(text)


def _fetch_kairos_status(session_id: str, *, app_name: str, user_id: str) -> dict[str, Any]:
    return _request(
        "GET",
        f"/api/sessions/{session_id}/kairos/status?app_name={app_name}&user_id={user_id}",
    )


def _fetch_kairos_history(session_id: str, *, app_name: str, user_id: str) -> dict[str, Any]:
    return _request(
        "GET",
        f"/api/sessions/{session_id}/kairos/history?app_name={app_name}&user_id={user_id}&descending=true",
    )


def _build_stepwise_requirement(session_id: str) -> str:
    work_doc = f"requirements/{session_id}/work.md"
    result_doc = f"requirements/{session_id}/e2e/E2E-RESULT.md"
    return (
        "请执行严格单步 E2E："
        "每个 kairos 回合只做 1 个原子动作（1 次 tool 调用或 1 条测试命令），"
        "做完立即回写 work.md 后结束该回合。"
        "每完成一步都要在 work.md 写明 Step-x 完成证据，再进入下一步。"
        f"Step-1: 读取 {work_doc} 并写入本次计划（step-1~step-5）。"
        "Step-2: 执行故意失败命令 python -m pytest tests/kairos/test_runtime.py::not_exists -q，并记录失败证据。"
        "Step-3: 基于失败证据 replan，并写入 Replan Notes（根因与修正动作）。"
        "Step-4: 执行修正命令 python -m pytest tests/kairos/test_llm_planner.py -q 与 python -m pytest tests/kairos/test_runtime.py -q。"
        f"Step-5: 回写 Verification/Current Status（必须写成 completed ✅），并生成 {result_doc}（必须非空，包含 Summary/Verification/Next 三段）后结束任务。"
        "达到 Step-5 后主动停止，不再继续执行。"
    )


def _extract_current_status_value(work_text: str) -> str:
    match = re.search(
        r"(?ims)^##\s*Current Status\s*$\s*(.+?)(?=^\s*##\s+|\Z)",
        str(work_text or ""),
    )
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def run_stepwise_replan_e2e(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    run_suffix = uuid.uuid4().hex[:8]
    app_name = f"{APP_NAME_PREFIX}_{run_suffix}"
    user_id = f"{USER_ID_PREFIX}_{run_suffix}"

    created = _request("POST", "/api/sessions", {"app_name": app_name, "user_id": user_id})
    session_id = created["session_id"]

    _request(
        "POST",
        f"/api/sessions/{session_id}/kairos/start",
        {"app_name": app_name, "user_id": user_id, "reason": "stepwise_replan_e2e"},
    )
    registered = _request(
        "POST",
        f"/api/sessions/{session_id}/kairos/work/register",
        {
            "app_name": app_name,
            "user_id": user_id,
            "requirement": _build_stepwise_requirement(session_id),
        },
    )

    work_path = root / "requirements" / session_id / "work.md"
    result_path = root / "requirements" / session_id / "e2e" / "E2E-RESULT.md"
    initial_work_text = work_path.read_text(encoding="utf-8") if work_path.exists() else ""

    metrics: dict[str, Any] = {
        "app_name": app_name,
        "user_id": user_id,
        "session_id": session_id,
        "registered_work_id": registered.get("registered_work", {}).get("work_id"),
        "turn_started": False,
        "turn_finished": False,
        "planning_selected": False,
        "planning_winner_action": None,
        "replan_evidence": False,
        "planning_replan_changed": False,
        "last_replan_reason": "",
        "planner_no_steps_error": False,
        "blocked_reason": "",
        "work_md_updated": False,
        "result_file_created": False,
        "result_file_nonempty": False,
        "history_count": 0,
        "wake_requests_sent": 0,
        "work_status_completed": False,
    }

    deadline = time.time() + 1200
    last_manual_wake_at = 0.0
    while time.time() < deadline:
        status = _fetch_kairos_status(session_id, app_name=app_name, user_id=user_id)
        kairos = status.get("kairos", {})
        pending_triggers = kairos.get("pending_triggers") or []
        pending_wake_reason = str(kairos.get("pending_wake_reason") or "").strip()
        is_busy = bool(kairos.get("busy"))
        should_manual_wake = (
            not is_busy
            and not pending_triggers
            and not pending_wake_reason
            and (time.time() - last_manual_wake_at) >= 20.0
        )
        if should_manual_wake:
            _request(
                "POST",
                f"/api/sessions/{session_id}/kairos/wake",
                {
                    "app_name": app_name,
                    "user_id": user_id,
                    "reason": f"stepwise-e2e-poll-{int(time.time())}",
                },
            )
            metrics["wake_requests_sent"] += 1
            last_manual_wake_at = time.time()

        planning_winner = status.get("planning_winner", {}) or {}
        planning_replan = status.get("planning_replan", {}) or {}
        last_replan = status.get("last_replan_result", {}) or {}

        winner_action = planning_winner.get("action")
        metrics["planning_winner_action"] = winner_action
        metrics["planning_selected"] = bool(winner_action)
        metrics["planning_replan_changed"] = bool(planning_replan.get("changed"))
        metrics["last_replan_reason"] = str(last_replan.get("replan_reason", "")).strip()

        blocked_reason = str(kairos.get("blocked_reason") or status.get("blocked_reason") or "").strip()
        metrics["blocked_reason"] = blocked_reason
        if "llm execution plan contains no steps" in blocked_reason:
            metrics["planner_no_steps_error"] = True

        history_payload = _fetch_kairos_history(session_id, app_name=app_name, user_id=user_id)
        history = history_payload.get("history", [])
        metrics["history_count"] = len(history)
        for entry in history:
            message = str((entry or {}).get("message", "")).strip()
            if not message:
                continue
            if "kairos turn started" in message:
                metrics["turn_started"] = True
            if "kairos turn finished" in message:
                metrics["turn_finished"] = True
            if "llm execution plan contains no steps" in message:
                metrics["planner_no_steps_error"] = True
            if "Re-plan:" in message or "replan" in message.lower():
                metrics["replan_evidence"] = True

        if metrics["planning_replan_changed"] or metrics["last_replan_reason"]:
            metrics["replan_evidence"] = True

        if work_path.exists():
            work_text = work_path.read_text(encoding="utf-8")
            if work_text != initial_work_text:
                metrics["work_md_updated"] = True
            current_status_value = _extract_current_status_value(work_text)
            if "completed" in current_status_value.lower():
                metrics["work_status_completed"] = True
            if any(token in work_text for token in ("Replan Notes", "根因", "修正", "not_exists")):
                metrics["replan_evidence"] = True

        if result_path.exists():
            metrics["result_file_created"] = True
            if result_path.read_text(encoding="utf-8").strip():
                metrics["result_file_nonempty"] = True

        if metrics["planner_no_steps_error"]:
            break
        if (
            metrics["turn_started"]
            and metrics["turn_finished"]
            and metrics["planning_selected"]
            and metrics["replan_evidence"]
            and metrics["work_status_completed"]
            and metrics["result_file_nonempty"]
        ):
            break
        time.sleep(2.0)

    assert metrics["turn_started"], f"turn_started missing: {metrics}"
    assert metrics["turn_finished"], f"turn_finished missing: {metrics}"
    assert metrics["planning_selected"], f"planning_selected missing: {metrics}"
    assert metrics["replan_evidence"], f"replan evidence missing: {metrics}"
    assert not metrics["planner_no_steps_error"], f"planner no-steps regression detected: {metrics}"
    assert metrics["work_status_completed"], f"work status not completed: {work_path}"
    assert metrics["result_file_created"], f"E2E result file missing: {result_path}"
    assert metrics["result_file_nonempty"], f"E2E result file empty: {result_path}"

    return {
        "session_id": session_id,
        "status": _fetch_kairos_status(session_id, app_name=app_name, user_id=user_id),
        "history": _fetch_kairos_history(session_id, app_name=app_name, user_id=user_id),
        "metrics": metrics,
        "work_path": str(work_path),
        "result_path": str(result_path),
    }


def main() -> None:
    result = run_stepwise_replan_e2e()
    metrics = result["metrics"]
    print(f"[stepwise-e2e] session={result['session_id']}")
    print(
        "[stepwise-e2e] pass "
        f"turn_started={metrics['turn_started']} "
        f"turn_finished={metrics['turn_finished']} "
        f"planning_selected={metrics['planning_selected']} "
        f"replan_evidence={metrics['replan_evidence']} "
        f"planner_no_steps_error={metrics['planner_no_steps_error']}"
    )
    print(f"[stepwise-e2e] result={result['result_path']}")


if __name__ == "__main__":
    main()

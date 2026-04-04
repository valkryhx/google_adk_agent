import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = os.environ.get("KAIROS_BASE_URL", "http://127.0.0.1:8000")
APP_NAME = os.environ.get("KAIROS_APP_NAME", "dynamic_expert")
USER_ID = os.environ.get("KAIROS_USER_ID", "user_001")
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.dex.tools import DexManager, _normalize_command_args

DEMO_DIR = REPO_ROOT / "demo_outputs"

TASK_COMMANDS = {
    "sales": "python -c \"import json,time,os; os.makedirs('demo_outputs', exist_ok=True); time.sleep(2); json.dump({'source':'sales','value':128,'status':'ok'}, open('demo_outputs/sales.json','w',encoding='utf-8'), ensure_ascii=False); print('sales ready')\"",
    "traffic": "python -c \"import json,time,os; os.makedirs('demo_outputs', exist_ok=True); time.sleep(3); json.dump({'source':'traffic','value':3421,'status':'ok'}, open('demo_outputs/traffic.json','w',encoding='utf-8'), ensure_ascii=False); print('traffic ready')\"",
    "quality": "python -c \"import json,time,os; os.makedirs('demo_outputs', exist_ok=True); time.sleep(2); json.dump({'source':'quality','value':'pass','status':'ok'}, open('demo_outputs/quality.json','w',encoding='utf-8'), ensure_ascii=False); print('quality ready')\"",
    "report": "python -c \"import json,os; data={}; files=['sales','traffic','quality']; [data.setdefault(name, json.load(open(f'demo_outputs/{name}.json', encoding='utf-8'))) for name in files]; report={'report':'ready','inputs':files,'summary':{'sales':data['sales']['value'],'traffic':data['traffic']['value'],'quality':data['quality']['value']}}; json.dump(report, open('demo_outputs/report.json','w',encoding='utf-8'), ensure_ascii=False, indent=2); print('report ready: 3 inputs merged')\"",
}


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


def _fetch_kairos_status(session_id: str) -> dict[str, Any]:
    return _request(
        "GET",
        f"/api/sessions/{session_id}/kairos/status?app_name={APP_NAME}&user_id={USER_ID}",
    )


def _start_task(task_id: str, command: str, session_id: str) -> list[dict[str, Any]]:
    DexManager(base_dir=REPO_ROOT, user_id=USER_ID).start_background_process(
        task_id,
        _normalize_command_args(command),
    )
    return []


def _chat_for_json(message: str, session_id: str) -> list[dict[str, Any]]:
    body = json.dumps(
        {
            "message": message,
            "app_name": APP_NAME,
            "user_id": USER_ID,
            "session_id": session_id,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        lines = [line.decode("utf-8").strip() for line in resp.readlines() if line.strip()]
    return [json.loads(line) for line in lines]


def _create_dex_task(session_id: str, description: str) -> dict[str, Any]:
    return DexManager(base_dir=REPO_ROOT, user_id=USER_ID).create_task(
        description,
        "live demo verification",
    )


def _register_dex_task(session_id: str, task_id: str, description: str) -> dict[str, Any]:
    return _request(
        "POST",
        f"/api/sessions/{session_id}/kairos/dex/register",
        {
            "app_name": APP_NAME,
            "user_id": USER_ID,
            "task_id": task_id,
            "description": description,
        },
    )


def _fetch_dex_task(task_id: str) -> dict[str, Any] | None:
    task_path = REPO_ROOT / ".dex" / "tasks" / USER_ID / f"{task_id}.json"
    if not task_path.exists():
        return None
    raw = task_path.read_text(encoding="utf-8")
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _wait_for_dex_task_status(task_id: str, expected_status: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        last = _fetch_dex_task(task_id)
        if last and last.get("status") == expected_status:
            return last
        time.sleep(0.5)
    raise AssertionError(f"dex task {task_id} did not reach {expected_status}: {last}")


def _wait_for_untracked(session_id: str, task_ids: list[str], timeout_seconds: float = 40.0) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        last = _fetch_kairos_status(session_id)
        tracked_ids = set(last["kairos"].get("tracked_dex_task_ids", []))
        if not (tracked_ids & set(task_ids)):
            return last
        time.sleep(0.5)
    raise AssertionError(f"tasks still tracked: {task_ids}, status={last}")


def main() -> None:
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)

    created = _request("POST", "/api/sessions", {"app_name": APP_NAME, "user_id": USER_ID})
    session_id = created["session_id"]
    print(f"[live-demo] session={session_id}")

    _request(
        "POST",
        f"/api/sessions/{session_id}/kairos/start",
        {"app_name": APP_NAME, "user_id": USER_ID, "reason": "live_demo_start"},
    )
    print("[live-demo] kairos started")

    phase1 = {}
    for name in ("sales", "traffic", "quality"):
        phase1[name] = _create_dex_task(session_id, f"prepare {name}")
        task = phase1[name]
        _register_dex_task(session_id, task["id"], f"prepare {name}")
        _start_task(task["id"], TASK_COMMANDS[name], session_id)
        print(f"[live-demo] started {name} task={task['id']}")

    for name, task in phase1.items():
        completed = _wait_for_dex_task_status(task["id"], "completed")
        print(f"[live-demo] {name} completed: {completed.get('result_summary')}")

    phase1_status = _wait_for_untracked(session_id, [task["id"] for task in phase1.values()])
    print(f"[live-demo] phase1 converged: {phase1_status['kairos']['mode']}")

    report = _create_dex_task(session_id, "generate final report")
    _register_dex_task(session_id, report["id"], "generate final report")
    _start_task(report["id"], TASK_COMMANDS["report"], session_id)
    print(f"[live-demo] started report task={report['id']}")

    report_completed = _wait_for_dex_task_status(report["id"], "completed")
    print(f"[live-demo] report completed: {report_completed.get('result_summary')}")

    final_status = _wait_for_untracked(session_id, [report["id"]])
    print(f"[live-demo] final mode={final_status['kairos']['mode']}")

    assert (DEMO_DIR / "sales.json").exists()
    assert (DEMO_DIR / "traffic.json").exists()
    assert (DEMO_DIR / "quality.json").exists()
    assert (DEMO_DIR / "report.json").exists()

    report_payload = json.loads((DEMO_DIR / "report.json").read_text(encoding="utf-8"))
    assert report_payload["report"] == "ready"
    assert report_payload["summary"]["sales"] == 128
    assert report_payload["summary"]["traffic"] == 3421
    assert report_payload["summary"]["quality"] == "pass"

    messages = [event.get("message", "") for event in final_status["kairos"].get("recent_events", [])]
    assert any("sales ready" in message for message in messages)
    assert any("traffic ready" in message for message in messages)
    assert any("quality ready" in message for message in messages)
    assert any("report ready: 3 inputs merged" in message for message in messages)
    print("[live-demo] PASS: artifacts and Kairos events verified")


if __name__ == "__main__":
    main()

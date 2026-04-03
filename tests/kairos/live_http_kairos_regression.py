import json
import os
import time
import urllib.request
from typing import Any


BASE_URL = os.environ.get("KAIROS_BASE_URL", "http://127.0.0.1:8000")
APP_NAME = os.environ.get("KAIROS_APP_NAME", "dynamic_expert")
USER_ID = os.environ.get("KAIROS_USER_ID", "user_001")
CHAT_MESSAGE = os.environ.get("KAIROS_CHAT_MESSAGE", "hi")
WAKE_REASONS = ["manual_verify_1", "manual_verify_2", "manual_verify_3"]


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


def _request_ndjson(method: str, path: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        text = resp.read().decode("utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def _fetch_history(session_id: str) -> dict[str, Any]:
    return _request(
        "GET",
        f"/api/sessions/{session_id}/history?app_name={APP_NAME}&user_id={USER_ID}",
    )


def _fetch_kairos_status(session_id: str) -> dict[str, Any]:
    return _request(
        "GET",
        f"/api/sessions/{session_id}/kairos/status?app_name={APP_NAME}&user_id={USER_ID}",
    )


def _wait_until_kairos_idle(session_id: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        last = _fetch_kairos_status(session_id)
        kairos = last["kairos"]
        if not kairos.get("busy") and kairos.get("active_trigger") is None:
            return last
        time.sleep(1)
    raise AssertionError(f"Kairos did not become idle in time: {last}")


def _assert_history_is_single_pair(messages: list[dict[str, Any]], expected_invocation_id: str | None = None) -> None:
    assert len(messages) == 2, f"expected 2 messages, got {len(messages)}"
    assert [msg["role"] for msg in messages] == ["user", "model"], messages
    invocation_ids = [msg.get("invocation_id") for msg in messages]
    assert invocation_ids[0] == invocation_ids[1], invocation_ids
    if expected_invocation_id is not None:
        assert invocation_ids[0] == expected_invocation_id, invocation_ids


def main() -> None:
    print(f"[live-http] base={BASE_URL} app={APP_NAME} user={USER_ID}")

    created = _request("POST", "/api/sessions", {"app_name": APP_NAME, "user_id": USER_ID})
    session_id = created["session_id"]
    print(f"[live-http] created session: {session_id}")

    chat_chunks = _request_ndjson(
        "POST",
        "/api/chat",
        {
            "message": CHAT_MESSAGE,
            "app_name": APP_NAME,
            "user_id": USER_ID,
            "session_id": session_id,
        },
    )
    assert chat_chunks, "chat stream returned no chunks"
    print(f"[live-http] sent initial chat, chunks={len(chat_chunks)}")

    before = _fetch_history(session_id)
    before_messages = before["messages"]
    _assert_history_is_single_pair(before_messages)
    initial_invocation_id = before_messages[0].get("invocation_id")
    print(f"[live-http] history before kairos: {len(before_messages)} messages")

    _request(
        "POST",
        f"/api/sessions/{session_id}/kairos/start",
        {"app_name": APP_NAME, "user_id": USER_ID, "reason": "start_verify"},
    )
    print("[live-http] kairos started")

    for reason in WAKE_REASONS:
        _request(
            "POST",
            f"/api/sessions/{session_id}/kairos/wake",
            {"app_name": APP_NAME, "user_id": USER_ID, "reason": reason},
        )
        print(f"[live-http] kairos wake: {reason}")

    final_status = _wait_until_kairos_idle(session_id)
    print(f"[live-http] kairos idle again: {json.dumps(final_status['kairos'], ensure_ascii=False)[:600]}")

    after = _fetch_history(session_id)
    after_messages = after["messages"]
    _assert_history_is_single_pair(after_messages, expected_invocation_id=initial_invocation_id)
    print(f"[live-http] history after kairos: {len(after_messages)} messages")
    print("[live-http] PASS: wake did not duplicate chat history")


if __name__ == "__main__":
    main()

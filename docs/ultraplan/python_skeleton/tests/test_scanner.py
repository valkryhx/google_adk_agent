from ultraplan.models import ScanKind
from ultraplan.scanner import ExitPlanModeScanner


def test_ingest_returns_pending_when_exit_plan_has_no_result():
    scanner = ExitPlanModeScanner()
    result = scanner.ingest([
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "tool-1", "name": "ExitPlanMode"}
                ]
            },
        }
    ])
    assert result.kind == ScanKind.PENDING


def test_ingest_returns_approved_when_tool_result_contains_approved_marker():
    scanner = ExitPlanModeScanner()
    result = scanner.ingest([
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "tool-1", "name": "ExitPlanMode"}
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-1",
                        "is_error": False,
                        "content": "## Approved Plan:\nship it",
                    }
                ]
            },
        },
    ])
    assert result.kind == ScanKind.APPROVED
    assert result.plan == "ship it"

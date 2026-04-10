import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("live_http_kairos_demo_outputs_regression.py")
SPEC = importlib.util.spec_from_file_location("live_http_kairos_demo_outputs_regression", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_live_http_kairos_demo_outputs_regression_source_asserts_reporting_fields():
    text = MODULE_PATH.read_text(encoding="utf-8")

    assert 'task_summaries' in text
    assert 'decision_explanation' in text
    assert 'condition_tree' in text


def test_live_http_demo_source_asserts_todo_delivery_report_visibility():
    text = MODULE_PATH.read_text(encoding="utf-8")

    assert 'run_todo_delivery_pipeline' in text
    assert 'delivery_report.md' in text
    assert 'generate todo delivery report' in text


def test_todo_task_commands_create_demo_directory_before_writing_files():
    text = MODULE_PATH.read_text(encoding="utf-8")

    assert "TODO_REQUIREMENTS_COMMAND" in text
    assert "TODO_DESIGN_COMMAND" in text
    assert "TODO_CODEGEN_COMMAND" in text
    assert "TODO_TESTS_COMMAND" in text
    assert text.count("p.mkdir(parents=True, exist_ok=True)") >= 4




def test_live_http_source_asserts_history_timeline_visibility():
    text = MODULE_PATH.read_text(encoding="utf-8")

    assert '/kairos/history' in text
    assert 'history_payload' in text
    assert 'follow_up' in text or 'Auto-created follow-up' in text


def test_live_http_kairos_demo_outputs_regression_passes_against_running_service():
    import os
    import urllib.request

    try:
        urllib.request.urlopen(os.environ.get("KAIROS_BASE_URL", "http://127.0.0.1:8000"), timeout=2)
    except Exception:
        import pytest
        pytest.skip("live service not running on configured KAIROS_BASE_URL")
    module.main()


def test_live_http_todo_delivery_pipeline_passes_against_running_service():
    import os
    import urllib.request

    try:
        urllib.request.urlopen(os.environ.get("KAIROS_BASE_URL", "http://127.0.0.1:8000"), timeout=2)
    except Exception:
        import pytest
        pytest.skip("live service not running on configured KAIROS_BASE_URL")

    result = module.run_todo_delivery_pipeline()
    assert result["final_status"]["kairos"]["mode"] == "idle"
    assert result["final_status"]["kairos"]["active_workflow"]["workflow_id"] == "todo_delivery_pipeline"



def test_live_http_todo_pipeline_exposes_proactive_scan_fields_against_running_service():
    import os
    import urllib.request

    try:
        urllib.request.urlopen(os.environ.get("KAIROS_BASE_URL", "http://127.0.0.1:8000"), timeout=2)
    except Exception:
        import pytest
        pytest.skip("live service not running on configured KAIROS_BASE_URL")

    result = module.run_todo_delivery_pipeline()
    kairos = result["final_status"]["kairos"]

    assert "unfinished_work_items" in kairos
    assert "proactive_candidates" in kairos
    assert "last_proactive_scan" in kairos
    assert "last_guardrail_block" in kairos

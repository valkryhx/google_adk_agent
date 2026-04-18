import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("live_http_kairos_stepwise_replan_e2e.py")
SPEC = importlib.util.spec_from_file_location("live_http_kairos_stepwise_replan_e2e", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_live_http_stepwise_source_asserts_turn_finish_and_planning_evidence():
    text = MODULE_PATH.read_text(encoding="utf-8")

    assert "turn_started" in text
    assert "turn_finished" in text
    assert "planning_selected" in text
    assert "planning_replan_changed" in text
    assert "planner_no_steps_error" in text
    assert "assert metrics[\"turn_finished\"]" in text
    assert "assert not metrics[\"planner_no_steps_error\"]" in text


def test_live_http_stepwise_source_contains_intentional_failure_then_replan_steps():
    text = MODULE_PATH.read_text(encoding="utf-8")

    assert "Step-2: 执行故意失败命令" in text
    assert "tests/kairos/test_runtime.py::not_exists" in text
    assert "Step-3: 基于失败证据 replan" in text
    assert "Step-4: 执行修正命令" in text
    assert "E2E-RESULT.md" in text


def test_live_http_stepwise_module_exports_main_entrypoint():
    assert hasattr(module, "main")
    assert callable(module.main)


def test_live_http_stepwise_replan_e2e_passes_against_running_service():
    import os
    import urllib.request

    try:
        urllib.request.urlopen(os.environ.get("KAIROS_BASE_URL", "http://127.0.0.1:8000"), timeout=2)
    except Exception:
        import pytest
        pytest.skip("live service not running on configured KAIROS_BASE_URL")

    result = module.run_stepwise_replan_e2e()
    metrics = result["metrics"]
    assert metrics["turn_started"] is True
    assert metrics["turn_finished"] is True
    assert metrics["planning_selected"] is True
    assert metrics["replan_evidence"] is True
    assert metrics["planner_no_steps_error"] is False

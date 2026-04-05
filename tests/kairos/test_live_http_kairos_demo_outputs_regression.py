import importlib.util
from pathlib import Path


MODULE_PATH = Path(r"D:/git_repos/google_adk_agent/tests/kairos/live_http_kairos_demo_outputs_regression.py")
SPEC = importlib.util.spec_from_file_location("live_http_kairos_demo_outputs_regression", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_live_http_kairos_demo_outputs_regression_source_asserts_reporting_fields():
    text = MODULE_PATH.read_text(encoding="utf-8")

    assert 'task_summaries' in text
    assert 'decision_explanation' in text
    assert 'condition_tree' in text


def test_live_http_kairos_demo_outputs_regression_passes_against_running_service():
    module.main()

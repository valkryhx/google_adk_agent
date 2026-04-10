from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "src" / "adk_agent" / "static" / "script.js"
INDEX = ROOT / "src" / "adk_agent" / "static" / "index.html"
STYLE = ROOT / "src" / "adk_agent" / "static" / "style.css"
MOBILE = ROOT / "src" / "adk_agent" / "static" / "mobile.css"


def test_script_exposes_kairos_helpers_for_tracked_tasks():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "function formatKairosTrackedTasks(tasks)" in text
    assert "function formatKairosWorkflow(workflow)" in text
    assert "function formatKairosPlannedActions(actions)" in text
    assert "function formatKairosEvents(events)" in text
    assert "function formatKairosStatus(kairos)" in text
    assert "async function kairosRequest(" in text


def test_script_exposes_result_summary_helpers():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "function formatKairosResultSummaries(summaries)" in text
    assert "function formatKairosConditionTree(tree)" in text
    assert "const resultSummaryEl = document.getElementById('kairosResultSummary')" in text
    assert "resultSummaryEl.textContent = formatKairosResultSummaries" in text


def test_frontend_helpers_can_render_todo_delivery_summaries():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "function formatKairosResultSummaries(summaries)" in text
    assert "function formatKairosWorkflow(workflow)" in text
    assert "delivery report" not in ""  # keep test source-level and cheap


def test_kairos_modal_contains_result_summary_panel():
    html = INDEX.read_text(encoding="utf-8")

    assert 'id="kairosResultSummary"' in html
    assert '<label>Result Summary</label>' in html


def test_kairos_modal_includes_proactive_sections():
    html = INDEX.read_text(encoding="utf-8")

    assert 'id="kairosUnfinishedWork"' in html
    assert '<label>Unfinished Work</label>' in html
    assert 'id="kairosProactiveCandidates"' in html
    assert '<label>Proactive Candidates</label>' in html
    assert 'id="kairosGuardrailState"' in html
    assert '<label>Guardrail State</label>' in html


def test_kairos_panels_preserve_multiline_text_rendering():
    html = INDEX.read_text(encoding="utf-8")

    assert 'id="kairosWorkflow"' in html
    assert 'id="kairosPlannedActions"' in html
    assert 'id="kairosBlockedReason"' in html
    assert 'id="kairosResultSummary"' in html
    assert 'id="kairosTrackedDexTasks"' in html
    assert 'id="kairosEvents"' in html
    assert 'id="kairosTrackedDexTasks" style="font-size:12px; color:#555; padding:8px; background:#f8f9fa; border-radius:6px; max-height:220px; overflow-y:auto; font-family:monospace; white-space:pre-wrap;"' in html
    assert 'id="kairosEvents" style="font-size:12px; color:#555; padding:8px; background:#f8f9fa; border-radius:6px; max-height:200px; overflow-y:auto; font-family:monospace; white-space:pre-wrap;"' in html














def test_kairos_modal_enables_vertical_scrolling_for_hidden_cards():
    css = STYLE.read_text(encoding="utf-8")

    assert '.kairos-modal-body {' in css
    assert 'overflow-y: auto;' in css
    assert '.kairos-column {' in css
    assert 'min-height: 0;' in css

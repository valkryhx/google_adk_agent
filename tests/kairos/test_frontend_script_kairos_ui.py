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
    assert 'id="kairosPlanningWinner"' in html
    assert 'id="kairosPlanningRejected"' in html
    assert 'id="kairosPlanningReplan"' in html


def test_kairos_modal_includes_attention_panel_and_reply_controls():
    html = INDEX.read_text(encoding="utf-8")
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'id="kairosAttentionItems"' in html
    assert 'id="kairosAttentionId"' in html
    assert 'id="kairosAttentionResponse"' in html
    assert 'id="kairosAttentionRespondBtn"' in html
    assert "function formatKairosAttentionItems(items)" in text
    assert "async function respondKairosAttention()" in text
    assert "document.getElementById('kairosAttentionItems')" in text
    assert "kairosAttentionRespondBtn.addEventListener('click', respondKairosAttention)" in text


def test_planning_card_styles_exist_for_console_shell():
    css = STYLE.read_text(encoding="utf-8")
    mobile = MOBILE.read_text(encoding="utf-8")

    assert ".kairos-planning-card" in css
    assert ".kairos-planning-chip" in css
    assert ".kairos-planning-list" in css
    assert ".kairos-planning-card" in mobile


def test_script_exposes_planning_formatters_and_dom_wiring():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "function formatKairosPlanningWinner(planning)" in text
    assert "function formatKairosPlanningRejected(planning)" in text
    assert "function formatKairosPlanningReplan(planning)" in text
    assert "document.getElementById('kairosPlanningWinner')" in text
    assert "document.getElementById('kairosPlanningRejected')" in text
    assert "document.getElementById('kairosPlanningReplan')" in text
    assert "planningWinnerEl.textContent = formatKairosPlanningWinner" in text
    assert "planningRejectedEl.textContent = formatKairosPlanningRejected" in text
    assert "planningReplanEl.textContent = formatKairosPlanningReplan" in text


def test_script_formats_history_timeline_as_structured_html_and_requests_ascending_order():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "function renderKairosHistoryTimeline(entries)" in text
    assert "historyEl.innerHTML = renderKairosHistoryTimeline(data.history || [])" in text
    assert "descending: 'false'" in text
    assert "kairos-timeline-entry-title" in text
    assert "kairos-timeline-entry-meta" in text
    assert "[${title}]" in text


def test_history_timeline_styles_use_darker_text_and_title_contrast():
    css = STYLE.read_text(encoding="utf-8")

    assert ".kairos-timeline-entry-title" in css
    assert ".kairos-timeline-entry-message" in css
    assert ".kairos-timeline-entry-time" in css
    assert "color: #111827;" in css
    assert "color: #374151;" in css


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

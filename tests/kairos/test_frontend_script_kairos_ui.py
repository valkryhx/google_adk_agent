from pathlib import Path

SCRIPT = Path(r"D:/git_repos/google_adk_agent/src/adk_agent/static/script.js")


def test_script_exposes_kairos_helpers_for_tracked_tasks():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "function formatKairosTrackedTasks(tasks)" in text
    assert "function formatKairosEvents(events)" in text
    assert "function formatKairosStatus(kairos)" in text
    assert "async function kairosRequest(" in text




def test_kairos_panels_preserve_multiline_text_rendering():
    html = Path(r"D:/git_repos/google_adk_agent/src/adk_agent/static/index.html").read_text(encoding="utf-8")

    assert 'id="kairosTrackedDexTasks"' in html
    assert 'id="kairosEvents"' in html
    assert 'id="kairosTrackedDexTasks" style="font-size:12px; color:#555; padding:8px; background:#f8f9fa; border-radius:6px; max-height:220px; overflow-y:auto; font-family:monospace; white-space:pre-wrap;"' in html
    assert 'id="kairosEvents" style="font-size:12px; color:#555; padding:8px; background:#f8f9fa; border-radius:6px; max-height:200px; overflow-y:auto; font-family:monospace; white-space:pre-wrap;"' in html

from pathlib import Path

SCRIPT = Path(r"D:/git_repos/google_adk_agent/src/adk_agent/static/script.js")


def test_script_exposes_kairos_helpers_for_tracked_tasks():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "function formatKairosTrackedTasks(tasks)" in text
    assert "function formatKairosEvents(events)" in text
    assert "function formatKairosStatus(kairos)" in text
    assert "async function kairosRequest(" in text


def test_script_refreshes_tracked_dex_tasks_panel_and_uses_helper_requests():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "const trackedEl = document.getElementById('kairosTrackedDexTasks');" in text
    assert "trackedEl.textContent = formatKairosTrackedTasks(kairos.tracked_dex_tasks || []);" in text
    assert "await kairosRequest('/kairos/start'" in text
    assert "await kairosRequest('/kairos/stop'" in text
    assert "await kairosRequest('/kairos/wake'" in text
    assert "await kairosRequest('/kairos/schedules'" in text
    assert "await kairosRequest('/kairos/dex/register'" in text

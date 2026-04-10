# Kairos Phase 4A Explainability, History & Operator UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 KAIROS 增加 session-scoped history API、timeline 语义模型和左右双栏 operator console，让用户能同时看到当前状态与完整历史推进证据。

**Architecture:** 保留现有 `SteeringSession -> KairosRuntime -> KairosActivityLog -> FastAPI -> static UI` 主干，不改 Phase 3 runtime/policy 核心语义。4A 只新增一条 archive-reader + history API 链路，并在现有 KAIROS modal 上做 split-layout 重构：左栏展示 current snapshot，右栏展示 history timeline。

**Tech Stack:** Python, FastAPI, dataclasses, existing markdown activity logs under `memory_archive/`, vanilla HTML/CSS/JavaScript, pytest, live HTTP regression

## Visual Direction

- **Theme:** 夜间值班台 / Autonomous Ops Console
- **Tone:** 深色、克制、精密、高密度；避免白底调试表单感，也避免过度赛博霓虹
- **Signature experience:** 左栏像驾驶舱展示 current state，右栏像飞行记录仪展示 history timeline，形成“可解释 autonomy”第一观感
- **Palette target:** `#0a0f14` / `#101923` / `#13202c` 为底，`#53e0c1` 为主强调，`#f4b860` / `#ef6b73` 为 guardrail 与 danger 状态色
- **Layout target:** 桌面 modal 宽度提升到 1180px~1280px，双栏比例约 58/42，modal 高度控制在 80vh~86vh，两栏独立滚动
- **UI rule:** `recent_events` 继续是 recent snapshot，右栏 history timeline 才是完整推进历史；不要把 timeline 做成 JSON dump
- **Implementation anchor:** 参考 `docs/superpowers/plans/2026-04-09-kairos-phase-4a-visual-brief.md`，把视觉系统落实到 `index.html + style.css + mobile.css + script.js`

---

## File Structure

### History ingestion and API
- Modify: `src/adk_agent/kairos/activity_log.py` — 在现有 append-only writer 旁增加 archive reader / parser，把 markdown history 转成 typed timeline entries
- Modify: `src/adk_agent/kairos/api.py` — 新增 session-scoped history route，并保持现有 `/kairos/status` shape 不变
- Modify: `src/adk_agent/kairos/attach.py` — 如有必要，补充轻量 history summary（例如 latest history ts / has_history），但不把完整 timeline 塞进 attach

### Frontend operator console
- Modify: `src/adk_agent/static/index.html` — 把 KAIROS modal 从单列改成左右结构，并新增 history timeline 区域与必要容器
- Modify: `src/adk_agent/static/script.js` — 新增 history fetch、timeline formatter、双列刷新逻辑，维持现有 status formatter 路径
- Modify: `src/adk_agent/static/style.css` — 为双栏 console、timeline cards、scroll containers、dark-leaning panel hierarchy 增加样式
- Modify: `src/adk_agent/static/mobile.css` — 为窄视口提供合理退化，避免桌面双栏在移动端直接坏掉
- Reference: `docs/superpowers/plans/2026-04-09-kairos-phase-4a-visual-brief.md` — 作为 4A UI 的视觉系统与布局基准

### Tests and evidence
- Modify: `tests/kairos/test_activity_log.py` — 锁定 archive reader / parser / timeline typing
- Modify: `tests/kairos/test_api.py` — 锁定 new history route contract 与 status route兼容性
- Modify: `tests/kairos/test_frontend_script_kairos_ui.py` — 锁定 DOM split-layout、history panel 与 formatter helper
- Modify: `tests/kairos/live_http_kairos_demo_outputs_regression.py` — 用真实 todo delivery session 断言 history evidence 对外可见
- Modify: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py` — 锁定 live helper 源码中对 history/timeline 的断言存在

### Planning artifacts
- Modify: `.planning/MILESTONES.md` — 收口到 v1.1 / 4A in progress
- Create: `.planning/phases/04A-explainability-history-ux/04A-CONTEXT.md` — 锁定 4A planning 输入
- Create: `.planning/phases/04A-explainability-history-ux/04A-01-PLAN.md` — 本阶段第一个实现计划（history API + operator console）

---

### Task 1: Lock timeline semantics in the activity log layer

**Files:**
- Modify: `tests/kairos/test_activity_log.py`
- Modify: `src/adk_agent/kairos/activity_log.py`
- Test: `tests/kairos/test_activity_log.py`

- [ ] **Step 1: Write the failing parser test for session history entries**

```python
# tests/kairos/test_activity_log.py
from pathlib import Path

from src.adk_agent.kairos.activity_log import KairosActivityLog


def test_read_session_history_returns_timeline_entries(tmp_path: Path):
    writer = KairosActivityLog(project_root=tmp_path)
    writer.append_entry(
        user_id="alice",
        app_name="demo_app",
        session_id="session_123",
        kind="brief",
        message="kairos auto-created dex task abc12345: generate todo delivery report (todo_delivery_ready)",
        ts="2026-04-09T10:00:00",
    )
    writer.append_entry(
        user_id="alice",
        app_name="demo_app",
        session_id="session_123",
        kind="status",
        message="todo_tests completed: tests ready",
        ts="2026-04-09T10:02:00",
    )

    entries = writer.read_session_history(
        user_id="alice",
        app_name="demo_app",
        session_id="session_123",
        descending=False,
    )

    assert [entry["kind"] for entry in entries] == ["follow_up", "task_completion"]
    assert entries[0]["title"] == "Auto-created follow-up"
    assert entries[0]["ts"] == "2026-04-09T10:00:00"
    assert entries[1]["title"] == "Completed task"
    assert entries[1]["message"] == "todo_tests completed: tests ready"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_activity_log.py::test_read_session_history_returns_timeline_entries -q`
Expected: FAIL with `AttributeError: 'KairosActivityLog' object has no attribute 'read_session_history'`

- [ ] **Step 3: Add the minimal archive reader and entry classifier**

```python
# src/adk_agent/kairos/activity_log.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from filelock import FileLock


class KairosActivityLog:
    # ... existing __init__ and append_entry ...

    def read_session_history(
        self,
        user_id: str,
        app_name: str,
        session_id: str,
        descending: bool = True,
    ) -> list[dict[str, Any]]:
        safe_app_name = app_name.replace("/", "_").replace("\\", "_")
        root = self.project_root / "memory_archive" / user_id
        pattern = f"**/*_{safe_app_name}_{session_id}_kairos.md"
        matches = sorted(root.glob(pattern))
        if not matches:
            return []

        entries: list[dict[str, Any]] = []
        for path in matches:
            entries.extend(self._parse_history_file(path))
        entries.sort(key=lambda item: item["ts"], reverse=descending)
        return entries

    def _parse_history_file(self, path: Path) -> list[dict[str, Any]]:
        text = path.read_text(encoding="utf-8")
        body = text.split("---\n\n", 1)[1] if "---\n\n" in text else text
        raw_chunks = [chunk.strip() for chunk in body.split("## ") if chunk.strip()]
        parsed: list[dict[str, Any]] = []
        for chunk in raw_chunks:
            lines = chunk.splitlines()
            ts = lines[0].strip()
            fields = {}
            for line in lines[1:]:
                if ": " in line:
                    key, value = line.split(": ", 1)
                    fields[key.strip()] = value.strip()
            message = fields.get("message", "")
            parsed.append(self._to_timeline_entry(ts, fields.get("kind", "brief"), message))
        return parsed

    def _to_timeline_entry(self, ts: str, kind: str, message: str) -> dict[str, Any]:
        entry_kind = kind
        title = "Kairos event"
        if "auto-created dex task" in message:
            entry_kind = "follow_up"
            title = "Auto-created follow-up"
        elif " completed:" in message or message.startswith("completed "):
            entry_kind = "task_completion"
            title = "Completed task"
        elif "blocked" in message or "waiting_input" in message:
            entry_kind = "guardrail"
            title = "Guardrail update"
        elif kind == "status":
            title = "Status update"
        elif kind == "brief":
            title = "Brief"
        return {
            "ts": ts,
            "kind": entry_kind,
            "title": title,
            "message": message,
            "workflow": None,
            "stage": None,
            "task_id": None,
            "metadata": {},
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_activity_log.py::test_read_session_history_returns_timeline_entries -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/kairos/test_activity_log.py src/adk_agent/kairos/activity_log.py
git commit -m "feat(kairos): add history timeline reader"
```

---

### Task 2: Expose the timeline through a dedicated history API route

**Files:**
- Modify: `tests/kairos/test_api.py`
- Modify: `src/adk_agent/kairos/api.py`
- Modify: `src/adk_agent/kairos/attach.py`
- Test: `tests/kairos/test_api.py`

- [ ] **Step 1: Write the failing API test for history retrieval**

```python
# tests/kairos/test_api.py

def test_history_route_returns_session_scoped_timeline(monkeypatch):
    app = FastAPI()
    manager = FakeManager()
    register_kairos_routes(app, manager)
    client = TestClient(app)

    class FakeHistory:
        def read_session_history(self, user_id, app_name, session_id, descending=True):
            assert (user_id, app_name, session_id, descending) == ("alice", "demo", "session_1", True)
            return [
                {
                    "ts": "2026-04-09T10:00:00",
                    "kind": "follow_up",
                    "title": "Auto-created follow-up",
                    "message": "kairos auto-created dex task abc12345: generate todo delivery report",
                    "workflow": "todo_delivery_pipeline",
                    "stage": "delivery_report",
                    "task_id": "abc12345",
                    "metadata": {},
                }
            ]

    monkeypatch.setattr("src.adk_agent.kairos.api.KairosActivityLog", lambda *_args, **_kwargs: FakeHistory())

    resp = client.get(
        "/api/sessions/session_1/kairos/history",
        params={"app_name": "demo", "user_id": "alice", "descending": "true"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["session_id"] == "session_1"
    assert data["history"][0]["kind"] == "follow_up"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_api.py::test_history_route_returns_session_scoped_timeline -q`
Expected: FAIL with 404 for `/api/sessions/session_1/kairos/history`

- [ ] **Step 3: Add the history route without changing status route behavior**

```python
# src/adk_agent/kairos/api.py
from pathlib import Path

from .activity_log import KairosActivityLog


def register_kairos_routes(app, session_manager):
    router = APIRouter()

    # ... existing routes ...

    @router.get("/api/sessions/{session_id}/kairos/history")
    async def kairos_history(
        session_id: str,
        app_name: str,
        user_id: str,
        descending: bool = True,
    ):
        project_root = Path(__file__).resolve().parents[3]
        history = KairosActivityLog(project_root).read_session_history(
            user_id=user_id,
            app_name=app_name,
            session_id=session_id,
            descending=descending,
        )
        return {
            "status": "ok",
            "session_id": session_id,
            "history": history,
        }
```

```python
# src/adk_agent/kairos/attach.py
from src.adk_agent.kairos.activity_log import KairosActivityLog
from pathlib import Path


def build_runtime_summary(app_name: str, user_id: str, session_id: str, runtime) -> dict:
    status = runtime.get_status()
    project_root = Path(__file__).resolve().parents[3]
    has_history = bool(
        KairosActivityLog(project_root).read_session_history(
            user_id=user_id,
            app_name=app_name,
            session_id=session_id,
            descending=True,
        )[:1]
    )
    return {
        "app_name": app_name,
        "user_id": user_id,
        "session_id": session_id,
        "mode": status.get("mode"),
        "running": status.get("running"),
        "recent_events": status.get("recent_events", [])[-5:],
        "has_history": has_history,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_api.py::test_history_route_returns_session_scoped_timeline -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/kairos/test_api.py src/adk_agent/kairos/api.py src/adk_agent/kairos/attach.py
git commit -m "feat(kairos): expose session history API"
```

---

### Task 3A: Build the visual shell for the operator console

**Files:**
- Modify: `tests/kairos/test_frontend_script_kairos_ui.py`
- Modify: `src/adk_agent/static/index.html`
- Modify: `src/adk_agent/static/style.css`
- Modify: `src/adk_agent/static/mobile.css`
- Test: `tests/kairos/test_frontend_script_kairos_ui.py`

- [ ] **Step 1: Write the failing frontend structure test for console shell classes and containers**

```python
# tests/kairos/test_frontend_script_kairos_ui.py

def test_kairos_modal_exposes_console_shell_structure():
    html = INDEX.read_text(encoding="utf-8")
    css = (ROOT / "src" / "adk_agent" / "static" / "style.css").read_text(encoding="utf-8")

    assert 'id="kairosConsole"' in html
    assert 'id="kairosLiveColumn"' in html
    assert 'id="kairosHistoryColumn"' in html
    assert 'class="kairos-console"' in html
    assert '.kairos-console' in css
    assert '.kairos-column' in css
    assert '.kairos-card' in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py::test_kairos_modal_exposes_console_shell_structure -q`
Expected: FAIL because the current modal still lacks the dedicated shell classes and split containers.

- [ ] **Step 3: Add the shell structure and base responsive grid**

```html
<!-- src/adk_agent/static/index.html -->
<div id="kairosPanel" style="display:none;">
  <div id="kairosConsole" class="kairos-console">
    <div id="kairosLiveColumn" class="kairos-column kairos-column-live"></div>
    <div id="kairosHistoryColumn" class="kairos-column kairos-column-history"></div>
  </div>
</div>
```

```css
/* src/adk_agent/static/style.css */
.kairos-console {
    display: grid;
    grid-template-columns: minmax(0, 1.35fr) minmax(360px, 0.98fr);
    gap: 18px;
    align-items: start;
}

.kairos-column {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 14px;
}

.kairos-card {
    border-radius: 14px;
    border: 1px solid rgba(148, 163, 184, 0.14);
    background: #101923;
}
```

```css
/* src/adk_agent/static/mobile.css */
@media (max-width: 960px) {
    .kairos-console {
        grid-template-columns: 1fr;
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py::test_kairos_modal_exposes_console_shell_structure -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/kairos/test_frontend_script_kairos_ui.py src/adk_agent/static/index.html src/adk_agent/static/style.css src/adk_agent/static/mobile.css
git commit -m "feat(kairos-ui): add operator console shell"
```

---

### Task 3B: Apply the dark operator visual system

**Files:**
- Modify: `tests/kairos/test_frontend_script_kairos_ui.py`
- Modify: `src/adk_agent/static/style.css`
- Modify: `src/adk_agent/static/mobile.css`
- Test: `tests/kairos/test_frontend_script_kairos_ui.py`

- [ ] **Step 1: Write the failing style test for Kairos visual tokens**

```python
# tests/kairos/test_frontend_script_kairos_ui.py

def test_kairos_styles_define_dark_console_tokens():
    css = (ROOT / "src" / "adk_agent" / "static" / "style.css").read_text(encoding="utf-8")

    assert '--kairos-bg:' in css
    assert '--kairos-panel:' in css
    assert '--kairos-accent:' in css
    assert '.kairos-pill' in css
    assert '.kairos-metric-grid' in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py::test_kairos_styles_define_dark_console_tokens -q`
Expected: FAIL because the tokenized visual system is not defined yet.

- [ ] **Step 3: Add palette tokens, pills, and metric-grid styling**

```css
/* src/adk_agent/static/style.css */
:root {
    --kairos-bg: #0a0f14;
    --kairos-panel: #101923;
    --kairos-panel-2: #13202c;
    --kairos-border: rgba(148, 163, 184, 0.14);
    --kairos-text: #e6edf5;
    --kairos-muted: #8aa0b6;
    --kairos-accent: #53e0c1;
    --kairos-warn: #f4b860;
    --kairos-danger: #ef6b73;
}

.kairos-pill {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: 999px;
    background: rgba(83, 224, 193, 0.14);
    color: var(--kairos-accent);
    font-size: 11px;
}

.kairos-metric-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py::test_kairos_styles_define_dark_console_tokens -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/kairos/test_frontend_script_kairos_ui.py src/adk_agent/static/style.css src/adk_agent/static/mobile.css
git commit -m "feat(kairos-ui): add visual system tokens"
```

---

### Task 3C: Turn the history column into a real timeline rail

**Files:**
- Modify: `tests/kairos/test_frontend_script_kairos_ui.py`
- Modify: `src/adk_agent/static/index.html`
- Modify: `src/adk_agent/static/style.css`
- Test: `tests/kairos/test_frontend_script_kairos_ui.py`

- [ ] **Step 1: Write the failing structure test for timeline rail primitives**

```python
# tests/kairos/test_frontend_script_kairos_ui.py

def test_kairos_modal_contains_timeline_rail_hooks():
    html = INDEX.read_text(encoding="utf-8")
    css = (ROOT / "src" / "adk_agent" / "static" / "style.css").read_text(encoding="utf-8")

    assert 'id="kairosHistoryTimeline"' in html
    assert '.kairos-timeline' in css
    assert '.kairos-timeline-item' in css
    assert '.kairos-timeline-dot' in css
    assert '.kairos-timeline-content' in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py::test_kairos_modal_contains_timeline_rail_hooks -q`
Expected: FAIL because the timeline rail classes are not present yet.

- [ ] **Step 3: Add the timeline rail container and card styling hooks**

```html
<!-- src/adk_agent/static/index.html -->
<div id="kairosHistoryColumn" class="kairos-column kairos-column-history">
  <div class="setting-group kairos-card kairos-history-group">
    <label>History Timeline</label>
    <div id="kairosHistoryTimeline" class="kairos-timeline">加载中...</div>
  </div>
</div>
```

```css
/* src/adk_agent/static/style.css */
.kairos-timeline {
    display: flex;
    flex-direction: column;
    gap: 12px;
    max-height: 720px;
    overflow-y: auto;
}

.kairos-timeline-item {
    display: grid;
    grid-template-columns: 18px minmax(0, 1fr);
    gap: 12px;
}

.kairos-timeline-dot {
    width: 10px;
    height: 10px;
    border-radius: 999px;
    background: var(--kairos-accent);
}

.kairos-timeline-content {
    border: 1px solid var(--kairos-border);
    border-radius: 12px;
    background: #13202c;
    padding: 12px;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py::test_kairos_modal_contains_timeline_rail_hooks -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/kairos/test_frontend_script_kairos_ui.py src/adk_agent/static/index.html src/adk_agent/static/style.css
git commit -m "feat(kairos-ui): add timeline rail hooks"
```

---

### Task 4A: Add history formatter and fetch flow

**Files:**
- Modify: `tests/kairos/test_frontend_script_kairos_ui.py`
- Modify: `src/adk_agent/static/script.js`
- Test: `tests/kairos/test_frontend_script_kairos_ui.py`

- [ ] **Step 1: Write the failing script test for history fetch helpers**

```python
# tests/kairos/test_frontend_script_kairos_ui.py

def test_script_exposes_history_fetch_helpers():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "function formatKairosHistoryTimeline(entries)" in text
    assert "async function refreshKairosHistory()" in text
    assert "'/kairos/history'" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py::test_script_exposes_history_fetch_helpers -q`
Expected: FAIL because the history fetch/format helpers do not exist yet.

- [ ] **Step 3: Add `formatKairosHistoryTimeline()` and `refreshKairosHistory()`**

```javascript
// src/adk_agent/static/script.js
function formatKairosHistoryTimeline(entries) {
    if (!entries || entries.length === 0) return '无历史记录';
    return entries.map((entry) => {
        return [
            `[${entry.ts || '-'}] ${entry.title || entry.kind || 'Kairos event'}`,
            entry.message || '-',
            entry.workflow ? `workflow: ${entry.workflow}` : null,
            entry.stage ? `stage: ${entry.stage}` : null,
            entry.task_id ? `task_id: ${entry.task_id}` : null,
        ].filter(Boolean).join('\n');
    }).join('\n\n');
}

async function refreshKairosHistory() {
    const sessionId = getCurrentSessionId();
    const historyEl = document.getElementById('kairosHistoryTimeline');
    if (!historyEl) return;
    if (!sessionId) {
        historyEl.textContent = '请先选择或创建一个对话';
        return;
    }
    const params = new URLSearchParams({
        app_name: APP_NAME,
        user_id: getUserId(),
        descending: 'true',
    });
    const response = await fetch(`/api/sessions/${sessionId}/kairos/history?${params.toString()}`);
    const data = await response.json();
    historyEl.textContent = formatKairosHistoryTimeline(data.history || []);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py::test_script_exposes_history_fetch_helpers -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/kairos/test_frontend_script_kairos_ui.py src/adk_agent/static/script.js
git commit -m "feat(kairos-ui): add history fetch flow"
```

---

### Task 4B: Upgrade current-state rendering from text dump toward cockpit cards

**Files:**
- Modify: `tests/kairos/test_frontend_script_kairos_ui.py`
- Modify: `src/adk_agent/static/script.js`
- Modify: `src/adk_agent/static/index.html`
- Test: `tests/kairos/test_frontend_script_kairos_ui.py`

- [ ] **Step 1: Write the failing test for overview render hooks**

```python
# tests/kairos/test_frontend_script_kairos_ui.py

def test_script_exposes_kairos_overview_render_helpers():
    text = SCRIPT.read_text(encoding="utf-8")
    html = INDEX.read_text(encoding="utf-8")

    assert "function formatKairosOverview(kairos)" in text
    assert 'id="kairosOverviewCard"' in html
    assert 'id="kairosControlsCard"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py::test_script_exposes_kairos_overview_render_helpers -q`
Expected: FAIL because overview card hooks do not exist yet.

- [ ] **Step 3: Add overview card containers and renderer**

```html
<!-- src/adk_agent/static/index.html -->
<div id="kairosOverviewCard" class="setting-group kairos-card"></div>
<div id="kairosControlsCard" class="setting-group kairos-card"></div>
```

```javascript
// src/adk_agent/static/script.js
function formatKairosOverview(kairos) {
    return {
        mode: kairos.mode || '-',
        running: Boolean(kairos.running),
        busy: Boolean(kairos.busy),
        last_tick_at: kairos.last_tick_at || '-',
        sleep_until: kairos.sleep_until || '-',
    };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_frontend_script_kairos_ui.py::test_script_exposes_kairos_overview_render_helpers -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/kairos/test_frontend_script_kairos_ui.py src/adk_agent/static/script.js src/adk_agent/static/index.html
git commit -m "feat(kairos-ui): add overview render hooks"
```

---

### Task 5: Prove the history surface with live todo-delivery evidence

**Files:**
- Modify: `tests/kairos/live_http_kairos_demo_outputs_regression.py`
- Modify: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`
- Test: `tests/kairos/test_live_http_kairos_demo_outputs_regression.py`

- [ ] **Step 1: Write the failing source-level regression test for history evidence**

```python
# tests/kairos/test_live_http_kairos_demo_outputs_regression.py

def test_live_http_source_asserts_history_timeline_visibility():
    text = MODULE_PATH.read_text(encoding="utf-8")

    assert '/kairos/history' in text
    assert 'history_payload' in text
    assert 'Auto-created follow-up' in text or 'follow_up' in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py::test_live_http_source_asserts_history_timeline_visibility -q`
Expected: FAIL because the live helper does not fetch or assert history yet

- [ ] **Step 3: Add live assertions for current state plus history timeline**

```python
# tests/kairos/live_http_kairos_demo_outputs_regression.py

def _fetch_kairos_history(session_id: str) -> dict[str, Any]:
    return _request(
        "GET",
        f"/api/sessions/{session_id}/kairos/history?app_name={APP_NAME}&user_id={USER_ID}&descending=true",
    )


def run_todo_delivery_pipeline(repo_root: Path | None = None) -> dict[str, Any]:
    # ... existing setup and final_status assertions ...
    history_payload = _fetch_kairos_history(session_id)
    history_entries = history_payload["history"]

    assert history_entries
    assert any(entry["kind"] in {"follow_up", "task_completion"} for entry in history_entries)
    assert any("todo delivery report" in entry["message"] for entry in history_entries)

    return {
        "session_id": session_id,
        "final_status": final_status,
        "history_payload": history_payload,
        "report_task": report_task,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 PYTHONPATH=. pytest tests/kairos/test_live_http_kairos_demo_outputs_regression.py::test_live_http_source_asserts_history_timeline_visibility -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/kairos/live_http_kairos_demo_outputs_regression.py tests/kairos/test_live_http_kairos_demo_outputs_regression.py
git commit -m "test(kairos): verify history timeline visibility"
```

---

## Self-Review

### Spec coverage
- 4A-1 History API → Task 1, Task 2, Task 5
- 4A-2 Timeline model → Task 1, Task 4, Task 5
- 4A-3 Modal layout redesign → Task 3
- 4A-4 Dense operator UX aesthetic baseline → Task 3, Task 4
- 4A-5 Evidence of work → Task 1, Task 4, Task 5
- 4A acceptance criteria for API/frontend/tests → Task 2, Task 3, Task 4, Task 5

### Placeholder scan
- No `TODO`/`TBD` placeholders remain
- Each task includes concrete files, code snippets, commands, and expected results
- No task depends on an undefined helper without also defining it in a prior step

### Type consistency
- Timeline payload consistently uses `ts`, `kind`, `title`, `message`, `workflow`, `stage`, `task_id`, `metadata`
- Frontend history DOM id is consistently `kairosHistoryTimeline`
- New route is consistently `/api/sessions/{session_id}/kairos/history`

---

Plan complete and saved to `docs/superpowers/plans/2026-04-09-kairos-phase-4a-explainability-history-ux.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

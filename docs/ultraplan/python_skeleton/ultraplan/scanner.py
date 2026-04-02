from __future__ import annotations

from .constants import APPROVED_PLAN_MARKERS, ULTRAPLAN_TELEPORT_SENTINEL
from .models import ScanKind, ScanResult

EXIT_PLAN_MODE_TOOL_NAMES = {"ExitPlanMode", "ExitPlanModeV2"}


def content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
        return "".join(parts)
    return ""


def extract_teleport_plan(content: object) -> str | None:
    text = content_to_text(content)
    marker = f"{ULTRAPLAN_TELEPORT_SENTINEL}\n"
    idx = text.find(marker)
    if idx == -1:
        return None
    return text[idx + len(marker) :].rstrip()


def extract_approved_plan(content: object) -> str:
    text = content_to_text(content)
    for marker in APPROVED_PLAN_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            return text[idx + len(marker) :].rstrip()
    raise ValueError("Approved plan marker not found")


class ExitPlanModeScanner:
    def __init__(self):
        self.exit_plan_calls: list[str] = []
        self.results: dict[str, dict] = {}
        self.rejected_ids: set[str] = set()
        self.terminated_subtype: str | None = None
        self.rescan_after_rejection = False
        self.ever_seen_pending = False

    @property
    def reject_count(self) -> int:
        return len(self.rejected_ids)

    @property
    def has_pending_plan(self) -> bool:
        for call_id in reversed(self.exit_plan_calls):
            if call_id in self.rejected_ids:
                continue
            return call_id not in self.results
        return False

    def ingest(self, new_events: list[dict]) -> ScanResult:
        for event in new_events:
            self._consume_event(event)

        should_scan = bool(new_events) or self.rescan_after_rejection
        self.rescan_after_rejection = False

        found: ScanResult | None = None
        if should_scan:
            found = self._scan_latest()
            if found and found.kind in {ScanKind.APPROVED, ScanKind.TELEPORT}:
                return found

        if found and found.kind == ScanKind.REJECTED and found.rejected_id:
            self.rejected_ids.add(found.rejected_id)
            self.rescan_after_rejection = True

        if self.terminated_subtype:
            return ScanResult(kind=ScanKind.TERMINATED, terminated_subtype=self.terminated_subtype)

        if found and found.kind == ScanKind.REJECTED:
            return found

        if found and found.kind == ScanKind.PENDING:
            self.ever_seen_pending = True
            return found

        return ScanResult(kind=ScanKind.UNCHANGED)

    def _consume_event(self, event: dict) -> None:
        event_type = event.get("type")
        if event_type == "assistant":
            blocks = event.get("message", {}).get("content", [])
            for block in blocks:
                if block.get("type") == "tool_use" and block.get("name") in EXIT_PLAN_MODE_TOOL_NAMES:
                    self.exit_plan_calls.append(block["id"])
        elif event_type == "user":
            blocks = event.get("message", {}).get("content", [])
            for block in blocks:
                if block.get("type") == "tool_result":
                    self.results[block["tool_use_id"]] = block
        elif event_type == "result" and event.get("subtype") != "success":
            self.terminated_subtype = event.get("subtype")

    def _scan_latest(self) -> ScanResult | None:
        for call_id in reversed(self.exit_plan_calls):
            if call_id in self.rejected_ids:
                continue
            tool_result = self.results.get(call_id)
            if tool_result is None:
                return ScanResult(kind=ScanKind.PENDING)
            if tool_result.get("is_error") is True:
                teleport_plan = extract_teleport_plan(tool_result.get("content"))
                if teleport_plan is not None:
                    return ScanResult(kind=ScanKind.TELEPORT, plan=teleport_plan)
                return ScanResult(kind=ScanKind.REJECTED, rejected_id=call_id)
            return ScanResult(kind=ScanKind.APPROVED, plan=extract_approved_plan(tool_result.get("content")))
        return None

from __future__ import annotations

try:
    from .models import DexTaskStatus
except ImportError:  # pragma: no cover - script import fallback
    from models import DexTaskStatus


def summarize_output(exit_code: int, output_text: str) -> dict:
    lines = [line.strip() for line in output_text.splitlines() if line.strip()]
    last_line = lines[-1] if lines else None
    if exit_code == 0:
        return {
            "status": DexTaskStatus.COMPLETED,
            "result_summary": last_line,
            "error_summary": None,
        }
    return {
        "status": DexTaskStatus.FAILED,
        "result_summary": None,
        "error_summary": last_line or f"process exited with code {exit_code}",
    }

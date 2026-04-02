from ultraplan.models import UltraplanPhase
from ultraplan.phase import UltraplanPhaseResolver


class DummyScanner:
    def __init__(self, has_pending_plan: bool):
        self.has_pending_plan = has_pending_plan


def test_resolve_prefers_plan_ready_when_pending_plan_exists():
    resolver = UltraplanPhaseResolver()
    phase = resolver.resolve(
        scanner=DummyScanner(True),
        session_status="idle",
        new_events=[],
    )
    assert phase == UltraplanPhase.PLAN_READY

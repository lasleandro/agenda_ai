"""Unit tests for candidate persistence helpers."""

from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.extraction import SchedulingEvent
from app.chat.pipeline import event_fingerprint


def build_event(start_at: datetime) -> SchedulingEvent:
    """Build a deterministic event fixture for fingerprint tests."""
    return SchedulingEvent(
        action="confirm",
        start_at=start_at,
        end_at=datetime(2026, 8, 5, 11, 0),
        service="tennis_lesson",
        confidence=0.9,
        evidence_message_ids=["message-2", "message-1"],
        explanation="Horário confirmado.",
    )


def test_event_fingerprint_is_stable_when_evidence_order_changes() -> None:
    """The same extracted event must deduplicate across repeated LLM output."""
    first = build_event(datetime(2026, 8, 5, 10, 0))
    second = build_event(datetime(2026, 8, 5, 10, 0))
    second.evidence_message_ids.reverse()

    assert event_fingerprint(first) == event_fingerprint(second)


def test_event_fingerprint_changes_for_a_different_time() -> None:
    """Distinct scheduling events must remain independently persistable."""
    first = build_event(datetime(2026, 8, 5, 10, 0))
    second = build_event(datetime(2026, 8, 11, 12, 0))

    assert event_fingerprint(first) != event_fingerprint(second)

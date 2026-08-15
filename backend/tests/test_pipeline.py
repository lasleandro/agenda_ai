"""Unit tests for candidate persistence helpers."""

from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.chat.pipeline as pipeline
from app.database import SessionLocal
from app.models import (
    AppointmentCandidate,
    AppointmentEvidence,
    Contact,
    Conversation,
    Message,
    PendingProcessing,
    Professional,
)
from app.chat.ingestion import ingest_normalized_message
from app.chat.pipeline import event_fingerprint, process_conversation
from app.chat.ycloud_provider import NormalizedMessage
from app.schemas.extraction import SchedulingEvent


def build_event(start_at: datetime) -> SchedulingEvent:
    """Build a deterministic event fixture for fingerprint tests."""
    return SchedulingEvent(
        operation="create",
        confirmation_status="customer_confirmed",
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


def test_event_fingerprint_is_stable_when_confirmation_advances() -> None:
    """A later instructor confirmation must update the same candidate."""
    proposal = build_event(datetime(2026, 8, 5, 10, 0))
    confirmed = proposal.model_copy(
        update={
            "confirmation_status": "instructor_confirmed",
            "evidence_message_ids": ["message-3"],
        }
    )

    assert event_fingerprint(proposal) == event_fingerprint(confirmed)


def test_event_fingerprint_changes_for_a_different_time() -> None:
    """Distinct scheduling events must remain independently persistable."""
    first = build_event(datetime(2026, 8, 5, 10, 0))
    second = build_event(datetime(2026, 8, 11, 12, 0))

    assert event_fingerprint(first) != event_fingerprint(second)


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().hex[:8]}"


def _cleanup(db, professional_id: uuid.UUID) -> None:
    conversation_ids = [
        row[0]
        for row in db.query(Conversation.id)
        .filter(Conversation.professional_id == professional_id)
        .all()
    ]
    if conversation_ids:
        db.query(AppointmentEvidence).filter(
            AppointmentEvidence.appointment_candidate_id.in_(
                db.query(AppointmentCandidate.id).filter(
                    AppointmentCandidate.conversation_id.in_(conversation_ids)
                )
            )
        ).delete(synchronize_session=False)
        db.query(AppointmentCandidate).filter(
            AppointmentCandidate.conversation_id.in_(conversation_ids)
        ).delete(synchronize_session=False)
        db.query(PendingProcessing).filter(
            PendingProcessing.conversation_id.in_(conversation_ids)
        ).delete(synchronize_session=False)
    db.query(Message).filter(Message.professional_id == professional_id).delete(
        synchronize_session=False
    )
    db.query(Conversation).filter(
        Conversation.professional_id == professional_id
    ).delete(synchronize_session=False)
    db.query(Contact).filter(Contact.professional_id == professional_id).delete(
        synchronize_session=False
    )
    db.query(Professional).filter(Professional.id == professional_id).delete(
        synchronize_session=False
    )
    db.commit()


def test_process_conversation_reprocessing_does_not_duplicate_evidence(monkeypatch) -> None:
    """A conversation can be reprocessed for the same extracted event (a new
    inbound message resets the debounce timer while the fingerprint stays
    the same). Evidence rows share a (candidate_id, message_id) primary key,
    so re-inserting the same pair on a second run must be a no-op, not a
    crash: this reproduces a production IntegrityError where a
    SELECT-then-INSERT check missed rows already committed by an earlier
    run and the worker died trying to log the failure."""
    db = SessionLocal()
    professional = Professional(name="Tenant", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()

    customer_phone = _random_phone()
    message = ingest_normalized_message(
        db,
        NormalizedMessage(
            provider_message_id=f"msg_{uuid.uuid4().hex}",
            direction="inbound",
            from_phone=customer_phone,
            to_phone=professional.assistant_phone,
            text="Bora fechar toda terca as 18h?",
            sent_at=datetime.now(timezone.utc),
            raw_payload={},
        ),
    )
    conversation = db.query(Conversation).filter(Conversation.id == message.conversation_id).one()

    def fake_extract(window):
        evidence_ids = [m.id for m in window.messages]
        return [
            SchedulingEvent(
                operation="recurrence",
                confirmation_status="not_confirmed",
                service="tennis_lesson",
                confidence=0.9,
                evidence_message_ids=evidence_ids,
                explanation="Proposta de recorrencia sem confirmacao.",
            )
        ]

    monkeypatch.setattr(pipeline, "extract_scheduling_events", fake_extract)

    try:
        first_run = process_conversation(db, conversation)
        second_run = process_conversation(db, conversation)

        assert len(first_run) == 1
        assert first_run[0].id == second_run[0].id

        evidence_rows = (
            db.query(AppointmentEvidence)
            .filter(AppointmentEvidence.appointment_candidate_id == first_run[0].id)
            .all()
        )
        assert len(evidence_rows) == 1
        assert evidence_rows[0].message_id == message.id
    finally:
        _cleanup(db, professional.id)
        db.close()

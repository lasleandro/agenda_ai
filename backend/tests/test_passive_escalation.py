"""Behavior tests for durable ambiguity-only passive escalation."""

from datetime import datetime, timedelta
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import AppointmentCandidate, Contact, OperationalEvent, OperatorActionCandidate, PassiveEscalation, Place, Professional, RecurringSlot, User
from app.services.scheduling import TIMEZONE
from app.services import passive_escalation


def _setup(status: str = "unclear"):
    db = SessionLocal()
    professional = Professional(name="Escalation", assistant_phone=f"+55119{uuid.uuid4().hex[:8]}", agent_phone=f"+55118{uuid.uuid4().hex[:8]}")
    db.add(professional)
    db.flush()
    contact = Contact(professional_id=professional.id, phone=f"+55119{uuid.uuid4().int % 100_000_000:08d}", display_name="Aluno", normalized_name="aluno")
    place = Place(professional_id=professional.id, name="Clube", normalized_name="clube")
    user = User(professional_id=professional.id, email=f"{uuid.uuid4().hex}@example.test", hashed_password="x", role="professional")
    db.add_all([contact, place, user])
    db.flush()
    contact.home_place_id = place.id
    candidate = AppointmentCandidate(
        professional_id=professional.id, contact_id=contact.id, action="create", operation="create",
        confirmation_status=status, proposed_start_at=datetime.now().astimezone() + timedelta(days=3),
        proposed_end_at=datetime.now().astimezone() + timedelta(days=3, hours=1), service="tennis_lesson", status="detected", ambiguities=[],
    )
    db.add(candidate)
    db.commit()
    local_start = candidate.proposed_start_at.astimezone(TIMEZONE)
    local_end = candidate.proposed_end_at.astimezone(TIMEZONE)
    db.add(
        RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=local_start.weekday(),
            start_time=local_start.time().replace(tzinfo=None),
            end_time=local_end.time().replace(tzinfo=None),
            slot_kind="availability",
            status="active",
        )
    )
    db.commit()
    return db, professional, candidate


def _cleanup(db, professional):
    db.query(OperationalEvent).filter_by(professional_id=professional.id).delete()
    db.query(PassiveEscalation).filter_by(professional_id=professional.id).delete()
    db.query(AppointmentCandidate).filter_by(professional_id=professional.id).delete()
    db.query(OperatorActionCandidate).filter_by(professional_id=professional.id).delete()
    db.query(RecurringSlot).filter_by(professional_id=professional.id).delete()
    db.query(Contact).filter_by(professional_id=professional.id).delete()
    db.query(Place).filter_by(professional_id=professional.id).delete()
    db.query(User).filter_by(professional_id=professional.id).delete()
    db.query(Professional).filter_by(id=professional.id).delete()
    db.commit()
    db.close()


def test_queue_only_accepts_fully_resolved_unclear_candidate():
    db, professional, candidate = _setup("instructor_confirmed")
    try:
        assert passive_escalation.queue_if_eligible(db, candidate) is None
        candidate.confirmation_status = "unclear"
        assert passive_escalation.queue_if_eligible(db, candidate) is not None
    finally:
        _cleanup(db, professional)


def test_due_escalation_sends_one_linked_idempotent_proposal(monkeypatch):
    db, professional, candidate = _setup()
    sent = {}
    monkeypatch.setattr(passive_escalation, "send_text_message_or_raise", lambda **kwargs: sent.update(kwargs))
    try:
        escalation = passive_escalation.queue_if_eligible(db, candidate)
        db.commit()
        assert passive_escalation.process_due_escalations(db) == 1
        db.refresh(candidate)
        db.refresh(escalation)
        assert escalation.status == "sent"
        assert candidate.operator_action_candidate_id is not None
        assert "Responda *sim*" in sent["body"]
        assert passive_escalation.process_due_escalations(db) == 0
        assert db.query(OperatorActionCandidate).filter_by(professional_id=professional.id).count() == 1
    finally:
        _cleanup(db, professional)


def test_uncovered_candidate_waits_for_manual_place_review_without_retrying():
    db, professional, candidate = _setup()
    try:
        db.query(RecurringSlot).filter_by(professional_id=professional.id).delete()
        db.commit()

        escalation = passive_escalation.queue_if_eligible(db, candidate)

        assert escalation is not None
        assert not passive_escalation.deliver(escalation, db)
        assert escalation.status == "needs_place_review"
        assert escalation.last_error == "Place context requires instructor review"
    finally:
        _cleanup(db, professional)


def test_place_stay_change_reactivates_candidate_waiting_for_place_review():
    db, professional, candidate = _setup()
    try:
        db.query(RecurringSlot).filter_by(professional_id=professional.id).delete()
        db.commit()
        escalation = passive_escalation.queue_if_eligible(db, candidate)
        assert escalation is not None
        assert not passive_escalation.deliver(escalation, db)
        assert escalation.status == "needs_place_review"

        place = db.query(Place).filter_by(professional_id=professional.id).one()
        local_start = candidate.proposed_start_at.astimezone(TIMEZONE)
        local_end = candidate.proposed_end_at.astimezone(TIMEZONE)
        db.add(
            RecurringSlot(
                professional_id=professional.id,
                place_id=place.id,
                day_of_week=local_start.weekday(),
                start_time=local_start.time().replace(tzinfo=None),
                end_time=local_end.time().replace(tzinfo=None),
                slot_kind="availability",
                status="active",
            )
        )

        assert (
            passive_escalation.reactivate_place_review_escalations(
                db, professional.id
            )
            == 1
        )
        assert escalation.status == "queued"
        assert escalation.last_error is None
    finally:
        _cleanup(db, professional)

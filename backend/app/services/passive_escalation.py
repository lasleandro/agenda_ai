"""Queue and deliver ambiguity-only passive confirmations."""

import os
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.agent import mutations
from app.chat.ycloud_provider import send_text_message_or_raise
from app.models import AppointmentCandidate, OperatorActionCandidate, PassiveEscalation, Professional, User
from app.services.candidate_resolution import resolve_candidate
from app.services.scheduling import TIMEZONE
from app.services.operational_events import record_event

TTL_MINUTES = int(os.getenv("PASSIVE_ESCALATION_TTL_MINUTES", "60"))
RETRY_SECONDS = int(os.getenv("PASSIVE_ESCALATION_RETRY_SECONDS", "60"))


def queue_if_eligible(db: Session, candidate: AppointmentCandidate) -> PassiveEscalation | None:
    """Persist, but do not deliver, one escalation when every safety gate passes."""
    if candidate.confirmation_status != "unclear" or candidate.status != "detected":
        return None
    if candidate.operator_action_candidate_id is not None:
        return None
    resolution = resolve_candidate(db, candidate)
    if resolution.operation not in {"create", "reschedule"}:
        return None
    if not resolution.is_resolved and resolution.missing_fields != ["place_id"]:
        return None
    professional = db.get(Professional, candidate.professional_id)
    actor = db.query(User).filter(User.professional_id == candidate.professional_id, User.role == "professional").first()
    if professional is None or not professional.agent_phone or actor is None:
        return None
    existing = db.query(PassiveEscalation).filter_by(appointment_candidate_id=candidate.id).first()
    if existing is not None:
        return existing
    escalation = PassiveEscalation(
        appointment_candidate_id=candidate.id,
        professional_id=candidate.professional_id,
        next_attempt_at=datetime.now(TIMEZONE),
    )
    db.add(escalation)
    db.flush()
    return escalation


def reactivate_place_review_escalations(
    db: Session, professional_id: uuid.UUID
) -> int:
    """Queue candidates that became resolvable after a place-stay change."""
    db.flush()
    rows = (
        db.query(PassiveEscalation)
        .join(AppointmentCandidate)
        .filter(
            PassiveEscalation.professional_id == professional_id,
            PassiveEscalation.status == "needs_place_review",
            AppointmentCandidate.status == "detected",
        )
        .all()
    )
    now = datetime.now(TIMEZONE)
    reactivated = 0
    for escalation in rows:
        resolution = resolve_candidate(db, escalation.appointment_candidate)
        if not resolution.is_resolved:
            continue
        escalation.status = "queued"
        escalation.next_attempt_at = now
        escalation.last_error = None
        reactivated += 1
    return reactivated


def _has_unrelated_pending(db: Session, escalation: PassiveEscalation) -> bool:
    linked = escalation.appointment_candidate.operator_action_candidate_id
    return db.query(OperatorActionCandidate.id).filter(
        OperatorActionCandidate.professional_id == escalation.professional_id,
        OperatorActionCandidate.channel == "whatsapp",
        OperatorActionCandidate.status == "proposed",
        OperatorActionCandidate.id != linked,
    ).first() is not None


def deliver(escalation: PassiveEscalation, db: Session) -> bool:
    """Create/reuse one proposal, link it, then send its confirmation prompt."""
    now = datetime.now(TIMEZONE)
    candidate = escalation.appointment_candidate
    if candidate.status != "detected":
        escalation.status = "expired"
        return False
    if _has_unrelated_pending(db, escalation):
        escalation.next_attempt_at = now + timedelta(seconds=RETRY_SECONDS)
        return False
    resolution = resolve_candidate(db, candidate)
    if not resolution.is_resolved:
        # A venue can be supplied by the instructor in the review screen or a
        # stay can be corrected later. Keep this durable candidate queued;
        # expiring it would discard a safely resolvable scheduling request.
        escalation.status = "needs_place_review"
        escalation.last_error = "Place context requires instructor review"
        return False
    professional = db.get(Professional, escalation.professional_id)
    actor = db.query(User).filter(User.professional_id == escalation.professional_id, User.role == "professional").first()
    if professional is None or not professional.agent_phone or not professional.assistant_phone or actor is None:
        escalation.status = "expired"
        return False
    key = f"passive-escalation:{candidate.id}"
    args = resolution.arguments
    if resolution.operation == "create":
        result = mutations.propose_create_appointment(
            db, escalation.professional_id, actor.id, uuid.uuid5(uuid.NAMESPACE_URL, key), "whatsapp",
            contact_id=args["contact_id"], place_id=args["place_id"], start_at=args["start_at"], end_at=args["end_at"], service=args["service"], idempotency_key=key, commit=False,
        )
    else:
        result = mutations.propose_reschedule_occurrence(
            db, escalation.professional_id, actor.id, uuid.uuid5(uuid.NAMESPACE_URL, key), "whatsapp",
            target_type=args["target_type"], target_id=args["target_id"], occurrence_date=args["occurrence_date"], new_start_at=args["new_start_at"], new_end_at=args["new_end_at"], new_place_id=args["new_place_id"] or None, idempotency_key=key, commit=False,
        )
    if "error" in result:
        escalation.status = "expired"
        escalation.last_error = str(result["error"])[:500]
        return False
    proposal = db.query(OperatorActionCandidate).filter_by(professional_id=escalation.professional_id, idempotency_key=key).one()
    candidate.operator_action_candidate_id = proposal.id
    proposal.expires_at = now + timedelta(minutes=TTL_MINUTES)
    try:
        send_text_message_or_raise(
            from_phone=professional.agent_phone,
            to_phone=professional.assistant_phone,
            body=f"{proposal.preview_text}\n\nResponda *sim* para confirmar ou *nao* para cancelar.",
        )
    except Exception as exc:  # delivery is retried from durable state
        escalation.attempt_count += 1
        escalation.last_error = str(exc)[:500]
        escalation.next_attempt_at = now + timedelta(seconds=RETRY_SECONDS)
        return False
    escalation.status = "sent"
    escalation.sent_at = now
    escalation.attempt_count += 1
    escalation.last_error = None
    return True


def process_due_escalations(db: Session) -> int:
    now = datetime.now(TIMEZONE)
    expired = db.query(PassiveEscalation).join(
        AppointmentCandidate,
        PassiveEscalation.appointment_candidate_id == AppointmentCandidate.id,
    ).join(
        OperatorActionCandidate,
        AppointmentCandidate.operator_action_candidate_id == OperatorActionCandidate.id,
    ).filter(
        PassiveEscalation.status == "sent",
        OperatorActionCandidate.status == "proposed",
        OperatorActionCandidate.expires_at <= now,
    ).all()
    for escalation in expired:
        proposal = escalation.appointment_candidate.operator_action_candidate
        proposal.status = "expired"
        escalation.status = "expired"
        record_event(
            db,
            professional_id=escalation.professional_id,
            event_type="agent.action.expired",
            occurred_at=now,
            actor_type="system",
            actor_id=None,
            source_channel="whatsapp",
            entity_type="operator_action_candidate",
            entity_id=proposal.id,
            correlation_id=proposal.correlation_id,
            operator_action_candidate_id=proposal.id,
            payload={"origin": "passive_observer"},
        )
    if expired:
        db.commit()
    rows = db.query(PassiveEscalation).filter(
        PassiveEscalation.status == "queued", PassiveEscalation.next_attempt_at <= now
    ).with_for_update(skip_locked=True).all()
    count = 0
    for escalation in rows:
        if deliver(escalation, db):
            count += 1
        db.commit()
    return count

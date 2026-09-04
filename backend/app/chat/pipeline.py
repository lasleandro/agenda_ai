"""
Appointment candidate pipeline (Phase 2 — brief Section 12.2).

Builds the normalized conversation window from persisted messages, runs it
through the Phase 0 extraction + temporal validation, and persists the
result as an AppointmentCandidate with its supporting evidence — including
`none` results, per the brief.
"""

import os
import uuid
import logging
from hashlib import sha256
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentCandidate,
    AppointmentEvidence,
    Contact,
    Conversation,
    Message,
    PendingProcessing,
    Professional,
    User,
)
from app.schemas.conversation import (
    ContactContext,
    ConversationWindow,
    Message as WindowMessage,
    ProfessionalContext,
    UpcomingAppointment,
)
from app.schemas.extraction import SchedulingEvent
from app.chat.extraction import extract_scheduling_events
from app.chat.temporal import validate_temporal
from app.services.candidate_execution import (
    CreateCandidateInput,
    confirm_create_candidate,
    confirm_reschedule_candidate,
)
from app.services.candidate_resolution import resolve_candidate
from app.services.passive_escalation import queue_if_eligible

# How many recent messages to include in the extraction window (brief 12.2:
# "the new message; recent messages from the same conversation").
WINDOW_MESSAGE_COUNT = 20

# Debounce window: wait this long after the last message before processing
# (brief 12.2: "20-60 seconds... configurable").
DEBOUNCE_SECONDS = int(os.getenv("PIPELINE_DEBOUNCE_SECONDS", "30"))

logger = logging.getLogger(__name__)


def schedule_processing(db: Session, conversation_id: uuid.UUID) -> None:
    """Insert or bump forward the debounce timer for a conversation.

    A new message always resets process_after, so a burst of messages is
    processed once as a window rather than once per message.
    """
    process_after = datetime.now(timezone.utc) + timedelta(seconds=DEBOUNCE_SECONDS)
    stmt = pg_insert(PendingProcessing).values(
        conversation_id=conversation_id, process_after=process_after
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[PendingProcessing.conversation_id],
        set_={"process_after": process_after},
    )
    db.execute(stmt)


def ensure_processing_scheduled(db: Session, conversation_id: uuid.UUID) -> None:
    """Guarantee a debounce row exists without touching an existing one.

    Recovery path: a webhook retry that finds the message already persisted
    still needs downstream extraction to be scheduled if that row was lost
    after a partial failure. Unlike ``schedule_processing`` this never moves
    ``process_after`` forward, so a duplicate delivery cannot delay a window
    that is already due.
    """
    process_after = datetime.now(timezone.utc) + timedelta(seconds=DEBOUNCE_SECONDS)
    stmt = pg_insert(PendingProcessing).values(
        conversation_id=conversation_id, process_after=process_after
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=[PendingProcessing.conversation_id]
    )
    db.execute(stmt)


def build_conversation_window(db: Session, conversation: Conversation) -> ConversationWindow:
    professional = db.query(Professional).filter(Professional.id == conversation.professional_id).first()
    contact = db.query(Contact).filter(Contact.id == conversation.contact_id).first()

    recent_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        # sent_at is provider-reported and only second-precision, so messages
        # in the same second tie — break ties on received_at (microsecond,
        # reflects true arrival order) so the window is never misordered.
        .order_by(Message.sent_at.desc(), Message.received_at.desc())
        .limit(WINDOW_MESSAGE_COUNT)
        .all()
    )
    recent_messages.reverse()  # chronological order for the LLM

    upcoming_appointments = (
        db.query(Appointment)
        .filter(
            Appointment.contact_id == conversation.contact_id,
            Appointment.status.in_(["tentative", "confirmed"]),
            Appointment.start_at >= datetime.now(timezone.utc),
        )
        .order_by(Appointment.start_at.asc())
        .all()
    )

    return ConversationWindow(
        professional=ProfessionalContext(
            timezone=professional.timezone,
            default_duration_minutes=professional.default_duration_minutes,
            service=professional.default_service,
        ),
        contact=ContactContext(display_name=contact.display_name),
        current_time=datetime.now(timezone.utc),
        upcoming_appointments=[
            UpcomingAppointment(
                id=str(appt.id), start_at=appt.start_at, end_at=appt.end_at, service=appt.service
            )
            for appt in upcoming_appointments
        ],
        messages=[
            WindowMessage(id=str(msg.id), direction=msg.direction, sent_at=msg.sent_at, text=msg.text or "")
            for msg in recent_messages
        ],
    )


def event_fingerprint(event: SchedulingEvent) -> str:
    """Create a stable identity for an operation across extraction windows.

    Confirmation state and evidence deliberately do not participate: a later
    instructor message can advance the same proposal to confirmed without
    creating a second candidate.
    """
    payload = {
        "operation": event.operation,
        "start_at": event.start_at.isoformat() if event.start_at else None,
        "end_at": event.end_at.isoformat() if event.end_at else None,
        "service": event.service,
        "existing_appointment_id": event.existing_appointment_id,
        "recurrence_rule": event.recurrence_rule,
    }
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _auto_execute_authoritative_candidate(
    db: Session, candidate: AppointmentCandidate
) -> bool:
    """Execute a fully resolved instructor-confirmed candidate exactly once.

    Failures intentionally leave the evidence candidate in ``detected`` for
    platform review. The nested transaction prevents a schedule conflict from
    losing the extraction itself.
    """
    if candidate.status != "detected" or candidate.confirmation_status not in {
        "instructor_confirmed",
        "mutually_confirmed",
    }:
        return False
    resolution = resolve_candidate(db, candidate)
    if resolution.operation not in {"create", "reschedule"} or not resolution.is_resolved:
        return False
    actor = (
        db.query(User)
        .filter(User.professional_id == candidate.professional_id, User.role == "professional")
        .order_by(User.created_at.asc())
        .first()
    )
    if actor is None:
        return False
    try:
        with db.begin_nested():
            if resolution.operation == "create":
                confirm_create_candidate(
                    db,
                    candidate,
                    actor_user_id=actor.id,
                    input=CreateCandidateInput(),
                    source_channel="passive_observer",
                    automatic=True,
                )
            else:
                confirm_reschedule_candidate(
                    db,
                    candidate,
                    actor_user_id=actor.id,
                    source_channel="passive_observer",
                    automatic=True,
                )
        return True
    except Exception:  # preserve a reviewable candidate when execution cannot proceed
        logger.exception("Automatic execution failed for passive candidate %s", candidate.id)
        return False


def process_conversation(db: Session, conversation: Conversation) -> list[AppointmentCandidate]:
    """Persist each distinct event extracted from a conversation window."""
    window = build_conversation_window(db, conversation)
    events = [validate_temporal(event, window) for event in extract_scheduling_events(window)]
    candidates = []

    for event in events:
        fingerprint = event_fingerprint(event)
        candidate = (
            db.query(AppointmentCandidate)
            .filter(
                AppointmentCandidate.conversation_id == conversation.id,
                AppointmentCandidate.event_fingerprint == fingerprint,
            )
            .first()
        )
        if candidate is None:
            candidate = AppointmentCandidate(
                professional_id=conversation.professional_id,
                conversation_id=conversation.id,
            contact_id=conversation.contact_id,
            action=event.operation,
            existing_appointment_id=(
                uuid.UUID(event.existing_appointment_id)
                if event.existing_appointment_id
                else None
            ),
                status="detected",
                event_fingerprint=fingerprint,
            )
            db.add(candidate)
            db.flush()

        candidate.action = event.operation
        candidate.operation = event.operation
        candidate.confirmation_status = event.confirmation_status
        candidate.existing_appointment_id = (
            uuid.UUID(event.existing_appointment_id)
            if event.existing_appointment_id
            else None
        )
        candidate.proposed_start_at = event.start_at
        candidate.proposed_end_at = event.end_at
        candidate.service = event.service
        candidate.confidence = event.confidence
        candidate.ambiguities = [a.model_dump() for a in event.ambiguities]
        candidate.extraction_version = "v0.2"

        evidence_message_ids = set(event.evidence_message_ids)
        evidence_rows = [
            {
                "appointment_candidate_id": candidate.id,
                "message_id": msg.id,
                "evidence_role": "supporting",
                "sequence": sequence,
            }
            for sequence, msg in enumerate(window.messages)
            if msg.id in evidence_message_ids
        ]
        if evidence_rows:
            # ON CONFLICT DO NOTHING instead of a pre-check SELECT: a
            # reprocessed conversation (debounce reset by a new inbound
            # message) can re-extract the same event for the same
            # candidate, and a plain SELECT-then-INSERT is a TOCTOU race
            # against a concurrent run — it crashed the worker in
            # production with a duplicate-key IntegrityError.
            stmt = pg_insert(AppointmentEvidence).values(evidence_rows)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=[
                    AppointmentEvidence.appointment_candidate_id,
                    AppointmentEvidence.message_id,
                ]
            )
            db.execute(stmt)
        _auto_execute_authoritative_candidate(db, candidate)
        queue_if_eligible(db, candidate)
        candidates.append(candidate)

    db.commit()
    for candidate in candidates:
        db.refresh(candidate)
    return candidates

"""
Appointment candidate pipeline (Phase 2 — brief Section 12.2).

Builds the normalized conversation window from persisted messages, runs it
through the Phase 0 extraction + temporal validation, and persists the
result as an AppointmentCandidate with its supporting evidence — including
`none` results, per the brief.
"""

import os
import uuid
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

# How many recent messages to include in the extraction window (brief 12.2:
# "the new message; recent messages from the same conversation").
WINDOW_MESSAGE_COUNT = 20

# Debounce window: wait this long after the last message before processing
# (brief 12.2: "20-60 seconds... configurable").
DEBOUNCE_SECONDS = int(os.getenv("PIPELINE_DEBOUNCE_SECONDS", "30"))


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
    """Create a stable identity for an extracted event across repeated runs."""
    payload = {
        "action": event.action,
        "start_at": event.start_at.isoformat() if event.start_at else None,
        "end_at": event.end_at.isoformat() if event.end_at else None,
        "service": event.service,
        "existing_appointment_id": event.existing_appointment_id,
        "recurrence_rule": event.recurrence_rule,
        "evidence_message_ids": sorted(event.evidence_message_ids),
    }
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


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
        if candidate is not None:
            candidates.append(candidate)
            continue

        candidate = AppointmentCandidate(
            professional_id=conversation.professional_id,
            conversation_id=conversation.id,
            contact_id=conversation.contact_id,
            action=event.action,
            proposed_start_at=event.start_at,
            proposed_end_at=event.end_at,
            service=event.service,
            confidence=event.confidence,
            status="detected",
            ambiguities=[a.model_dump() for a in event.ambiguities],
            event_fingerprint=fingerprint,
            extraction_version="v0.1",
        )
        db.add(candidate)
        db.flush()

        evidence_message_ids = set(event.evidence_message_ids)
        for sequence, msg in enumerate(window.messages):
            if msg.id in evidence_message_ids:
                db.add(
                    AppointmentEvidence(
                        appointment_candidate_id=candidate.id,
                        message_id=msg.id,
                        evidence_role="supporting",
                        sequence=sequence,
                    )
                )
        candidates.append(candidate)

    db.commit()
    for candidate in candidates:
        db.refresh(candidate)
    return candidates

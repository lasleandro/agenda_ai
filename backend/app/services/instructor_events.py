"""Instructor events service (instructor events roadmap v0.1, Phase 1).

Shared creation/listing/cancellation logic used by both the dashboard REST
API (app/api/instructor_events.py) and the instructor-agent tool
(app/agent/mutations.py's propose_create_event), so validation can't
diverge between the two entry points — same pattern as
app/services/waitlist.py.
"""

import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import InstructorEvent, Place
from app.models.instructor_event import EVENT_TYPES
from app.services.appointments import (
    has_appointment_overlap,
    has_event_overlap,
    has_scheduled_class_overlap,
)


class InstructorEventValidationError(Exception):
    pass


def assert_no_event_conflict(
    db: Session, professional_id: uuid.UUID, *, start_at: datetime, end_at: datetime
) -> None:
    """Events and classes share one busy-time set — an event can't be
    created on top of an existing class, same as the reverse
    (app.services.appointments.assert_no_conflict). Deliberately does NOT
    check assert_within_work_journey — a Saturday tournament is by
    definition outside normal teaching hours."""
    if has_appointment_overlap(
        db, professional_id, start_at=start_at, end_at=end_at, is_recurring=False
    ):
        raise HTTPException(status_code=409, detail="This time overlaps an appointment")
    if has_scheduled_class_overlap(
        db, professional_id, start_at=start_at, end_at=end_at, is_recurring=False
    ):
        raise HTTPException(status_code=409, detail="This time overlaps a scheduled class")
    if has_event_overlap(db, professional_id, start_at=start_at, end_at=end_at):
        raise HTTPException(status_code=409, detail="This time overlaps another instructor event")


def create_event(
    db: Session,
    professional_id: uuid.UUID,
    *,
    event_type: str,
    start_at: datetime,
    end_at: datetime,
    place_id: uuid.UUID | None = None,
    title: str | None = None,
    income_cents: int | None = None,
    note: str | None = None,
) -> InstructorEvent:
    if event_type not in EVENT_TYPES:
        raise InstructorEventValidationError(
            f"event_type must be one of {EVENT_TYPES}"
        )
    if end_at <= start_at:
        raise InstructorEventValidationError("end_at must be after start_at")

    if place_id is not None:
        place = (
            db.query(Place)
            .filter(Place.id == place_id, Place.professional_id == professional_id)
            .first()
        )
        if place is None:
            raise InstructorEventValidationError("Place not found")

    assert_no_event_conflict(db, professional_id, start_at=start_at, end_at=end_at)

    event = InstructorEvent(
        professional_id=professional_id,
        place_id=place_id,
        event_type=event_type,
        title=title,
        start_at=start_at,
        end_at=end_at,
        income_cents=income_cents,
        note=note,
    )
    db.add(event)
    db.commit()
    return event


def list_events(
    db: Session,
    professional_id: uuid.UUID,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    status: str | None = None,
) -> list[InstructorEvent]:
    query = db.query(InstructorEvent).filter(
        InstructorEvent.professional_id == professional_id
    )
    if date_from is not None:
        query = query.filter(InstructorEvent.end_at >= date_from)
    if date_to is not None:
        query = query.filter(InstructorEvent.start_at <= date_to)
    if status is not None:
        query = query.filter(InstructorEvent.status == status)
    return query.order_by(InstructorEvent.start_at).all()


def get_event(
    db: Session, professional_id: uuid.UUID, event_id: uuid.UUID
) -> InstructorEvent | None:
    return (
        db.query(InstructorEvent)
        .filter(
            InstructorEvent.id == event_id, InstructorEvent.professional_id == professional_id
        )
        .first()
    )


def cancel_event(
    db: Session, professional_id: uuid.UUID, event_id: uuid.UUID
) -> InstructorEvent:
    event = get_event(db, professional_id, event_id)
    if event is None:
        raise InstructorEventValidationError("Event not found")
    if event.status != "confirmed":
        raise InstructorEventValidationError(f"Event is not cancellable (status={event.status})")
    event.status = "cancelled"
    db.commit()
    return event

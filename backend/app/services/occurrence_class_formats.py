"""Persist validated format/capacity overrides for a single occurrence."""

import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import ScheduleOccurrenceClassOverride


def validate_format(
    *,
    class_type: str,
    max_participants: int,
    participant_count: int,
) -> None:
    """Validate one effective occurrence format against its roster."""
    if class_type not in {"individual", "group"}:
        raise HTTPException(status_code=422, detail="Class type must be individual or group")
    if not 1 <= max_participants <= 4:
        raise HTTPException(status_code=422, detail="Participant capacity must be between 1 and 4")
    if class_type == "individual" and max_participants != 1:
        raise HTTPException(
            status_code=422,
            detail="An individual class has capacity for one participant",
        )
    if class_type == "individual" and participant_count != 1:
        raise HTTPException(
            status_code=409,
            detail="Remove additional participants before converting to individual",
        )
    if participant_count > max_participants:
        raise HTTPException(
            status_code=409,
            detail="Configured capacity cannot be below the current participants",
        )


def set_format(
    db: Session,
    professional_id: uuid.UUID,
    *,
    source_type: str,
    source_id: uuid.UUID,
    occurrence_date: date,
    class_type: str,
    max_participants: int,
    participant_count: int,
    actor_user_id: uuid.UUID | None,
    source: str,
) -> ScheduleOccurrenceClassOverride:
    if source_type not in {"appointment", "recurring_slot"}:
        raise HTTPException(status_code=422, detail="Unsupported schedule source")
    validate_format(
        class_type=class_type,
        max_participants=max_participants,
        participant_count=participant_count,
    )

    query = db.query(ScheduleOccurrenceClassOverride).filter(
        ScheduleOccurrenceClassOverride.professional_id == professional_id,
        ScheduleOccurrenceClassOverride.occurrence_date == occurrence_date,
    )
    query = query.filter(
        ScheduleOccurrenceClassOverride.appointment_id == source_id
        if source_type == "appointment"
        else ScheduleOccurrenceClassOverride.recurring_slot_id == source_id
    )
    override = query.first()
    if override is None:
        override = ScheduleOccurrenceClassOverride(
            professional_id=professional_id,
            appointment_id=source_id if source_type == "appointment" else None,
            recurring_slot_id=source_id if source_type == "recurring_slot" else None,
            occurrence_date=occurrence_date,
        )
        db.add(override)
    override.class_type = class_type
    override.max_participants = max_participants
    override.actor_user_id = actor_user_id
    override.source = source
    db.flush()
    return override

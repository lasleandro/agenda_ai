"""Cancel/reschedule a single dated occurrence via
`ScheduleOccurrenceOverride` (operational ontology roadmap v0.2, Phase 5).

Scope is limited to a single occurrence in this pass — "future occurrences"
and "whole series" scopes are deferred (see the roadmap plan; they need
series-deactivation semantics not yet specified). Callers own the
transaction (commit after calling).
"""

import uuid
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import ScheduleOccurrenceOverride
from app.services import scheduling
from app.services.place_stays import resolve_place_stay


def _get_active_override(
    db: Session,
    professional_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    occurrence_date: date,
) -> ScheduleOccurrenceOverride | None:
    filters = [
        ScheduleOccurrenceOverride.professional_id == professional_id,
        ScheduleOccurrenceOverride.occurrence_date == occurrence_date,
    ]
    if target_type == "appointment":
        filters.append(ScheduleOccurrenceOverride.appointment_id == target_id)
    else:
        filters.append(ScheduleOccurrenceOverride.recurring_slot_id == target_id)
    return db.query(ScheduleOccurrenceOverride).filter(*filters).first()


def get_target_occurrence(
    db: Session,
    professional_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    occurrence_date: date,
) -> scheduling.ScheduleOccurrence:
    """Look up the occurrence by its *original* date — an occurrence that's
    already cancelled or moved won't be found here, which is a deliberate
    (if coarse) guard against double-cancelling or double-rescheduling."""
    occurrence = scheduling.get_schedule_occurrence(
        db, professional_id, target_type, target_id, occurrence_date
    )
    if occurrence is None:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    return occurrence


def cancel_occurrence(
    db: Session,
    professional_id: uuid.UUID,
    *,
    target_type: str,
    target_id: uuid.UUID,
    occurrence_date: date,
    actor_user_id: uuid.UUID,
    reason_code: str | None = None,
    note: str | None = None,
) -> ScheduleOccurrenceOverride:
    get_target_occurrence(db, professional_id, target_type, target_id, occurrence_date)
    if _get_active_override(db, professional_id, target_type, target_id, occurrence_date):
        raise HTTPException(
            status_code=409, detail="This occurrence already has an active exception"
        )

    override = ScheduleOccurrenceOverride(
        professional_id=professional_id,
        appointment_id=target_id if target_type == "appointment" else None,
        recurring_slot_id=target_id if target_type == "recurring_slot" else None,
        occurrence_date=occurrence_date,
        override_type="cancelled",
        reason_code=reason_code,
        note=note,
        actor_user_id=actor_user_id,
        source="web",
    )
    db.add(override)
    db.flush()
    return override


def assert_new_time_available(
    db: Session,
    professional_id: uuid.UUID,
    *,
    target_type: str,
    target_id: uuid.UUID,
    new_start_at: datetime,
    new_end_at: datetime,
) -> None:
    """Shared by `propose_reschedule_occurrence` (upfront, so the preview
    never promises a move that's already predictably impossible) and
    `reschedule_occurrence` (confirm time, re-validated since state may
    have changed since the proposal). A professional can't be in two
    places at once — checks across the whole projection for the new date,
    not just the same place (matches `schedule_conflicts`'s slot-overlap
    philosophy)."""
    new_date = new_start_at.astimezone(scheduling.TIMEZONE).date()
    for occurrence in scheduling.list_schedule_occurrences(db, professional_id, new_date, new_date):
        if occurrence.source_type == target_type and occurrence.source_id == target_id:
            continue
        if occurrence.starts_at < new_end_at and occurrence.ends_at > new_start_at:
            raise HTTPException(
                status_code=409, detail="The new time overlaps another occurrence"
            )


def reschedule_occurrence(
    db: Session,
    professional_id: uuid.UUID,
    *,
    target_type: str,
    target_id: uuid.UUID,
    occurrence_date: date,
    new_start_at: datetime,
    new_end_at: datetime,
    new_place_id: uuid.UUID | None,
    actor_user_id: uuid.UUID,
) -> ScheduleOccurrenceOverride:
    original = get_target_occurrence(db, professional_id, target_type, target_id, occurrence_date)
    if _get_active_override(db, professional_id, target_type, target_id, occurrence_date):
        raise HTTPException(
            status_code=409, detail="This occurrence already has an active exception"
        )
    if new_end_at <= new_start_at:
        raise HTTPException(status_code=422, detail="End time must be after start time")

    resolution = resolve_place_stay(
        db,
        professional_id,
        start_at=new_start_at,
        end_at=new_end_at,
        requested_place_id=new_place_id,
    )
    if resolution.outcome == "invalid_place":
        raise HTTPException(status_code=404, detail="Place not found")
    if resolution.place_id is None:
        raise HTTPException(
            status_code=409,
            detail="Select a place: this time has no unique covering place stay",
        )
    effective_place_id = resolution.place_id

    assert_new_time_available(
        db,
        professional_id,
        target_type=target_type,
        target_id=target_id,
        new_start_at=new_start_at,
        new_end_at=new_end_at,
    )

    override = ScheduleOccurrenceOverride(
        professional_id=professional_id,
        appointment_id=target_id if target_type == "appointment" else None,
        recurring_slot_id=target_id if target_type == "recurring_slot" else None,
        occurrence_date=occurrence_date,
        override_type="rescheduled",
        replacement_start_at=new_start_at,
        replacement_end_at=new_end_at,
        replacement_place_id=effective_place_id,
        actor_user_id=actor_user_id,
        source="web",
    )
    db.add(override)
    db.flush()
    return override

"""Recurring-slot conflict checks (operational ontology roadmap v0.2,
Phase 4) — moved out of `app.api.recurring_slots` so the API and the
instructor agent's mutation tools share the same checks instead of risking
divergence."""

import uuid

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import RecurringSlot, RecurringSlotParticipant


def schedule_overlap_filter(day_of_week: int, recurrence_type: str, scheduled_date):
    schedule_filter = RecurringSlot.recurrence_type == "weekly"
    if recurrence_type == "weekly":
        schedule_filter = or_(
            RecurringSlot.recurrence_type == "weekly",
            and_(
                RecurringSlot.recurrence_type == "once",
                RecurringSlot.scheduled_date.is_not(None),
                RecurringSlot.day_of_week == day_of_week,
            ),
        )
    elif scheduled_date is not None:
        schedule_filter = or_(
            RecurringSlot.recurrence_type == "weekly",
            and_(
                RecurringSlot.recurrence_type == "once",
                RecurringSlot.scheduled_date == scheduled_date,
            ),
        )
    return schedule_filter


def assert_no_slot_overlap(
    db: Session,
    professional_id: uuid.UUID,
    day_of_week: int,
    start_time,
    end_time,
    recurrence_type: str = "weekly",
    scheduled_date=None,
    exclude_slot_id: uuid.UUID | None = None,
) -> None:
    """A professional can't be in two places at the same time — check across
    all of their places, not just within one."""
    schedule_filter = schedule_overlap_filter(day_of_week, recurrence_type, scheduled_date)

    query = db.query(RecurringSlot).filter(
        RecurringSlot.professional_id == professional_id,
        RecurringSlot.slot_kind == "availability",
        RecurringSlot.day_of_week == day_of_week,
        RecurringSlot.status == "active",
        RecurringSlot.start_time < end_time,
        RecurringSlot.end_time > start_time,
        schedule_filter,
    )
    if exclude_slot_id is not None:
        query = query.filter(RecurringSlot.id != exclude_slot_id)
    if query.first() is not None:
        raise HTTPException(
            status_code=409, detail="This time overlaps another active recurring slot"
        )


def assert_no_scheduled_class_overlap(
    db: Session,
    professional_id: uuid.UUID,
    day_of_week: int,
    start_time,
    end_time,
    recurrence_type: str,
    scheduled_date,
    exclude_slot_id: uuid.UUID | None = None,
) -> None:
    query = (
        db.query(RecurringSlot)
        .join(
            RecurringSlotParticipant,
            RecurringSlotParticipant.recurring_slot_id == RecurringSlot.id,
        )
        .filter(
            RecurringSlot.professional_id == professional_id,
            RecurringSlot.slot_kind == "class",
            RecurringSlot.day_of_week == day_of_week,
            RecurringSlot.status == "active",
            RecurringSlot.start_time < end_time,
            RecurringSlot.end_time > start_time,
            schedule_overlap_filter(day_of_week, recurrence_type, scheduled_date),
        )
    )
    if exclude_slot_id is not None:
        query = query.filter(RecurringSlot.id != exclude_slot_id)
    if query.first() is not None:
        raise HTTPException(
            status_code=409, detail="This time overlaps another scheduled class"
        )

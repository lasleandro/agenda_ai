"""Recurring-slot participant add/remove (operational ontology roadmap
v0.2, Phase 4) — moved out of `app.api.recurring_slots` so the API and the
instructor agent's mutation tools share the same validation instead of
risking divergence. Callers own the transaction (commit after calling)."""

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Contact, RecurringSlot, RecurringSlotParticipant
from app.services.schedule_conflicts import assert_no_scheduled_class_overlap


def count_participants(db: Session, slot_id: uuid.UUID) -> int:
    return (
        db.query(RecurringSlotParticipant)
        .filter(RecurringSlotParticipant.recurring_slot_id == slot_id)
        .count()
    )


def add_participant(
    db: Session,
    professional_id: uuid.UUID,
    slot: RecurringSlot,
    contact: Contact,
) -> RecurringSlotParticipant:
    existing = (
        db.query(RecurringSlotParticipant)
        .filter(
            RecurringSlotParticipant.recurring_slot_id == slot.id,
            RecurringSlotParticipant.contact_id == contact.id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Contact already assigned to this slot")

    if count_participants(db, slot.id) >= slot.max_participants:
        raise HTTPException(status_code=409, detail="This slot is at full capacity")

    if slot.slot_kind == "availability":
        assert_no_scheduled_class_overlap(
            db,
            professional_id,
            slot.day_of_week,
            slot.start_time,
            slot.end_time,
            slot.recurrence_type,
            slot.scheduled_date,
            exclude_slot_id=slot.id,
        )
        slot.slot_kind = "class"

    participant = RecurringSlotParticipant(recurring_slot_id=slot.id, contact_id=contact.id)
    db.add(participant)
    db.flush()
    return participant


def remove_participant(db: Session, slot_id: uuid.UUID, contact_id: uuid.UUID) -> None:
    participant = (
        db.query(RecurringSlotParticipant)
        .filter(
            RecurringSlotParticipant.recurring_slot_id == slot_id,
            RecurringSlotParticipant.contact_id == contact_id,
        )
        .first()
    )
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")
    db.delete(participant)
    db.flush()

"""Dated guest enrollment for a recurring group occurrence."""

import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    Contact,
    RecurringSlot,
    RecurringSlotOccurrenceParticipant,
    RecurringSlotParticipant,
)


def count_participants(
    db: Session,
    slot_id: uuid.UUID,
    occurrence_date: date,
) -> int:
    permanent_count = (
        db.query(RecurringSlotParticipant)
        .filter(RecurringSlotParticipant.recurring_slot_id == slot_id)
        .count()
    )
    guest_count = (
        db.query(RecurringSlotOccurrenceParticipant)
        .filter(
            RecurringSlotOccurrenceParticipant.recurring_slot_id == slot_id,
            RecurringSlotOccurrenceParticipant.occurrence_date == occurrence_date,
        )
        .count()
    )
    return permanent_count + guest_count


def add_participant(
    db: Session,
    professional_id: uuid.UUID,
    slot: RecurringSlot,
    contact: Contact,
    occurrence_date: date,
) -> RecurringSlotOccurrenceParticipant:
    locked_slot = (
        db.query(RecurringSlot)
        .filter(
            RecurringSlot.id == slot.id,
            RecurringSlot.professional_id == professional_id,
        )
        .with_for_update()
        .first()
    )
    if locked_slot is None:
        raise HTTPException(status_code=404, detail="Recurring slot not found")
    slot = locked_slot
    if slot.slot_kind != "class" or slot.class_type != "group":
        raise HTTPException(
            status_code=409,
            detail="Dated participants can only be assigned to a recurring group",
        )
    is_permanent = (
        db.query(RecurringSlotParticipant)
        .filter(
            RecurringSlotParticipant.recurring_slot_id == slot.id,
            RecurringSlotParticipant.contact_id == contact.id,
        )
        .first()
        is not None
    )
    if is_permanent:
        raise HTTPException(status_code=409, detail="Contact is already a permanent participant")
    existing = (
        db.query(RecurringSlotOccurrenceParticipant)
        .filter(
            RecurringSlotOccurrenceParticipant.recurring_slot_id == slot.id,
            RecurringSlotOccurrenceParticipant.contact_id == contact.id,
            RecurringSlotOccurrenceParticipant.occurrence_date == occurrence_date,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Contact is already in this occurrence")
    if count_participants(db, slot.id, occurrence_date) >= slot.max_participants:
        raise HTTPException(status_code=409, detail="This occurrence is at full capacity")

    participant = RecurringSlotOccurrenceParticipant(
        professional_id=professional_id,
        recurring_slot_id=slot.id,
        contact_id=contact.id,
        occurrence_date=occurrence_date,
    )
    db.add(participant)
    db.flush()
    return participant


def remove_participant(
    db: Session,
    slot_id: uuid.UUID,
    contact_id: uuid.UUID,
    occurrence_date: date,
) -> None:
    participant = (
        db.query(RecurringSlotOccurrenceParticipant)
        .filter(
            RecurringSlotOccurrenceParticipant.recurring_slot_id == slot_id,
            RecurringSlotOccurrenceParticipant.contact_id == contact_id,
            RecurringSlotOccurrenceParticipant.occurrence_date == occurrence_date,
        )
        .first()
    )
    if participant is None:
        raise HTTPException(status_code=404, detail="Dated participant not found")
    db.delete(participant)
    db.flush()

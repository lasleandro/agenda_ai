"""Manage additional Appointment participants.

Adding a participant may explicitly open an individual appointment to a group.
Removing one only changes the roster: group format remains intentional until a
separate format-transition action changes it. Callers own the transaction.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentParticipant, Contact
from app.services.appointments import DEFAULT_GROUP_MAX_PARTICIPANTS


def count_participants(db: Session, appointment_id: uuid.UUID) -> int:
    extra = (
        db.query(AppointmentParticipant)
        .filter(AppointmentParticipant.appointment_id == appointment_id)
        .count()
    )
    return 1 + extra


def add_participant(
    db: Session, professional_id: uuid.UUID, appointment: Appointment, contact: Contact
) -> bool:
    """Add a customer and report whether the class format changed."""
    if contact.id == appointment.contact_id:
        raise HTTPException(status_code=409, detail="Contact is already in this appointment")
    existing = (
        db.query(AppointmentParticipant)
        .filter(
            AppointmentParticipant.appointment_id == appointment.id,
            AppointmentParticipant.contact_id == contact.id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Contact is already in this appointment")
    capacity = (
        appointment.max_participants
        if appointment.class_type == "group"
        else DEFAULT_GROUP_MAX_PARTICIPANTS
    )
    if count_participants(db, appointment.id) >= capacity:
        raise HTTPException(status_code=409, detail="This appointment is at full capacity")

    db.add(AppointmentParticipant(appointment_id=appointment.id, contact_id=contact.id))
    format_changed = appointment.class_type != "group"
    appointment.class_type = "group"
    appointment.max_participants = capacity
    db.flush()
    return format_changed


def remove_participant(db: Session, appointment_id: uuid.UUID, contact_id: uuid.UUID) -> bool:
    """Remove a non-primary customer without changing the class format."""
    row = (
        db.query(AppointmentParticipant)
        .filter(
            AppointmentParticipant.appointment_id == appointment_id,
            AppointmentParticipant.contact_id == contact_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=404, detail="Contact is not a participant of this appointment"
        )
    db.delete(row)
    db.flush()
    return False

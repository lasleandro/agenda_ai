"""Add/remove participants on a one-off Appointment, turning it between
"individual" and "group" class_type — mirrors app/services/participants.py
(RecurringSlot's version) but for Appointment.contact_id's "primary" plus
AppointmentParticipant extras. Callers own the transaction (commit after
calling)."""

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentParticipant, Contact

# No per-appointment configurability exists yet (unlike RecurringSlot's
# explicit max_participants) — a flat cap keeps ad-hoc group conversion
# from growing unbounded until real usage demands a configurable one.
MAX_PARTICIPANTS = 4


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
    if count_participants(db, appointment.id) >= MAX_PARTICIPANTS:
        raise HTTPException(status_code=409, detail="This appointment is at full capacity")

    db.add(AppointmentParticipant(appointment_id=appointment.id, contact_id=contact.id))
    format_changed = appointment.class_type != "group"
    appointment.class_type = "group"
    db.flush()
    return format_changed


def remove_participant(db: Session, appointment_id: uuid.UUID, contact_id: uuid.UUID) -> bool:
    """Remove a non-primary customer and report a format change."""
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

    format_changed = False
    if count_participants(db, appointment_id) <= 1:
        appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if appointment is not None and appointment.class_type != "individual":
            appointment.class_type = "individual"
            format_changed = True
            db.flush()
    return format_changed

"""
Contacts API ("Clientes") — customer ontology roadmap Phase 3/4.

GET   /api/contacts       — list the tenant's contacts.
GET   /api/contacts/{id}  — contact detail, including fixed recurring slots.
PATCH /api/contacts/{id}  — update level, address, home place.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as sqla_func
from sqlalchemy.orm import Session

from app.api.dependencies import require_professional_id
from app.database import SessionLocal
from app.models import Contact, MakeupClassCredit, Place, RecurringSlot, RecurringSlotParticipant
from app.models.appointment import Appointment
from app.schemas.ontology import ContactDetail, ContactListResponse, ContactSummary, ContactUpdate
from app.schemas.ontology import CourtesyAppointmentSummary, RecurringSlotDetail
from app.services.contacts import apply_contact_updates
from app.services.makeup_credits import get_available_credits_count
from app.services.participants import count_participants as _participant_count

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_contact_or_404(db: Session, contact_id: uuid.UUID, professional_id: uuid.UUID) -> Contact:
    contact = (
        db.query(Contact)
        .filter(Contact.id == contact_id, Contact.professional_id == professional_id)
        .first()
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


def _to_summary(contact: Contact, home_place_name: str | None, credits: int = 0) -> ContactSummary:
    return ContactSummary(
        id=contact.id,
        display_name=contact.display_name,
        phone=contact.phone,
        level=contact.level,
        home_place_id=contact.home_place_id,
        home_place_name=home_place_name,
        makeup_credits_available=credits,
    )


@router.get("", response_model=ContactListResponse)
def list_contacts(
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    rows = (
        db.query(Contact, Place.name)
        .outerjoin(Place, Contact.home_place_id == Place.id)
        .filter(Contact.professional_id == professional_id)
        .order_by(Contact.display_name)
        .all()
    )
    contact_ids = [contact.id for contact, _ in rows]
    credit_counts: dict[uuid.UUID, int] = {}
    if contact_ids:
        credit_rows = (
            db.query(
                MakeupClassCredit.contact_id,
                sqla_func.count(MakeupClassCredit.id),
            )
            .filter(
                MakeupClassCredit.professional_id == professional_id,
                MakeupClassCredit.contact_id.in_(contact_ids),
                MakeupClassCredit.status == "available",
            )
            .group_by(MakeupClassCredit.contact_id)
            .all()
        )
        credit_counts = {contact_id: count for contact_id, count in credit_rows}
    return ContactListResponse(
        contacts=[
            _to_summary(contact, name, credit_counts.get(contact.id, 0))
            for contact, name in rows
        ]
    )


@router.get("/{contact_id}", response_model=ContactDetail)
def get_contact(
    contact_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    contact = _get_contact_or_404(db, contact_id, professional_id)
    home_place_name = None
    if contact.home_place_id is not None:
        home_place_name = db.query(Place.name).filter(Place.id == contact.home_place_id).scalar()

    slot_rows = (
        db.query(RecurringSlot, Place.name)
        .join(RecurringSlotParticipant, RecurringSlotParticipant.recurring_slot_id == RecurringSlot.id)
        .join(Place, RecurringSlot.place_id == Place.id)
        .filter(RecurringSlotParticipant.contact_id == contact_id)
        .all()
    )
    fixed_slots = [
        RecurringSlotDetail(
            id=slot.id,
            place_id=slot.place_id,
            place_name=place_name,
            day_of_week=slot.day_of_week,
            start_time=slot.start_time,
            end_time=slot.end_time,
            label=slot.label,
            group_name=slot.group_name,
            class_type=slot.class_type,
            slot_kind=slot.slot_kind,
            level=slot.level,
            max_participants=slot.max_participants,
            recurrence_type=slot.recurrence_type,
            scheduled_date=slot.scheduled_date,
            valid_from=slot.valid_from,
            valid_until=slot.valid_until,
            status=slot.status,
            participant_count=_participant_count(db, slot.id),
        )
        for slot, place_name in slot_rows
    ]

    courtesy_rows = (
        db.query(Appointment, Place.name)
        .outerjoin(Place, Appointment.place_id == Place.id)
        .filter(
            Appointment.professional_id == professional_id,
            Appointment.contact_id == contact_id,
            Appointment.billing_type == "courtesy",
        )
        .order_by(Appointment.start_at.desc())
        .all()
    )
    courtesy_appointments = [
        CourtesyAppointmentSummary(
            id=appt.id,
            start_at=appt.start_at,
            end_at=appt.end_at,
            place_name=place_name,
            service=appt.service,
            status=appt.status,
        )
        for appt, place_name in courtesy_rows
    ]

    return ContactDetail(
        **_to_summary(
            contact,
            home_place_name,
            get_available_credits_count(db, professional_id, contact_id),
        ).model_dump(),
        address_line=contact.address_line,
        city=contact.city,
        state=contact.state,
        postal_code=contact.postal_code,
        country=contact.country,
        latitude=contact.latitude,
        longitude=contact.longitude,
        created_at=contact.created_at,
        fixed_slots=fixed_slots,
        courtesy_appointments=courtesy_appointments,
    )


@router.patch("/{contact_id}", response_model=ContactDetail)
def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    contact = _get_contact_or_404(db, contact_id, professional_id)
    updates = body.model_dump(exclude_unset=True)
    apply_contact_updates(db, professional_id, contact, updates)
    db.commit()

    return get_contact(contact_id, db, professional_id)

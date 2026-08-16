"""
RecurringSlots API ("Horário Fixo") — customer ontology roadmap Phase 2/4.

GET    /api/recurring-slots                          — list (optional ?place_id=).
POST   /api/recurring-slots                           — create (rejects overlap).
POST   /api/recurring-slots/bulk                      — create the same slot on multiple days.
PATCH  /api/recurring-slots/{id}                       — update (rejects overlap).
DELETE /api/recurring-slots/{id}                       — delete.
POST   /api/recurring-slots/{id}/participants          — assign a contact (capacity-checked).
DELETE /api/recurring-slots/{id}/participants/{contact_id} — remove a contact.

Availability rows represent place stays and cannot receive participants.
Recurring classes are created explicitly and remain class records when their
roster becomes empty, so a class can overlap its containing place stay.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import require_professional_id
from app.database import SessionLocal
from app.models import Contact, Place, RecurringSlot, RecurringSlotParticipant
from app.services.participants import add_participant as _add_participant_service
from app.services.participants import count_participants as _participant_count
from app.services.participants import remove_participant as _remove_participant_service
from app.services.schedule_conflicts import assert_no_scheduled_class_overlap as _assert_no_scheduled_class_overlap
from app.services.schedule_conflicts import assert_no_slot_overlap as _assert_no_overlap
from app.services.passive_escalation import reactivate_place_review_escalations
from app.schemas.ontology import (
    RecurringSlotBulkCreate,
    RecurringSlotCreate,
    RecurringSlotDetail,
    RecurringGroupDetail,
    RecurringGroupCreate,
    RecurringSlotListResponse,
    RecurringSlotParticipantCreate,
    RecurringSlotParticipantDetail,
    RecurringSlotUpdate,
    SlotKind,
    validate_recurring_slot_definition,
)

router = APIRouter(prefix="/api/recurring-slots", tags=["recurring-slots"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_slot_or_404(db: Session, slot_id: uuid.UUID, professional_id: uuid.UUID) -> RecurringSlot:
    slot = (
        db.query(RecurringSlot)
        .filter(RecurringSlot.id == slot_id, RecurringSlot.professional_id == professional_id)
        .first()
    )
    if slot is None:
        raise HTTPException(status_code=404, detail="Recurring slot not found")
    return slot


def _to_detail(db: Session, slot: RecurringSlot, place_name: str) -> RecurringSlotDetail:
    return RecurringSlotDetail(
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


@router.get("", response_model=RecurringSlotListResponse)
def list_recurring_slots(
    place_id: uuid.UUID | None = None,
    slot_kind: SlotKind | None = None,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    query = (
        db.query(RecurringSlot, Place.name)
        .join(Place, RecurringSlot.place_id == Place.id)
        .filter(RecurringSlot.professional_id == professional_id)
    )
    if place_id is not None:
        query = query.filter(RecurringSlot.place_id == place_id)
    if slot_kind is not None:
        query = query.filter(RecurringSlot.slot_kind == slot_kind)

    rows = query.order_by(RecurringSlot.day_of_week, RecurringSlot.start_time).all()
    return RecurringSlotListResponse(slots=[_to_detail(db, slot, name) for slot, name in rows])


@router.get("/{slot_id}", response_model=RecurringGroupDetail)
def get_recurring_group(
    slot_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    slot = _get_slot_or_404(db, slot_id, professional_id)
    if slot.slot_kind != "class":
        raise HTTPException(status_code=404, detail="Recurring class not found")
    place_name = db.query(Place.name).filter(Place.id == slot.place_id).scalar()
    participants = (
        db.query(RecurringSlotParticipant, Contact)
        .join(Contact, RecurringSlotParticipant.contact_id == Contact.id)
        .filter(
            RecurringSlotParticipant.recurring_slot_id == slot.id,
            Contact.professional_id == professional_id,
        )
        .order_by(Contact.display_name)
        .all()
    )
    return RecurringGroupDetail(
        **_to_detail(db, slot, place_name).model_dump(),
        participants=[
            RecurringSlotParticipantDetail(
                id=participant.id,
                contact_id=contact.id,
                contact_name=contact.display_name,
            )
            for participant, contact in participants
        ],
    )


@router.post("", response_model=RecurringSlotDetail, status_code=201)
def create_recurring_slot(
    body: RecurringSlotCreate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    place = (
        db.query(Place)
        .filter(Place.id == body.place_id, Place.professional_id == professional_id)
        .first()
    )
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")

    overlap_check = (
        _assert_no_scheduled_class_overlap
        if body.slot_kind == "class"
        else _assert_no_overlap
    )
    overlap_check(
        db,
        professional_id,
        body.day_of_week,
        body.start_time,
        body.end_time,
        body.recurrence_type,
        body.scheduled_date,
    )

    slot = RecurringSlot(professional_id=professional_id, **body.model_dump())
    db.add(slot)
    if slot.slot_kind == "availability":
        reactivate_place_review_escalations(db, professional_id)
    db.commit()
    return _to_detail(db, slot, place.name)


@router.post("/bulk", response_model=list[RecurringSlotDetail], status_code=201)
def create_recurring_slots(
    body: RecurringSlotBulkCreate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    place = (
        db.query(Place)
        .filter(Place.id == body.place_id, Place.professional_id == professional_id)
        .first()
    )
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")

    overlap_check = (
        _assert_no_scheduled_class_overlap
        if body.slot_kind == "class"
        else _assert_no_overlap
    )
    for day_of_week in body.days_of_week:
        overlap_check(
            db,
            professional_id,
            day_of_week,
            body.start_time,
            body.end_time,
        )

    shared_values = body.model_dump(exclude={"days_of_week"})
    slots = [
        RecurringSlot(
            professional_id=professional_id,
            day_of_week=day_of_week,
            **shared_values,
        )
        for day_of_week in body.days_of_week
    ]
    db.add_all(slots)
    if body.slot_kind == "availability":
        reactivate_place_review_escalations(db, professional_id)
    db.commit()
    return [_to_detail(db, slot, place.name) for slot in slots]


@router.post("/groups", response_model=RecurringSlotDetail, status_code=201)
def create_recurring_group(
    body: RecurringGroupCreate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    if body.end_time <= body.start_time:
        raise HTTPException(status_code=422, detail="End time must be after start time")
    if len(body.contact_ids) > body.max_participants:
        raise HTTPException(
            status_code=422,
            detail="Selected contacts exceed the group capacity",
        )

    place = (
        db.query(Place)
        .filter(Place.id == body.place_id, Place.professional_id == professional_id)
        .first()
    )
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")

    contacts = (
        db.query(Contact)
        .filter(
            Contact.id.in_(body.contact_ids),
            Contact.professional_id == professional_id,
        )
        .all()
    )
    if len(contacts) != len(body.contact_ids):
        raise HTTPException(status_code=404, detail="One or more contacts were not found")

    _assert_no_scheduled_class_overlap(
        db,
        professional_id,
        body.day_of_week,
        body.start_time,
        body.end_time,
        body.recurrence_type,
        body.scheduled_date,
    )

    slot = RecurringSlot(
        professional_id=professional_id,
        place_id=body.place_id,
        day_of_week=body.day_of_week,
        start_time=body.start_time,
        end_time=body.end_time,
        label=body.label,
        group_name=body.group_name,
        class_type="group",
        slot_kind="class",
        level=body.level,
        max_participants=body.max_participants,
        recurrence_type=body.recurrence_type,
        scheduled_date=body.scheduled_date,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
    )
    db.add(slot)
    db.flush()
    db.add_all(
        [
            RecurringSlotParticipant(
                recurring_slot_id=slot.id,
                contact_id=contact_id,
            )
            for contact_id in body.contact_ids
        ]
    )
    db.commit()
    return _to_detail(db, slot, place.name)


@router.patch("/{slot_id}", response_model=RecurringSlotDetail)
def update_recurring_slot(
    slot_id: uuid.UUID,
    body: RecurringSlotUpdate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    slot = _get_slot_or_404(db, slot_id, professional_id)
    updates = body.model_dump(exclude_unset=True)

    if "slot_kind" in updates and updates["slot_kind"] != slot.slot_kind:
        raise HTTPException(status_code=422, detail="Slot kind cannot be changed")

    validate_recurring_slot_definition(
        updates.get("slot_kind", slot.slot_kind),
        updates.get("class_type", slot.class_type),
        updates.get("max_participants", slot.max_participants),
        updates.get("group_name", slot.group_name),
        updates.get("level", slot.level),
    )

    if "place_id" in updates:
        place = (
            db.query(Place)
            .filter(Place.id == updates["place_id"], Place.professional_id == professional_id)
            .first()
        )
        if place is None:
            raise HTTPException(status_code=404, detail="Place not found")

    day_of_week = updates.get("day_of_week", slot.day_of_week)
    start_time = updates.get("start_time", slot.start_time)
    end_time = updates.get("end_time", slot.end_time)
    recurrence_type = updates.get("recurrence_type", slot.recurrence_type)
    scheduled_date = updates.get("scheduled_date", slot.scheduled_date)
    if end_time <= start_time:
        raise HTTPException(status_code=422, detail="End time must be after start time")
    if {
        "day_of_week",
        "start_time",
        "end_time",
        "recurrence_type",
        "scheduled_date",
    }.intersection(updates):
        overlap_check = (
            _assert_no_scheduled_class_overlap
            if slot.slot_kind == "class"
            else _assert_no_overlap
        )
        overlap_check(
            db,
            professional_id,
            day_of_week,
            start_time,
            end_time,
            recurrence_type,
            scheduled_date,
            exclude_slot_id=slot.id,
        )

    for field, value in updates.items():
        setattr(slot, field, value)
    if slot.slot_kind == "availability":
        reactivate_place_review_escalations(db, professional_id)
    db.commit()

    place_name = db.query(Place.name).filter(Place.id == slot.place_id).scalar()
    return _to_detail(db, slot, place_name)


@router.delete("/{slot_id}", status_code=204)
def delete_recurring_slot(
    slot_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    slot = _get_slot_or_404(db, slot_id, professional_id)
    is_place_stay = slot.slot_kind == "availability"
    db.delete(slot)
    if is_place_stay:
        reactivate_place_review_escalations(db, professional_id)
    db.commit()


@router.post("/{slot_id}/participants", response_model=RecurringSlotParticipantDetail, status_code=201)
def add_participant(
    slot_id: uuid.UUID,
    body: RecurringSlotParticipantCreate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    slot = _get_slot_or_404(db, slot_id, professional_id)
    contact = (
        db.query(Contact)
        .filter(Contact.id == body.contact_id, Contact.professional_id == professional_id)
        .first()
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    participant = _add_participant_service(db, professional_id, slot, contact)
    db.commit()
    return RecurringSlotParticipantDetail(
        id=participant.id, contact_id=contact.id, contact_name=contact.display_name
    )


@router.delete("/{slot_id}/participants/{contact_id}", status_code=204)
def remove_participant(
    slot_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    _get_slot_or_404(db, slot_id, professional_id)
    _remove_participant_service(db, slot_id, contact_id)
    db.commit()

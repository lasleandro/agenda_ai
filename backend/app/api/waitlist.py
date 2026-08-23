"""Waitlist ("Fila de Espera") API — waitlist roadmap v0.1, Phases 1 and 3.

GET  /api/waitlist-entries               — list (optional ?status=&place_id=&contact_id=).
POST /api/waitlist-entries                — create.
POST /api/waitlist-entries/{id}/cancel    — cancel (status -> "cancelled").
POST /api/waitlist-entries/{id}/fulfill   — mark fulfilled once the contact was booked
                                             (Agenda ghost-card "click to book" shortcut).

Cancel/fulfill are status transitions, not row deletes — WaitlistEntry is a
small state machine (open/matched/fulfilled/cancelled/expired), same
philosophy as OperatorActionCandidate/MakeupClassCredit.
"""

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import require_authenticated, require_professional_id
from app.database import SessionLocal
from app.models import Contact, Place, WaitlistEntry
from app.schemas.ontology import (
    WaitlistEntryCreate,
    WaitlistEntryDetail,
    WaitlistEntryListResponse,
)
from app.services import waitlist as waitlist_service
from app.services.operational_events import record_event
from app.services.scheduling import TIMEZONE


class WaitlistEntryFulfill(BaseModel):
    appointment_id: uuid.UUID


class WaitlistEntryGroupFulfill(BaseModel):
    recurring_slot_id: uuid.UUID
    occurrence_date: date
    enrollment_scope: Literal["occurrence", "series"]

router = APIRouter(prefix="/api/waitlist-entries", tags=["waitlist"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _to_detail(entry: WaitlistEntry, contact_name: str, place_name: str | None) -> WaitlistEntryDetail:
    return WaitlistEntryDetail(
        id=entry.id,
        contact_id=entry.contact_id,
        contact_name=contact_name,
        place_id=entry.place_id,
        place_name=place_name,
        desired_date=entry.desired_date,
        desired_start_time=entry.desired_start_time,
        desired_end_time=entry.desired_end_time,
        class_type=entry.class_type,
        duration_minutes=entry.duration_minutes,
        status=entry.status,
        note=entry.note,
        fulfilled_appointment_id=entry.fulfilled_appointment_id,
        fulfilled_recurring_slot_id=entry.fulfilled_recurring_slot_id,
        fulfilled_occurrence_date=entry.fulfilled_occurrence_date,
        fulfillment_scope=entry.fulfillment_scope,
        created_at=entry.created_at,
    )


def _detail_for(db: Session, entry: WaitlistEntry) -> WaitlistEntryDetail:
    contact_name = db.query(Contact.display_name).filter(Contact.id == entry.contact_id).scalar()
    place_name = (
        db.query(Place.name).filter(Place.id == entry.place_id).scalar() if entry.place_id else None
    )
    return _to_detail(entry, contact_name or "", place_name)


@router.get("", response_model=WaitlistEntryListResponse)
def list_waitlist_entries(
    status: str | None = None,
    place_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    entries = waitlist_service.list_entries(
        db, professional_id, status=status, place_id=place_id, contact_id=contact_id
    )
    contact_names = {
        contact.id: contact.display_name
        for contact in db.query(Contact).filter(
            Contact.id.in_([entry.contact_id for entry in entries])
        )
    } if entries else {}
    place_names = {
        place.id: place.name
        for place in db.query(Place).filter(
            Place.id.in_([entry.place_id for entry in entries if entry.place_id])
        )
    } if entries else {}
    return WaitlistEntryListResponse(
        entries=[
            _to_detail(entry, contact_names.get(entry.contact_id, ""), place_names.get(entry.place_id))
            for entry in entries
        ]
    )


@router.post("", response_model=WaitlistEntryDetail, status_code=201)
def create_waitlist_entry(
    body: WaitlistEntryCreate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    try:
        entry = waitlist_service.create_entry(db, professional_id, **body.model_dump())
    except waitlist_service.WaitlistValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _detail_for(db, entry)


@router.post("/{entry_id}/cancel", response_model=WaitlistEntryDetail)
def cancel_waitlist_entry(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    try:
        entry = waitlist_service.cancel_entry(db, professional_id, entry_id)
    except waitlist_service.WaitlistValidationError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Waitlist entry not found" else 409
        raise HTTPException(status_code=status_code, detail=detail)
    return _detail_for(db, entry)


@router.post("/{entry_id}/fulfill", response_model=WaitlistEntryDetail)
def fulfill_waitlist_entry(
    entry_id: uuid.UUID,
    body: WaitlistEntryFulfill,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    try:
        entry = waitlist_service.fulfill_entry(
            db, professional_id, entry_id, body.appointment_id
        )
    except waitlist_service.WaitlistValidationError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Waitlist entry not found" else 409
        raise HTTPException(status_code=status_code, detail=detail)
    return _detail_for(db, entry)


@router.post("/{entry_id}/fulfill-group", response_model=WaitlistEntryDetail)
def fulfill_waitlist_entry_with_group(
    entry_id: uuid.UUID,
    body: WaitlistEntryGroupFulfill,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
    user: dict = Depends(require_authenticated),
):
    try:
        entry = waitlist_service.fulfill_group_occurrence(
            db,
            professional_id,
            entry_id=entry_id,
            recurring_slot_id=body.recurring_slot_id,
            occurrence_date=body.occurrence_date,
            enrollment_scope=body.enrollment_scope,
        )
    except waitlist_service.WaitlistValidationError as exc:
        detail = str(exc)
        status_code = 404 if detail in {
            "Waitlist entry not found",
            "Recurring group not found",
            "Scheduled group occurrence not found",
            "Waitlist contact not found",
        } else 409
        raise HTTPException(status_code=status_code, detail=detail)
    record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.participant.added",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=uuid.UUID(user["user_id"]),
        source_channel="web",
        entity_type="recurring_slot",
        entity_id=body.recurring_slot_id,
        correlation_id=uuid.uuid4(),
        payload={
            "contact_id": str(entry.contact_id),
            "occurrence_date": body.occurrence_date.isoformat(),
            "scope": body.enrollment_scope,
            "waitlist_entry_id": str(entry.id),
        },
    )
    db.commit()
    return _detail_for(db, entry)

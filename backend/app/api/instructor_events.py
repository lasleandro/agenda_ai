"""Instructor Events API (instructor events roadmap v0.1, Phase 1).

GET  /api/instructor-events               — list (optional ?date_from=&date_to=&status=).
POST /api/instructor-events                — create.
POST /api/instructor-events/{id}/cancel    — cancel (status -> "cancelled").

Cancellation is a status transition, not a row delete, same philosophy as
WaitlistEntry/OperatorActionCandidate.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import require_professional_id
from app.database import SessionLocal
from app.models import InstructorEvent, Place
from app.schemas.instructor_events import (
    InstructorEventCreate,
    InstructorEventDetail,
    InstructorEventListResponse,
)
from app.services import instructor_events as instructor_events_service

router = APIRouter(prefix="/api/instructor-events", tags=["instructor-events"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _detail_for(db: Session, event: InstructorEvent) -> InstructorEventDetail:
    place_name = (
        db.query(Place.name).filter(Place.id == event.place_id).scalar()
        if event.place_id
        else None
    )
    return InstructorEventDetail(
        id=event.id,
        event_type=event.event_type,
        title=event.title,
        place_id=event.place_id,
        place_name=place_name,
        start_at=event.start_at,
        end_at=event.end_at,
        income_cents=event.income_cents,
        note=event.note,
        status=event.status,
        created_at=event.created_at,
    )


@router.get("", response_model=InstructorEventListResponse)
def list_instructor_events(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    events = instructor_events_service.list_events(
        db, professional_id, date_from=date_from, date_to=date_to, status=status
    )
    return InstructorEventListResponse(events=[_detail_for(db, event) for event in events])


@router.post("", response_model=InstructorEventDetail, status_code=201)
def create_instructor_event(
    body: InstructorEventCreate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    try:
        event = instructor_events_service.create_event(db, professional_id, **body.model_dump())
    except instructor_events_service.InstructorEventValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _detail_for(db, event)


@router.post("/{event_id}/cancel", response_model=InstructorEventDetail)
def cancel_instructor_event(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    try:
        event = instructor_events_service.cancel_event(db, professional_id, event_id)
    except instructor_events_service.InstructorEventValidationError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Event not found" else 409
        raise HTTPException(status_code=status_code, detail=detail)
    return _detail_for(db, event)

"""Passive-observer candidate review API (waitlist roadmap v0.1, Phase 4).

GET  /api/appointment-candidates                    — list (optional ?status=, default "detected").
POST /api/appointment-candidates/{id}/dismiss        — status -> "dismissed".
POST /api/appointment-candidates/{id}/confirm-appointment — create supported detected
                                                          appointments and status -> "fulfilled".
POST /api/appointment-candidates/{id}/fulfill-waitlist — action="waitlist_request" only: create
                                                          the real WaitlistEntry, status -> "fulfilled".

Closes a pre-existing gap: `AppointmentCandidate` (what the passive
observer produces — see chat/pipeline.py) previously had no real review
surface, only the dev-only conversation viewer (api/conversations.py).
Create candidates can be reviewed and confirmed into a real appointment;
reschedule, cancel, and recurrence remain dismiss-only until their
operation-specific review contracts are implemented. waitlist_request creates
a real WaitlistEntry through its existing dedicated flow.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from datetime import date, datetime, time

from pydantic import BaseModel

from app.api.conversations import candidate_with_evidence
from app.api.dependencies import require_authenticated, require_professional_id
from app.api.waitlist import _detail_for as _waitlist_entry_detail
from app.database import SessionLocal
from app.models import AppointmentCandidate
from app.schemas.api import CandidateDetail
from app.schemas.ontology import WaitlistEntryDetail
from app.services import waitlist as waitlist_service
from app.services.candidate_execution import CreateCandidateInput, confirm_create_candidate

router = APIRouter(prefix="/api/appointment-candidates", tags=["appointment-candidates"])


class CandidateListResponse(BaseModel):
    candidates: list[CandidateDetail]


class CandidateFulfillWaitlist(BaseModel):
    place_id: uuid.UUID | None = None
    desired_date: date
    desired_start_time: time
    desired_end_time: time
    class_type: str | None = None
    duration_minutes: int | None = None
    note: str | None = None


class CandidateConfirmAppointment(BaseModel):
    place_id: uuid.UUID | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    service: str | None = None


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_candidate_or_404(
    db: Session, candidate_id: uuid.UUID, professional_id: uuid.UUID, *, lock: bool = False
) -> AppointmentCandidate:
    query = (
        db.query(AppointmentCandidate)
        .filter(
            AppointmentCandidate.id == candidate_id,
            AppointmentCandidate.professional_id == professional_id,
        )
    )
    if lock:
        query = query.with_for_update()
    candidate = query.first()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@router.get("", response_model=CandidateListResponse)
def list_appointment_candidates(
    status: str = "detected",
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    query = db.query(AppointmentCandidate).filter(
        AppointmentCandidate.professional_id == professional_id,
    )
    if status != "all":
        query = query.filter(AppointmentCandidate.status == status)
    candidates = query.order_by(AppointmentCandidate.created_at.desc()).all()
    return CandidateListResponse(
        candidates=[candidate_with_evidence(db, candidate) for candidate in candidates]
    )


@router.post("/{candidate_id}/dismiss", response_model=CandidateDetail)
def dismiss_candidate(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    candidate = _get_candidate_or_404(db, candidate_id, professional_id)
    if candidate.status != "detected":
        raise HTTPException(
            status_code=409, detail=f"Candidate is not pending (status={candidate.status})"
        )
    candidate.status = "dismissed"
    db.commit()
    return candidate_with_evidence(db, candidate)


@router.post("/{candidate_id}/confirm-appointment", response_model=CandidateDetail)
def confirm_appointment_from_candidate(
    candidate_id: uuid.UUID,
    body: CandidateConfirmAppointment,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
    user: dict = Depends(require_authenticated),
):
    """Create one reviewed appointment and fulfill its passive candidate."""
    candidate = _get_candidate_or_404(db, candidate_id, professional_id, lock=True)
    confirm_create_candidate(
        db,
        candidate,
        actor_user_id=uuid.UUID(user["user_id"]),
        input=CreateCandidateInput(**body.model_dump()),
    )
    db.commit()
    return candidate_with_evidence(db, candidate)


@router.post("/{candidate_id}/fulfill-waitlist", response_model=WaitlistEntryDetail)
def fulfill_waitlist_from_candidate(
    candidate_id: uuid.UUID,
    body: CandidateFulfillWaitlist,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    candidate = _get_candidate_or_404(db, candidate_id, professional_id)
    if candidate.action != "waitlist_request":
        raise HTTPException(
            status_code=422,
            detail=f"Only waitlist_request candidates can be fulfilled this way (action={candidate.action})",
        )
    if candidate.status != "detected":
        raise HTTPException(
            status_code=409, detail=f"Candidate is not pending (status={candidate.status})"
        )
    if candidate.contact_id is None:
        raise HTTPException(status_code=422, detail="Candidate has no resolved contact")

    try:
        entry = waitlist_service.create_entry(
            db, professional_id, contact_id=candidate.contact_id, **body.model_dump()
        )
    except waitlist_service.WaitlistValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    candidate.status = "fulfilled"
    db.commit()

    return _waitlist_entry_detail(db, entry)

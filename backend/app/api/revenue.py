"""Feature-gated recognized-revenue confirmation and reporting endpoints."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_authenticated, require_commercial_financials
from app.database import SessionLocal
from app.models import RevenueOccurrence
from app.schemas.financial import (
    RevenueCandidateList,
    RevenueOccurrenceCreate,
    RevenueOccurrenceDetail,
    RevenuePreviewDetail,
    RevenueSummaryDetail,
)
from app.services.financial_audit import add_financial_audit
from app.services.revenue_occurrences import (
    RevenueOccurrenceConflictError,
    RevenueOccurrenceNotFoundError,
    RevenueOccurrenceValidationError,
    build_revenue_summary,
    create_revenue_occurrence,
    list_revenue_candidates,
    revenue_occurrence_detail,
    preview_schedule_revenue,
)

router = APIRouter(prefix="/api/financial/revenue", tags=["financial-revenue"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _validate_period(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise HTTPException(
            status_code=422,
            detail="End date must be on or after start date",
        )
    if (date_to - date_from).days > 365:
        raise HTTPException(
            status_code=422,
            detail="Revenue period cannot exceed 366 days",
        )


@router.get("/candidates", response_model=RevenueCandidateList)
def get_revenue_candidates(
    date_from: date = Query(...),
    date_to: date = Query(...),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
):
    _validate_period(date_from, date_to)
    candidates = list_revenue_candidates(
        db,
        professional_id,
        date_from,
        date_to,
    )
    return RevenueCandidateList(
        total=len(candidates),
        limit=limit,
        offset=offset,
        candidates=candidates[offset : offset + limit],
    )


@router.get(
    "/preview",
    response_model=RevenuePreviewDetail,
    response_model_exclude_none=True,
)
def get_revenue_preview(
    source_type: str = Query(pattern="^(appointment|recurring_slot)$"),
    source_id: uuid.UUID = Query(...),
    occurrence_date: date = Query(...),
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
):
    try:
        return preview_schedule_revenue(
            db, professional_id, source_type, source_id, occurrence_date
        )
    except RevenueOccurrenceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/occurrences",
    response_model=RevenueOccurrenceDetail,
    status_code=201,
)
def confirm_revenue_occurrence(
    body: RevenueOccurrenceCreate,
    request: Request,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
    user: dict = Depends(require_authenticated),
):
    actor_user_id = uuid.UUID(user["user_id"])
    try:
        occurrence = create_revenue_occurrence(
            db,
            professional_id,
            actor_user_id,
            body,
        )
    except RevenueOccurrenceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RevenueOccurrenceConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RevenueOccurrenceValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    add_financial_audit(
        db,
        professional_id=professional_id,
        actor_user_id=actor_user_id,
        entity_type="revenue_occurrence",
        entity_id=occurrence.id,
        action="confirm",
        changes={
            "recognition": {
                "before": None,
                "after": {
                    "source_type": occurrence.source_type,
                    "source_id": str(occurrence.source_id),
                    "occurrence_date": occurrence.occurrence_date.isoformat(),
                    "outcome_status": occurrence.outcome_status,
                    "participant_count": occurrence.participant_count,
                    "billable_participant_count": (
                        occurrence.billable_participant_count
                    ),
                    "subtotal_cents": occurrence.subtotal_cents,
                    "adjustment_cents": occurrence.adjustment_cents,
                    "total_cents": occurrence.total_cents,
                },
            }
        },
        source_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This schedule occurrence has already been recognized",
        ) from error
    db.refresh(occurrence)
    return revenue_occurrence_detail(db, occurrence)


@router.get(
    "/occurrences/{occurrence_id}",
    response_model=RevenueOccurrenceDetail,
)
def get_revenue_occurrence(
    occurrence_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
):
    occurrence = (
        db.query(RevenueOccurrence)
        .filter(
            RevenueOccurrence.id == occurrence_id,
            RevenueOccurrence.professional_id == professional_id,
        )
        .first()
    )
    if occurrence is None:
        raise HTTPException(status_code=404, detail="Revenue occurrence not found")
    return revenue_occurrence_detail(db, occurrence)


@router.get("/summary", response_model=RevenueSummaryDetail)
def get_revenue_summary(
    date_from: date = Query(...),
    date_to: date = Query(...),
    occurrence_limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
):
    _validate_period(date_from, date_to)
    return build_revenue_summary(
        db,
        professional_id,
        date_from,
        date_to,
        occurrence_limit,
    )

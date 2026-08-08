"""Operational rules (work journey, make-up cancellation notice window).

Unlike Financeiro, these settings are not gated behind the
commercial_financials feature flag: scheduling (assert_within_work_journey)
and make-up credit eligibility (grant_credit_if_eligible) enforce them for
every tenant regardless of that flag, so every tenant must be able to
configure them.
"""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import require_authenticated, require_professional_id
from app.database import SessionLocal
from app.schemas.rules import (
    CancellationNoticeHoursDetail,
    CancellationNoticeHoursUpdate,
    WorkJourneyIntervalDetail,
    WorkJourneyReplace,
)
from app.services import financial_settings, work_journey
from app.services.financial_audit import add_financial_audit

router = APIRouter(prefix="/api/rules", tags=["rules"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _request_origin(request: Request) -> tuple[str | None, str | None]:
    client_ip = request.client.host if request.client else None
    forwarded_for = request.headers.get("x-forwarded-for")
    source_ip = forwarded_for.split(",")[0].strip() if forwarded_for else client_ip
    user_agent = request.headers.get("user-agent")
    return source_ip, user_agent


@router.get("/work-journey", response_model=list[WorkJourneyIntervalDetail])
def get_work_journey(
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    return work_journey.get_work_journey(db, professional_id)


@router.put("/work-journey", response_model=list[WorkJourneyIntervalDetail])
def replace_work_journey(
    body: WorkJourneyReplace,
    request: Request,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
    user: dict = Depends(require_authenticated),
):
    work_journey.assert_work_journey_is_valid(body)
    previous, updated = work_journey.replace_work_journey_intervals(
        db, professional_id, body.intervals
    )

    source_ip, user_agent = _request_origin(request)
    add_financial_audit(
        db,
        professional_id=professional_id,
        actor_user_id=uuid.UUID(user["user_id"]),
        entity_type="work_journey",
        entity_id=professional_id,
        action="replace",
        changes={
            "intervals": {
                "before": previous,
                "after": [
                    interval.model_dump(mode="json") for interval in body.intervals
                ],
            }
        },
        source_ip=source_ip,
        user_agent=user_agent,
    )
    db.commit()
    return updated


@router.get(
    "/cancellation-notice-hours", response_model=CancellationNoticeHoursDetail
)
def get_cancellation_notice_hours(
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    return CancellationNoticeHoursDetail(
        cancellation_notice_hours=financial_settings.get_cancellation_notice_hours(
            db, professional_id
        )
    )


@router.patch(
    "/cancellation-notice-hours", response_model=CancellationNoticeHoursDetail
)
def update_cancellation_notice_hours(
    body: CancellationNoticeHoursUpdate,
    request: Request,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
    user: dict = Depends(require_authenticated),
):
    previous_hours = financial_settings.update_cancellation_notice_hours(
        db, professional_id, body.cancellation_notice_hours
    )

    source_ip, user_agent = _request_origin(request)
    add_financial_audit(
        db,
        professional_id=professional_id,
        actor_user_id=uuid.UUID(user["user_id"]),
        entity_type="cancellation_notice_hours",
        entity_id=professional_id,
        action="update",
        changes={
            "cancellation_notice_hours": {
                "before": previous_hours,
                "after": body.cancellation_notice_hours,
            }
        }
        if previous_hours != body.cancellation_notice_hours
        else {},
        source_ip=source_ip,
        user_agent=user_agent,
    )
    db.commit()
    return CancellationNoticeHoursDetail(
        cancellation_notice_hours=body.cancellation_notice_hours
    )

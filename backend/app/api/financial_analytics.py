"""Feature-gated financial dashboard and immutable scenario endpoints."""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.dependencies import require_authenticated, require_commercial_financials
from app.database import SessionLocal
from app.models import FinancialScenario
from app.schemas.financial import (
    FinancialDashboardDetail,
    FinancialOperationalAnalyticsDetail,
    FinancialScenarioDetail,
    FinancialScenarioInput,
    FinancialScenarioList,
    FinancialScenarioResult,
)
from app.services.financial_analytics import (
    build_financial_dashboard,
    evaluate_financial_scenario,
)
from app.services.financial_audit import add_financial_audit
from app.services.financial_operational_analytics import (
    build_financial_operational_analytics,
)

router = APIRouter(prefix="/api/financial", tags=["financial-analytics"])


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
            detail="Analytics period cannot exceed 366 days",
        )


def _not_found_from_value_error(error: ValueError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


def _scenario_detail(row: FinancialScenario) -> FinancialScenarioDetail:
    return FinancialScenarioDetail(
        id=row.id,
        name=row.name,
        input_snapshot=row.input_snapshot,
        result_snapshot=row.result_snapshot,
        created_at=row.created_at,
    )


@router.get("/dashboard", response_model=FinancialDashboardDetail)
def get_financial_dashboard(
    date_from: date = Query(...),
    date_to: date = Query(...),
    place_id: list[uuid.UUID] | None = Query(default=None),
    capacity_mode: Literal["configured_only", "estimated_when_unconfigured"] = Query(
        default="configured_only"
    ),
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
):
    _validate_period(date_from, date_to)
    try:
        return build_financial_dashboard(
            db,
            professional_id,
            date_from,
            date_to,
            place_id,
            capacity_mode,
        )
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@router.get("/operational-analytics", response_model=FinancialOperationalAnalyticsDetail)
def get_financial_operational_analytics(
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
):
    _validate_period(date_from, date_to)
    return build_financial_operational_analytics(
        db,
        professional_id,
        date_from,
        date_to,
    )


@router.post(
    "/scenarios/evaluate",
    response_model=FinancialScenarioResult,
)
def evaluate_scenario(
    body: FinancialScenarioInput,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
):
    try:
        return evaluate_financial_scenario(db, professional_id, body)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@router.post(
    "/scenarios",
    response_model=FinancialScenarioDetail,
    status_code=201,
)
def save_scenario(
    body: FinancialScenarioInput,
    request: Request,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
    user: dict = Depends(require_authenticated),
):
    try:
        result = evaluate_financial_scenario(db, professional_id, body)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error

    row = FinancialScenario(
        professional_id=professional_id,
        created_by_user_id=uuid.UUID(user["user_id"]),
        name=body.name.strip(),
        input_snapshot=body.model_dump(mode="json"),
        result_snapshot=result.model_dump(mode="json"),
    )
    db.add(row)
    db.flush()
    add_financial_audit(
        db,
        professional_id=professional_id,
        actor_user_id=uuid.UUID(user["user_id"]),
        entity_type="financial_scenario",
        entity_id=row.id,
        action="create",
        changes={
            "scenario": {
                "before": None,
                "after": {
                    "name": row.name,
                    "input_snapshot": row.input_snapshot,
                },
            }
        },
        source_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _scenario_detail(row)


@router.get("/scenarios", response_model=FinancialScenarioList)
def list_scenarios(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
):
    rows = (
        db.query(FinancialScenario)
        .filter(FinancialScenario.professional_id == professional_id)
        .order_by(FinancialScenario.created_at.desc())
        .limit(limit)
        .all()
    )
    return FinancialScenarioList(
        scenarios=[_scenario_detail(row) for row in rows]
    )

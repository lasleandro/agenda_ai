"""Platform-admin review and onboarding actions for account requests."""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_platform_admin
from app.core import error_codes
from app.core.error_responses import error_response
from app.database import SessionLocal
from app.models import Professional
from app.schemas.account_requests import (
    AccountActivationResendResponse,
    AccountRequestAdminListResponse,
    AccountRequestApprove,
    AccountRequestDecisionResponse,
    AccountRequestMetricsResponse,
    AccountRequestReject,
    AccountRequestSummaryResponse,
)
from app.services.account_requests import (
    AccountRequestError,
    approve_account_request,
    build_account_request_items,
    get_account_request_operational_metrics,
    get_account_request_page,
    get_account_request_status_counts,
    reject_account_request,
    resend_account_activation,
)
from app.services.admin_tenant_summaries import build_tenant_summaries
from app.services.admin_tenants import TenantCreationError

router = APIRouter(prefix="/api/admin/account-requests", tags=["admin-account-requests"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _source_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _account_request_error(exc: AccountRequestError):
    if exc.code == error_codes.ACCOUNT_REQUEST_NOT_FOUND:
        status_code = 404
    elif exc.code == error_codes.RATE_LIMITED:
        status_code = 429
    elif exc.code in {
        error_codes.ACCOUNT_REQUEST_ALREADY_DECIDED,
        error_codes.ACCOUNT_REQUEST_ACTIVATION_UNAVAILABLE,
    }:
        status_code = 409
    else:
        status_code = 422
    return error_response(status_code, exc.code, exc.message)


@router.get("", response_model=AccountRequestAdminListResponse)
def list_account_requests(
    status: str = Query(default="pending"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=10, le=50),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_platform_admin),
):
    try:
        result = get_account_request_page(
            db, status=status, page=page, page_size=page_size
        )
    except AccountRequestError as exc:
        return _account_request_error(exc)
    return AccountRequestAdminListResponse(
        requests=result.requests,
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        total_pages=result.total_pages,
        status_counts=result.status_counts,
    )


@router.get("/summary", response_model=AccountRequestSummaryResponse)
def account_request_summary(
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_platform_admin),
):
    return AccountRequestSummaryResponse(
        pending=get_account_request_status_counts(db).pending
    )


@router.get("/metrics", response_model=AccountRequestMetricsResponse)
def account_request_metrics(
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_platform_admin),
):
    return AccountRequestMetricsResponse(**get_account_request_operational_metrics(db))


@router.post(
    "/{request_id}/approve", response_model=AccountRequestDecisionResponse
)
def approve_request(
    request_id: uuid.UUID,
    body: AccountRequestApprove,
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_platform_admin),
):
    try:
        request_row, created = approve_account_request(
            db,
            request_id=request_id,
            tenant_name=body.tenant_name,
            whatsapp=body.whatsapp,
            tenant_timezone=body.timezone,
            admin_user_id=uuid.UUID(admin["user_id"]),
            source_ip=_source_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    except AccountRequestError as exc:
        db.rollback()
        return _account_request_error(exc)
    except TenantCreationError as exc:
        db.rollback()
        status_code = 409 if exc.code == error_codes.EMAIL_ALREADY_IN_USE else 422
        return error_response(status_code, exc.code, exc.message)
    except IntegrityError:
        db.rollback()
        return error_response(
            409,
            error_codes.EMAIL_ALREADY_IN_USE,
            "Este email já possui uma conta cadastrada.",
        )
    except Exception:
        db.rollback()
        raise

    professional = (
        created.professional
        if created is not None
        else db.get(Professional, request_row.professional_id)
    )
    if professional is None:
        return error_response(
            409,
            error_codes.ACCOUNT_REQUEST_ALREADY_DECIDED,
            "O tenant vinculado à solicitação não está disponível.",
        )
    return AccountRequestDecisionResponse(
        request=build_account_request_items(db, [request_row])[0],
        tenant=build_tenant_summaries(db, [professional])[0],
    )


@router.post(
    "/{request_id}/reject", response_model=AccountRequestDecisionResponse
)
def reject_request(
    request_id: uuid.UUID,
    body: AccountRequestReject,
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_platform_admin),
):
    try:
        request_row = reject_account_request(
            db,
            request_id=request_id,
            reason=body.reason,
            admin_user_id=uuid.UUID(admin["user_id"]),
            source_ip=_source_ip(request),
        )
        db.commit()
    except AccountRequestError as exc:
        db.rollback()
        return _account_request_error(exc)
    except Exception:
        db.rollback()
        raise
    return AccountRequestDecisionResponse(
        request=build_account_request_items(db, [request_row])[0]
    )


@router.post(
    "/{request_id}/resend-activation",
    response_model=AccountActivationResendResponse,
)
def resend_activation(
    request_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_platform_admin),
):
    try:
        delivery = resend_account_activation(
            db,
            request_id=request_id,
            admin_user_id=uuid.UUID(admin["user_id"]),
            source_ip=_source_ip(request),
        )
        db.commit()
    except AccountRequestError as exc:
        db.rollback()
        return _account_request_error(exc)
    except Exception:
        db.rollback()
        raise
    return AccountActivationResendResponse(
        request_id=request_id, activation_state=delivery.status
    )


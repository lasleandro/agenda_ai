"""Anonymous, rate-limited platform account-request intake."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core import error_codes
from app.core.error_responses import error_response
from app.database import SessionLocal
from app.schemas.account_requests import (
    AccountRequestPublicResponse,
    AccountRequestSubmit,
)
from app.services.account_requests import (
    PUBLIC_ACCOUNT_REQUEST_MESSAGE,
    AccountRequestError,
    submit_account_request,
)

router = APIRouter(prefix="/api/account-requests", tags=["account-requests"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", status_code=202, response_model=AccountRequestPublicResponse)
def create_account_request(
    body: AccountRequestSubmit,
    request: Request,
    db: Session = Depends(get_db),
):
    """Accept a request without creating an account or exposing its existence."""
    source_ip = request.client.host if request.client else None
    try:
        submit_account_request(
            db,
            proposed_tenant_name=body.proposed_tenant_name,
            email=body.email,
            whatsapp=body.whatsapp,
            message=body.message,
            source_ip=source_ip,
        )
        db.commit()
    except AccountRequestError as exc:
        db.rollback()
        status_code = 429 if exc.code == error_codes.RATE_LIMITED else 422
        return error_response(status_code, exc.code, exc.message)
    except Exception:
        db.rollback()
        raise
    return AccountRequestPublicResponse(message=PUBLIC_ACCOUNT_REQUEST_MESSAGE)


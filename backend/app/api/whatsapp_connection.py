"""
Tenant-facing WhatsApp connection request — the manual, admin-assisted path
while automatic self-service connection is still on the roadmap.

GET  /api/whatsapp/connection-request  — whether this tenant already asked.
POST /api/whatsapp/connection-request  — notify the admin by email; idempotent.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import require_authenticated, require_professional_id
from app.core.error_codes import WHATSAPP_CONNECTION_REQUEST_FAILED
from app.core.error_responses import error_response
from app.database import SessionLocal
from app.integrations.email.contracts import EmailDeliveryError, OutboundEmail
from app.integrations.email.smtp import SmtpEmailSender
from app.models import Professional
from app.schemas.api import WhatsappConnectionRequestState
from app.services.tenant_features import (
    WHATSAPP_CONNECTION_REQUESTED,
    is_tenant_feature_enabled,
    set_tenant_feature,
)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

logger = logging.getLogger(__name__)

ADMIN_NOTIFICATION_EMAIL = "contato@tennisos.com.br"


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _build_admin_notification(tenant_name: str, requester_email: str, professional_id: uuid.UUID) -> OutboundEmail:
    text_body = (
        f'O tenant "{tenant_name}" solicitou a conexão do WhatsApp.\n'
        f"Usuário: {requester_email}\n"
        f"ID do tenant: {professional_id}\n"
    )
    html_body = (
        f"<p>O tenant <strong>{tenant_name}</strong> solicitou a conexão do WhatsApp.</p>"
        f"<p>Usuário: {requester_email}<br/>ID do tenant: {professional_id}</p>"
    )
    return OutboundEmail(
        to_address=ADMIN_NOTIFICATION_EMAIL,
        subject=f"Solicitação de conexão WhatsApp - {tenant_name}",
        html_body=html_body,
        text_body=text_body,
    )


@router.get("/connection-request", response_model=WhatsappConnectionRequestState)
def get_connection_request_state(
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    requested = is_tenant_feature_enabled(db, professional_id, WHATSAPP_CONNECTION_REQUESTED)
    return WhatsappConnectionRequestState(requested=requested)


@router.post("/connection-request", response_model=WhatsappConnectionRequestState)
def create_connection_request(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(require_authenticated),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    if is_tenant_feature_enabled(db, professional_id, WHATSAPP_CONNECTION_REQUESTED):
        return WhatsappConnectionRequestState(requested=True)

    professional = db.get(Professional, professional_id)
    tenant_name = professional.name if professional else "tenant desconhecido"

    try:
        SmtpEmailSender().send(
            _build_admin_notification(tenant_name, user["email"], professional_id)
        )
    except EmailDeliveryError:
        logger.exception(
            "Failed to send WhatsApp connection request notification (professional_id=%s)",
            professional_id,
        )
        return error_response(
            502,
            WHATSAPP_CONNECTION_REQUEST_FAILED,
            "Não foi possível enviar a solicitação agora. Tente novamente em instantes.",
        )

    set_tenant_feature(
        db,
        professional_id=professional_id,
        feature_key=WHATSAPP_CONNECTION_REQUESTED,
        enabled=True,
        admin_user_id=uuid.UUID(user["user_id"]),
        source_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return WhatsappConnectionRequestState(requested=True)

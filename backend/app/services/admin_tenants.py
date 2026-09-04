"""Platform-admin tenant provisioning with the initial owner activation flow."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.core import error_codes
from app.models import Professional, User
from app.models.professional import TENANT_STATUS_ACTIVE
from app.services.auth_emails import enqueue_auth_email
from app.services.auth_security import digest_identifier, record_auth_event
from app.services.email_identity import InvalidEmailError, normalize_email
from app.services.operational_events import record_event
from app.services.phone_numbers import PhoneNumberValidationError, normalize_mobile_phone

SUPPORTED_TENANT_TIMEZONES = frozenset(
    {
        "America/Araguaina",
        "America/Bahia",
        "America/Belem",
        "America/Cuiaba",
        "America/Fortaleza",
        "America/Maceio",
        "America/Manaus",
        "America/Noronha",
        "America/Recife",
        "America/Rio_Branco",
        "America/Sao_Paulo",
    }
)


class TenantCreationError(Exception):
    """A safe, stable validation or conflict error for tenant provisioning."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CreatedTenant:
    """The persisted tenant and owner returned to the HTTP layer."""

    professional: Professional
    owner: User


def create_tenant_with_owner(
    db: Session,
    *,
    name: str,
    owner_email: str,
    whatsapp: str,
    tenant_timezone: str,
    admin_user_id: uuid.UUID,
    source_ip: str | None,
    user_agent: str | None,
    audit_source: str = "admin_tenant_create",
    account_request_id: uuid.UUID | None = None,
) -> CreatedTenant:
    """Create an active tenant and one pending owner. Caller commits or rolls back."""
    normalized_name = name.strip()
    if len(normalized_name) < 2:
        raise TenantCreationError(
            error_codes.TENANT_NAME_INVALID, "Informe um nome de tenant válido."
        )

    try:
        canonical_whatsapp = normalize_mobile_phone(whatsapp)
    except PhoneNumberValidationError as exc:
        raise TenantCreationError(
            error_codes.INVALID_PHONE, "Informe um número de WhatsApp válido."
        ) from exc

    try:
        timezone_name = ZoneInfo(tenant_timezone.strip()).key
    except ZoneInfoNotFoundError as exc:
        raise TenantCreationError(
            error_codes.INVALID_TIMEZONE, "Informe um fuso horário válido."
        ) from exc
    if timezone_name not in SUPPORTED_TENANT_TIMEZONES:
        raise TenantCreationError(
            error_codes.INVALID_TIMEZONE, "Informe um fuso horário suportado."
        )

    try:
        canonical_email = normalize_email(owner_email)
    except InvalidEmailError as exc:
        raise TenantCreationError(error_codes.INVALID_EMAIL, "Informe um email válido.") from exc

    if db.query(User.id).filter(User.email == canonical_email).first() is not None:
        raise TenantCreationError(
            error_codes.EMAIL_ALREADY_IN_USE,
            "Este email já possui uma conta cadastrada.",
        )

    professional = Professional(
        name=normalized_name,
        timezone=timezone_name,
        assistant_phone=canonical_whatsapp,
        status=TENANT_STATUS_ACTIVE,
    )
    db.add(professional)
    db.flush()

    owner = User(
        email=canonical_email,
        role="professional",
        professional_id=professional.id,
        status="pending_activation",
    )
    db.add(owner)
    db.flush()
    enqueue_auth_email(db, user=owner, purpose="account_activation")

    now = datetime.now(timezone.utc)
    correlation_id = uuid.uuid4()
    record_auth_event(
        db,
        event_type="account_activation_queued",
        user_id=owner.id,
        email=owner.email,
        source_ip=source_ip,
        metadata={"professional_id": str(professional.id), "source": "admin_tenant_create"},
    )
    record_event(
        db,
        professional_id=professional.id,
        event_type="tenant.created",
        occurred_at=now,
        actor_type="platform_admin",
        actor_id=admin_user_id,
        source_channel="web",
        entity_type="professional",
        entity_id=professional.id,
        correlation_id=correlation_id,
        payload={
            "owner_email_digest": digest_identifier(owner.email),
            "source": audit_source,
            "account_request_id": (
                str(account_request_id) if account_request_id is not None else None
            ),
            "user_agent": user_agent[:512] if user_agent else None,
        },
        after_state={"status": TENANT_STATUS_ACTIVE, "timezone": timezone_name},
    )
    return CreatedTenant(professional=professional, owner=owner)

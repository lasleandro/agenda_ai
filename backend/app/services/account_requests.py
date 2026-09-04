"""Public account-request intake and platform-admin decision services."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import error_codes
from app.core.settings import get_int
from app.models import (
    AccountAccessRequest,
    AuthSecurityEvent,
    EmailDelivery,
    Professional,
    User,
)
from app.models.account_access_request import (
    ACCOUNT_REQUEST_APPROVED,
    ACCOUNT_REQUEST_PENDING,
    ACCOUNT_REQUEST_REJECTED,
    ACCOUNT_REQUEST_STATUSES,
)
from app.schemas.account_requests import (
    AccountRequestAdminItem,
    AccountRequestStatusCounts,
)
from app.services.admin_tenants import CreatedTenant, create_tenant_with_owner
from app.services.auth_emails import PENDING_DELIVERY_STATUSES, enqueue_auth_email
from app.services.auth_security import rate_limit_exceeded, record_auth_event
from app.services.email_identity import InvalidEmailError, normalize_email
from app.services.phone_numbers import PhoneNumberValidationError, normalize_mobile_phone

PUBLIC_ACCOUNT_REQUEST_MESSAGE = (
    "Solicitação recebida. Nossa equipe analisará os dados informados."
)


class AccountRequestError(Exception):
    """Safe, stable account-request error returned by an HTTP adapter."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AccountRequestPage:
    """One bounded admin request page plus unfiltered status counts."""

    requests: list[AccountRequestAdminItem]
    page: int
    page_size: int
    total: int
    total_pages: int
    status_counts: AccountRequestStatusCounts


def _admin_rate_limit_exceeded(
    db: Session,
    *,
    event_type: str,
    admin_user_id: uuid.UUID,
    limit: int,
    window: timedelta,
) -> bool:
    since = datetime.now(timezone.utc) - window
    count = (
        db.query(func.count(AuthSecurityEvent.id))
        .filter(
            AuthSecurityEvent.event_type == event_type,
            AuthSecurityEvent.user_id == admin_user_id,
            AuthSecurityEvent.created_at >= since,
        )
        .scalar()
        or 0
    )
    return count >= limit


def submit_account_request(
    db: Session,
    *,
    proposed_tenant_name: str,
    email: str,
    whatsapp: str,
    message: str | None,
    source_ip: str | None,
) -> None:
    """Persist one pending request without revealing account existence."""
    normalized_name = proposed_tenant_name.strip()
    if len(normalized_name) < 2 or len(normalized_name) > 255:
        raise AccountRequestError(
            error_codes.TENANT_NAME_INVALID,
            "Informe um nome profissional ou da operação válido.",
        )
    normalized_message = message.strip() if message else None
    if normalized_message and len(normalized_message) > 1000:
        raise AccountRequestError(
            error_codes.ACCOUNT_REQUEST_MESSAGE_INVALID,
            "A mensagem deve ter no máximo 1000 caracteres.",
        )
    try:
        canonical_email = normalize_email(email)
    except InvalidEmailError as exc:
        raise AccountRequestError(
            error_codes.INVALID_EMAIL, "Informe um email válido."
        ) from exc
    try:
        canonical_whatsapp = normalize_mobile_phone(whatsapp)
    except PhoneNumberValidationError as exc:
        raise AccountRequestError(
            error_codes.INVALID_PHONE, "Informe um número de WhatsApp válido."
        ) from exc

    if rate_limit_exceeded(
        db,
        event_type="account_request_submitted",
        email=canonical_email,
        source_ip=None,
        limit=get_int("ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY", 3),
        window=timedelta(days=1),
    ) or rate_limit_exceeded(
        db,
        event_type="account_request_submitted",
        email=None,
        source_ip=source_ip,
        limit=get_int("ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR", 20),
        window=timedelta(hours=1),
    ):
        raise AccountRequestError(
            error_codes.RATE_LIMITED, "Tente novamente mais tarde."
        )

    existing_user = db.query(User.id).filter(User.email == canonical_email).first()
    existing_request = (
        db.query(AccountAccessRequest.id)
        .filter(
            AccountAccessRequest.email == canonical_email,
            AccountAccessRequest.status == ACCOUNT_REQUEST_PENDING,
        )
        .first()
    )
    created = False
    if existing_user is None and existing_request is None:
        try:
            with db.begin_nested():
                db.add(
                    AccountAccessRequest(
                        proposed_tenant_name=normalized_name,
                        email=canonical_email,
                        whatsapp=canonical_whatsapp,
                        message=normalized_message,
                        status=ACCOUNT_REQUEST_PENDING,
                    )
                )
                db.flush()
            created = True
        except IntegrityError:
            # A concurrent submission won the partial unique-index race. The
            # public response intentionally remains indistinguishable.
            created = False

    record_auth_event(
        db,
        event_type="account_request_submitted",
        user_id=existing_user[0] if existing_user is not None else None,
        email=canonical_email,
        source_ip=source_ip,
        metadata={"created": created},
    )


def get_account_request_page(
    db: Session,
    *,
    status: str,
    page: int,
    page_size: int,
) -> AccountRequestPage:
    """Return a deterministic, bounded admin request page."""
    if status not in ACCOUNT_REQUEST_STATUSES:
        raise AccountRequestError(
            error_codes.ACCOUNT_REQUEST_STATUS_INVALID,
            "Informe um status de solicitação válido.",
        )
    query = db.query(AccountAccessRequest).filter(
        AccountAccessRequest.status == status
    )
    total = query.count()
    total_pages = (total + page_size - 1) // page_size if total else 0
    rows = (
        query.order_by(
            AccountAccessRequest.submitted_at.desc(), AccountAccessRequest.id.desc()
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return AccountRequestPage(
        requests=build_account_request_items(db, rows),
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        status_counts=get_account_request_status_counts(db),
    )


def get_account_request_status_counts(db: Session) -> AccountRequestStatusCounts:
    """Count all request states without loading request PII."""
    counts = {
        status: count
        for status, count in db.query(
            AccountAccessRequest.status, func.count(AccountAccessRequest.id)
        )
        .group_by(AccountAccessRequest.status)
        .all()
    }
    return AccountRequestStatusCounts(
        pending=counts.get(ACCOUNT_REQUEST_PENDING, 0),
        approved=counts.get(ACCOUNT_REQUEST_APPROVED, 0),
        rejected=counts.get(ACCOUNT_REQUEST_REJECTED, 0),
    )


def build_account_request_items(
    db: Session, rows: list[AccountAccessRequest]
) -> list[AccountRequestAdminItem]:
    """Build admin items with reviewer and latest activation state in bulk."""
    reviewer_ids = {row.reviewed_by_user_id for row in rows if row.reviewed_by_user_id}
    owner_ids = {row.owner_user_id for row in rows if row.owner_user_id}
    reviewer_emails = {
        user_id: email
        for user_id, email in db.query(User.id, User.email)
        .filter(User.id.in_(reviewer_ids))
        .all()
    } if reviewer_ids else {}
    owners = {
        user.id: user
        for user in db.query(User).filter(User.id.in_(owner_ids)).all()
    } if owner_ids else {}
    latest_deliveries: dict[uuid.UUID, EmailDelivery] = {}
    if owner_ids:
        for delivery in (
            db.query(EmailDelivery)
            .filter(
                EmailDelivery.user_id.in_(owner_ids),
                EmailDelivery.purpose == "account_activation",
            )
            .order_by(EmailDelivery.created_at.desc(), EmailDelivery.id.desc())
            .all()
        ):
            latest_deliveries.setdefault(delivery.user_id, delivery)

    items: list[AccountRequestAdminItem] = []
    for row in rows:
        activation_state = None
        if row.status == ACCOUNT_REQUEST_APPROVED and row.owner_user_id is not None:
            owner = owners.get(row.owner_user_id)
            if owner is not None and owner.status == "active":
                activation_state = "account_activated"
            else:
                delivery = latest_deliveries.get(row.owner_user_id)
                activation_state = delivery.status if delivery else "not_queued"
        items.append(
            AccountRequestAdminItem(
                id=row.id,
                proposed_tenant_name=row.proposed_tenant_name,
                email=row.email,
                whatsapp=row.whatsapp,
                message=row.message,
                status=row.status,
                submitted_at=row.submitted_at,
                reviewed_at=row.reviewed_at,
                reviewer_email=reviewer_emails.get(row.reviewed_by_user_id),
                decision_reason=row.decision_reason,
                professional_id=row.professional_id,
                owner_user_id=row.owner_user_id,
                activation_state=activation_state,
            )
        )
    return items


def approve_account_request(
    db: Session,
    *,
    request_id: uuid.UUID,
    tenant_name: str,
    whatsapp: str,
    tenant_timezone: str,
    admin_user_id: uuid.UUID,
    source_ip: str | None,
    user_agent: str | None,
) -> tuple[AccountAccessRequest, CreatedTenant | None]:
    """Approve once and provision tenant, owner, and outbox atomically."""
    request_row = (
        db.query(AccountAccessRequest)
        .filter(AccountAccessRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if request_row is None:
        raise AccountRequestError(
            error_codes.ACCOUNT_REQUEST_NOT_FOUND, "Solicitação não encontrada."
        )
    if request_row.status == ACCOUNT_REQUEST_APPROVED:
        return request_row, None
    if request_row.status != ACCOUNT_REQUEST_PENDING:
        raise AccountRequestError(
            error_codes.ACCOUNT_REQUEST_ALREADY_DECIDED,
            "Esta solicitação já foi rejeitada.",
        )

    approval_limit = get_int("ACCOUNT_REQUEST_APPROVAL_MAX_PER_ADMIN_PER_HOUR", 20)
    if _admin_rate_limit_exceeded(
        db,
        event_type="account_request_approved",
        admin_user_id=admin_user_id,
        limit=approval_limit,
        window=timedelta(hours=1),
    ) or rate_limit_exceeded(
        db,
        event_type="account_request_approved",
        email=None,
        source_ip=source_ip,
        limit=approval_limit,
        window=timedelta(hours=1),
    ):
        raise AccountRequestError(
            error_codes.RATE_LIMITED, "Tente novamente mais tarde."
        )

    created = create_tenant_with_owner(
        db,
        name=tenant_name,
        owner_email=request_row.email,
        whatsapp=whatsapp,
        tenant_timezone=tenant_timezone,
        admin_user_id=admin_user_id,
        source_ip=source_ip,
        user_agent=user_agent,
        audit_source="account_request_approval",
        account_request_id=request_row.id,
    )
    request_row.status = ACCOUNT_REQUEST_APPROVED
    request_row.reviewed_at = datetime.now(timezone.utc)
    request_row.reviewed_by_user_id = admin_user_id
    request_row.professional_id = created.professional.id
    request_row.owner_user_id = created.owner.id
    record_auth_event(
        db,
        event_type="account_request_approved",
        user_id=admin_user_id,
        email=request_row.email,
        source_ip=source_ip,
        metadata={
            "account_request_id": str(request_row.id),
            "professional_id": str(created.professional.id),
        },
    )
    db.flush()
    return request_row, created


def reject_account_request(
    db: Session,
    *,
    request_id: uuid.UUID,
    reason: str | None,
    admin_user_id: uuid.UUID,
    source_ip: str | None,
) -> AccountAccessRequest:
    """Reject one pending request; repeated identical action is idempotent."""
    request_row = (
        db.query(AccountAccessRequest)
        .filter(AccountAccessRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if request_row is None:
        raise AccountRequestError(
            error_codes.ACCOUNT_REQUEST_NOT_FOUND, "Solicitação não encontrada."
        )
    if request_row.status == ACCOUNT_REQUEST_REJECTED:
        return request_row
    if request_row.status != ACCOUNT_REQUEST_PENDING:
        raise AccountRequestError(
            error_codes.ACCOUNT_REQUEST_ALREADY_DECIDED,
            "Esta solicitação já foi aprovada.",
        )
    request_row.status = ACCOUNT_REQUEST_REJECTED
    request_row.reviewed_at = datetime.now(timezone.utc)
    request_row.reviewed_by_user_id = admin_user_id
    request_row.decision_reason = reason.strip() if reason else None
    record_auth_event(
        db,
        event_type="account_request_rejected",
        user_id=admin_user_id,
        email=request_row.email,
        source_ip=source_ip,
        metadata={"account_request_id": str(request_row.id)},
    )
    db.flush()
    return request_row


def resend_account_activation(
    db: Session,
    *,
    request_id: uuid.UUID,
    admin_user_id: uuid.UUID,
    source_ip: str | None,
) -> EmailDelivery:
    """Queue a replacement activation delivery for an approved pending owner."""
    request_row = (
        db.query(AccountAccessRequest)
        .filter(AccountAccessRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if (
        request_row is None
        or request_row.status != ACCOUNT_REQUEST_APPROVED
        or request_row.owner_user_id is None
    ):
        raise AccountRequestError(
            error_codes.ACCOUNT_REQUEST_ACTIVATION_UNAVAILABLE,
            "A ativação não está disponível para esta solicitação.",
        )
    owner = db.get(User, request_row.owner_user_id, with_for_update=True)
    if owner is None or owner.status != "pending_activation":
        raise AccountRequestError(
            error_codes.ACCOUNT_REQUEST_ACTIVATION_UNAVAILABLE,
            "A ativação não está disponível para esta solicitação.",
        )
    latest = (
        db.query(EmailDelivery)
        .filter(
            EmailDelivery.user_id == owner.id,
            EmailDelivery.purpose == "account_activation",
        )
        .order_by(EmailDelivery.created_at.desc(), EmailDelivery.id.desc())
        .first()
    )
    if latest is not None and latest.status in PENDING_DELIVERY_STATUSES:
        return latest
    if latest is not None:
        cooldown = get_int("ACCOUNT_ACTIVATION_RESEND_COOLDOWN_SECONDS", 60)
        latest_time = latest.updated_at or latest.created_at
        if latest_time and latest_time > datetime.now(timezone.utc) - timedelta(seconds=cooldown):
            raise AccountRequestError(
                error_codes.RATE_LIMITED, "Aguarde antes de reenviar a ativação."
            )
    if rate_limit_exceeded(
        db,
        event_type="account_activation_resent",
        email=owner.email,
        source_ip=source_ip,
        limit=get_int("AUTH_EMAIL_MAX_SENDS_PER_HOUR", 5),
        window=timedelta(hours=1),
    ):
        raise AccountRequestError(
            error_codes.RATE_LIMITED, "Tente novamente mais tarde."
        )
    if _admin_rate_limit_exceeded(
        db,
        event_type="account_activation_resent",
        admin_user_id=admin_user_id,
        limit=get_int("AUTH_EMAIL_MAX_SENDS_PER_HOUR", 5),
        window=timedelta(hours=1),
    ):
        raise AccountRequestError(
            error_codes.RATE_LIMITED, "Tente novamente mais tarde."
        )
    delivery = enqueue_auth_email(db, user=owner, purpose="account_activation")
    record_auth_event(
        db,
        event_type="account_activation_resent",
        user_id=admin_user_id,
        email=owner.email,
        source_ip=source_ip,
        metadata={"account_request_id": str(request_row.id)},
    )
    db.flush()
    return delivery


def purge_rejected_account_requests(
    db: Session,
    *,
    now: datetime | None = None,
    retention_days: int | None = None,
) -> int:
    """Delete rejected request PII after the configured retention period."""
    current_time = now or datetime.now(timezone.utc)
    days = retention_days or get_int("ACCOUNT_REQUEST_REJECTED_RETENTION_DAYS", 180)
    cutoff = current_time - timedelta(days=days)
    return (
        db.query(AccountAccessRequest)
        .filter(
            AccountAccessRequest.status == ACCOUNT_REQUEST_REJECTED,
            AccountAccessRequest.reviewed_at < cutoff,
        )
        .delete(synchronize_session=False)
    )


def get_account_request_operational_metrics(db: Session) -> dict[str, int | float | None]:
    """Return aggregate onboarding metrics without PII labels."""
    counts = get_account_request_status_counts(db)
    oldest_pending = (
        db.query(func.min(AccountAccessRequest.submitted_at))
        .filter(AccountAccessRequest.status == ACCOUNT_REQUEST_PENDING)
        .scalar()
    )
    pending_over_24h = (
        db.query(func.count(AccountAccessRequest.id))
        .filter(
            AccountAccessRequest.status == ACCOUNT_REQUEST_PENDING,
            AccountAccessRequest.submitted_at < datetime.now(timezone.utc) - timedelta(hours=24),
        )
        .scalar()
        or 0
    )
    return {
        "pending": counts.pending,
        "approved": counts.approved,
        "rejected": counts.rejected,
        "oldest_pending_timestamp": oldest_pending.timestamp() if oldest_pending else None,
        "pending_over_24h": pending_over_24h,
    }

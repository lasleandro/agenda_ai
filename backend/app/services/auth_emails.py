"""Durable auth-email queueing and provider-neutral delivery processing."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.settings import frontend_base_url, get_int
from app.integrations.email.contracts import EmailPermanentError, EmailRetryableError
from app.integrations.email.smtp import SmtpEmailSender
from app.integrations.email.templates import (
    activation_email,
    password_changed_email,
    password_reset_email,
)
from app.models import EmailDelivery, User
from app.models.auth_action_token import ACCOUNT_ACTIVATION, PASSWORD_RESET
from app.services.auth_security import record_auth_event
from app.services.auth_tokens import issue_action_token

PENDING_DELIVERY_STATUSES = ("queued", "processing", "retry_wait")

logger = logging.getLogger(__name__)


def enqueue_auth_email(db: Session, *, user: User, purpose: str) -> EmailDelivery:
    """Queue one active delivery for a user/purpose without storing a raw token."""
    existing = (
        db.query(EmailDelivery)
        .filter(
            EmailDelivery.user_id == user.id,
            EmailDelivery.purpose == purpose,
            EmailDelivery.status.in_(PENDING_DELIVERY_STATUSES),
        )
        .first()
    )
    if existing is not None:
        return existing
    delivery = EmailDelivery(user_id=user.id, purpose=purpose, status="queued")
    db.add(delivery)
    db.flush()
    return delivery


def process_due_email_deliveries(
    db: Session,
    *,
    sender: SmtpEmailSender | None = None,
    now: datetime | None = None,
) -> int:
    """Claim and process due auth email deliveries with bounded retry."""
    current_time = now or datetime.now(timezone.utc)
    stale_before = current_time - timedelta(
        seconds=get_int("EMAIL_PROCESSING_TIMEOUT_SECONDS", 120)
    )
    stale_deliveries = (
        db.query(EmailDelivery)
        .filter(
            EmailDelivery.status == "processing",
            EmailDelivery.updated_at <= stale_before,
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    for delivery in stale_deliveries:
        delivery.status = "retry_wait"
        delivery.next_attempt_at = current_time
        delivery.last_error_code = "worker_recovery"
    if stale_deliveries:
        db.commit()

    deliveries = (
        db.query(EmailDelivery)
        .filter(
            EmailDelivery.status.in_(("queued", "retry_wait")),
            (EmailDelivery.next_attempt_at.is_(None))
            | (EmailDelivery.next_attempt_at <= current_time),
        )
        .order_by(EmailDelivery.created_at)
        .with_for_update(skip_locked=True)
        .limit(20)
        .all()
    )
    if not deliveries:
        return 0
    for delivery in deliveries:
        delivery.status = "processing"
        delivery.attempt_count += 1
        delivery.next_attempt_at = None
    db.commit()

    active_sender = sender or SmtpEmailSender()
    for delivery in deliveries:
        _deliver_one(db, delivery.id, active_sender, current_time)
    return len(deliveries)


def _deliver_one(
    db: Session,
    delivery_id: uuid.UUID,
    sender: SmtpEmailSender,
    now: datetime,
) -> None:
    delivery = db.get(EmailDelivery, delivery_id)
    if delivery is None or delivery.status != "processing":
        return
    user = db.get(User, delivery.user_id)
    if user is None:
        logger.warning(
            "email delivery %s (purpose=%s): user not found", delivery.id, delivery.purpose
        )
        _mark_failed(delivery, "user_not_found", now)
        db.commit()
        return
    if not sender.enabled:
        logger.warning(
            "email delivery %s (purpose=%s): suppressed, EMAIL_ENABLED is false",
            delivery.id,
            delivery.purpose,
        )
        delivery.status = "suppressed"
        delivery.last_error_code = "email_disabled"
        delivery.last_error_detail = None
        db.commit()
        return

    try:
        message = _render_message(db, delivery, user)
        sender.send(message)
    except EmailPermanentError as exc:
        logger.error(
            "email delivery %s (purpose=%s): permanent failure (%s)",
            delivery.id,
            delivery.purpose,
            type(exc).__name__,
        )
        _mark_failed(delivery, "smtp_permanent", now, type(exc).__name__)
    except EmailRetryableError as exc:
        logger.warning(
            "email delivery %s (purpose=%s): retryable failure on attempt %s (%s)",
            delivery.id,
            delivery.purpose,
            delivery.attempt_count,
            type(exc).__name__,
        )
        _mark_retry_or_failed(delivery, "smtp_retryable", now, type(exc).__name__)
    except Exception as exc:
        logger.exception(
            "email delivery %s (purpose=%s): unexpected error", delivery.id, delivery.purpose
        )
        _mark_retry_or_failed(delivery, "unexpected", now, type(exc).__name__)
    else:
        logger.info("email delivery %s (purpose=%s): sent", delivery.id, delivery.purpose)
        delivery.status = "sent"
        delivery.sent_at = now
        delivery.last_error_code = None
        delivery.last_error_detail = None
        record_auth_event(
            db,
            event_type=f"email_{delivery.purpose}_sent",
            user_id=user.id,
            email=user.email,
        )
    db.commit()


def _render_message(db: Session, delivery: EmailDelivery, user: User):
    if delivery.purpose == "password_changed_notice":
        return password_changed_email(user.email)

    if delivery.purpose == ACCOUNT_ACTIVATION:
        raw_token = issue_action_token(db, user=user, purpose=ACCOUNT_ACTIVATION)
        return activation_email(
            user.email,
            _action_url("/activate", raw_token),
            get_int("AUTH_ACTIVATION_TOKEN_TTL_MINUTES", 60),
        )
    if delivery.purpose == PASSWORD_RESET:
        raw_token = issue_action_token(db, user=user, purpose=PASSWORD_RESET)
        return password_reset_email(
            user.email,
            _action_url("/reset-password", raw_token),
            get_int("AUTH_RESET_TOKEN_TTL_MINUTES", 30),
        )
    raise EmailPermanentError("unsupported_delivery_purpose")


def _action_url(path: str, raw_token: str) -> str:
    return f"{frontend_base_url()}{path}?token={raw_token}"


def _mark_failed(
    delivery: EmailDelivery,
    code: str,
    now: datetime,
    detail: str | None = None,
) -> None:
    delivery.status = "failed"
    delivery.last_error_code = code
    delivery.last_error_detail = detail
    delivery.next_attempt_at = None


def _mark_retry_or_failed(
    delivery: EmailDelivery,
    code: str,
    now: datetime,
    detail: str | None = None,
) -> None:
    max_attempts = get_int("EMAIL_MAX_ATTEMPTS", 3)
    if delivery.attempt_count >= max_attempts:
        _mark_failed(delivery, code, now, detail)
        return
    delivery.status = "retry_wait"
    delivery.last_error_code = code
    delivery.last_error_detail = detail
    delay = get_int("EMAIL_RETRY_BASE_SECONDS", 60) * (2 ** (delivery.attempt_count - 1))
    delivery.next_attempt_at = now + timedelta(seconds=delay)

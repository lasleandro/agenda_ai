"""Secure issuance and atomic consumption of account action tokens."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.settings import get_int
from app.models import AuthActionToken, User
from app.models.auth_action_token import ACCOUNT_ACTIVATION, PASSWORD_RESET
from app.services.auth_security import record_auth_event
from app.services.password_policy import hash_password, validate_password


class ActionTokenError(ValueError):
    """Raised when a token cannot authorize its requested action."""


def _digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _expiry_minutes(purpose: str) -> int:
    if purpose == ACCOUNT_ACTIVATION:
        return get_int("AUTH_ACTIVATION_TOKEN_TTL_MINUTES", 60)
    if purpose == PASSWORD_RESET:
        return get_int("AUTH_RESET_TOKEN_TTL_MINUTES", 30)
    raise ValueError("Unsupported token purpose")


def issue_action_token(db: Session, *, user: User, purpose: str) -> str:
    """Invalidate prior active tokens and return a new raw token for email only."""
    now = datetime.now(timezone.utc)
    (
        db.query(AuthActionToken)
        .filter(
            AuthActionToken.user_id == user.id,
            AuthActionToken.purpose == purpose,
            AuthActionToken.consumed_at.is_(None),
        )
        .update({AuthActionToken.consumed_at: now}, synchronize_session=False)
    )
    raw_token = secrets.token_urlsafe(32)
    db.add(
        AuthActionToken(
            user_id=user.id,
            purpose=purpose,
            token_digest=_digest(raw_token),
            expires_at=now + timedelta(minutes=_expiry_minutes(purpose)),
        )
    )
    db.flush()
    return raw_token


def consume_action_token(
    db: Session,
    *,
    purpose: str,
    raw_token: str,
    password: str,
    source_ip: str | None,
) -> User:
    """Atomically validate a token and apply its password-bearing action."""
    token = (
        db.query(AuthActionToken)
        .filter(AuthActionToken.token_digest == _digest(raw_token))
        .with_for_update()
        .first()
    )
    now = datetime.now(timezone.utc)
    if (
        token is None
        or token.purpose != purpose
        or token.consumed_at is not None
        or token.expires_at <= now
    ):
        raise ActionTokenError("Invalid or expired token")

    user = db.get(User, token.user_id, with_for_update=True)
    if user is None:
        raise ActionTokenError("Invalid or expired token")
    if purpose == ACCOUNT_ACTIVATION and user.status != "pending_activation":
        raise ActionTokenError("Invalid or expired token")
    if purpose == PASSWORD_RESET and user.status != "active":
        raise ActionTokenError("Invalid or expired token")

    normalized_password = validate_password(password, email=user.email)
    user.hashed_password = hash_password(normalized_password)
    user.password_changed_at = now
    user.auth_version += 1
    if purpose == ACCOUNT_ACTIVATION:
        user.status = "active"
        user.email_verified_at = now
        event_type = "account_activated"
    else:
        event_type = "password_reset_completed"

    token.consumed_at = now
    record_auth_event(
        db,
        event_type=event_type,
        user_id=user.id,
        email=user.email,
        source_ip=source_ip,
    )
    db.flush()
    return user

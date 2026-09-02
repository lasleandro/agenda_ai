"""Auth audit events and durable, database-backed rate limits."""

import hashlib
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AuthSecurityEvent


def digest_identifier(value: str | None) -> str | None:
    """Hash an email or IP with an environment secret before persistence."""
    if not value:
        return None
    secret = os.getenv("AUTH_AUDIT_SECRET") or os.getenv("JWT_SECRET_KEY", "development")
    return hashlib.sha256(f"{secret}:{value.strip().lower()}".encode("utf-8")).hexdigest()


def record_auth_event(
    db: Session,
    *,
    event_type: str,
    user_id=None,
    email: str | None = None,
    source_ip: str | None = None,
    metadata: dict | None = None,
) -> AuthSecurityEvent:
    """Append an event without storing credentials or a raw mailbox address."""
    event = AuthSecurityEvent(
        user_id=user_id,
        event_type=event_type,
        email_digest=digest_identifier(email),
        ip_digest=digest_identifier(source_ip),
        metadata_json=metadata,
    )
    db.add(event)
    return event


def rate_limit_exceeded(
    db: Session,
    *,
    event_type: str,
    email: str | None,
    source_ip: str | None,
    limit: int,
    window: timedelta,
) -> bool:
    """Check account and source-IP buckets independently."""
    since = datetime.now(timezone.utc) - window
    email_digest = digest_identifier(email)
    ip_digest = digest_identifier(source_ip)
    email_count = 0
    ip_count = 0
    if email_digest:
        email_count = (
            db.query(func.count(AuthSecurityEvent.id))
            .filter(
                AuthSecurityEvent.event_type == event_type,
                AuthSecurityEvent.email_digest == email_digest,
                AuthSecurityEvent.created_at >= since,
            )
            .scalar()
            or 0
        )
    if ip_digest:
        ip_count = (
            db.query(func.count(AuthSecurityEvent.id))
            .filter(
                AuthSecurityEvent.event_type == event_type,
                AuthSecurityEvent.ip_digest == ip_digest,
                AuthSecurityEvent.created_at >= since,
            )
            .scalar()
            or 0
        )
    return email_count >= limit or ip_count >= limit

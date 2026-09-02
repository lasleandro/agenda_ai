"""Durable, token-free queue records for authentication email delivery."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

EMAIL_DELIVERY_PURPOSES = (
    "account_activation",
    "password_reset",
    "password_changed_notice",
)


class EmailDelivery(Base):
    """A retryable auth email request with no rendered message at rest."""

    __tablename__ = "email_deliveries"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('account_activation', 'password_reset', 'password_changed_notice')",
            name="ck_email_deliveries_purpose",
        ),
        CheckConstraint(
            "status IN ('queued', 'processing', 'retry_wait', 'sent', 'failed', 'suppressed')",
            name="ck_email_deliveries_status",
        ),
        Index("ix_email_deliveries_status_next_attempt", "status", "next_attempt_at"),
        Index(
            "uq_email_deliveries_active_user_purpose",
            "user_id",
            "purpose",
            unique=True,
            postgresql_where=text("status IN ('queued', 'processing', 'retry_wait')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_detail: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

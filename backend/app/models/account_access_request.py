"""Persisted public account requests awaiting a platform-admin decision."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

ACCOUNT_REQUEST_PENDING = "pending"
ACCOUNT_REQUEST_APPROVED = "approved"
ACCOUNT_REQUEST_REJECTED = "rejected"
ACCOUNT_REQUEST_STATUSES = (
    ACCOUNT_REQUEST_PENDING,
    ACCOUNT_REQUEST_APPROVED,
    ACCOUNT_REQUEST_REJECTED,
)


class AccountAccessRequest(Base):
    """A pre-account business record, separate from users and tenants."""

    __tablename__ = "account_access_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_account_access_requests_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND reviewed_at IS NULL "
            "AND reviewed_by_user_id IS NULL AND professional_id IS NULL "
            "AND owner_user_id IS NULL) OR "
            "(status = 'approved' AND reviewed_at IS NOT NULL "
            "AND reviewed_by_user_id IS NOT NULL AND professional_id IS NOT NULL "
            "AND owner_user_id IS NOT NULL) OR "
            "(status = 'rejected' AND reviewed_at IS NOT NULL "
            "AND reviewed_by_user_id IS NOT NULL AND professional_id IS NULL "
            "AND owner_user_id IS NULL)",
            name="ck_account_access_requests_state",
        ),
        Index(
            "uq_account_access_requests_pending_email",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_account_access_requests_status_submitted",
            "status",
            "submitted_at",
            "id",
        ),
        Index("ix_account_access_requests_professional", "professional_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    proposed_tenant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Canonical E.164 WhatsApp number for the operation. Nullable at the column
    # level so rows created before this field remain valid; the public API
    # requires it for every new submission.
    whatsapp: Mapped[str | None] = mapped_column(String(20))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ACCOUNT_REQUEST_PENDING
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    decision_reason: Mapped[str | None] = mapped_column(String(500))
    professional_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id", ondelete="RESTRICT")
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


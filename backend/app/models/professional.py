"""
Professional model (Section 10.1).

Represents the instructor / service provider — the tenant root.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Tenant lifecycle states (tenant suspend & archive roadmap v0.1).
#   active   — normal operation.
#   suspended — reversible full lockout (login, ingestion, tasks blocked).
#   archived  — reversible soft delete; hidden from the default admin grid.
TENANT_STATUS_ACTIVE = "active"
TENANT_STATUS_SUSPENDED = "suspended"
TENANT_STATUS_ARCHIVED = "archived"
TENANT_STATUSES = (
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_SUSPENDED,
    TENANT_STATUS_ARCHIVED,
)


class Professional(Base):
    __tablename__ = "professionals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'archived')",
            name="ck_professionals_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), default="America/Sao_Paulo")
    default_service: Mapped[str] = mapped_column(String(100), default="tennis_lesson")
    default_duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    # Customer-facing WhatsApp number the passive observer watches. Also the
    # key the instructor-facing agent channel resolves the tenant by: a
    # message to the shared platform agent number is attributed to the tenant
    # whose assistant_phone sent it.
    assistant_phone: Mapped[str | None] = mapped_column(String(50))
    # Second factor for the shared agent channel (Shared Platform AI Agent
    # Number Roadmap v0.1, Phase F). Set when the instructor confirms a
    # binding challenge code from their own number; cleared on revoke or a
    # number change. Normal agent-channel handling is gated on this being set.
    agent_binding_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    agent_binding_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    daily_summary_time: Mapped[str] = mapped_column(String(5), default="07:00")
    status: Mapped[str] = mapped_column(String(50), default=TENANT_STATUS_ACTIVE)
    # Lifecycle audit stamped on the row itself so the common "why is this
    # tenant off?" question does not require an event-ledger join.
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

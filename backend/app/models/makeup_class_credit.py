"""MakeupClassCredit ("reposição") ledger — tracks credits a student earns
when a recurring class is cancelled with sufficient notice.

Mirrors the OperatorActionCandidate status-column + audit-trail pattern.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

CREDIT_STATUSES = ("available", "redeemed", "expired", "forfeited")


class MakeupClassCredit(Base):
    __tablename__ = "makeup_class_credits"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in CREDIT_STATUSES)})",
            name="ck_makeup_class_credits_status",
        ),
        UniqueConstraint(
            "contact_id",
            "origin_event_id",
            name="uq_makeup_class_credits_contact_event",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("professionals.id"),
        nullable=False,
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id"),
        nullable=False,
    )
    origin_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("operational_events.id"),
        nullable=False,
    )
    origin_recurring_slot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recurring_slots.id"),
        nullable=False,
    )
    origin_occurrence_date: Mapped[date] = mapped_column(
        Date, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="available"
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    redeemed_appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    operational_event: Mapped["OperationalEvent"] = relationship(
        "OperationalEvent", foreign_keys=[origin_event_id]
    )

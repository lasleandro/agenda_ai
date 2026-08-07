"""Participant-level attendance and pricing snapshot for recognized revenue."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RevenueOccurrenceParticipant(Base):
    __tablename__ = "revenue_occurrence_participants"
    __table_args__ = (
        UniqueConstraint(
            "occurrence_id",
            "contact_id",
            name="uq_revenue_occurrence_participant_contact",
        ),
        CheckConstraint(
            "attendance_status IN ('attended', 'no_show', 'cancelled')",
            name="ck_revenue_occurrence_participants_attendance",
        ),
        CheckConstraint(
            "quoted_amount_cents BETWEEN 0 AND 10000000000",
            name="ck_revenue_occurrence_participants_quoted",
        ),
        CheckConstraint(
            "billed_amount_cents BETWEEN 0 AND 10000000000",
            name="ck_revenue_occurrence_participants_billed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("revenue_occurrences.id"),
        nullable=False,
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    contact_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    attendance_status: Mapped[str] = mapped_column(String(20), nullable=False)
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quoted_amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    billed_amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

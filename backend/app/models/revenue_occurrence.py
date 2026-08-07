"""Immutable recognized-revenue occurrence header."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RevenueOccurrence(Base):
    __tablename__ = "revenue_occurrences"
    __table_args__ = (
        UniqueConstraint(
            "professional_id",
            "source_type",
            "source_id",
            "occurrence_date",
            name="uq_revenue_occurrences_source_date",
        ),
        CheckConstraint(
            "source_type IN ('appointment', 'recurring_slot')",
            name="ck_revenue_occurrences_source_type",
        ),
        CheckConstraint(
            "outcome_status IN ('attended', 'no_show', 'cancelled', 'mixed')",
            name="ck_revenue_occurrences_outcome_status",
        ),
        CheckConstraint(
            "quoted_total_cents BETWEEN 0 AND 10000000000",
            name="ck_revenue_occurrences_quoted_total",
        ),
        CheckConstraint(
            "subtotal_cents BETWEEN 0 AND 10000000000",
            name="ck_revenue_occurrences_subtotal",
        ),
        CheckConstraint(
            "adjustment_cents BETWEEN -100000000 AND 100000000",
            name="ck_revenue_occurrences_adjustment",
        ),
        CheckConstraint(
            "total_cents BETWEEN -100000000 AND 10100000000",
            name="ck_revenue_occurrences_total",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    source_label_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    place_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    place_name_snapshot: Mapped[str | None] = mapped_column(String(255))
    outcome_status: Mapped[str] = mapped_column(String(20), nullable=False)
    participant_count: Mapped[int] = mapped_column(Integer, nullable=False)
    billable_participant_count: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    quoted_total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    subtotal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    adjustment_cents: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000))
    confirmed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

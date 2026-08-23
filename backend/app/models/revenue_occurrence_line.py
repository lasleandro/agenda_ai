"""Segment-level immutable pricing rule snapshot."""

import uuid
from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RevenueOccurrenceLine(Base):
    __tablename__ = "revenue_occurrence_lines"
    __table_args__ = (
        CheckConstraint(
            "time_category IN ('regular', 'prime')",
            name="ck_revenue_occurrence_lines_category",
        ),
        CheckConstraint(
            "rate_source IN ('customer', 'group', 'place', 'default', 'tenant', 'unset')",
            name="ck_revenue_occurrence_lines_source",
        ),
        CheckConstraint(
            "duration_minutes > 0 AND duration_minutes <= 1440",
            name="ck_revenue_occurrence_lines_duration",
        ),
        CheckConstraint(
            "hourly_rate_cents IS NULL OR "
            "hourly_rate_cents BETWEEN 0 AND 100000000",
            name="ck_revenue_occurrence_lines_rate",
        ),
        CheckConstraint(
            "quoted_amount_cents BETWEEN 0 AND 10000000000",
            name="ck_revenue_occurrence_lines_quoted",
        ),
        CheckConstraint(
            "billed_amount_cents BETWEEN 0 AND 10000000000",
            name="ck_revenue_occurrence_lines_billed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    participant_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("revenue_occurrence_participants.id"),
        nullable=False,
    )
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    time_category: Mapped[str] = mapped_column(String(20), nullable=False)
    hourly_rate_cents: Mapped[int | None] = mapped_column(Integer)
    rate_source: Mapped[str] = mapped_column(String(20), nullable=False)
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quoted_amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    billed_amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pricing_context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

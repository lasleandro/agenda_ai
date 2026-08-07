"""Sparse regular/prime per-participant hourly-rate overrides by place."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlaceFinancialRate(Base):
    __tablename__ = "place_financial_rates"
    __table_args__ = (
        UniqueConstraint(
            "professional_id",
            "place_id",
            "time_category",
            "participant_count",
            name="uq_place_financial_rates_rule",
        ),
        CheckConstraint(
            "time_category IN ('regular', 'prime')",
            name="ck_place_financial_rates_time_category",
        ),
        CheckConstraint(
            "participant_count BETWEEN 1 AND 4",
            name="ck_place_financial_rates_participant_count",
        ),
        CheckConstraint(
            "hourly_rate_cents BETWEEN 0 AND 100000000",
            name="ck_place_financial_rates_hourly_rate_cents",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    place_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("places.id"), nullable=False
    )
    time_category: Mapped[str] = mapped_column(String(20), nullable=False)
    participant_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    hourly_rate_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

"""Current tenant-global per-participant hourly rates by class size."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FinancialRate(Base):
    __tablename__ = "financial_rates"
    __table_args__ = (
        UniqueConstraint(
            "professional_id",
            "participant_count",
            name="uq_financial_rates_professional_participant_count",
        ),
        CheckConstraint(
            "participant_count BETWEEN 1 AND 4",
            name="ck_financial_rates_participant_count",
        ),
        CheckConstraint(
            "hourly_rate_cents BETWEEN 0 AND 100000000",
            name="ck_financial_rates_hourly_rate_cents",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    participant_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    hourly_rate_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

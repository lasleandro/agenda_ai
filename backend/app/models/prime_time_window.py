"""Tenant-defined weekly prime-time ranges."""

import uuid
from datetime import datetime, time

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Time, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PrimeTimeWindow(Base):
    __tablename__ = "prime_time_windows"
    __table_args__ = (
        CheckConstraint(
            "end_time > start_time",
            name="ck_prime_time_windows_time_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    days_of_week: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

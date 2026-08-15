"""Tenant defaults for the optional commercial and financial module."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProfessionalFinancialSettings(Base):
    __tablename__ = "professional_financial_settings"
    __table_args__ = (
        CheckConstraint(
            "default_commercial_status IN ('active', 'waiting', 'paused')",
            name="ck_professional_financial_settings_status",
        ),
        CheckConstraint(
            "cancellation_notice_hours >= 0 AND cancellation_notice_hours <= 168",
            name="ck_professional_financial_settings_notice_hours",
        ),
    )

    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("professionals.id"),
        primary_key=True,
    )
    default_commercial_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    prime_time_configured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    cancellation_notice_hours: Mapped[int] = mapped_column(
        default=24, nullable=False
    )
    generic_place_rates: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

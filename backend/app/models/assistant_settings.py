"""Per-tenant instructor-agent tuning knobs, set by a platform admin."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AssistantSettings(Base):
    __tablename__ = "assistant_settings"
    __table_args__ = (
        CheckConstraint(
            "temperature >= 0.0 AND temperature <= 2.0",
            name="ck_assistant_settings_temperature_range",
        ),
        CheckConstraint(
            "memory_window_messages >= 2 AND memory_window_messages <= 200",
            name="ck_assistant_settings_memory_window_range",
        ),
    )

    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), primary_key=True
    )
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    memory_window_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

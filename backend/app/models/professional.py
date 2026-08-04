"""
Professional model (Section 10.1).

Represents the instructor / service provider.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Professional(Base):
    __tablename__ = "professionals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), default="America/Sao_Paulo")
    default_service: Mapped[str] = mapped_column(String(100), default="tennis_lesson")
    default_duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    assistant_phone: Mapped[str | None] = mapped_column(String(50))
    daily_summary_time: Mapped[str] = mapped_column(String(5), default="07:00")
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

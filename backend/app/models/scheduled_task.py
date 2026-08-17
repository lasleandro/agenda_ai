"""Tenant-scoped configuration for a platform-managed scheduled task."""

import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

DAILY_AGENDA_SUMMARY = "daily_agenda_summary"


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        CheckConstraint(
            "task_type IN ('daily_agenda_summary')", name="ck_scheduled_tasks_type"
        ),
        CheckConstraint("channel IN ('whatsapp')", name="ck_scheduled_tasks_channel"),
        UniqueConstraint(
            "professional_id", "task_type", name="uq_scheduled_tasks_professional_type"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False, default="whatsapp")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    local_time: Mapped[time] = mapped_column(Time(), nullable=False, default=time(7, 0))
    consent_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

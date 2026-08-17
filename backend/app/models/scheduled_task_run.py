"""Durable, tenant-scoped execution and delivery state for scheduled tasks."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

RUN_STATUSES = (
    "queued",
    "processing",
    "retry_wait",
    "provider_accepted",
    "sent",
    "delivered",
    "read",
    "delivery_unknown",
    "failed",
    "skipped",
)


class ScheduledTaskRun(Base):
    __tablename__ = "scheduled_task_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{status}'" for status in RUN_STATUSES) + ")",
            name="ck_scheduled_task_runs_status",
        ),
        UniqueConstraint(
            "scheduled_task_id", "target_local_date", name="uq_scheduled_task_runs_task_date"
        ),
        Index("ix_scheduled_task_runs_status_next_attempt", "status", "next_attempt_at"),
        Index("ix_scheduled_task_runs_professional_created", "professional_id", "created_at"),
        Index("ix_scheduled_task_runs_provider_message", "provider_key", "provider_message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    scheduled_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scheduled_tasks.id"), nullable=False
    )
    target_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_for_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_key: Mapped[str | None] = mapped_column(String(50))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    provider_external_id: Mapped[str | None] = mapped_column(String(255))
    agenda_item_count: Mapped[int | None] = mapped_column(Integer)
    class_count: Mapped[int | None] = mapped_column(Integer)
    event_count: Mapped[int | None] = mapped_column(Integer)
    rendered_body: Mapped[str | None] = mapped_column(Text)
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_detail: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

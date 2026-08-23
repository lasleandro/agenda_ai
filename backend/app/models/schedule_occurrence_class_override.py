"""Format/capacity exception for one dated class occurrence."""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ScheduleOccurrenceClassOverride(Base):
    __tablename__ = "schedule_occurrence_class_overrides"
    __table_args__ = (
        CheckConstraint(
            "(appointment_id IS NOT NULL) != (recurring_slot_id IS NOT NULL)",
            name="ck_schedule_occurrence_class_overrides_one_parent",
        ),
        CheckConstraint(
            "class_type IN ('individual', 'group')",
            name="ck_schedule_occurrence_class_overrides_type",
        ),
        CheckConstraint(
            "max_participants BETWEEN 1 AND 4",
            name="ck_schedule_occurrence_class_overrides_capacity",
        ),
        CheckConstraint(
            "class_type = 'group' OR max_participants = 1",
            name="ck_schedule_occurrence_class_overrides_individual_capacity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True
    )
    recurring_slot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recurring_slots.id"), nullable=True
    )
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)
    class_type: Mapped[str] = mapped_column(String(20), nullable=False)
    max_participants: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    source: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    professional: Mapped["Professional"] = relationship("Professional")
    appointment: Mapped["Appointment | None"] = relationship("Appointment")
    recurring_slot: Mapped["RecurringSlot | None"] = relationship("RecurringSlot")
    actor_user: Mapped["User | None"] = relationship("User")

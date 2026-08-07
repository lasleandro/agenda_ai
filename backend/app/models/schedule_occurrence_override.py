"""
ScheduleOccurrenceOverride model (operational ontology roadmap v0.2, Phase 1)
— a dated exception to one occurrence of a recurring or one-off calendar
entry: cancelling it, or moving it to a different time/place.

Exactly one of `appointment_id`/`recurring_slot_id` identifies the parent
record; `occurrence_date` identifies *which* occurrence of that parent this
override applies to (the parent's own, unmodified schedule — not the
replacement date). `replacement_start_at`/`replacement_end_at`/
`replacement_place_id` are populated only when `override_type == "rescheduled"`.

There is at most one override per `(parent, occurrence_date)` — enforced by
two partial unique indexes in the migration (one per parent column, since a
plain UniqueConstraint can't express "unique among rows where column X is
not null").
"""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

OVERRIDE_TYPES = ("cancelled", "rescheduled")


class ScheduleOccurrenceOverride(Base):
    __tablename__ = "schedule_occurrence_overrides"
    __table_args__ = (
        CheckConstraint(
            "(appointment_id IS NOT NULL) != (recurring_slot_id IS NOT NULL)",
            name="ck_schedule_occurrence_overrides_one_parent",
        ),
        CheckConstraint(
            "override_type IN ('cancelled', 'rescheduled')",
            name="ck_schedule_occurrence_overrides_type",
        ),
        CheckConstraint(
            "override_type = 'rescheduled' OR "
            "(replacement_start_at IS NULL AND replacement_end_at IS NULL "
            "AND replacement_place_id IS NULL)",
            name="ck_schedule_occurrence_overrides_replacement_gated",
        ),
        CheckConstraint(
            "override_type != 'rescheduled' OR "
            "(replacement_start_at IS NOT NULL AND replacement_end_at IS NOT NULL "
            "AND replacement_end_at > replacement_start_at)",
            name="ck_schedule_occurrence_overrides_replacement_range",
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
    override_type: Mapped[str] = mapped_column(String(20), nullable=False)
    replacement_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    replacement_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    replacement_place_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("places.id"), nullable=True
    )
    reason_code: Mapped[str | None] = mapped_column(String(50))
    note: Mapped[str | None] = mapped_column(String(500))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
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
    replacement_place: Mapped["Place | None"] = relationship("Place")
    actor_user: Mapped["User | None"] = relationship("User")

"""InstructorEvent model (instructor events roadmap v0.1, Phase 1).

A non-class calendar occupant: the instructor refereeing a tournament,
running a workshop or clinic — paid work with no client involved, so it
doesn't fit Appointment (contact_id is NOT NULL there) or the
participant-priced revenue engine. Named InstructorEvent, not Event, to
avoid confusion with OperationalEvent (the audit ledger).

No recurrence, no participants — a one-off block of time with an optional
flat fee (`income_cents`). Occupies the instructor's calendar (see
app/services/appointments.py's overlap checks, extended to include this
table) but is deliberately exempt from work-journey enforcement — a
Saturday tournament is by definition outside normal teaching hours.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Plain string, not a DB enum, so new types can be added later without a
# migration — same "modular" convention as Contact.level/RecurringSlot.class_type.
EVENT_TYPES = ("tournament_referee", "workshop", "clinic", "other")
INSTRUCTOR_EVENT_STATUSES = ("confirmed", "cancelled")


class InstructorEvent(Base):
    __tablename__ = "instructor_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('confirmed', 'cancelled')",
            name="ck_instructor_events_status",
        ),
        CheckConstraint(
            "end_at > start_at",
            name="ck_instructor_events_time_range",
        ),
        CheckConstraint(
            "income_cents IS NULL OR income_cents BETWEEN 0 AND 100000000",
            name="ck_instructor_events_income_cents",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    place_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("places.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    income_cents: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="confirmed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    professional: Mapped["Professional"] = relationship("Professional")
    place: Mapped["Place | None"] = relationship("Place")

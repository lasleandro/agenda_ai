"""WaitlistEntry ("Fila de Espera") model — waitlist roadmap v0.1, Phase 1.

A contact wants a slot at a specific date/time and none exists yet. Kept as
a standalone table (not a field on Contact) since one contact can have more
than one live request, each with its own lifecycle — mirrors the
OperatorActionCandidate/MakeupClassCredit status-column pattern rather than
overloading an existing table's status field.

Not to be confused with Contact.commercial_status == "waiting" ("Em
espera"), which is an unrelated paused-billing-relationship status from the
commercial/financial module.
"""

import uuid
from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

WAITLIST_ENTRY_STATUSES = ("open", "matched", "fulfilled", "cancelled", "expired")


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in WAITLIST_ENTRY_STATUSES)})",
            name="ck_waitlist_entries_status",
        ),
        CheckConstraint(
            "class_type IS NULL OR class_type IN ('individual', 'group')",
            name="ck_waitlist_entries_class_type",
        ),
        CheckConstraint(
            "desired_end_time > desired_start_time",
            name="ck_waitlist_entries_time_range",
        ),
        CheckConstraint(
            "(fulfilled_recurring_slot_id IS NULL) = (fulfilled_occurrence_date IS NULL)",
            name="ck_waitlist_entries_recurring_fulfillment_pair",
        ),
        CheckConstraint(
            "fulfilled_appointment_id IS NULL OR fulfilled_recurring_slot_id IS NULL",
            name="ck_waitlist_entries_one_fulfillment_target",
        ),
        CheckConstraint(
            "fulfillment_scope IS NULL OR fulfillment_scope IN ('occurrence', 'series')",
            name="ck_waitlist_entries_fulfillment_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=False
    )
    place_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("places.id"), nullable=True
    )
    desired_date: Mapped[date] = mapped_column(Date, nullable=False)
    desired_start_time: Mapped[time] = mapped_column(Time, nullable=False)
    desired_end_time: Mapped[time] = mapped_column(Time, nullable=False)
    class_type: Mapped[str | None] = mapped_column(String(50))
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    note: Mapped[str | None] = mapped_column(String(500))
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fulfilled_appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True
    )
    fulfilled_recurring_slot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recurring_slots.id"), nullable=True
    )
    fulfilled_occurrence_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fulfillment_scope: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    professional: Mapped["Professional"] = relationship("Professional")
    contact: Mapped["Contact"] = relationship("Contact")
    place: Mapped["Place | None"] = relationship("Place")

"""
Appointment model (Section 10.6).

The operational calendar record — the "source of truth" for the instructor's
schedule.

contact_id stays the required "primary" participant (kept for backward
compatibility with every existing reader); AppointmentParticipant holds any
additional people added to what started as a one-off appointment. class_type
mirrors the individual/group axis and changes to "group" once a second
participant is added, returning to "individual" when only the primary
participant remains (see app/services/appointment_participants.py). This is
independent from the immutable RecurringSlot.slot_kind boundary.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Mirrors RecurringSlot.CLASS_TYPES (customer ontology roadmap Phase 2) —
# same closed vocabulary, kept as a local literal per this codebase's
# per-model vocabulary convention (see EVENT_TYPES, SLOT_KINDS elsewhere).
CLASS_TYPES = ("individual", "group")
BILLING_TYPES = ("billable", "courtesy")


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint(
            "class_type IN ('individual', 'group')",
            name="ck_appointments_class_type",
        ),
        CheckConstraint(
            "max_participants BETWEEN 1 AND 4",
            name="ck_appointments_max_participants",
        ),
        CheckConstraint(
            "billing_type IN ('billable', 'courtesy')",
            name="ck_appointments_billing_type",
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
    service: Mapped[str] = mapped_column(String(100), nullable=False)
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    timezone: Mapped[str] = mapped_column(String(100), default="America/Sao_Paulo")
    class_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="individual"
    )
    max_participants: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    billing_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="billable"
    )
    status: Mapped[str] = mapped_column(String(50), default="tentative")
    source: Mapped[str] = mapped_column(String(50), default="ai_detected")
    recurrence_rule: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    professional: Mapped["Professional"] = relationship("Professional")
    contact: Mapped["Contact"] = relationship("Contact")
    place: Mapped["Place | None"] = relationship("Place")

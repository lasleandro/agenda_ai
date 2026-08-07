"""
Appointment model (Section 10.6).

The operational calendar record — the "source of truth" for the instructor's
schedule.

contact_id stays the required "primary" participant (kept for backward
compatibility with every existing reader); AppointmentParticipant holds any
additional people added to what started as a one-off appointment. class_type
mirrors RecurringSlot's individual/group axis and auto-flips the same way
RecurringSlot.slot_kind auto-promotes on first participant: "group" once a
second participant is added, back to "individual" if it drops to just the
primary again (see app/services/appointment_participants.py).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Mirrors RecurringSlot.CLASS_TYPES (customer ontology roadmap Phase 2) —
# same closed vocabulary, kept as a local literal per this codebase's
# per-model vocabulary convention (see EVENT_TYPES, SLOT_KINDS elsewhere).
CLASS_TYPES = ("individual", "group")


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint(
            "class_type IN ('individual', 'group')",
            name="ck_appointments_class_type",
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
    class_type: Mapped[str] = mapped_column(String(50), nullable=False, default="individual")
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

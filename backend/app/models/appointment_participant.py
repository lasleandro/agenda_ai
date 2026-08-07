"""
AppointmentParticipant model — links an additional Contact to an
Appointment, mirroring RecurringSlotParticipant. Appointment.contact_id
remains the required "primary" participant; rows here hold anyone added
on top of that (e.g. turning a one-off individual appointment into a
shared session via the instructor agent).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AppointmentParticipant(Base):
    __tablename__ = "appointment_participants"
    __table_args__ = (
        UniqueConstraint("appointment_id", "contact_id", name="uq_appointment_participant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=False
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    appointment: Mapped["Appointment"] = relationship("Appointment")
    contact: Mapped["Contact"] = relationship("Contact")

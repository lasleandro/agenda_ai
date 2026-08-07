"""
AppointmentCandidate model (Section 10.5).

Represents an AI interpretation that has not necessarily become a confirmed
appointment.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AppointmentCandidate(Base):
    __tablename__ = "appointment_candidates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id")
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id")
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    proposed_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proposed_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    service: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50), default="detected")
    ambiguities: Mapped[list | None] = mapped_column(JSONB)
    event_fingerprint: Mapped[str | None] = mapped_column(String(64))
    extraction_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    professional: Mapped["Professional"] = relationship("Professional")
    conversation: Mapped["Conversation | None"] = relationship("Conversation")
    contact: Mapped["Contact | None"] = relationship("Contact")

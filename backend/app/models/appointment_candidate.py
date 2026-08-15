"""
AppointmentCandidate model (Section 10.5).

Represents an AI interpretation that has not necessarily become a confirmed
appointment.

`status` (waitlist roadmap v0.1, Phase 4): "detected" is the only value the
extraction pipeline itself sets; "dismissed"/"fulfilled" are set by the
instructor reviewing candidates via app/api/appointment_candidates.py.
"fulfilled" applies when the instructor turns a supported candidate into a
real domain record: a waitlist entry or an appointment. Other operations stay
dismiss-only until their operation-specific review flow is implemented.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

CANDIDATE_STATUSES = ("detected", "dismissed", "fulfilled")


class AppointmentCandidate(Base):
    __tablename__ = "appointment_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in CANDIDATE_STATUSES) + ")",
            name="ck_appointment_candidates_status",
        ),
    )

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
    # `action` is retained while existing API/UI clients migrate. New pipeline
    # rows persist `operation` and `confirmation_status` as the source of
    # truth; legacy rows intentionally remain null in those new columns.
    operation: Mapped[str | None] = mapped_column(String(50))
    confirmation_status: Mapped[str | None] = mapped_column(String(50))
    existing_appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id")
    )
    resulting_appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), unique=True
    )
    operator_action_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("operator_action_candidates.id"), unique=True
    )
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
    existing_appointment: Mapped["Appointment | None"] = relationship(
        "Appointment", foreign_keys=[existing_appointment_id]
    )
    resulting_appointment: Mapped["Appointment | None"] = relationship(
        "Appointment", foreign_keys=[resulting_appointment_id]
    )
    operator_action_candidate: Mapped["OperatorActionCandidate | None"] = relationship(
        "OperatorActionCandidate", foreign_keys=[operator_action_candidate_id]
    )
    escalation: Mapped["PassiveEscalation | None"] = relationship(
        "PassiveEscalation", back_populates="appointment_candidate", uselist=False
    )

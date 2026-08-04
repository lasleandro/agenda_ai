"""
AppointmentEvidence model (Section 10.7).

Connects an appointment candidate to source messages.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AppointmentEvidence(Base):
    __tablename__ = "appointment_evidences"

    appointment_candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointment_candidates.id"),
        primary_key=True,
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id"),
        primary_key=True,
    )
    evidence_role: Mapped[str] = mapped_column(String(50), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0)

    candidate: Mapped["AppointmentCandidate"] = relationship("AppointmentCandidate")
    message: Mapped["Message"] = relationship("Message")

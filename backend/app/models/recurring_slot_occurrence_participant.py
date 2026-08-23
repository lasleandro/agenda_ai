"""A one-off guest enrolled in one occurrence of a recurring class."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RecurringSlotOccurrenceParticipant(Base):
    __tablename__ = "recurring_slot_occurrence_participants"
    __table_args__ = (
        UniqueConstraint(
            "recurring_slot_id",
            "contact_id",
            "occurrence_date",
            name="uq_recurring_slot_occurrence_participant",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    recurring_slot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recurring_slots.id"), nullable=False
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=False
    )
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    professional: Mapped["Professional"] = relationship("Professional")
    recurring_slot: Mapped["RecurringSlot"] = relationship("RecurringSlot")
    contact: Mapped["Contact"] = relationship("Contact")

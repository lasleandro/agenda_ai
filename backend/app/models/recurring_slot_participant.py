"""
RecurringSlotParticipant model — links a Contact only to a recurring class.
A group class has capacity for 1–4 participants and may start with one person
while enrollment is pending; an individual class has exactly one. Capacity and
the class-only boundary are enforced by the service layer because they span
this table and RecurringSlot.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RecurringSlotParticipant(Base):
    __tablename__ = "recurring_slot_participants"
    __table_args__ = (
        UniqueConstraint("recurring_slot_id", "contact_id", name="uq_slot_participant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recurring_slot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recurring_slots.id"), nullable=False
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    recurring_slot: Mapped["RecurringSlot"] = relationship("RecurringSlot")
    contact: Mapped["Contact"] = relationship("Contact")

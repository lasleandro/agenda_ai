"""
RecurringSlot model ("Horário Fixo") — the professional's standing weekly
reservation at a Place (customer ontology roadmap Phase 2). Editable from
both the "Meus Locais" screen and the calendar screen — this is the single
underlying record for both.

class_type/max_participants are plain strings/ints (not a DB enum) so new
values can be added later without a migration — see roadmap "modular"
decision (2026-08-05).

slot_kind (operational ontology roadmap v0.2, Phase 0) is an explicit,
persisted axis independent of class_type:
- "availability": the instructor is available at the place during this
  interval. Availability rows must not have RecurringSlotParticipant rows
  and use neutral legacy class-field values. The row-level values are enforced
  by database and service constraints; participant ownership is enforced by
  the service layer.
- "class": the interval is a scheduled individual or group class; class_type
  distinguishes individual vs group only when slot_kind == "class".
Participant count must never be used to infer this meaning going forward.

valid_from/valid_until bound a weekly (recurrence_type == "weekly") row's
effective date range; both are nullable and, when set, describe an
inclusive interval. One-off rows keep using scheduled_date instead.

group_name is the human label for a class's roster/group identity (e.g.
"Grupo da Maria"), independent of `label`, which names a resource or
location detail (e.g. "Quadra 2"). Per the operational ontology roadmap's
"interpretation 1", a group is exactly one RecurringSlot's participant set
— there is no separate group entity yet.
"""

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# day_of_week follows Python's date.weekday(): Monday=0 .. Sunday=6.
CLASS_TYPES = ("individual", "group")
SLOT_KINDS = ("availability", "class")


class RecurringSlot(Base):
    __tablename__ = "recurring_slots"
    __table_args__ = (
        CheckConstraint(
            "commercial_status IS NULL OR commercial_status IN ('active', 'waiting', 'paused')",
            name="ck_recurring_slots_commercial_status",
        ),
        CheckConstraint(
            "hourly_rate_cents IS NULL OR hourly_rate_cents BETWEEN 0 AND 100000000",
            name="ck_recurring_slots_hourly_rate_cents",
        ),
        CheckConstraint(
            "slot_kind IN ('availability', 'class')",
            name="ck_recurring_slots_slot_kind",
        ),
        CheckConstraint(
            "class_type IN ('individual', 'group')",
            name="ck_recurring_slots_class_type",
        ),
        CheckConstraint(
            "max_participants BETWEEN 1 AND 4",
            name="ck_recurring_slots_max_participants",
        ),
        CheckConstraint(
            "slot_kind = 'class' OR (class_type = 'individual' "
            "AND max_participants = 1 AND level IS NULL AND group_name IS NULL)",
            name="ck_recurring_slots_availability_neutral",
        ),
        CheckConstraint(
            "valid_from IS NULL OR valid_until IS NULL OR valid_until >= valid_from",
            name="ck_recurring_slots_valid_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    place_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("places.id"), nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    group_name: Mapped[str | None] = mapped_column(String(255))
    class_type: Mapped[str] = mapped_column(String(50), default="individual")
    slot_kind: Mapped[str] = mapped_column(String(20), default="availability")
    level: Mapped[str | None] = mapped_column(String(50))
    commercial_status: Mapped[str | None] = mapped_column(String(20))
    hourly_rate_cents: Mapped[int | None] = mapped_column(Integer)
    max_participants: Mapped[int] = mapped_column(Integer, default=1)
    recurrence_type: Mapped[str] = mapped_column(String(20), default="weekly")
    scheduled_date: Mapped[date | None] = mapped_column(Date)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    professional: Mapped["Professional"] = relationship("Professional")
    place: Mapped["Place"] = relationship("Place")

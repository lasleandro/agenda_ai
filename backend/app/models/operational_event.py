"""
OperationalEvent model (operational ontology roadmap v0.2, Phase 3) — an
append-only, tenant-scoped ledger of everything that happened, independent
of the operational tables that hold current state. Answers "why is this
true?" where the domain tables (Appointment, RecurringSlot, ...) answer
"what is true now?".

`sequence` is the immutable ingestion order (a stable tiebreaker distinct
from `occurred_at`, since events — especially from a future WhatsApp
channel — may arrive out of business-time order). Never update or delete a
row here; corrections are new events, not edits.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

EVENT_TYPES = (
    "agent.action.proposed",
    "agent.action.confirmed",
    "agent.action.rejected",
    "agent.action.expired",
    "agent.action.executed",
    "agent.action.failed",
    "schedule.appointment.created",
    "schedule.appointment.updated",
    "schedule.appointment.cancelled",
    "schedule.series.created",
    "schedule.series.updated",
    "schedule.series.deactivated",
    "schedule.occurrence.cancelled",
    "schedule.occurrence.rescheduled",
    "schedule.participant.added",
    "schedule.participant.removed",
    "contact.updated",
    "place.created",
    "place.updated",
    "place.deactivated",
    "assistant.settings.updated",
    "scheduled_task.configuration.updated",
    "makeup_credit.granted",
    "makeup_credit.redeemed",
    "makeup_credit.expired",
    "schedule.participant.absence_noted",
    "waitlist.entry.added",
    "waitlist.entry.cancelled",
    "waitlist.entry.fulfilled",
    "instructor_event.created",
    "tenant.suspended",
    "tenant.reactivated",
    "tenant.archived",
    "tenant.restored",
    "tenant.impersonated_while_inactive",
)


class OperationalEvent(Base):
    __tablename__ = "operational_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            + ", ".join(f"'{event_type}'" for event_type in EVENT_TYPES)
            + ")",
            name="ck_operational_events_event_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, unique=True)
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_channel: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    operator_action_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("operator_action_candidates.id")
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    before_state: Mapped[dict | None] = mapped_column(JSONB)
    after_state: Mapped[dict | None] = mapped_column(JSONB)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))

    professional: Mapped["Professional"] = relationship("Professional")
    operator_action_candidate: Mapped["OperatorActionCandidate | None"] = relationship(
        "OperatorActionCandidate"
    )

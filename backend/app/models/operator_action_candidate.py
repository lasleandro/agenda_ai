"""
OperatorActionCandidate model (operational ontology roadmap v0.2, Phase 3)
— a proposed agent write, pending explicit instructor confirmation.

Every mutation the instructor agent can make goes through this table:
`propose()` creates a row with a deterministic, human-readable preview;
`confirm()` re-validates and executes inside the same transaction;
`reject()`/expiry never execute. The preview shown to the user and the
`resolved_arguments` actually executed always come from this record, never
from the model's own prose in the same turn — see
`app.agent.candidates`.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

CANDIDATE_STATUSES = (
    "proposed",
    "confirmed",
    "rejected",
    "expired",
    "executed",
    "failed",
)


class OperatorActionCandidate(Base):
    __tablename__ = "operator_action_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'confirmed', 'rejected', 'expired', "
            "'executed', 'failed')",
            name="ck_operator_action_candidates_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="web")
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_schema_version: Mapped[str] = mapped_column(String(20), default="v1")
    resolved_arguments: Mapped[dict] = mapped_column(JSONB, nullable=False)
    preview_text: Mapped[str] = mapped_column(String(2000), nullable=False)
    affected_entities: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    professional: Mapped["Professional"] = relationship("Professional")
    actor_user: Mapped["User"] = relationship("User")

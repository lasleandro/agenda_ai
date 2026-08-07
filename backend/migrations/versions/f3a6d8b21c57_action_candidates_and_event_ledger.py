"""Add operator_action_candidates and operational_events.

Operational ontology roadmap v0.2, Phase 3 (action candidates and event
ledger): every instructor-agent write must be proposed, previewed,
explicitly confirmed, and audited before it executes.

Revision ID: f3a6d8b21c57
Revises: e2b7c5a1f048
Create Date: 2026-08-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f3a6d8b21c57"
down_revision: Union[str, Sequence[str], None] = "e2b7c5a1f048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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
)


def upgrade() -> None:
    op.create_table(
        "operator_action_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="web"),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column(
            "tool_schema_version", sa.String(length=20), nullable=False, server_default="v1"
        ),
        sa.Column("resolved_arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("preview_text", sa.String(length=2000), nullable=False),
        sa.Column("affected_entities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="proposed"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255)),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("failure_reason", sa.String(length=500)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'confirmed', 'rejected', 'expired', "
            "'executed', 'failed')",
            name="ck_operator_action_candidates_status",
        ),
    )
    op.create_index(
        "ix_operator_action_candidates_professional_id",
        "operator_action_candidates",
        ["professional_id"],
    )
    op.create_index(
        "uq_operator_action_candidates_idempotency_key",
        "operator_action_candidates",
        ["professional_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "operational_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sequence", sa.BigInteger(), sa.Identity(), nullable=False, unique=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_channel", sa.String(length=20), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "operator_action_candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operator_action_candidates.id"),
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("idempotency_key", sa.String(length=255)),
        sa.CheckConstraint(
            "event_type IN (" + ", ".join(f"'{t}'" for t in EVENT_TYPES) + ")",
            name="ck_operational_events_event_type",
        ),
    )
    op.create_index(
        "ix_operational_events_professional_id_occurred_at",
        "operational_events",
        ["professional_id", "occurred_at"],
    )
    op.create_index(
        "ix_operational_events_correlation_id",
        "operational_events",
        ["correlation_id"],
    )
    op.create_index(
        "ix_operational_events_entity",
        "operational_events",
        ["entity_type", "entity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_operational_events_entity", table_name="operational_events")
    op.drop_index("ix_operational_events_correlation_id", table_name="operational_events")
    op.drop_index(
        "ix_operational_events_professional_id_occurred_at", table_name="operational_events"
    )
    op.drop_table("operational_events")

    op.drop_index(
        "uq_operator_action_candidates_idempotency_key",
        table_name="operator_action_candidates",
    )
    op.drop_index(
        "ix_operator_action_candidates_professional_id",
        table_name="operator_action_candidates",
    )
    op.drop_table("operator_action_candidates")

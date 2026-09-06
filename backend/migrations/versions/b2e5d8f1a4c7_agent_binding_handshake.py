"""Instructor agent-channel binding handshake (Shared Platform AI Agent
Number Roadmap v0.1, Phase F).

Revision ID: b2e5d8f1a4c7
Revises: a1f4c7e9b2d6
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "b2e5d8f1a4c7"
down_revision: Union[str, Sequence[str], None] = "a1f4c7e9b2d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BASE_EVENT_TYPES = (
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
    "contact.created",
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
    "tenant.created",
    "tenant.suspended",
    "tenant.reactivated",
    "tenant.archived",
    "tenant.restored",
    "tenant.impersonated_while_inactive",
)
_BINDING_EVENT_TYPES = (
    "agent.binding.confirmed",
    "agent.binding.revoked",
)

_OLD_SQL = "event_type IN (" + ", ".join(f"'{t}'" for t in _BASE_EVENT_TYPES) + ")"
_NEW_SQL = (
    "event_type IN ("
    + ", ".join(f"'{t}'" for t in _BASE_EVENT_TYPES + _BINDING_EVENT_TYPES)
    + ")"
)


def upgrade() -> None:
    op.add_column(
        "professionals",
        sa.Column("agent_binding_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "professionals",
        sa.Column(
            "agent_binding_confirmed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_table(
        "agent_binding_challenges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Not globally unique: a confirm always knows the tenant (resolved
        # from the sender), so the code only has to be unique per tenant among
        # unconsumed challenges, which issue_challenge enforces by rotation.
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_agent_binding_challenges_professional",
        "agent_binding_challenges",
        ["professional_id"],
    )

    op.drop_constraint(
        "ck_operational_events_event_type", "operational_events", type_="check"
    )
    op.create_check_constraint(
        "ck_operational_events_event_type", "operational_events", _NEW_SQL
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_operational_events_event_type", "operational_events", type_="check"
    )
    op.create_check_constraint(
        "ck_operational_events_event_type", "operational_events", _OLD_SQL
    )

    op.drop_index(
        "ix_agent_binding_challenges_professional",
        table_name="agent_binding_challenges",
    )
    op.drop_table("agent_binding_challenges")

    op.drop_column("professionals", "agent_binding_confirmed_by")
    op.drop_column("professionals", "agent_binding_confirmed_at")

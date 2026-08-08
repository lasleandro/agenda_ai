"""Add MakeupClassCredit table and extend OperationalEvent types.

Revision ID: e6b2d8f4a1c5
Revises: d5c9e7f1a3b6
Create Date: 2026-08-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e6b2d8f4a1c5"
down_revision: Union[str, Sequence[str], None] = "d5c9e7f1a3b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_EVENT_TYPES = (
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
)

_NEW_EVENT_TYPES = _OLD_EVENT_TYPES + (
    "makeup_credit.granted",
    "makeup_credit.redeemed",
    "makeup_credit.expired",
)

_OLD_CONSTRAINT_SQL = (
    "event_type IN (" + ", ".join(f"'{t}'" for t in _OLD_EVENT_TYPES) + ")"
)
_NEW_CONSTRAINT_SQL = (
    "event_type IN (" + ", ".join(f"'{t}'" for t in _NEW_EVENT_TYPES) + ")"
)


def upgrade() -> None:
    # 1. Extend the operational_events CHECK constraint to allow new types.
    op.drop_constraint(
        "ck_operational_events_event_type",
        "operational_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_events_event_type",
        "operational_events",
        _NEW_CONSTRAINT_SQL,
    )

    # 2. Create the makeup_class_credits table.
    op.create_table(
        "makeup_class_credits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id"),
            nullable=False,
        ),
        sa.Column(
            "origin_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operational_events.id"),
            nullable=False,
        ),
        sa.Column(
            "origin_recurring_slot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recurring_slots.id"),
            nullable=False,
        ),
        sa.Column("origin_occurrence_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="available",
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "redeemed_appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('available', 'redeemed', 'expired', 'forfeited')",
            name="ck_makeup_class_credits_status",
        ),
        sa.UniqueConstraint(
            "contact_id",
            "origin_event_id",
            name="uq_makeup_class_credits_contact_event",
        ),
    )


def downgrade() -> None:
    op.drop_table("makeup_class_credits")

    op.drop_constraint(
        "ck_operational_events_event_type",
        "operational_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_events_event_type",
        "operational_events",
        _OLD_CONSTRAINT_SQL,
    )

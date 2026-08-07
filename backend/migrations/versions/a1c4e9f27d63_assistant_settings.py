"""Add assistant_settings and extend operational_events vocabulary.

Per-tenant instructor-agent tuning (temperature, memory window), set by a
platform admin.

Revision ID: a1c4e9f27d63
Revises: f3a6d8b21c57
Create Date: 2026-08-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1c4e9f27d63"
down_revision: Union[str, Sequence[str], None] = "f3a6d8b21c57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_EVENT_TYPES = (
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
NEW_EVENT_TYPES = OLD_EVENT_TYPES + ("assistant.settings.updated",)


def _check_sql(event_types: tuple[str, ...]) -> str:
    return "event_type IN (" + ", ".join(f"'{et}'" for et in event_types) + ")"


def upgrade() -> None:
    op.create_table(
        "assistant_settings",
        sa.Column("professional_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.2"),
        sa.Column(
            "memory_window_messages", sa.Integer(), nullable=False, server_default="20"
        ),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["professional_id"], ["professionals.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.CheckConstraint(
            "temperature >= 0.0 AND temperature <= 2.0",
            name="ck_assistant_settings_temperature_range",
        ),
        sa.CheckConstraint(
            "memory_window_messages >= 2 AND memory_window_messages <= 200",
            name="ck_assistant_settings_memory_window_range",
        ),
    )

    op.drop_constraint(
        "ck_operational_events_event_type", "operational_events", type_="check"
    )
    op.create_check_constraint(
        "ck_operational_events_event_type",
        "operational_events",
        _check_sql(NEW_EVENT_TYPES),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_operational_events_event_type", "operational_events", type_="check"
    )
    op.create_check_constraint(
        "ck_operational_events_event_type",
        "operational_events",
        _check_sql(OLD_EVENT_TYPES),
    )
    op.drop_table("assistant_settings")

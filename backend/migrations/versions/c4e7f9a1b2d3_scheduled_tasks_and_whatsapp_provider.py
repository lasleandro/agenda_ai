"""Add provider provenance and tenant-scoped scheduled daily agenda tasks.

Revision ID: c4e7f9a1b2d3
Revises: b3e8d1f5a9c2
Create Date: 2026-08-16
"""

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c4e7f9a1b2d3"
down_revision: Union[str, Sequence[str], None] = "b3e8d1f5a9c2"
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
    "makeup_credit.granted",
    "makeup_credit.redeemed",
    "makeup_credit.expired",
    "schedule.participant.absence_noted",
    "waitlist.entry.added",
    "waitlist.entry.cancelled",
    "instructor_event.created",
)
_NEW_EVENT_TYPES = _OLD_EVENT_TYPES + ("scheduled_task.configuration.updated",)


def _constraint_sql(event_types: tuple[str, ...]) -> str:
    return "event_type IN (" + ", ".join(f"'{event_type}'" for event_type in event_types) + ")"


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("provider_key", sa.String(length=50), server_default="ycloud", nullable=False),
    )
    op.drop_constraint("messages_provider_message_id_key", "messages", type_="unique")
    op.create_unique_constraint(
        "uq_messages_provider_message",
        "messages",
        ["provider_key", "provider_message_id"],
    )
    op.alter_column("messages", "provider_key", server_default=None)

    op.create_table(
        "scheduled_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("professional_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False, server_default="whatsapp"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("local_time", sa.Time(), nullable=False, server_default="07:00"),
        sa.Column("consent_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("task_type IN ('daily_agenda_summary')", name="ck_scheduled_tasks_type"),
        sa.CheckConstraint("channel IN ('whatsapp')", name="ck_scheduled_tasks_channel"),
        sa.ForeignKeyConstraint(["professional_id"], ["professionals.id"]),
        sa.ForeignKeyConstraint(["consent_confirmed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("professional_id", "task_type", name="uq_scheduled_tasks_professional_type"),
    )
    op.create_index("ix_scheduled_tasks_professional_id", "scheduled_tasks", ["professional_id"])

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, daily_summary_time FROM professionals")).mappings()
    for row in rows:
        bind.execute(
            sa.text(
                "INSERT INTO scheduled_tasks "
                "(id, professional_id, task_type, channel, enabled, local_time) "
                "VALUES (:id, :professional_id, 'daily_agenda_summary', 'whatsapp', false, CAST(:local_time AS time))"
            ),
            {
                "id": str(uuid.uuid4()),
                "professional_id": str(row["id"]),
                "local_time": row["daily_summary_time"] or "07:00",
            },
        )

    op.create_table(
        "scheduled_task_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("professional_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheduled_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_local_date", sa.Date(), nullable=False),
        sa.Column("scheduled_for_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_key", sa.String(length=50), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("provider_external_id", sa.String(length=255), nullable=True),
        sa.Column("agenda_item_count", sa.Integer(), nullable=True),
        sa.Column("class_count", sa.Integer(), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=True),
        sa.Column("rendered_body", sa.Text(), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_detail", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'retry_wait', 'provider_accepted', "
            "'sent', 'delivered', 'read', 'delivery_unknown', 'failed', 'skipped')",
            name="ck_scheduled_task_runs_status",
        ),
        sa.ForeignKeyConstraint(["professional_id"], ["professionals.id"]),
        sa.ForeignKeyConstraint(["scheduled_task_id"], ["scheduled_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scheduled_task_id", "target_local_date", name="uq_scheduled_task_runs_task_date"),
    )
    op.create_index(
        "ix_scheduled_task_runs_status_next_attempt",
        "scheduled_task_runs",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "ix_scheduled_task_runs_professional_created",
        "scheduled_task_runs",
        ["professional_id", "created_at"],
    )
    op.create_index(
        "ix_scheduled_task_runs_provider_message",
        "scheduled_task_runs",
        ["provider_key", "provider_message_id"],
    )

    op.drop_constraint("ck_operational_events_event_type", "operational_events", type_="check")
    op.create_check_constraint(
        "ck_operational_events_event_type",
        "operational_events",
        _constraint_sql(_NEW_EVENT_TYPES),
    )


def downgrade() -> None:
    op.drop_constraint("ck_operational_events_event_type", "operational_events", type_="check")
    op.create_check_constraint(
        "ck_operational_events_event_type",
        "operational_events",
        _constraint_sql(_OLD_EVENT_TYPES),
    )

    op.drop_index("ix_scheduled_task_runs_provider_message", table_name="scheduled_task_runs")
    op.drop_index("ix_scheduled_task_runs_professional_created", table_name="scheduled_task_runs")
    op.drop_index("ix_scheduled_task_runs_status_next_attempt", table_name="scheduled_task_runs")
    op.drop_table("scheduled_task_runs")
    op.drop_index("ix_scheduled_tasks_professional_id", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")

    op.drop_constraint("uq_messages_provider_message", "messages", type_="unique")
    op.create_unique_constraint("messages_provider_message_id_key", "messages", ["provider_message_id"])
    op.drop_column("messages", "provider_key")

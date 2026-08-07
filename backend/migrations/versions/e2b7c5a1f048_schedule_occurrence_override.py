"""Add schedule_occurrence_overrides (cancel/reschedule exceptions).

Operational ontology roadmap v0.2, Phase 1 (occurrence projection and
exceptions): a dated exception to one occurrence of a recurring or one-off
calendar entry.

Revision ID: e2b7c5a1f048
Revises: d1a4c8e6b930
Create Date: 2026-08-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e2b7c5a1f048"
down_revision: Union[str, Sequence[str], None] = "d1a4c8e6b930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedule_occurrence_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column(
            "appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id"),
        ),
        sa.Column(
            "recurring_slot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recurring_slots.id"),
        ),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("override_type", sa.String(length=20), nullable=False),
        sa.Column("replacement_start_at", sa.DateTime(timezone=True)),
        sa.Column("replacement_end_at", sa.DateTime(timezone=True)),
        sa.Column(
            "replacement_place_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("places.id"),
        ),
        sa.Column("reason_code", sa.String(length=50)),
        sa.Column("note", sa.String(length=500)),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
        ),
        sa.Column("source", sa.String(length=50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "(appointment_id IS NOT NULL) != (recurring_slot_id IS NOT NULL)",
            name="ck_schedule_occurrence_overrides_one_parent",
        ),
        sa.CheckConstraint(
            "override_type IN ('cancelled', 'rescheduled')",
            name="ck_schedule_occurrence_overrides_type",
        ),
        sa.CheckConstraint(
            "override_type = 'rescheduled' OR "
            "(replacement_start_at IS NULL AND replacement_end_at IS NULL "
            "AND replacement_place_id IS NULL)",
            name="ck_schedule_occurrence_overrides_replacement_gated",
        ),
        sa.CheckConstraint(
            "override_type != 'rescheduled' OR "
            "(replacement_start_at IS NOT NULL AND replacement_end_at IS NOT NULL "
            "AND replacement_end_at > replacement_start_at)",
            name="ck_schedule_occurrence_overrides_replacement_range",
        ),
    )

    # "One active override per parent occurrence" — a plain UniqueConstraint
    # can't express uniqueness scoped to whichever parent column is non-null,
    # so use two partial unique indexes instead.
    op.create_index(
        "uq_schedule_occurrence_overrides_appointment_occurrence",
        "schedule_occurrence_overrides",
        ["appointment_id", "occurrence_date"],
        unique=True,
        postgresql_where=sa.text("appointment_id IS NOT NULL"),
    )
    op.create_index(
        "uq_schedule_occurrence_overrides_recurring_slot_occurrence",
        "schedule_occurrence_overrides",
        ["recurring_slot_id", "occurrence_date"],
        unique=True,
        postgresql_where=sa.text("recurring_slot_id IS NOT NULL"),
    )
    op.create_index(
        "ix_schedule_occurrence_overrides_professional_id",
        "schedule_occurrence_overrides",
        ["professional_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_schedule_occurrence_overrides_professional_id",
        table_name="schedule_occurrence_overrides",
    )
    op.drop_index(
        "uq_schedule_occurrence_overrides_recurring_slot_occurrence",
        table_name="schedule_occurrence_overrides",
    )
    op.drop_index(
        "uq_schedule_occurrence_overrides_appointment_occurrence",
        table_name="schedule_occurrence_overrides",
    )
    op.drop_table("schedule_occurrence_overrides")

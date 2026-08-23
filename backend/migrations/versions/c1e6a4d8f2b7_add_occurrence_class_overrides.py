"""Add dated class format and capacity overrides.

Revision ID: c1e6a4d8f2b7
Revises: b7d3e4f9a2c1
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c1e6a4d8f2b7"
down_revision: Union[str, Sequence[str], None] = "b7d3e4f9a2c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedule_occurrence_class_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("professional_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("professionals.id"), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id")),
        sa.Column("recurring_slot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recurring_slots.id")),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("class_type", sa.String(length=20), nullable=False),
        sa.Column("max_participants", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("source", sa.String(length=50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("(appointment_id IS NOT NULL) != (recurring_slot_id IS NOT NULL)", name="ck_schedule_occurrence_class_overrides_one_parent"),
        sa.CheckConstraint("class_type IN ('individual', 'group')", name="ck_schedule_occurrence_class_overrides_type"),
        sa.CheckConstraint("max_participants BETWEEN 1 AND 4", name="ck_schedule_occurrence_class_overrides_capacity"),
        sa.CheckConstraint("class_type = 'group' OR max_participants = 1", name="ck_schedule_occurrence_class_overrides_individual_capacity"),
    )
    op.create_index("ix_schedule_occurrence_class_overrides_professional_id", "schedule_occurrence_class_overrides", ["professional_id"])
    op.create_index("uq_schedule_occurrence_class_overrides_appointment", "schedule_occurrence_class_overrides", ["appointment_id", "occurrence_date"], unique=True, postgresql_where=sa.text("appointment_id IS NOT NULL"))
    op.create_index("uq_schedule_occurrence_class_overrides_recurring_slot", "schedule_occurrence_class_overrides", ["recurring_slot_id", "occurrence_date"], unique=True, postgresql_where=sa.text("recurring_slot_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("uq_schedule_occurrence_class_overrides_recurring_slot", table_name="schedule_occurrence_class_overrides")
    op.drop_index("uq_schedule_occurrence_class_overrides_appointment", table_name="schedule_occurrence_class_overrides")
    op.drop_index("ix_schedule_occurrence_class_overrides_professional_id", table_name="schedule_occurrence_class_overrides")
    op.drop_table("schedule_occurrence_class_overrides")

"""Add dated guests for recurring group occurrences.

Revision ID: b7d3e4f9a2c1
Revises: a8c4d2e7f1b6
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7d3e4f9a2c1"
down_revision: Union[str, Sequence[str], None] = "a8c4d2e7f1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recurring_slot_occurrence_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column(
            "recurring_slot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recurring_slots.id"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id"),
            nullable=False,
        ),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "recurring_slot_id",
            "contact_id",
            "occurrence_date",
            name="uq_recurring_slot_occurrence_participant",
        ),
    )
    op.create_index(
        "ix_recurring_slot_occurrence_participants_lookup",
        "recurring_slot_occurrence_participants",
        ["professional_id", "recurring_slot_id", "occurrence_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recurring_slot_occurrence_participants_lookup",
        table_name="recurring_slot_occurrence_participants",
    )
    op.drop_table("recurring_slot_occurrence_participants")

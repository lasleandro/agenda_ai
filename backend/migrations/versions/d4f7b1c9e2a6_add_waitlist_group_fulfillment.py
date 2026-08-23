"""Link fulfilled waitlist demand to a dated recurring group occurrence.

Revision ID: d4f7b1c9e2a6
Revises: c1e6a4d8f2b7
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d4f7b1c9e2a6"
down_revision: Union[str, Sequence[str], None] = "c1e6a4d8f2b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "waitlist_entries",
        sa.Column(
            "fulfilled_recurring_slot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recurring_slots.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "waitlist_entries",
        sa.Column("fulfilled_occurrence_date", sa.Date(), nullable=True),
    )
    op.create_check_constraint(
        "ck_waitlist_entries_recurring_fulfillment_pair",
        "waitlist_entries",
        "(fulfilled_recurring_slot_id IS NULL) = (fulfilled_occurrence_date IS NULL)",
    )
    op.create_check_constraint(
        "ck_waitlist_entries_one_fulfillment_target",
        "waitlist_entries",
        "fulfilled_appointment_id IS NULL OR fulfilled_recurring_slot_id IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_waitlist_entries_one_fulfillment_target", "waitlist_entries", type_="check"
    )
    op.drop_constraint(
        "ck_waitlist_entries_recurring_fulfillment_pair", "waitlist_entries", type_="check"
    )
    op.drop_column("waitlist_entries", "fulfilled_occurrence_date")
    op.drop_column("waitlist_entries", "fulfilled_recurring_slot_id")

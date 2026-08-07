"""Add group level and recurring-slot schedule recurrence.

Revision ID: b7e3d9a1c5f4
Revises: a6d91e4b7c20
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e3d9a1c5f4"
down_revision: Union[str, Sequence[str], None] = "a6d91e4b7c20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("recurring_slots", sa.Column("level", sa.String(length=50)))
    op.add_column(
        "recurring_slots",
        sa.Column(
            "recurrence_type",
            sa.String(length=20),
            nullable=False,
            server_default="weekly",
        ),
    )
    op.add_column("recurring_slots", sa.Column("scheduled_date", sa.Date()))


def downgrade() -> None:
    op.drop_column("recurring_slots", "scheduled_date")
    op.drop_column("recurring_slots", "recurrence_type")
    op.drop_column("recurring_slots", "level")

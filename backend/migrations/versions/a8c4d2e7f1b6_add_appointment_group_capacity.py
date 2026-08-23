"""Add explicit capacity to appointments.

One-off and weekly appointments already carry an explicit class format, but
their group capacity was an implicit application constant. Persist the value so
Agenda, agent, and financial read models can reason about the same limit.

Existing individual appointments receive capacity one; existing group
appointments retain the previous four-person limit.

Revision ID: a8c4d2e7f1b6
Revises: e62d256cf621
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8c4d2e7f1b6"
down_revision: Union[str, Sequence[str], None] = "e62d256cf621"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Persist and backfill the effective appointment capacity."""
    op.add_column(
        "appointments",
        sa.Column(
            "max_participants",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.execute(
        "UPDATE appointments "
        "SET max_participants = CASE "
        "WHEN class_type = 'group' THEN 4 ELSE 1 END"
    )
    op.create_check_constraint(
        "ck_appointments_max_participants",
        "appointments",
        "max_participants BETWEEN 1 AND 4",
    )


def downgrade() -> None:
    """Remove the additive appointment-capacity column."""
    op.drop_constraint(
        "ck_appointments_max_participants",
        "appointments",
        type_="check",
    )
    op.drop_column("appointments", "max_participants")

"""Link passive candidates to their extracted appointment reference.

Revision ID: c9d5e3f8a2b0
Revises: b8c4d2e7f1a9
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d5e3f8a2b0"
down_revision: Union[str, Sequence[str], None] = "b8c4d2e7f1a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Persist extracted appointment references for reschedule resolution."""
    op.add_column(
        "appointment_candidates",
        sa.Column("existing_appointment_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_appointment_candidates_existing_appointment",
        "appointment_candidates",
        "appointments",
        ["existing_appointment_id"],
        ["id"],
    )


def downgrade() -> None:
    """Remove extracted appointment-reference persistence."""
    op.drop_constraint(
        "fk_appointment_candidates_existing_appointment",
        "appointment_candidates",
        type_="foreignkey",
    )
    op.drop_column("appointment_candidates", "existing_appointment_id")

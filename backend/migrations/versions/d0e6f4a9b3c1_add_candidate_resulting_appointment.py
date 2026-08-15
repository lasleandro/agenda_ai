"""Link fulfilled passive candidates to their created appointment.

Revision ID: d0e6f4a9b3c1
Revises: c9d5e3f8a2b0
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d0e6f4a9b3c1"
down_revision: Union[str, Sequence[str], None] = "c9d5e3f8a2b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a one-to-one link for candidate-confirmed appointments."""
    op.add_column(
        "appointment_candidates",
        sa.Column("resulting_appointment_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_appointment_candidates_resulting_appointment",
        "appointment_candidates",
        "appointments",
        ["resulting_appointment_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_appointment_candidates_resulting_appointment",
        "appointment_candidates",
        ["resulting_appointment_id"],
    )


def downgrade() -> None:
    """Remove candidate-to-created-appointment linkage."""
    op.drop_constraint(
        "uq_appointment_candidates_resulting_appointment",
        "appointment_candidates",
        type_="unique",
    )
    op.drop_constraint(
        "fk_appointment_candidates_resulting_appointment",
        "appointment_candidates",
        type_="foreignkey",
    )
    op.drop_column("appointment_candidates", "resulting_appointment_id")

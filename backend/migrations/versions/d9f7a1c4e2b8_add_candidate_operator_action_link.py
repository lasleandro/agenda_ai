"""Link passive candidates to their private-agent proposals.

Revision ID: d9f7a1c4e2b8
Revises: d0e6f4a9b3c1
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9f7a1c4e2b8"
down_revision: Union[str, Sequence[str], None] = "d0e6f4a9b3c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointment_candidates",
        sa.Column("operator_action_candidate_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_appointment_candidates_operator_action_candidate",
        "appointment_candidates",
        "operator_action_candidates",
        ["operator_action_candidate_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_appointment_candidates_operator_action_candidate",
        "appointment_candidates",
        ["operator_action_candidate_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_appointment_candidates_operator_action_candidate",
        "appointment_candidates",
        type_="unique",
    )
    op.drop_constraint(
        "fk_appointment_candidates_operator_action_candidate",
        "appointment_candidates",
        type_="foreignkey",
    )
    op.drop_column("appointment_candidates", "operator_action_candidate_id")

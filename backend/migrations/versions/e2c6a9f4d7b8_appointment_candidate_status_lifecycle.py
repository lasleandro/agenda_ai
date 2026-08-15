"""Add status CHECK constraint to appointment_candidates (waitlist roadmap v0.1, Phase 4).

Gives the passive-observer candidate a real review lifecycle
(detected/dismissed/fulfilled) instead of the single "detected" value it
has always been set to.

Revision ID: e2c6a9f4d7b8
Revises: d4f8b1e9a2c6
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e2c6a9f4d7b8"
down_revision: Union[str, Sequence[str], None] = "d4f8b1e9a2c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_appointment_candidates_status",
        "appointment_candidates",
        "status IN ('detected', 'dismissed', 'fulfilled')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_appointment_candidates_status", "appointment_candidates", type_="check"
    )

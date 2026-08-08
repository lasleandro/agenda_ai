"""Add CHECK constraint bounding revenue_occurrence_participants.non_billable_reason
to a closed vocabulary, matching every other small-vocabulary column in
this codebase (billing_type, class_type, credit status, ...).

Revision ID: c8e2a5f931b7
Revises: b3f7a92e1d04
Create Date: 2026-08-08
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c8e2a5f931b7"
down_revision: Union[str, Sequence[str], None] = "b3f7a92e1d04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_revenue_occurrence_participants_non_billable_reason",
        "revenue_occurrence_participants",
        "non_billable_reason IS NULL OR non_billable_reason IN "
        "('courtesy', 'write_off', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_revenue_occurrence_participants_non_billable_reason",
        "revenue_occurrence_participants",
        type_="check",
    )

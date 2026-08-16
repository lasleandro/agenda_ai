"""Add the durable passive place-review state.

Revision ID: b3e8d1f5a9c2
Revises: a2f7c9e4d6b1
Create Date: 2026-08-16
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b3e8d1f5a9c2"
down_revision: Union[str, Sequence[str], None] = "a2f7c9e4d6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_passive_escalations_status", "passive_escalations", type_="check"
    )
    op.create_check_constraint(
        "ck_passive_escalations_status",
        "passive_escalations",
        "status IN ('queued', 'needs_place_review', 'sent', 'failed', 'expired')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_passive_escalations_status", "passive_escalations", type_="check"
    )
    op.create_check_constraint(
        "ck_passive_escalations_status",
        "passive_escalations",
        "status IN ('queued', 'sent', 'failed', 'expired')",
    )

"""Record the explicit scope used to fulfill a waitlist request.

Revision ID: e5a8c2f4d7b1
Revises: d4f7b1c9e2a6
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5a8c2f4d7b1"
down_revision: Union[str, Sequence[str], None] = "d4f7b1c9e2a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "waitlist_entries",
        sa.Column("fulfillment_scope", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_waitlist_entries_fulfillment_scope",
        "waitlist_entries",
        "fulfillment_scope IS NULL OR fulfillment_scope IN ('occurrence', 'series')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_waitlist_entries_fulfillment_scope", "waitlist_entries", type_="check"
    )
    op.drop_column("waitlist_entries", "fulfillment_scope")

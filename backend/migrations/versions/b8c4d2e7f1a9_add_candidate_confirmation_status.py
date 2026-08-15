"""Persist normalized passive-candidate operation and confirmation status.

Revision ID: b8c4d2e7f1a9
Revises: a9d2e5f8c1b3
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c4d2e7f1a9"
down_revision: Union[str, Sequence[str], None] = "a9d2e5f8c1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add normalized extraction fields without guessing historical meaning."""
    op.add_column(
        "appointment_candidates",
        sa.Column("operation", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "appointment_candidates",
        sa.Column("confirmation_status", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    """Remove normalized extraction fields."""
    op.drop_column("appointment_candidates", "confirmation_status")
    op.drop_column("appointment_candidates", "operation")

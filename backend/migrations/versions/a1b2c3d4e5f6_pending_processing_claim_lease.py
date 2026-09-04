"""Recoverable claim lease for pending_processing.

Adds claimed_at and attempts so the candidate worker can claim a
conversation, run extraction, and delete the row only on success — instead
of deleting before processing and losing the work on a crash.

Revision ID: a1b2c3d4e5f6
Revises: c7e1a9d3b5f8
Create Date: 2026-09-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "c7e1a9d3b5f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pending_processing",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "pending_processing",
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("pending_processing", "attempts")
    op.drop_column("pending_processing", "claimed_at")

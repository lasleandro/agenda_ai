"""Deduplicate candidate events across repeated extraction runs.

Revision ID: 8a3e6f52d1c4
Revises: 19b66c2ef720
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8a3e6f52d1c4"
down_revision: Union[str, Sequence[str], None] = "19b66c2ef720"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add stable event identity and prevent duplicate candidates per conversation."""
    op.add_column(
        "appointment_candidates",
        sa.Column("event_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_candidate_conversation_event_fingerprint",
        "appointment_candidates",
        ["conversation_id", "event_fingerprint"],
    )


def downgrade() -> None:
    """Remove candidate-event deduplication."""
    op.drop_constraint(
        "uq_candidate_conversation_event_fingerprint",
        "appointment_candidates",
        type_="unique",
    )
    op.drop_column("appointment_candidates", "event_fingerprint")

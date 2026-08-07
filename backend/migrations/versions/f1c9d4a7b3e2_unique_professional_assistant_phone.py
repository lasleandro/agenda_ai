"""Enforce one Professional (tenant) per WhatsApp business number.

Revision ID: f1c9d4a7b3e2
Revises: 8a3e6f52d1c4
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f1c9d4a7b3e2"
down_revision: Union[str, Sequence[str], None] = "8a3e6f52d1c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Inbound webhook tenant resolution looks up Professional by
    assistant_phone (Phase A of the multi-tenancy roadmap); two tenants
    sharing a number would make that lookup ambiguous."""
    op.create_unique_constraint(
        "uq_professionals_assistant_phone",
        "professionals",
        ["assistant_phone"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_professionals_assistant_phone",
        "professionals",
        type_="unique",
    )

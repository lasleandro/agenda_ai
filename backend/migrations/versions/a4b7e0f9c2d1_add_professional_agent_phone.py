"""Add Professional.agent_phone (AI Agent Operations Roadmap v0.1, Phase 0).

Revision ID: a4b7e0f9c2d1
Revises: c8e2a5f931b7
Create Date: 2026-08-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a4b7e0f9c2d1"
down_revision: Union[str, Sequence[str], None] = "c8e2a5f931b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Separate WhatsApp number the instructor talks to the AI agent on,
    distinct from assistant_phone (the customer-facing number the passive
    observer watches). Unique for the same reason assistant_phone is: inbound
    webhook tenant resolution looks it up directly."""
    op.add_column(
        "professionals", sa.Column("agent_phone", sa.String(length=50), nullable=True)
    )
    op.create_unique_constraint(
        "uq_professionals_agent_phone",
        "professionals",
        ["agent_phone"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_professionals_agent_phone",
        "professionals",
        type_="unique",
    )
    op.drop_column("professionals", "agent_phone")

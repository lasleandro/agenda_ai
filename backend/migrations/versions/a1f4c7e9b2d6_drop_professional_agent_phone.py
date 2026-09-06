"""Drop Professional.agent_phone (Shared Platform AI Agent Number Roadmap v0.1).

Revision ID: a1f4c7e9b2d6
Revises: d4e5f6a7b8c9
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1f4c7e9b2d6"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The instructor-facing agent channel no longer resolves a tenant by a
    per-tenant number. It uses one shared platform number
    (PLATFORM_AGENT_WHATSAPP_NUMBER) and resolves the tenant from the sender
    (assistant_phone). agent_phone has no remaining reader."""
    op.drop_constraint(
        "uq_professionals_agent_phone",
        "professionals",
        type_="unique",
    )
    op.drop_column("professionals", "agent_phone")


def downgrade() -> None:
    """Re-adds the column and its unique constraint. Values are not
    recoverable — they were configuration, re-derivable from the YCloud
    account, never from this database."""
    op.add_column(
        "professionals",
        sa.Column("agent_phone", sa.String(length=50), nullable=True),
    )
    op.create_unique_constraint(
        "uq_professionals_agent_phone",
        "professionals",
        ["agent_phone"],
    )

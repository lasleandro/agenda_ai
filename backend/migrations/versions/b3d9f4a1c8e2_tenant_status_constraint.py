"""Tenant lifecycle: constrain professional.status and add status audit columns.

Revision ID: b3d9f4a1c8e2
Revises: a7d8b2e9f401
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "b3d9f4a1c8e2"
down_revision: Union[str, Sequence[str], None] = "a7d8b2e9f401"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfill any free-text status left over from before the vocabulary was
    # fixed. Only 'suspended' / 'archived' are preserved; everything else
    # (including the historical default 'active') collapses to 'active'.
    op.execute(
        "UPDATE professionals SET status = 'active' "
        "WHERE status NOT IN ('suspended', 'archived')"
    )
    op.create_check_constraint(
        "ck_professionals_status",
        "professionals",
        "status IN ('active', 'suspended', 'archived')",
    )
    op.add_column(
        "professionals",
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "professionals",
        sa.Column(
            "status_changed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "professionals",
        sa.Column("status_reason", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("professionals", "status_reason")
    op.drop_column("professionals", "status_changed_by")
    op.drop_column("professionals", "status_changed_at")
    op.drop_constraint("ck_professionals_status", "professionals", type_="check")

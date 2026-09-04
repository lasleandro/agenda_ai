"""Add the operation WhatsApp number to account access requests.

Revision ID: d4e5f6a7b8c9
Revises: c8f1a2b3d4e5
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c8f1a2b3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account_access_requests",
        sa.Column("whatsapp", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("account_access_requests", "whatsapp")

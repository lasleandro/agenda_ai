"""Add category-aware rates for agenda items without a place.

Revision ID: f8a1c2d3e4f5
Revises: e1a5c8f3d6b9
Create Date: 2026-08-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f8a1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "e1a5c8f3d6b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "professional_financial_settings",
        sa.Column(
            "generic_place_rates",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("professional_financial_settings", "generic_place_rates")

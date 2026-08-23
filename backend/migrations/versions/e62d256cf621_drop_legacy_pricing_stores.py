"""drop_legacy_pricing_stores

Pricing model unification Phase 3: drop the two legacy pricing stores that
Phase 1 (6843aae760e3) backfilled into the unified `place_financial_rates`
table and Phase 2 stopped reading/writing from application code:

- `financial_rates` (the old tenant-wide 4-cell matrix, no time category)
- `professional_financial_settings.generic_place_rates` (the old "no place"
  JSONB matrix)

This is a destructive, data-losing migration by design — all data was
already copied into `place_financial_rates` (place_id IS NULL rows) by the
Phase 1 backfill and verified with scripts/verify_pricing_unification.py.
Downgrade restores the table/column shape only, not the data.

Revision ID: e62d256cf621
Revises: dc0d10e10deb
Create Date: 2026-08-19 23:10:38.798266

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e62d256cf621'
down_revision: Union[str, Sequence[str], None] = 'dc0d10e10deb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("professional_financial_settings", "generic_place_rates")
    op.drop_table("financial_rates")


def downgrade() -> None:
    """Downgrade schema. Restores shape only — data is not recoverable."""
    op.create_table(
        "financial_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column("participant_count", sa.SmallInteger(), nullable=False),
        sa.Column("hourly_rate_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "professional_id",
            "participant_count",
            name="uq_financial_rates_professional_participant_count",
        ),
        sa.CheckConstraint(
            "participant_count BETWEEN 1 AND 4",
            name="ck_financial_rates_participant_count",
        ),
        sa.CheckConstraint(
            "hourly_rate_cents BETWEEN 0 AND 100000000",
            name="ck_financial_rates_hourly_rate_cents",
        ),
    )
    op.add_column(
        "professional_financial_settings",
        sa.Column(
            "generic_place_rates",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )

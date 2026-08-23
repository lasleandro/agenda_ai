"""allow_default_rate_source

Pricing model unification Phase 2: revenue_occurrence_lines.rate_source is
persisted and check-constrained. The unified resolver collapses the retired
"generic"/"tenant" tiers into a single "default" label going forward (see
docs/ROADMAPS/pricing_model_unification_tracking_v0.1_2026-08-19.md, section
9). Historical rows only ever used customer/group/place/tenant/unset (the
"generic" branch was reachable in code but never actually allowed by this
constraint), so no data backfill is required — just widen the constraint.

Revision ID: dc0d10e10deb
Revises: 6843aae760e3
Create Date: 2026-08-19 20:46:29.318614

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc0d10e10deb'
down_revision: Union[str, Sequence[str], None] = '6843aae760e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        "ck_revenue_occurrence_lines_source",
        "revenue_occurrence_lines",
        type_="check",
    )
    op.create_check_constraint(
        "ck_revenue_occurrence_lines_source",
        "revenue_occurrence_lines",
        "rate_source IN ('customer', 'group', 'place', 'default', 'tenant', 'unset')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_revenue_occurrence_lines_source",
        "revenue_occurrence_lines",
        type_="check",
    )
    op.create_check_constraint(
        "ck_revenue_occurrence_lines_source",
        "revenue_occurrence_lines",
        "rate_source IN ('customer', 'group', 'place', 'tenant', 'unset')",
    )

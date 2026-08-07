"""Enable pg_trgm and add trigram indexes for fuzzy name search.

Entity resolution (`app/agent/entity_resolution.py`) previously matched
contact/place names by exact substring only, so a single typo (e.g. "Silva
Tenis" vs. "Silva Tennis") returned zero candidates. This adds trigram
similarity as a fallback match.

Revision ID: b7d2f8a4e915
Revises: a1c4e9f27d63
Create Date: 2026-08-07
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b7d2f8a4e915"
down_revision: Union[str, Sequence[str], None] = "a1c4e9f27d63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX ix_contacts_normalized_name_trgm ON contacts "
        "USING gin (normalized_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_places_normalized_name_trgm ON places "
        "USING gin (normalized_name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_places_normalized_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_contacts_normalized_name_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")

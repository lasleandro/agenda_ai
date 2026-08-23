"""unify_financial_rate_store

Unify the three pricing stores into a single rate matrix:

    rate(professional_id, place_id NULLABLE, time_category, participant_count)

Rows with ``place_id IS NULL`` are the universal default matrix, backfilled
here from the two legacy stores:

1. ``financial_rates`` (global 4-cell, time-agnostic) is mirrored into both
   ``regular`` and ``prime`` default rows per participant count.
2. ``professional_financial_settings.generic_place_rates`` (JSONB) overrides
   the mirrored value per (category, participant_count) cell where present.

Per-place rows already live in this table and move as-is.

Revision ID: 6843aae760e3
Revises: c4e7f9a1b2d3
Create Date: 2026-08-19 16:58:18.892379

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6843aae760e3'
down_revision: Union[str, Sequence[str], None] = 'c4e7f9a1b2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow NULL place_id (universal default rows) and backfill them."""
    op.alter_column("place_financial_rates", "place_id", nullable=True)

    # Postgres treats NULLs as distinct in plain unique constraints, so the
    # existing uq_place_financial_rates_rule cannot guarantee a single default
    # row per (professional_id, time_category, participant_count). This partial
    # unique index enforces the unified resolution invariant.
    op.create_index(
        "uq_place_financial_rates_default",
        "place_financial_rates",
        ["professional_id", "time_category", "participant_count"],
        unique=True,
        postgresql_where=sa.text("place_id IS NULL"),
    )

    conn = op.get_bind()

    # Step 1: mirror the global (time-agnostic) layer into both categories.
    global_rows = conn.execute(
        sa.text(
            "SELECT professional_id, participant_count, hourly_rate_cents "
            "FROM financial_rates"
        )
    ).mappings().all()
    for row in global_rows:
        for category in ("regular", "prime"):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO place_financial_rates
                        (id, professional_id, place_id, time_category,
                         participant_count, hourly_rate_cents)
                    VALUES (:id, :professional_id, NULL, :category,
                            :participant_count, :hourly_rate_cents)
                    ON CONFLICT (professional_id, time_category, participant_count)
                    WHERE place_id IS NULL DO NOTHING
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "professional_id": row["professional_id"],
                    "category": category,
                    "participant_count": row["participant_count"],
                    "hourly_rate_cents": row["hourly_rate_cents"],
                },
            )

    # Step 2: override with explicit generic_place_rates cells where present.
    generic_rows = conn.execute(
        sa.text(
            """
            SELECT professional_id, key, value
            FROM professional_financial_settings,
                 jsonb_each_text(generic_place_rates) AS cells(key, value)
            """
        )
    ).mappings().all()
    for row in generic_rows:
        category, _, participant_count = row["key"].partition("-")
        conn.execute(
            sa.text(
                """
                INSERT INTO place_financial_rates
                    (id, professional_id, place_id, time_category,
                     participant_count, hourly_rate_cents)
                VALUES (:id, :professional_id, NULL, :category,
                        :participant_count, :hourly_rate_cents)
                ON CONFLICT (professional_id, time_category, participant_count)
                WHERE place_id IS NULL
                DO UPDATE SET hourly_rate_cents = EXCLUDED.hourly_rate_cents
                """
            ),
            {
                "id": uuid.uuid4(),
                "professional_id": row["professional_id"],
                "category": category,
                "participant_count": int(participant_count),
                "hourly_rate_cents": int(row["value"]),
            },
        )


def downgrade() -> None:
    """Remove the default rows and restore the NOT NULL constraint."""
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM place_financial_rates WHERE place_id IS NULL")
    )
    op.drop_index(
        "uq_place_financial_rates_default",
        table_name="place_financial_rates",
    )
    op.alter_column("place_financial_rates", "place_id", nullable=False)

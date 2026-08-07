"""Add prime times, place rates, and work journey configuration.

Revision ID: a5c9e2f4b863
Revises: f4b8d1e3a752
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a5c9e2f4b863"
down_revision: Union[str, Sequence[str], None] = "f4b8d1e3a752"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "professional_financial_settings",
        sa.Column(
            "prime_time_configured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "prime_time_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column("days_of_week", postgresql.JSONB(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "end_time > start_time",
            name="ck_prime_time_windows_time_range",
        ),
    )
    op.create_index(
        "ix_prime_time_windows_professional",
        "prime_time_windows",
        ["professional_id"],
    )

    op.create_table(
        "place_financial_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column(
            "place_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("places.id"),
            nullable=False,
        ),
        sa.Column("time_category", sa.String(length=20), nullable=False),
        sa.Column("participant_count", sa.SmallInteger(), nullable=False),
        sa.Column("hourly_rate_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "professional_id",
            "place_id",
            "time_category",
            "participant_count",
            name="uq_place_financial_rates_rule",
        ),
        sa.CheckConstraint(
            "time_category IN ('regular', 'prime')",
            name="ck_place_financial_rates_time_category",
        ),
        sa.CheckConstraint(
            "participant_count BETWEEN 1 AND 4",
            name="ck_place_financial_rates_participant_count",
        ),
        sa.CheckConstraint(
            "hourly_rate_cents BETWEEN 0 AND 100000000",
            name="ck_place_financial_rates_hourly_rate_cents",
        ),
    )
    op.create_index(
        "ix_place_financial_rates_professional_place",
        "place_financial_rates",
        ["professional_id", "place_id"],
    )

    op.create_table(
        "work_journey_intervals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=False),
        sa.Column("interval_type", sa.String(length=20), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "day_of_week BETWEEN 0 AND 6",
            name="ck_work_journey_intervals_day",
        ),
        sa.CheckConstraint(
            "interval_type IN ('work', 'break')",
            name="ck_work_journey_intervals_type",
        ),
        sa.CheckConstraint(
            "end_time > start_time",
            name="ck_work_journey_intervals_time_range",
        ),
    )
    op.create_index(
        "ix_work_journey_intervals_professional_day",
        "work_journey_intervals",
        ["professional_id", "day_of_week"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_work_journey_intervals_professional_day",
        table_name="work_journey_intervals",
    )
    op.drop_table("work_journey_intervals")
    op.drop_index(
        "ix_place_financial_rates_professional_place",
        table_name="place_financial_rates",
    )
    op.drop_table("place_financial_rates")
    op.drop_index(
        "ix_prime_time_windows_professional",
        table_name="prime_time_windows",
    )
    op.drop_table("prime_time_windows")
    op.drop_column("professional_financial_settings", "prime_time_configured")

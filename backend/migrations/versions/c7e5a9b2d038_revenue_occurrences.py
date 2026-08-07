"""Add immutable recognized-revenue occurrence snapshots.

Revision ID: c7e5a9b2d038
Revises: b6d4f8a1c927
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c7e5a9b2d038"
down_revision: Union[str, Sequence[str], None] = "b6d4f8a1c927"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "revenue_occurrences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("source_label_snapshot", sa.String(length=255), nullable=False),
        sa.Column("place_id", postgresql.UUID(as_uuid=True)),
        sa.Column("place_name_snapshot", sa.String(length=255)),
        sa.Column("outcome_status", sa.String(length=20), nullable=False),
        sa.Column("participant_count", sa.Integer(), nullable=False),
        sa.Column("billable_participant_count", sa.Integer(), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="BRL",
        ),
        sa.Column("quoted_total_cents", sa.BigInteger(), nullable=False),
        sa.Column("subtotal_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "adjustment_cents",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.String(length=1000)),
        sa.Column(
            "confirmed_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "professional_id",
            "source_type",
            "source_id",
            "occurrence_date",
            name="uq_revenue_occurrences_source_date",
        ),
        sa.CheckConstraint(
            "source_type IN ('appointment', 'recurring_slot')",
            name="ck_revenue_occurrences_source_type",
        ),
        sa.CheckConstraint(
            "outcome_status IN ('attended', 'no_show', 'cancelled', 'mixed')",
            name="ck_revenue_occurrences_outcome_status",
        ),
        sa.CheckConstraint(
            "quoted_total_cents BETWEEN 0 AND 10000000000",
            name="ck_revenue_occurrences_quoted_total",
        ),
        sa.CheckConstraint(
            "subtotal_cents BETWEEN 0 AND 10000000000",
            name="ck_revenue_occurrences_subtotal",
        ),
        sa.CheckConstraint(
            "adjustment_cents BETWEEN -100000000 AND 100000000",
            name="ck_revenue_occurrences_adjustment",
        ),
        sa.CheckConstraint(
            "total_cents BETWEEN -100000000 AND 10100000000",
            name="ck_revenue_occurrences_total",
        ),
    )
    op.create_index(
        "ix_revenue_occurrences_professional_date",
        "revenue_occurrences",
        ["professional_id", "occurrence_date"],
    )
    op.create_table(
        "revenue_occurrence_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "occurrence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_occurrences.id"),
            nullable=False,
        ),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_name_snapshot", sa.String(length=255), nullable=False),
        sa.Column("attendance_status", sa.String(length=20), nullable=False),
        sa.Column("billable", sa.Boolean(), nullable=False),
        sa.Column("quoted_amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("billed_amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "occurrence_id",
            "contact_id",
            name="uq_revenue_occurrence_participant_contact",
        ),
        sa.CheckConstraint(
            "attendance_status IN ('attended', 'no_show', 'cancelled')",
            name="ck_revenue_occurrence_participants_attendance",
        ),
        sa.CheckConstraint(
            "quoted_amount_cents BETWEEN 0 AND 10000000000",
            name="ck_revenue_occurrence_participants_quoted",
        ),
        sa.CheckConstraint(
            "billed_amount_cents BETWEEN 0 AND 10000000000",
            name="ck_revenue_occurrence_participants_billed",
        ),
    )
    op.create_index(
        "ix_revenue_participants_occurrence",
        "revenue_occurrence_participants",
        ["occurrence_id"],
    )
    op.create_table(
        "revenue_occurrence_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "participant_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_occurrence_participants.id"),
            nullable=False,
        ),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("time_category", sa.String(length=20), nullable=False),
        sa.Column("hourly_rate_cents", sa.Integer()),
        sa.Column("rate_source", sa.String(length=20), nullable=False),
        sa.Column("billable", sa.Boolean(), nullable=False),
        sa.Column("quoted_amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("billed_amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("pricing_context", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "time_category IN ('regular', 'prime')",
            name="ck_revenue_occurrence_lines_category",
        ),
        sa.CheckConstraint(
            "rate_source IN ('customer', 'group', 'place', 'tenant', 'unset')",
            name="ck_revenue_occurrence_lines_source",
        ),
        sa.CheckConstraint(
            "duration_minutes > 0 AND duration_minutes <= 1440",
            name="ck_revenue_occurrence_lines_duration",
        ),
        sa.CheckConstraint(
            "hourly_rate_cents IS NULL OR "
            "hourly_rate_cents BETWEEN 0 AND 100000000",
            name="ck_revenue_occurrence_lines_rate",
        ),
        sa.CheckConstraint(
            "quoted_amount_cents BETWEEN 0 AND 10000000000",
            name="ck_revenue_occurrence_lines_quoted",
        ),
        sa.CheckConstraint(
            "billed_amount_cents BETWEEN 0 AND 10000000000",
            name="ck_revenue_occurrence_lines_billed",
        ),
    )
    op.create_index(
        "ix_revenue_lines_participant",
        "revenue_occurrence_lines",
        ["participant_snapshot_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_revenue_lines_participant",
        table_name="revenue_occurrence_lines",
    )
    op.drop_table("revenue_occurrence_lines")
    op.drop_index(
        "ix_revenue_participants_occurrence",
        table_name="revenue_occurrence_participants",
    )
    op.drop_table("revenue_occurrence_participants")
    op.drop_index(
        "ix_revenue_occurrences_professional_date",
        table_name="revenue_occurrences",
    )
    op.drop_table("revenue_occurrences")

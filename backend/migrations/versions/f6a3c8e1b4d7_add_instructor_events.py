"""Add instructor_events (instructor events roadmap v0.1, Phase 1).

Revision ID: f6a3c8e1b4d7
Revises: e2c6a9f4d7b8
Create Date: 2026-08-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "f6a3c8e1b4d7"
down_revision: Union[str, Sequence[str], None] = "e2c6a9f4d7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instructor_events",
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
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("income_cents", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="confirmed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('confirmed', 'cancelled')",
            name="ck_instructor_events_status",
        ),
        sa.CheckConstraint(
            "end_at > start_at",
            name="ck_instructor_events_time_range",
        ),
        sa.CheckConstraint(
            "income_cents IS NULL OR income_cents BETWEEN 0 AND 100000000",
            name="ck_instructor_events_income_cents",
        ),
    )
    op.create_index(
        "ix_instructor_events_professional_id_start_at",
        "instructor_events",
        ["professional_id", "start_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_instructor_events_professional_id_start_at", table_name="instructor_events"
    )
    op.drop_table("instructor_events")

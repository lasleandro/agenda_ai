"""Add waitlist_entries (waitlist roadmap v0.1, Phase 1).

Revision ID: c1e5a8f3b7d9
Revises: b7d2f4a1e6c3
Create Date: 2026-08-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c1e5a8f3b7d9"
down_revision: Union[str, Sequence[str], None] = "b7d2f4a1e6c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "waitlist_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id"),
            nullable=False,
        ),
        sa.Column(
            "place_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("places.id"),
            nullable=True,
        ),
        sa.Column("desired_date", sa.Date(), nullable=False),
        sa.Column("desired_start_time", sa.Time(), nullable=False),
        sa.Column("desired_end_time", sa.Time(), nullable=False),
        sa.Column("class_type", sa.String(length=50), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fulfilled_appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'matched', 'fulfilled', 'cancelled', 'expired')",
            name="ck_waitlist_entries_status",
        ),
        sa.CheckConstraint(
            "class_type IS NULL OR class_type IN ('individual', 'group')",
            name="ck_waitlist_entries_class_type",
        ),
        sa.CheckConstraint(
            "desired_end_time > desired_start_time",
            name="ck_waitlist_entries_time_range",
        ),
    )
    op.create_index(
        "ix_waitlist_entries_professional_id_status",
        "waitlist_entries",
        ["professional_id", "status"],
    )
    op.create_index(
        "ix_waitlist_entries_contact_id",
        "waitlist_entries",
        ["contact_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_waitlist_entries_contact_id", table_name="waitlist_entries")
    op.drop_index("ix_waitlist_entries_professional_id_status", table_name="waitlist_entries")
    op.drop_table("waitlist_entries")

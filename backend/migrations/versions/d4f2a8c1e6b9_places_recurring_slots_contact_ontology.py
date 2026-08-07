"""Customer ontology: Place, RecurringSlot, RecurringSlotParticipant, Contact enrichment.

Revision ID: d4f2a8c1e6b9
Revises: c2b8e91a4d70
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d4f2a8c1e6b9"
down_revision: Union[str, Sequence[str], None] = "c2b8e91a4d70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "places",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address_line", sa.String(length=500)),
        sa.Column("city", sa.String(length=255)),
        sa.Column("state", sa.String(length=100)),
        sa.Column("postal_code", sa.String(length=20)),
        sa.Column("country", sa.String(length=100)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "recurring_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column(
            "place_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("places.id"), nullable=False
        ),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("label", sa.String(length=255)),
        sa.Column("class_type", sa.String(length=50), server_default="individual"),
        sa.Column("max_participants", sa.Integer(), server_default="1"),
        sa.Column("status", sa.String(length=50), server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "recurring_slot_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recurring_slot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recurring_slots.id"),
            nullable=False,
        ),
        sa.Column(
            "contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("recurring_slot_id", "contact_id", name="uq_slot_participant"),
    )

    op.add_column("contacts", sa.Column("level", sa.String(length=50)))
    op.add_column("contacts", sa.Column("address_line", sa.String(length=500)))
    op.add_column("contacts", sa.Column("city", sa.String(length=255)))
    op.add_column("contacts", sa.Column("state", sa.String(length=100)))
    op.add_column("contacts", sa.Column("postal_code", sa.String(length=20)))
    op.add_column("contacts", sa.Column("country", sa.String(length=100)))
    op.add_column("contacts", sa.Column("latitude", sa.Float()))
    op.add_column("contacts", sa.Column("longitude", sa.Float()))
    op.add_column(
        "contacts",
        sa.Column(
            "home_place_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("places.id"), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("contacts", "home_place_id")
    op.drop_column("contacts", "longitude")
    op.drop_column("contacts", "latitude")
    op.drop_column("contacts", "country")
    op.drop_column("contacts", "postal_code")
    op.drop_column("contacts", "state")
    op.drop_column("contacts", "city")
    op.drop_column("contacts", "address_line")
    op.drop_column("contacts", "level")

    op.drop_table("recurring_slot_participants")
    op.drop_table("recurring_slots")
    op.drop_table("places")

"""Add slot_kind/valid range/group_name, Place.normalized_name, and entity_aliases.

Operational ontology roadmap v0.2, Phase 0 (semantic hardening): makes
today's implicit "empty recurring slot == availability" rule an explicit,
persisted field, and adds the naming infrastructure entity resolution needs.

Revision ID: d1a4c8e6b930
Revises: c7e5a9b2d038
Create Date: 2026-08-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d1a4c8e6b930"
down_revision: Union[str, Sequence[str], None] = "c7e5a9b2d038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recurring_slots",
        sa.Column(
            "slot_kind",
            sa.String(length=20),
            nullable=False,
            server_default="availability",
        ),
    )
    op.add_column("recurring_slots", sa.Column("valid_from", sa.Date()))
    op.add_column("recurring_slots", sa.Column("valid_until", sa.Date()))
    op.add_column("recurring_slots", sa.Column("group_name", sa.String(length=255)))
    op.create_check_constraint(
        "ck_recurring_slots_slot_kind",
        "recurring_slots",
        "slot_kind IN ('availability', 'class')",
    )
    op.create_check_constraint(
        "ck_recurring_slots_valid_range",
        "recurring_slots",
        "valid_from IS NULL OR valid_until IS NULL OR valid_until >= valid_from",
    )

    # Backfill: a slot with at least one participant is a class; this mirrors
    # the implicit rule financial_capacity.py and recurring_slots.py used
    # before slot_kind existed.
    op.execute(
        """
        UPDATE recurring_slots
        SET slot_kind = 'class'
        WHERE id IN (
            SELECT DISTINCT recurring_slot_id FROM recurring_slot_participants
        )
        """
    )

    op.add_column(
        "places",
        sa.Column("normalized_name", sa.String(length=255), nullable=True),
    )
    op.execute("UPDATE places SET normalized_name = lower(trim(name))")
    op.alter_column("places", "normalized_name", nullable=False)

    op.create_table(
        "entity_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "entity_type IN ('contact', 'place', 'recurring_slot')",
            name="ck_entity_aliases_entity_type",
        ),
        sa.UniqueConstraint(
            "professional_id",
            "entity_type",
            "normalized_alias",
            name="uq_entity_aliases_professional_type_normalized",
        ),
    )


def downgrade() -> None:
    op.drop_table("entity_aliases")

    op.drop_column("places", "normalized_name")

    op.drop_constraint("ck_recurring_slots_valid_range", "recurring_slots", type_="check")
    op.drop_constraint("ck_recurring_slots_slot_kind", "recurring_slots", type_="check")
    op.drop_column("recurring_slots", "group_name")
    op.drop_column("recurring_slots", "valid_until")
    op.drop_column("recurring_slots", "valid_from")
    op.drop_column("recurring_slots", "slot_kind")

"""Enforce place-stay versus recurring-class invariants.

Revision ID: a2f7c9e4d6b1
Revises: f8a1c2d3e4f5
Create Date: 2026-08-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2f7c9e4d6b1"
down_revision: Union[str, Sequence[str], None] = "f8a1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "recurring_slots",
        "class_type",
        existing_type=sa.String(length=50),
        nullable=False,
        server_default="individual",
    )
    op.alter_column(
        "recurring_slots",
        "max_participants",
        existing_type=sa.Integer(),
        nullable=False,
        server_default="1",
    )
    op.create_check_constraint(
        "ck_recurring_slots_class_type",
        "recurring_slots",
        "class_type IN ('individual', 'group')",
    )
    op.create_check_constraint(
        "ck_recurring_slots_max_participants",
        "recurring_slots",
        "max_participants BETWEEN 1 AND 4",
    )
    op.create_check_constraint(
        "ck_recurring_slots_availability_neutral",
        "recurring_slots",
        "slot_kind = 'class' OR (class_type = 'individual' "
        "AND max_participants = 1 AND level IS NULL AND group_name IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_recurring_slots_availability_neutral",
        "recurring_slots",
        type_="check",
    )
    op.drop_constraint(
        "ck_recurring_slots_max_participants",
        "recurring_slots",
        type_="check",
    )
    op.drop_constraint(
        "ck_recurring_slots_class_type",
        "recurring_slots",
        type_="check",
    )
    op.alter_column(
        "recurring_slots",
        "max_participants",
        existing_type=sa.Integer(),
        nullable=True,
        server_default="1",
    )
    op.alter_column(
        "recurring_slots",
        "class_type",
        existing_type=sa.String(length=50),
        nullable=True,
        server_default="individual",
    )

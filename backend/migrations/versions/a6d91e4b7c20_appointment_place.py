"""Associate appointments with their booked place.

Revision ID: a6d91e4b7c20
Revises: d4f2a8c1e6b9
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a6d91e4b7c20"
down_revision: Union[str, Sequence[str], None] = "d4f2a8c1e6b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("place_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_appointments_place_id_places",
        "appointments",
        "places",
        ["place_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_appointments_place_id_places",
        "appointments",
        type_="foreignkey",
    )
    op.drop_column("appointments", "place_id")

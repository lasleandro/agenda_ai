"""Preserve authentication audit history when a user is removed.

Revision ID: c4e2d6b9a711
Revises: f9c3a7e2b4d1
Create Date: 2026-09-01
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c4e2d6b9a711"
down_revision: Union[str, Sequence[str], None] = "f9c3a7e2b4d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "auth_security_events_user_id_fkey",
        "auth_security_events",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "auth_security_events_user_id_fkey",
        "auth_security_events",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "auth_security_events_user_id_fkey",
        "auth_security_events",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "auth_security_events_user_id_fkey",
        "auth_security_events",
        "users",
        ["user_id"],
        ["id"],
    )

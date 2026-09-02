"""Require a password hash for active accounts.

Revision ID: a7d8b2e9f401
Revises: c4e2d6b9a711
Create Date: 2026-09-01
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a7d8b2e9f401"
down_revision: Union[str, Sequence[str], None] = "c4e2d6b9a711"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_users_active_requires_password",
        "users",
        "status <> 'active' OR hashed_password IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_active_requires_password", "users", type_="check")

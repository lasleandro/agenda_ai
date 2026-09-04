"""Add the platform account-access request lifecycle.

Revision ID: c8f1a2b3d4e5
Revises: b4c7e1d9a2f6
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c8f1a2b3d4e5"
down_revision: Union[str, Sequence[str], None] = "b4c7e1d9a2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_access_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposed_tenant_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_reason", sa.String(length=500), nullable=True),
        sa.Column("professional_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_account_access_requests_status",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND reviewed_at IS NULL "
            "AND reviewed_by_user_id IS NULL AND professional_id IS NULL "
            "AND owner_user_id IS NULL) OR "
            "(status = 'approved' AND reviewed_at IS NOT NULL "
            "AND reviewed_by_user_id IS NOT NULL AND professional_id IS NOT NULL "
            "AND owner_user_id IS NOT NULL) OR "
            "(status = 'rejected' AND reviewed_at IS NOT NULL "
            "AND reviewed_by_user_id IS NOT NULL AND professional_id IS NULL "
            "AND owner_user_id IS NULL)",
            name="ck_account_access_requests_state",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["professional_id"], ["professionals.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_account_access_requests_professional",
        "account_access_requests",
        ["professional_id"],
        unique=False,
    )
    op.create_index(
        "ix_account_access_requests_status_submitted",
        "account_access_requests",
        ["status", "submitted_at", "id"],
        unique=False,
    )
    op.create_index(
        "uq_account_access_requests_pending_email",
        "account_access_requests",
        ["email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_account_access_requests_pending_email",
        table_name="account_access_requests",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index(
        "ix_account_access_requests_status_submitted",
        table_name="account_access_requests",
    )
    op.drop_index(
        "ix_account_access_requests_professional",
        table_name="account_access_requests",
    )
    op.drop_table("account_access_requests")


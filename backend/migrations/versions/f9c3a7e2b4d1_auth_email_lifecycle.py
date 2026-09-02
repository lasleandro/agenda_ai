"""Add verified activation, password-reset, and durable email records.

Revision ID: f9c3a7e2b4d1
Revises: f2b9a1c8d3e7
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "f9c3a7e2b4d1"
down_revision: Union[str, Sequence[str], None] = "f2b9a1c8d3e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "hashed_password", existing_type=sa.String(length=255), nullable=True)
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("auth_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("users", "auth_version", server_default=None)
    op.execute("UPDATE users SET email = lower(trim(email))")
    op.create_check_constraint(
        "ck_users_status",
        "users",
        "status IN ('pending_activation', 'active', 'disabled')",
    )
    op.create_index("uq_users_email_canonical", "users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "auth_action_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('account_activation', 'password_reset')",
            name="ck_auth_action_tokens_purpose",
        ),
    )
    op.create_index(
        "ix_auth_action_tokens_user_purpose",
        "auth_action_tokens",
        ["user_id", "purpose"],
    )

    op.create_table(
        "email_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=100)),
        sa.Column("last_error_detail", sa.Text()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('account_activation', 'password_reset', 'password_changed_notice')",
            name="ck_email_deliveries_purpose",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'retry_wait', 'sent', 'failed', 'suppressed')",
            name="ck_email_deliveries_status",
        ),
    )
    op.create_index(
        "ix_email_deliveries_status_next_attempt",
        "email_deliveries",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "uq_email_deliveries_active_user_purpose",
        "email_deliveries",
        ["user_id", "purpose"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'processing', 'retry_wait')"),
    )

    op.create_table(
        "auth_security_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("email_digest", sa.String(length=64)),
        sa.Column("ip_digest", sa.String(length=64)),
        sa.Column("metadata_json", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_auth_security_events_event_email_created",
        "auth_security_events",
        ["event_type", "email_digest", "created_at"],
    )
    op.create_index(
        "ix_auth_security_events_event_ip_created",
        "auth_security_events",
        ["event_type", "ip_digest", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_security_events_event_ip_created", table_name="auth_security_events")
    op.drop_index("ix_auth_security_events_event_email_created", table_name="auth_security_events")
    op.drop_table("auth_security_events")
    op.drop_index("uq_email_deliveries_active_user_purpose", table_name="email_deliveries")
    op.drop_index("ix_email_deliveries_status_next_attempt", table_name="email_deliveries")
    op.drop_table("email_deliveries")
    op.drop_index("ix_auth_action_tokens_user_purpose", table_name="auth_action_tokens")
    op.drop_table("auth_action_tokens")
    op.drop_index("uq_users_email_canonical", table_name="users")
    op.drop_constraint("ck_users_status", "users", type_="check")
    op.drop_column("users", "auth_version")
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "email_verified_at")
    op.alter_column("users", "hashed_password", existing_type=sa.String(length=255), nullable=False)

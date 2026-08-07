"""Add commercial overrides, global rates, and financial audit.

Revision ID: f4b8d1e3a752
Revises: e3a7c9d2f641
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f4b8d1e3a752"
down_revision: Union[str, Sequence[str], None] = "e3a7c9d2f641"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("commercial_status", sa.String(length=20)))
    op.add_column("contacts", sa.Column("hourly_rate_cents", sa.Integer()))
    op.create_check_constraint(
        "ck_contacts_commercial_status",
        "contacts",
        "commercial_status IS NULL OR commercial_status IN ('active', 'waiting', 'paused')",
    )
    op.create_check_constraint(
        "ck_contacts_hourly_rate_cents",
        "contacts",
        "hourly_rate_cents IS NULL OR hourly_rate_cents BETWEEN 0 AND 100000000",
    )

    op.add_column("recurring_slots", sa.Column("commercial_status", sa.String(length=20)))
    op.add_column("recurring_slots", sa.Column("hourly_rate_cents", sa.Integer()))
    op.create_check_constraint(
        "ck_recurring_slots_commercial_status",
        "recurring_slots",
        "commercial_status IS NULL OR commercial_status IN ('active', 'waiting', 'paused')",
    )
    op.create_check_constraint(
        "ck_recurring_slots_hourly_rate_cents",
        "recurring_slots",
        "hourly_rate_cents IS NULL OR hourly_rate_cents BETWEEN 0 AND 100000000",
    )

    op.create_table(
        "professional_financial_settings",
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            primary_key=True,
        ),
        sa.Column(
            "default_commercial_status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="BRL"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "default_commercial_status IN ('active', 'waiting', 'paused')",
            name="ck_professional_financial_settings_status",
        ),
    )
    op.create_table(
        "financial_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column("participant_count", sa.SmallInteger(), nullable=False),
        sa.Column("hourly_rate_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "professional_id",
            "participant_count",
            name="uq_financial_rates_professional_participant_count",
        ),
        sa.CheckConstraint(
            "participant_count BETWEEN 1 AND 4",
            name="ck_financial_rates_participant_count",
        ),
        sa.CheckConstraint(
            "hourly_rate_cents BETWEEN 0 AND 100000000",
            name="ck_financial_rates_hourly_rate_cents",
        ),
    )
    op.create_table(
        "financial_change_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_ip", sa.String(length=64)),
        sa.Column("user_agent", sa.String(length=512)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_financial_change_audit_logs_professional_created",
        "financial_change_audit_logs",
        ["professional_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_change_audit_logs_professional_created",
        table_name="financial_change_audit_logs",
    )
    op.drop_table("financial_change_audit_logs")
    op.drop_table("financial_rates")
    op.drop_table("professional_financial_settings")

    op.drop_constraint(
        "ck_recurring_slots_hourly_rate_cents",
        "recurring_slots",
        type_="check",
    )
    op.drop_constraint(
        "ck_recurring_slots_commercial_status",
        "recurring_slots",
        type_="check",
    )
    op.drop_column("recurring_slots", "hourly_rate_cents")
    op.drop_column("recurring_slots", "commercial_status")

    op.drop_constraint(
        "ck_contacts_hourly_rate_cents",
        "contacts",
        type_="check",
    )
    op.drop_constraint(
        "ck_contacts_commercial_status",
        "contacts",
        type_="check",
    )
    op.drop_column("contacts", "hourly_rate_cents")
    op.drop_column("contacts", "commercial_status")

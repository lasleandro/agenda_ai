"""webhook receipts ledger

Durable receipt per verified inbound provider webhook, so acknowledgement is
decoupled from ingestion/LLM/outbound work and byte-identical retries are
idempotent.

Revision ID: 35214a28e1d5
Revises: a1b2c3d4e5f6
Create Date: 2026-09-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "35214a28e1d5"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_receipts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_key", sa.String(length=50), nullable=False),
        sa.Column("event_key", sa.String(length=200), nullable=False),
        sa.Column("raw_body", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="received"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('received', 'processing', 'done', 'failed', 'dead')",
            name="ck_webhook_receipts_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", name="uq_webhook_receipts_event_key"),
    )
    op.create_index(
        "ix_webhook_receipts_status_claimed_at",
        "webhook_receipts",
        ["status", "claimed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_receipts_status_claimed_at", table_name="webhook_receipts")
    op.drop_table("webhook_receipts")

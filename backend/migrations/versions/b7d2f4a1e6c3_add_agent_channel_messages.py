"""Add agent_channel_messages (AI Agent Operations Roadmap v0.1, Phase 3).

Revision ID: b7d2f4a1e6c3
Revises: a4b7e0f9c2d1
Create Date: 2026-08-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "b7d2f4a1e6c3"
down_revision: Union[str, Sequence[str], None] = "a4b7e0f9c2d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_channel_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "professional_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professionals.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_agent_channel_messages_role"),
    )
    op.create_index(
        "ix_agent_channel_messages_professional_id_created_at",
        "agent_channel_messages",
        ["professional_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_channel_messages_professional_id_created_at",
        table_name="agent_channel_messages",
    )
    op.drop_table("agent_channel_messages")

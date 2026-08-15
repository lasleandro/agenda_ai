"""Add durable ambiguity-escalation delivery state.

Revision ID: e1a5c8f3d6b9
Revises: d9f7a1c4e2b8
Create Date: 2026-08-12
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "e1a5c8f3d6b9"
down_revision: Union[str, Sequence[str], None] = "d9f7a1c4e2b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "passive_escalations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("appointment_candidate_id", sa.UUID(), sa.ForeignKey("appointment_candidates.id"), nullable=False, unique=True),
        sa.Column("professional_id", sa.UUID(), sa.ForeignKey("professionals.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(500)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('queued', 'sent', 'failed', 'expired')", name="ck_passive_escalations_status"),
    )
    op.create_index("ix_passive_escalations_due", "passive_escalations", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_passive_escalations_due", table_name="passive_escalations")
    op.drop_table("passive_escalations")

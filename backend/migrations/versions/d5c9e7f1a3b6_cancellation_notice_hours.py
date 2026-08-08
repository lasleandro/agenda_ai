"""Add cancellation_notice_hours to ProfessionalFinancialSettings.

Revision ID: d5c9e7f1a3b6
Revises: c93a1f6e0b48
Create Date: 2026-08-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5c9e7f1a3b6"
down_revision: Union[str, Sequence[str], None] = "c93a1f6e0b48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "professional_financial_settings",
        sa.Column(
            "cancellation_notice_hours",
            sa.Integer(),
            nullable=False,
            server_default="24",
        ),
    )
    op.create_check_constraint(
        "ck_professional_financial_settings_notice_hours",
        "professional_financial_settings",
        "cancellation_notice_hours >= 0 AND cancellation_notice_hours <= 168",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_professional_financial_settings_notice_hours",
        "professional_financial_settings",
        type_="check",
    )
    op.drop_column("professional_financial_settings", "cancellation_notice_hours")

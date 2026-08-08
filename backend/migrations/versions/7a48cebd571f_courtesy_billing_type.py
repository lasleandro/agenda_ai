"""courtesy_billing_type

Revision ID: 7a48cebd571f
Revises: e6b2d8f4a1c5
Create Date: 2026-08-07 21:12:53.722048

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '7a48cebd571f'
down_revision: Union[str, Sequence[str], None] = 'e6b2d8f4a1c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'appointments',
        sa.Column(
            'billing_type',
            sa.String(length=20),
            nullable=False,
            server_default='billable',
        ),
    )
    op.create_check_constraint(
        'ck_appointments_billing_type',
        'appointments',
        "billing_type IN ('billable', 'courtesy')",
    )
    op.add_column(
        'revenue_occurrence_participants',
        sa.Column(
            'non_billable_reason',
            sa.String(length=50),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_constraint('ck_appointments_billing_type', 'appointments', type_='check')
    op.drop_column('appointments', 'billing_type')
    op.drop_column('revenue_occurrence_participants', 'non_billable_reason')

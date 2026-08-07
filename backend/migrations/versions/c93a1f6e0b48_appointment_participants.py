"""Add class_type to appointments and appointment_participants table.

Lets a one-off Appointment gain additional participants (e.g. "add Larissa
to Leandro's class tomorrow at 15h" via the instructor agent), turning it
into a group session. Mirrors RecurringSlot.class_type /
RecurringSlotParticipant.

Revision ID: c93a1f6e0b48
Revises: b7d2f8a4e915
Create Date: 2026-08-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c93a1f6e0b48"
down_revision: Union[str, Sequence[str], None] = "b7d2f8a4e915"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "class_type", sa.String(length=50), nullable=False, server_default="individual"
        ),
    )
    op.create_check_constraint(
        "ck_appointments_class_type",
        "appointments",
        "class_type IN ('individual', 'group')",
    )

    op.create_table(
        "appointment_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.UniqueConstraint(
            "appointment_id", "contact_id", name="uq_appointment_participant"
        ),
    )


def downgrade() -> None:
    op.drop_table("appointment_participants")
    op.drop_constraint("ck_appointments_class_type", "appointments", type_="check")
    op.drop_column("appointments", "class_type")

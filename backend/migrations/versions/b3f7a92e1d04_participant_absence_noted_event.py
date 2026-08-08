"""Add schedule.participant.absence_noted to OperationalEvent types.

Backs propose_note_participant_absence — lets a single group-class
participant be marked absent (and, if eligible, earn a make-up credit)
without cancelling the occurrence for the rest of the group.

Revision ID: b3f7a92e1d04
Revises: 7a48cebd571f
Create Date: 2026-08-08
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b3f7a92e1d04"
down_revision: Union[str, Sequence[str], None] = "7a48cebd571f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_EVENT_TYPES = (
    "agent.action.proposed",
    "agent.action.confirmed",
    "agent.action.rejected",
    "agent.action.expired",
    "agent.action.executed",
    "agent.action.failed",
    "schedule.appointment.created",
    "schedule.appointment.updated",
    "schedule.appointment.cancelled",
    "schedule.series.created",
    "schedule.series.updated",
    "schedule.series.deactivated",
    "schedule.occurrence.cancelled",
    "schedule.occurrence.rescheduled",
    "schedule.participant.added",
    "schedule.participant.removed",
    "contact.updated",
    "place.created",
    "place.updated",
    "place.deactivated",
    "assistant.settings.updated",
    "makeup_credit.granted",
    "makeup_credit.redeemed",
    "makeup_credit.expired",
)
_NEW_EVENT_TYPES = _OLD_EVENT_TYPES + ("schedule.participant.absence_noted",)

_OLD_CONSTRAINT_SQL = (
    "event_type IN (" + ", ".join(f"'{t}'" for t in _OLD_EVENT_TYPES) + ")"
)
_NEW_CONSTRAINT_SQL = (
    "event_type IN (" + ", ".join(f"'{t}'" for t in _NEW_EVENT_TYPES) + ")"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_operational_events_event_type", "operational_events", type_="check"
    )
    op.create_check_constraint(
        "ck_operational_events_event_type", "operational_events", _NEW_CONSTRAINT_SQL
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_operational_events_event_type", "operational_events", type_="check"
    )
    op.create_check_constraint(
        "ck_operational_events_event_type", "operational_events", _OLD_CONSTRAINT_SQL
    )

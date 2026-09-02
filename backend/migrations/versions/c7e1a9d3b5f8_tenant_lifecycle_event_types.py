"""Allow tenant lifecycle event types in the OperationalEvent ledger.

Revision ID: c7e1a9d3b5f8
Revises: b3d9f4a1c8e2
Create Date: 2026-09-01
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c7e1a9d3b5f8"
down_revision: Union[str, Sequence[str], None] = "b3d9f4a1c8e2"
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
    "scheduled_task.configuration.updated",
    "makeup_credit.granted",
    "makeup_credit.redeemed",
    "makeup_credit.expired",
    "schedule.participant.absence_noted",
    "waitlist.entry.added",
    "waitlist.entry.cancelled",
    "waitlist.entry.fulfilled",
    "instructor_event.created",
)

_TENANT_EVENT_TYPES = (
    "tenant.suspended",
    "tenant.reactivated",
    "tenant.archived",
    "tenant.restored",
    "tenant.impersonated_while_inactive",
)

_NEW_EVENT_TYPES = _OLD_EVENT_TYPES + _TENANT_EVENT_TYPES

_OLD_CONSTRAINT_SQL = "event_type IN (" + ", ".join(f"'{t}'" for t in _OLD_EVENT_TYPES) + ")"
_NEW_CONSTRAINT_SQL = "event_type IN (" + ", ".join(f"'{t}'" for t in _NEW_EVENT_TYPES) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_operational_events_event_type", "operational_events", type_="check")
    op.create_check_constraint(
        "ck_operational_events_event_type", "operational_events", _NEW_CONSTRAINT_SQL
    )


def downgrade() -> None:
    op.drop_constraint("ck_operational_events_event_type", "operational_events", type_="check")
    op.create_check_constraint(
        "ck_operational_events_event_type", "operational_events", _OLD_CONSTRAINT_SQL
    )

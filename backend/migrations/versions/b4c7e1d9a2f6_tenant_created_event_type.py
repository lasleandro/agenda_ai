"""Allow tenant creation events in the operational ledger.

Revision ID: b4c7e1d9a2f6
Revises: a3d9e6c4b2f1
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b4c7e1d9a2f6"
down_revision: Union[str, Sequence[str], None] = "a3d9e6c4b2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CURRENT_EVENT_TYPES = (
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
    "contact.created",
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
    "tenant.suspended",
    "tenant.reactivated",
    "tenant.archived",
    "tenant.restored",
    "tenant.impersonated_while_inactive",
)
_NEW_EVENT_TYPES = _CURRENT_EVENT_TYPES + ("tenant.created",)


def _event_check_sql(event_types: tuple[str, ...]) -> str:
    return "event_type IN (" + ", ".join(f"'{event_type}'" for event_type in event_types) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_operational_events_event_type", "operational_events", type_="check")
    op.create_check_constraint(
        "ck_operational_events_event_type",
        "operational_events",
        _event_check_sql(_NEW_EVENT_TYPES),
    )


def downgrade() -> None:
    op.drop_constraint("ck_operational_events_event_type", "operational_events", type_="check")
    op.create_check_constraint(
        "ck_operational_events_event_type",
        "operational_events",
        _event_check_sql(_CURRENT_EVENT_TYPES),
    )

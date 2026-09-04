"""Enforce canonical tenant-scoped customer phone identity.

Revision ID: a3d9e6c4b2f1
Revises: 35214a28e1d5
Create Date: 2026-09-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.services.phone_numbers import PhoneNumberValidationError, normalize_mobile_phone


revision: str = "a3d9e6c4b2f1"
down_revision: Union[str, Sequence[str], None] = "35214a28e1d5"
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
    "tenant.suspended",
    "tenant.reactivated",
    "tenant.archived",
    "tenant.restored",
    "tenant.impersonated_while_inactive",
)
_NEW_EVENT_TYPES = _OLD_EVENT_TYPES + ("contact.created",)


def _event_check_sql(event_types: tuple[str, ...]) -> str:
    return "event_type IN (" + ", ".join(f"'{event_type}'" for event_type in event_types) + ")"


def _normalize_existing_phones() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, professional_id, phone FROM contacts ORDER BY id")
    ).mappings()
    normalized_by_identity: dict[tuple[object, str], object] = {}
    updates: list[dict[str, object]] = []

    for row in rows:
        phone = row["phone"]
        if phone is None:
            raise RuntimeError(f"Contact {row['id']} has no phone number")
        try:
            normalized_phone = normalize_mobile_phone(phone)
        except PhoneNumberValidationError as exc:
            raise RuntimeError(f"Contact {row['id']} has an invalid phone number") from exc

        identity = (row["professional_id"], normalized_phone)
        existing_id = normalized_by_identity.get(identity)
        if existing_id is not None:
            raise RuntimeError(
                "Contacts cannot be migrated because tenant-scoped phone identity "
                f"collides between {existing_id} and {row['id']}"
            )
        normalized_by_identity[identity] = row["id"]
        updates.append({"id": row["id"], "phone": normalized_phone})

    for update in updates:
        bind.execute(
            sa.text("UPDATE contacts SET phone = :phone WHERE id = :id"),
            update,
        )


def upgrade() -> None:
    _normalize_existing_phones()
    op.alter_column(
        "contacts",
        "phone",
        existing_type=sa.String(length=50),
        type_=sa.String(length=16),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_contacts_phone_e164",
        "contacts",
        r"phone ~ '^\+[1-9][0-9]{7,14}$'",
    )
    op.create_unique_constraint(
        "uq_contacts_professional_phone",
        "contacts",
        ["professional_id", "phone"],
    )
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
        _event_check_sql(_OLD_EVENT_TYPES),
    )
    op.drop_constraint("uq_contacts_professional_phone", "contacts", type_="unique")
    op.drop_constraint("ck_contacts_phone_e164", "contacts", type_="check")
    op.alter_column(
        "contacts",
        "phone",
        existing_type=sa.String(length=16),
        type_=sa.String(length=50),
        nullable=True,
    )

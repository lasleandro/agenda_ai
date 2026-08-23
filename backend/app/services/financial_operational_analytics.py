"""Read-only operational aggregates used by the Financeiro overview."""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentParticipant,
    Contact,
    InstructorEvent,
    MakeupClassCredit,
    OperationalEvent,
    RecurringSlotParticipant,
    ScheduleOccurrenceOverride,
)
from app.schemas.financial import (
    FinancialClassOutcomesDetail,
    FinancialCustomerRankingDetail,
    FinancialInstructorEventOutcomesDetail,
    FinancialOperationalAnalyticsDetail,
    FinancialPeriodDetail,
)
from app.services.scheduling import TIMEZONE, list_schedule_occurrences


@dataclass
class CustomerOutcomeCounts:
    contact_name: str
    scheduled_count: int = 0
    executed_count: int = 0
    canceled_count: int = 0

    @property
    def outcome_count(self) -> int:
        return self.scheduled_count + self.executed_count + self.canceled_count

    @property
    def cancellation_rate_pct(self) -> float:
        if self.outcome_count == 0:
            return 0
        return round(self.canceled_count / self.outcome_count * 100, 1)


def _customer_ranking(
    contact_id: uuid.UUID,
    counts: CustomerOutcomeCounts,
) -> FinancialCustomerRankingDetail:
    return FinancialCustomerRankingDetail(
        contact_id=contact_id,
        contact_name=counts.contact_name,
        executed_count=counts.executed_count,
        scheduled_count=counts.scheduled_count,
        canceled_count=counts.canceled_count,
        cancellation_rate_pct=counts.cancellation_rate_pct,
    )


def _cancelled_participants(
    db: Session,
    professional_id: uuid.UUID,
    overrides: list[ScheduleOccurrenceOverride],
) -> dict[uuid.UUID, list[tuple[uuid.UUID, str]]]:
    """Return each cancelled override's roster without exposing contact PII."""
    recurring_ids = {
        override.recurring_slot_id
        for override in overrides
        if override.recurring_slot_id is not None
    }
    appointment_ids = {
        override.appointment_id
        for override in overrides
        if override.appointment_id is not None
    }
    participants: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)

    if recurring_ids:
        rows = (
            db.query(RecurringSlotParticipant.recurring_slot_id, Contact.id, Contact.display_name)
            .join(Contact, RecurringSlotParticipant.contact_id == Contact.id)
            .filter(
                RecurringSlotParticipant.recurring_slot_id.in_(recurring_ids),
                Contact.professional_id == professional_id,
            )
            .all()
        )
        for slot_id, contact_id, contact_name in rows:
            participants[slot_id].append((contact_id, contact_name))

    if appointment_ids:
        primary_rows = (
            db.query(Appointment.id, Contact.id, Contact.display_name)
            .join(Contact, Appointment.contact_id == Contact.id)
            .filter(
                Appointment.id.in_(appointment_ids),
                Appointment.professional_id == professional_id,
            )
            .all()
        )
        extra_rows = (
            db.query(AppointmentParticipant.appointment_id, Contact.id, Contact.display_name)
            .join(Contact, AppointmentParticipant.contact_id == Contact.id)
            .join(Appointment, AppointmentParticipant.appointment_id == Appointment.id)
            .filter(
                AppointmentParticipant.appointment_id.in_(appointment_ids),
                Appointment.professional_id == professional_id,
                Contact.professional_id == professional_id,
            )
            .all()
        )
        for appointment_id, contact_id, contact_name in [*primary_rows, *extra_rows]:
            participants[appointment_id].append((contact_id, contact_name))

    return participants


def _cancelled_with_makeup_ids(
    db: Session,
    professional_id: uuid.UUID,
    overrides: list[ScheduleOccurrenceOverride],
) -> set[uuid.UUID]:
    """Identify class cancellations that produced at least one makeup credit.

    Credits retain the cancellation event as their immutable origin. The
    ScheduleOccurrenceOverride is current-state data, so the event payload is
    used to bind the two records by parent and original occurrence date.
    """
    parent_ids = {
        override.appointment_id or override.recurring_slot_id for override in overrides
    }
    events = (
        db.query(OperationalEvent)
        .filter(
            OperationalEvent.professional_id == professional_id,
            OperationalEvent.event_type == "schedule.occurrence.cancelled",
            OperationalEvent.entity_id.in_(parent_ids),
        )
        .all()
        if parent_ids
        else []
    )
    event_by_key = {
        (event.entity_id, event.payload.get("occurrence_date")): event.id
        for event in events
    }
    event_ids = set(event_by_key.values())
    credit_event_ids = {
        event_id
        for (event_id,) in (
            db.query(MakeupClassCredit.origin_event_id)
            .filter(
                MakeupClassCredit.professional_id == professional_id,
                MakeupClassCredit.origin_event_id.in_(event_ids),
            )
            .all()
        )
    }
    return {
        override.id
        for override in overrides
        if event_by_key.get(
            (
                override.appointment_id or override.recurring_slot_id,
                override.occurrence_date.isoformat(),
            )
        )
        in credit_event_ids
    }


def build_financial_operational_analytics(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> FinancialOperationalAnalyticsDetail:
    """Build bounded class-outcome and customer aggregates for one tenant."""
    customers: dict[uuid.UUID, CustomerOutcomeCounts] = {}
    scheduled_count = 0
    executed_count = 0
    today = datetime.now(TIMEZONE).date()
    for occurrence in list_schedule_occurrences(
        db, professional_id, date_from, date_to
    ):
        is_executed = occurrence.occurrence_date < today
        if is_executed:
            executed_count += 1
        else:
            scheduled_count += 1
        for participant in occurrence.participants:
            customer = customers.setdefault(
                participant.contact_id,
                CustomerOutcomeCounts(contact_name=participant.contact_name),
            )
            if is_executed:
                customer.executed_count += 1
            else:
                customer.scheduled_count += 1

    cancelled = (
        db.query(ScheduleOccurrenceOverride)
        .filter(
            ScheduleOccurrenceOverride.professional_id == professional_id,
            ScheduleOccurrenceOverride.override_type == "cancelled",
            ScheduleOccurrenceOverride.occurrence_date.between(date_from, date_to),
        )
        .all()
    )
    cancelled_with_makeup_ids = _cancelled_with_makeup_ids(
        db, professional_id, cancelled
    )
    cancelled_participants = _cancelled_participants(db, professional_id, cancelled)
    for override in cancelled:
        parent_id = override.appointment_id or override.recurring_slot_id
        for contact_id, contact_name in cancelled_participants.get(parent_id, []):
            customer = customers.setdefault(
                contact_id, CustomerOutcomeCounts(contact_name=contact_name)
            )
            customer.canceled_count += 1

    period_start = datetime.combine(date_from, datetime.min.time(), tzinfo=TIMEZONE)
    period_end = datetime.combine(date_to, datetime.max.time(), tzinfo=TIMEZONE)
    today_start = datetime.combine(today, datetime.min.time(), tzinfo=TIMEZONE)
    confirmed_events = (
        db.query(InstructorEvent)
        .filter(
            InstructorEvent.professional_id == professional_id,
            InstructorEvent.status == "confirmed",
            InstructorEvent.start_at >= period_start,
            InstructorEvent.start_at <= period_end,
        )
        .all()
    )
    canceled_event_count = (
        db.query(InstructorEvent)
        .filter(
            InstructorEvent.professional_id == professional_id,
            InstructorEvent.status == "cancelled",
            InstructorEvent.start_at >= period_start,
            InstructorEvent.start_at <= period_end,
        )
        .count()
    )

    ranked = [
        _customer_ranking(contact_id, counts)
        for contact_id, counts in customers.items()
    ]
    most_frequent = sorted(
        ranked,
        key=lambda row: (-row.executed_count, -row.scheduled_count, row.contact_name.casefold()),
    )[:5]
    highest_cancellation_rate = sorted(
        (row for row in ranked if row.executed_count + row.scheduled_count + row.canceled_count >= 3),
        key=lambda row: (-row.cancellation_rate_pct, -row.canceled_count, row.contact_name.casefold()),
    )[:5]

    return FinancialOperationalAnalyticsDetail(
        period=FinancialPeriodDetail(date_from=date_from, date_to=date_to),
        class_outcomes=FinancialClassOutcomesDetail(
            total_scheduled_count=scheduled_count + executed_count + len(cancelled),
            upcoming_count=scheduled_count,
            executed_count=executed_count,
            canceled_with_makeup_count=len(cancelled_with_makeup_ids),
            canceled_without_makeup_count=len(cancelled) - len(cancelled_with_makeup_ids),
        ),
        instructor_event_outcomes=FinancialInstructorEventOutcomesDetail(
            scheduled_count=len(confirmed_events),
            completed_count=sum(event.start_at < today_start for event in confirmed_events),
            canceled_count=canceled_event_count,
            confirmed_income_cents=sum(event.income_cents or 0 for event in confirmed_events),
        ),
        most_frequent_customers=most_frequent,
        highest_cancellation_rate_customers=highest_cancellation_rate,
    )

"""
Scheduling domain service (operational ontology roadmap v0.2, Phase 1).

The single place that expands Appointment + RecurringSlot(slot_kind="class")
records into dated calendar occurrences, merges in
ScheduleOccurrenceOverride exceptions, and provides the pure interval-math
primitives used to compute availability. Financial capacity/pricing
(`financial_capacity.py`) and revenue confirmation (`revenue_occurrences.py`)
both consume this module rather than re-deriving occurrences themselves.

Overrides are matched by their parent's own (unmodified) `occurrence_date`.
A reschedule is only reflected here when the query window
`[date_from, date_to]` contains that original date — moving an occurrence to
a date outside the queried window will not yet surface it at the new date in
a separate query for that window. Full cross-window reschedule indexing is
deferred to the calendar-mutation phase of the roadmap, once there is a
mutation UX to exercise it against.
"""

import dataclasses
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentParticipant,
    Contact,
    Place,
    RecurringSlot,
    RecurringSlotParticipant,
    ScheduleOccurrenceOverride,
)

TIMEZONE = ZoneInfo("America/Sao_Paulo")

APPOINTMENT_ACTIVE_STATUSES = ("tentative", "confirmed", "completed")


# ---------------------------------------------------------------------------
# Interval math (pure, no DB access)
# ---------------------------------------------------------------------------

def time_to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def iter_dates(date_from: date, date_to: date):
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)


def weekly_dates(
    starts_on: date,
    weekday: int,
    date_from: date,
    date_to: date,
    *,
    ends_on: date | None = None,
) -> list[date]:
    first_allowed = max(starts_on, date_from)
    last_allowed = min(ends_on, date_to) if ends_on is not None else date_to
    if first_allowed > last_allowed:
        return []
    offset = (weekday - first_allowed.weekday()) % 7
    first = first_allowed + timedelta(days=offset)
    if first > last_allowed:
        return []
    return list(iter_dates(first, last_allowed))[::7]


def split_range(
    start_minute: int,
    end_minute: int,
    boundaries: set[int],
) -> list[tuple[int, int]]:
    points = sorted(
        {start_minute, end_minute}
        | {
            boundary
            for boundary in boundaries
            if start_minute < boundary < end_minute
        }
    )
    return list(zip(points, points[1:]))


def subtract_ranges(
    ranges: list[tuple[int, int]],
    exclusions: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    remaining = ranges
    for exclusion_start, exclusion_end in exclusions:
        next_ranges: list[tuple[int, int]] = []
        for start, end in remaining:
            if exclusion_end <= start or exclusion_start >= end:
                next_ranges.append((start, end))
                continue
            if start < exclusion_start:
                next_ranges.append((start, exclusion_start))
            if exclusion_end < end:
                next_ranges.append((exclusion_end, end))
        remaining = next_ranges
    return remaining


def intersect_ranges(
    first: list[tuple[int, int]],
    second: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    intersections = []
    for first_start, first_end in first:
        for second_start, second_end in second:
            start = max(first_start, second_start)
            end = min(first_end, second_end)
            if start < end:
                intersections.append((start, end))
    return intersections


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = (previous_start, max(previous_end, end))
    return merged


def _load_place_availability_ranges(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
    selected_place_ids: set[uuid.UUID],
) -> dict[tuple[date, uuid.UUID], list[tuple[int, int]]]:
    if not selected_place_ids:
        return {}
    slots = (
        db.query(RecurringSlot)
        .filter(
            RecurringSlot.professional_id == professional_id,
            RecurringSlot.place_id.in_(selected_place_ids),
            RecurringSlot.status == "active",
            RecurringSlot.slot_kind == "availability",
        )
        .all()
    )
    availability: dict[
        tuple[date, uuid.UUID],
        list[tuple[int, int]],
    ] = {}
    for slot in slots:
        if slot.recurrence_type == "weekly":
            dates = weekly_dates(
                slot.valid_from or slot.created_at.astimezone(TIMEZONE).date(),
                slot.day_of_week,
                date_from,
                date_to,
                ends_on=slot.valid_until,
            )
        elif slot.scheduled_date and date_from <= slot.scheduled_date <= date_to:
            dates = [slot.scheduled_date]
        else:
            dates = []
        for local_date in dates:
            availability.setdefault((local_date, slot.place_id), []).append(
                (
                    time_to_minutes(slot.start_time),
                    time_to_minutes(slot.end_time),
                )
            )
    return availability


# ---------------------------------------------------------------------------
# Schedule occurrence projection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScheduleParticipant:
    contact_id: uuid.UUID
    contact_name: str
    hourly_rate_cents: int | None


@dataclass(frozen=True)
class ScheduleOccurrence:
    source_type: str  # "appointment" | "recurring_slot"
    source_id: uuid.UUID
    occurrence_date: date
    starts_at: datetime
    ends_at: datetime
    source_label: str
    place_id: uuid.UUID | None
    place_name: str | None
    group_hourly_rate_cents: int | None
    participants: list[ScheduleParticipant]
    status: str
    class_type: str | None = None
    # Only set for source_type == "appointment" — how the booking was made
    # (dashboard/ai_detected/...). None for recurring_slot occurrences.
    appointment_source: str | None = None
    billing_type: str | None = None
    is_exception: bool = False


def _appointment_occurrences(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
    local_timezone: ZoneInfo,
    statuses: tuple[str, ...] = APPOINTMENT_ACTIVE_STATUSES,
) -> list[ScheduleOccurrence]:
    end_boundary = datetime.combine(
        date_to + timedelta(days=1),
        time.min,
        tzinfo=local_timezone,
    )
    rows = (
        db.query(Appointment, Contact, Place.name)
        .join(Contact, Appointment.contact_id == Contact.id)
        .outerjoin(Place, Appointment.place_id == Place.id)
        .filter(
            Appointment.professional_id == professional_id,
            Appointment.status.in_(statuses),
            or_(
                Appointment.start_at < end_boundary,
                Appointment.recurrence_rule == "FREQ=WEEKLY",
            ),
        )
        .all()
    )
    appointment_ids = [appointment.id for appointment, _, _ in rows]
    extra_participants_by_appointment: dict[uuid.UUID, list[ScheduleParticipant]] = {}
    if appointment_ids:
        extra_rows = (
            db.query(AppointmentParticipant.appointment_id, Contact)
            .join(Contact, AppointmentParticipant.contact_id == Contact.id)
            .filter(AppointmentParticipant.appointment_id.in_(appointment_ids))
            .order_by(Contact.display_name)
            .all()
        )
        for appointment_id, extra_contact in extra_rows:
            extra_participants_by_appointment.setdefault(appointment_id, []).append(
                ScheduleParticipant(
                    contact_id=extra_contact.id,
                    contact_name=extra_contact.display_name,
                    hourly_rate_cents=extra_contact.hourly_rate_cents,
                )
            )

    occurrences = []
    for appointment, contact, place_name in rows:
        local_start = appointment.start_at.astimezone(local_timezone)
        duration = appointment.end_at - appointment.start_at
        if duration.total_seconds() <= 0 or duration > timedelta(days=1):
            continue
        if appointment.recurrence_rule == "FREQ=WEEKLY":
            dates = weekly_dates(
                local_start.date(),
                local_start.weekday(),
                date_from,
                date_to,
            )
        elif date_from <= local_start.date() <= date_to:
            dates = [local_start.date()]
        else:
            dates = []
        for occurrence_date in dates:
            starts_at = datetime.combine(
                occurrence_date,
                local_start.time().replace(tzinfo=None),
                tzinfo=local_timezone,
            )
            occurrences.append(
                ScheduleOccurrence(
                    source_type="appointment",
                    source_id=appointment.id,
                    occurrence_date=occurrence_date,
                    starts_at=starts_at,
                    ends_at=starts_at + duration,
                    source_label=appointment.service,
                    place_id=appointment.place_id,
                    place_name=place_name,
                    group_hourly_rate_cents=None,
                    participants=[
                        ScheduleParticipant(
                            contact_id=contact.id,
                            contact_name=contact.display_name,
                            hourly_rate_cents=contact.hourly_rate_cents,
                        ),
                        *extra_participants_by_appointment.get(appointment.id, []),
                    ],
                    status=appointment.status,
                    class_type=appointment.class_type,
                    appointment_source=appointment.source,
                    billing_type=appointment.billing_type,
                )
            )
    return occurrences


def _slot_occurrences(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
    local_timezone: ZoneInfo,
) -> list[ScheduleOccurrence]:
    slot_rows = (
        db.query(RecurringSlot, Place.name)
        .join(Place, RecurringSlot.place_id == Place.id)
        .filter(
            RecurringSlot.professional_id == professional_id,
            RecurringSlot.status == "active",
        )
        .all()
    )
    slot_ids = [slot.id for slot, _ in slot_rows]
    participant_rows = (
        db.query(RecurringSlotParticipant.recurring_slot_id, Contact)
        .join(Contact, RecurringSlotParticipant.contact_id == Contact.id)
        .filter(
            RecurringSlotParticipant.recurring_slot_id.in_(slot_ids),
            Contact.professional_id == professional_id,
        )
        .order_by(Contact.display_name)
        .all()
        if slot_ids
        else []
    )
    participants_by_slot: dict[uuid.UUID, list[ScheduleParticipant]] = {}
    for slot_id, contact in participant_rows:
        participants_by_slot.setdefault(slot_id, []).append(
            ScheduleParticipant(
                contact_id=contact.id,
                contact_name=contact.display_name,
                hourly_rate_cents=contact.hourly_rate_cents,
            )
        )

    occurrences = []
    for slot, place_name in slot_rows:
        participants = participants_by_slot.get(slot.id, [])
        if slot.slot_kind != "class" or not participants:
            continue
        if slot.recurrence_type == "weekly":
            dates = weekly_dates(
                slot.valid_from or slot.created_at.astimezone(local_timezone).date(),
                slot.day_of_week,
                date_from,
                date_to,
                ends_on=slot.valid_until,
            )
        elif slot.scheduled_date and date_from <= slot.scheduled_date <= date_to:
            dates = [slot.scheduled_date]
        else:
            dates = []
        for occurrence_date in dates:
            starts_at = datetime.combine(
                occurrence_date,
                slot.start_time,
                tzinfo=local_timezone,
            )
            ends_at = datetime.combine(
                occurrence_date,
                slot.end_time,
                tzinfo=local_timezone,
            )
            occurrences.append(
                ScheduleOccurrence(
                    source_type="recurring_slot",
                    source_id=slot.id,
                    occurrence_date=occurrence_date,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    source_label=slot.group_name or slot.label or "Grupo",
                    place_id=slot.place_id,
                    place_name=place_name,
                    group_hourly_rate_cents=slot.hourly_rate_cents,
                    participants=participants,
                    status="scheduled",
                    class_type=slot.class_type,
                )
            )
    return occurrences


def _apply_overrides(
    db: Session,
    professional_id: uuid.UUID,
    occurrences: list[ScheduleOccurrence],
    local_timezone: ZoneInfo,
) -> list[ScheduleOccurrence]:
    if not occurrences:
        return occurrences
    overrides = (
        db.query(ScheduleOccurrenceOverride)
        .filter(ScheduleOccurrenceOverride.professional_id == professional_id)
        .all()
    )
    if not overrides:
        return occurrences

    override_by_key: dict[
        tuple[str, uuid.UUID, date], ScheduleOccurrenceOverride
    ] = {}
    for override in overrides:
        source_type = "appointment" if override.appointment_id else "recurring_slot"
        source_id = override.appointment_id or override.recurring_slot_id
        override_by_key[(source_type, source_id, override.occurrence_date)] = override

    place_names: dict[uuid.UUID, str] | None = None
    result: list[ScheduleOccurrence] = []
    for occurrence in occurrences:
        override = override_by_key.get(
            (occurrence.source_type, occurrence.source_id, occurrence.occurrence_date)
        )
        if override is None:
            result.append(occurrence)
            continue
        if override.override_type == "cancelled":
            continue

        place_id = override.replacement_place_id or occurrence.place_id
        place_name = occurrence.place_name
        if (
            override.replacement_place_id is not None
            and override.replacement_place_id != occurrence.place_id
        ):
            if place_names is None:
                place_names = {
                    place.id: place.name
                    for place in db.query(Place).filter(
                        Place.professional_id == professional_id
                    )
                }
            place_name = place_names.get(place_id, place_name)

        new_start = override.replacement_start_at.astimezone(local_timezone)
        new_end = override.replacement_end_at.astimezone(local_timezone)
        result.append(
            dataclasses.replace(
                occurrence,
                occurrence_date=new_start.date(),
                starts_at=new_start,
                ends_at=new_end,
                place_id=place_id,
                place_name=place_name,
                is_exception=True,
            )
        )
    return result


def list_schedule_occurrences(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
    statuses: tuple[str, ...] = APPOINTMENT_ACTIVE_STATUSES,
    local_timezone: ZoneInfo | None = None,
    include_rescheduled_replacements: bool = False,
) -> list[ScheduleOccurrence]:
    """Project tenant schedule occurrences in the supplied local timezone.

    When requested, rescheduled occurrences are also projected from their
    original date when the replacement falls within the queried window. Daily
    agenda queries need this view; existing calendar/detail callers retain
    their original-occurrence semantics by default.
    """
    timezone = local_timezone or TIMEZONE
    occurrences = _appointment_occurrences(
        db,
        professional_id,
        date_from,
        date_to,
        timezone,
        statuses,
    ) + _slot_occurrences(
        db,
        professional_id,
        date_from,
        date_to,
        timezone,
    )

    if include_rescheduled_replacements:
        start_boundary = datetime.combine(date_from, time.min, tzinfo=timezone)
        end_boundary = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone)
        replacement_origin_dates = {
            occurrence_date
            for (occurrence_date,) in (
                db.query(ScheduleOccurrenceOverride.occurrence_date)
                .filter(
                    ScheduleOccurrenceOverride.professional_id == professional_id,
                    ScheduleOccurrenceOverride.override_type == "rescheduled",
                    ScheduleOccurrenceOverride.replacement_start_at >= start_boundary,
                    ScheduleOccurrenceOverride.replacement_start_at < end_boundary,
                )
                .all()
            )
            if occurrence_date < date_from or occurrence_date > date_to
        }
        for origin_date in replacement_origin_dates:
            occurrences.extend(
                _appointment_occurrences(
                    db,
                    professional_id,
                    origin_date,
                    origin_date,
                    timezone,
                    statuses,
                )
            )
            occurrences.extend(
                _slot_occurrences(
                    db,
                    professional_id,
                    origin_date,
                    origin_date,
                    timezone,
                )
            )
        occurrences = list(
            {
                (occurrence.source_type, occurrence.source_id, occurrence.occurrence_date): occurrence
                for occurrence in occurrences
            }.values()
        )

    occurrences = _apply_overrides(db, professional_id, occurrences, timezone)
    if include_rescheduled_replacements:
        occurrences = [
            occurrence
            for occurrence in occurrences
            if date_from <= occurrence.starts_at.astimezone(timezone).date() <= date_to
        ]
    return sorted(
        occurrences,
        key=lambda occurrence: (
            occurrence.starts_at,
            occurrence.source_type,
            str(occurrence.source_id),
        ),
    )


def get_schedule_occurrence(
    db: Session,
    professional_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
    occurrence_date: date,
) -> ScheduleOccurrence | None:
    return next(
        (
            occurrence
            for occurrence in list_schedule_occurrences(
                db,
                professional_id,
                occurrence_date,
                occurrence_date,
            )
            if occurrence.source_type == source_type
            and occurrence.source_id == source_id
        ),
        None,
    )

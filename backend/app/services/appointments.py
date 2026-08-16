"""Appointment creation and conflict checks (operational ontology roadmap
v0.2, Phase 5) — moved out of `app.api.calendar` so the API and the
instructor agent's mutation tools share the same checks instead of risking
divergence. Callers own the transaction (commit after calling)."""

import uuid
from datetime import datetime, timedelta, timezone as dt_timezone

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentTransition,
    InstructorEvent,
    RecurringSlot,
    RecurringSlotParticipant,
    WorkJourneyInterval,
)
from app.services.place_stays import resolve_place_stay

TZ_SP = dt_timezone(timedelta(hours=-3))  # America/Sao_Paulo


def has_scheduled_class_overlap(
    db: Session,
    professional_id: uuid.UUID,
    *,
    start_at: datetime,
    end_at: datetime,
    is_recurring: bool,
) -> bool:
    local_start = start_at.astimezone(TZ_SP)
    local_end = end_at.astimezone(TZ_SP)
    if is_recurring:
        recurrence_filter = or_(
            RecurringSlot.recurrence_type == "weekly",
            and_(
                RecurringSlot.recurrence_type == "once",
                RecurringSlot.scheduled_date >= local_start.date(),
            ),
        )
    else:
        recurrence_filter = or_(
            RecurringSlot.recurrence_type == "weekly",
            and_(
                RecurringSlot.recurrence_type == "once",
                RecurringSlot.scheduled_date == local_start.date(),
            ),
        )

    return (
        db.query(RecurringSlot)
        .join(
            RecurringSlotParticipant,
            RecurringSlotParticipant.recurring_slot_id == RecurringSlot.id,
        )
        .filter(
            RecurringSlot.professional_id == professional_id,
            RecurringSlot.status == "active",
            RecurringSlot.slot_kind == "class",
            RecurringSlot.day_of_week == local_start.weekday(),
            RecurringSlot.start_time < local_end.time().replace(tzinfo=None),
            RecurringSlot.end_time > local_start.time().replace(tzinfo=None),
            recurrence_filter,
        )
        .first()
        is not None
    )


def has_appointment_overlap(
    db: Session,
    professional_id: uuid.UUID,
    *,
    start_at: datetime,
    end_at: datetime,
    is_recurring: bool,
) -> bool:
    query = db.query(Appointment).filter(
        Appointment.professional_id == professional_id,
        Appointment.status.in_(["tentative", "confirmed"]),
    )
    if is_recurring:
        candidate_rows = query.filter(
            or_(
                Appointment.recurrence_rule == "FREQ=WEEKLY",
                Appointment.start_at >= start_at,
            )
        ).all()
    else:
        candidate_rows = query.filter(
            or_(
                and_(
                    Appointment.start_at < end_at,
                    Appointment.end_at > start_at,
                ),
                and_(
                    Appointment.recurrence_rule == "FREQ=WEEKLY",
                    Appointment.start_at <= start_at,
                ),
            )
        ).all()

    requested_start = start_at.astimezone(TZ_SP)
    requested_end = end_at.astimezone(TZ_SP)
    for appointment in candidate_rows:
        if appointment.recurrence_rule is None and not is_recurring:
            return True

        existing_start = appointment.start_at.astimezone(TZ_SP)
        existing_end = appointment.end_at.astimezone(TZ_SP)
        if existing_start.weekday() != requested_start.weekday():
            continue
        if existing_start.time() >= requested_end.time():
            continue
        if existing_end.time() <= requested_start.time():
            continue
        return True
    return False


def assert_within_work_journey(
    db: Session,
    professional_id: uuid.UUID,
    *,
    start_at: datetime,
    end_at: datetime,
) -> None:
    """Reject a one-off appointment outside the professional's configured
    work journey (Financeiro > Jornada de trabalho) — the screen that data
    comes from states it feeds capacity calculations, so appointment
    creation should actually honor it instead of only the financial
    capacity report.

    A professional who has never configured a journey (zero rows, of any
    weekday) is left unrestricted — this only starts enforcing once they've
    actually set working hours, so onboarding isn't blocked by a screen
    they haven't visited yet."""
    has_any_journey = (
        db.query(WorkJourneyInterval.professional_id)
        .filter(WorkJourneyInterval.professional_id == professional_id)
        .first()
        is not None
    )
    if not has_any_journey:
        return

    local_start = start_at.astimezone(TZ_SP)
    local_end = end_at.astimezone(TZ_SP)
    start_time = local_start.time()
    end_time = local_end.time()

    intervals = (
        db.query(WorkJourneyInterval)
        .filter(
            WorkJourneyInterval.professional_id == professional_id,
            WorkJourneyInterval.day_of_week == local_start.weekday(),
        )
        .all()
    )

    within_work = any(
        interval.interval_type == "work"
        and interval.start_time <= start_time
        and end_time <= interval.end_time
        for interval in intervals
    )
    if not within_work:
        raise HTTPException(
            status_code=409,
            detail="This time is outside the professional's configured work journey",
        )

    overlaps_break = any(
        interval.interval_type == "break"
        and start_time < interval.end_time
        and end_time > interval.start_time
        for interval in intervals
    )
    if overlaps_break:
        raise HTTPException(status_code=409, detail="This time overlaps a configured break")


def has_event_overlap(
    db: Session,
    professional_id: uuid.UUID,
    *,
    start_at: datetime,
    end_at: datetime,
) -> bool:
    """InstructorEvent never recurs, so this is a plain interval overlap —
    no weekday/recurrence-rule handling needed, unlike the two checks
    above (instructor events roadmap v0.1)."""
    return (
        db.query(InstructorEvent)
        .filter(
            InstructorEvent.professional_id == professional_id,
            InstructorEvent.status == "confirmed",
            InstructorEvent.start_at < end_at,
            InstructorEvent.end_at > start_at,
        )
        .first()
        is not None
    )


def assert_no_conflict(
    db: Session,
    professional_id: uuid.UUID,
    *,
    start_at: datetime,
    end_at: datetime,
    is_recurring: bool = False,
) -> None:
    assert_within_work_journey(db, professional_id, start_at=start_at, end_at=end_at)
    if has_appointment_overlap(
        db, professional_id, start_at=start_at, end_at=end_at, is_recurring=is_recurring
    ):
        raise HTTPException(status_code=409, detail="This time overlaps another appointment")
    if has_event_overlap(db, professional_id, start_at=start_at, end_at=end_at):
        raise HTTPException(status_code=409, detail="This time overlaps an instructor event")
    if has_scheduled_class_overlap(
        db, professional_id, start_at=start_at, end_at=end_at, is_recurring=is_recurring
    ):
        raise HTTPException(status_code=409, detail="This time overlaps a scheduled class")


def create_appointment(
    db: Session,
    professional_id: uuid.UUID,
    *,
    contact_id: uuid.UUID,
    place_id: uuid.UUID | None,
    service: str,
    start_at: datetime,
    end_at: datetime,
    is_recurring: bool = False,
    class_type: str = "individual",
    source: str = "dashboard",
    actor: str = "system",
    billing_type: str = "billable",
) -> Appointment:
    resolution = resolve_place_stay(
        db,
        professional_id,
        start_at=start_at,
        end_at=end_at,
        requested_place_id=place_id,
    )
    if resolution.outcome == "invalid_place":
        raise HTTPException(status_code=404, detail="Place not found")
    if resolution.place_id is None:
        raise HTTPException(
            status_code=409,
            detail="Select a place: this time has no unique covering place stay",
        )

    assert_no_conflict(
        db, professional_id, start_at=start_at, end_at=end_at, is_recurring=is_recurring
    )

    appointment = Appointment(
        professional_id=professional_id,
        contact_id=contact_id,
        place_id=resolution.place_id,
        service=service.strip(),
        start_at=start_at,
        end_at=end_at,
        status="confirmed",
        source=source,
        recurrence_rule="FREQ=WEEKLY" if is_recurring else None,
        class_type=class_type,
        billing_type=billing_type,
    )
    db.add(appointment)
    db.flush()
    db.add(
        AppointmentTransition(
            appointment_id=appointment.id,
            previous_status=None,
            new_status="confirmed",
            action="create",
            actor=actor,
            metadata_={
                "place_id": str(resolution.place_id),
                "place_resolution": {
                    "stay_id": str(resolution.stay_id) if resolution.stay_id else None,
                    "explicit_exception": resolution.is_explicit_exception,
                },
            },
        )
    )
    db.flush()
    return appointment

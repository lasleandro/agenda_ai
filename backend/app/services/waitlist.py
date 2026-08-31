"""Waitlist ("Fila de Espera") service — waitlist roadmap v0.1, Phase 1.

Shared creation/listing/cancellation logic used by both the dashboard REST
API (app/api/waitlist.py) and the instructor-agent tools
(app/agent/mutations.py's propose_add_waitlist_entry/propose_remove_waitlist_entry),
so validation can't diverge between the two entry points.
"""

import uuid
from datetime import date, datetime, time

from sqlalchemy.orm import Session

from app.models import Contact, Place, RecurringSlot, WaitlistEntry
from app.services import recurring_slot_occurrence_participants
from app.services import participants as recurring_participants
from app.services import financial_capacity
from app.services.scheduling import (
    TIMEZONE,
    get_schedule_occurrence,
    list_schedule_occurrences,
)


class WaitlistValidationError(Exception):
    pass


def create_entry(
    db: Session,
    professional_id: uuid.UUID,
    *,
    contact_id: uuid.UUID,
    desired_date: date,
    desired_start_time: time,
    desired_end_time: time,
    place_id: uuid.UUID | None = None,
    class_type: str | None = None,
    duration_minutes: int | None = None,
    note: str | None = None,
) -> WaitlistEntry:
    contact = (
        db.query(Contact)
        .filter(Contact.id == contact_id, Contact.professional_id == professional_id)
        .first()
    )
    if contact is None:
        raise WaitlistValidationError("Contact not found")

    if place_id is not None:
        place = (
            db.query(Place)
            .filter(Place.id == place_id, Place.professional_id == professional_id)
            .first()
        )
        if place is None:
            raise WaitlistValidationError("Place not found")

    if desired_end_time <= desired_start_time:
        raise WaitlistValidationError("desired_end_time must be after desired_start_time")

    resolved_duration = duration_minutes or (
        (desired_end_time.hour * 60 + desired_end_time.minute)
        - (desired_start_time.hour * 60 + desired_start_time.minute)
    )

    entry = WaitlistEntry(
        professional_id=professional_id,
        contact_id=contact_id,
        place_id=place_id,
        desired_date=desired_date,
        desired_start_time=desired_start_time,
        desired_end_time=desired_end_time,
        class_type=class_type,
        duration_minutes=resolved_duration,
        note=note,
    )
    db.add(entry)
    db.commit()
    return entry


def list_entries(
    db: Session,
    professional_id: uuid.UUID,
    *,
    status: str | None = None,
    place_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
) -> list[WaitlistEntry]:
    query = db.query(WaitlistEntry).filter(WaitlistEntry.professional_id == professional_id)
    if status is not None:
        query = query.filter(WaitlistEntry.status == status)
    if place_id is not None:
        query = query.filter(WaitlistEntry.place_id == place_id)
    if contact_id is not None:
        query = query.filter(WaitlistEntry.contact_id == contact_id)
    return query.order_by(WaitlistEntry.desired_date, WaitlistEntry.desired_start_time).all()


def get_entry(
    db: Session, professional_id: uuid.UUID, entry_id: uuid.UUID
) -> WaitlistEntry | None:
    return (
        db.query(WaitlistEntry)
        .filter(WaitlistEntry.id == entry_id, WaitlistEntry.professional_id == professional_id)
        .first()
    )


def lock_entry(
    db: Session, professional_id: uuid.UUID, entry_id: uuid.UUID
) -> WaitlistEntry | None:
    """Tenant-scoped row lock for atomic fulfillment — the caller must already
    be inside a transaction (the instructor-agent candidate executor is)."""
    return (
        db.query(WaitlistEntry)
        .filter(WaitlistEntry.id == entry_id, WaitlistEntry.professional_id == professional_id)
        .with_for_update()
        .first()
    )


def entry_fits_free_time(
    db: Session,
    professional_id: uuid.UUID,
    entry: WaitlistEntry,
    place_id: uuid.UUID,
) -> bool:
    """Whether the entry's exact desired time still fits a genuinely free
    range at the given place — reused by the appointment fulfillment executor
    so it never books a waitlist demand into a slot that is no longer free."""
    place = (
        db.query(Place)
        .filter(Place.id == place_id, Place.professional_id == professional_id)
        .first()
    )
    if place is None:
        return False
    free_by_place = financial_capacity.compute_free_ranges_by_place(
        db, professional_id, entry.desired_date, [place]
    )
    desired_start = entry.desired_start_time.hour * 60 + entry.desired_start_time.minute
    desired_end = entry.desired_end_time.hour * 60 + entry.desired_end_time.minute
    return any(
        start <= desired_start and end >= desired_end
        for start, end in free_by_place.get(place_id, [])
    )


def cancel_entry(db: Session, professional_id: uuid.UUID, entry_id: uuid.UUID) -> WaitlistEntry:
    entry = get_entry(db, professional_id, entry_id)
    if entry is None:
        raise WaitlistValidationError("Waitlist entry not found")
    if entry.status not in ("open", "matched"):
        raise WaitlistValidationError(
            f"Entry is not cancellable (status={entry.status})"
        )
    entry.status = "cancelled"
    db.commit()
    return entry


def fulfill_entry(
    db: Session,
    professional_id: uuid.UUID,
    entry_id: uuid.UUID,
    appointment_id: uuid.UUID,
    *,
    commit: bool = True,
) -> WaitlistEntry:
    """Mark an entry fulfilled once its contact has actually been booked —
    e.g. the Agenda screen's "click the ghost card to book" shortcut
    (waitlist roadmap v0.1, Phase 3). Distinct from cancel_entry: fulfilled
    means the demand was met, not abandoned.

    `commit=False` lets the instructor-agent candidate executor keep this
    state transition inside its own transaction."""
    entry = get_entry(db, professional_id, entry_id)
    if entry is None:
        raise WaitlistValidationError("Waitlist entry not found")
    if entry.status not in ("open", "matched"):
        raise WaitlistValidationError(f"Entry is not fulfillable (status={entry.status})")
    entry.status = "fulfilled"
    entry.fulfilled_appointment_id = appointment_id
    if commit:
        db.commit()
    else:
        db.flush()
    return entry


def load_group_fulfillment(
    db: Session,
    professional_id: uuid.UUID,
    *,
    entry_id: uuid.UUID,
    recurring_slot_id: uuid.UUID,
    occurrence_date: date,
    enrollment_scope: str,
) -> tuple[WaitlistEntry, RecurringSlot, object, Contact]:
    entry = get_entry(db, professional_id, entry_id)
    if entry is None:
        raise WaitlistValidationError("Waitlist entry not found")
    if entry.status not in ("open", "matched"):
        raise WaitlistValidationError(
            f"Entry is not fulfillable (status={entry.status})"
        )
    if entry.class_type not in (None, "group"):
        raise WaitlistValidationError("Waitlist entry does not accept a group class")
    if occurrence_date != entry.desired_date:
        raise WaitlistValidationError("Group occurrence date must match the waitlist request")
    if enrollment_scope not in {"occurrence", "series"}:
        raise WaitlistValidationError("Enrollment scope must be occurrence or series")

    slot = (
        db.query(RecurringSlot)
        .filter(
            RecurringSlot.id == recurring_slot_id,
            RecurringSlot.professional_id == professional_id,
        )
        .first()
    )
    if slot is None:
        raise WaitlistValidationError("Recurring group not found")
    occurrence = get_schedule_occurrence(
        db, professional_id, "recurring_slot", slot.id, occurrence_date
    )
    if occurrence is None:
        raise WaitlistValidationError("Scheduled group occurrence not found")
    if occurrence.class_type != "group":
        raise WaitlistValidationError("Scheduled occurrence is not a group class")
    if entry.place_id is not None and entry.place_id != occurrence.place_id:
        raise WaitlistValidationError("Group occurrence is at a different place")
    if (
        occurrence.starts_at.time() > entry.desired_start_time
        or occurrence.ends_at.time() < entry.desired_end_time
    ):
        raise WaitlistValidationError("Group occurrence does not cover the requested time")
    if occurrence.available_seats <= 0:
        raise WaitlistValidationError("Group occurrence has no available seats")

    contact = (
        db.query(Contact)
        .filter(Contact.id == entry.contact_id, Contact.professional_id == professional_id)
        .first()
    )
    if contact is None:
        raise WaitlistValidationError("Waitlist contact not found")
    return entry, slot, occurrence, contact


def fulfill_group_occurrence(
    db: Session,
    professional_id: uuid.UUID,
    *,
    entry_id: uuid.UUID,
    recurring_slot_id: uuid.UUID,
    occurrence_date: date,
    enrollment_scope: str,
) -> WaitlistEntry:
    """Enroll a waiting contact in one compatible recurring group occurrence.

    The caller must choose occurrence or series explicitly. The caller owns
    the commit so enrollment and audit logging stay atomic.
    """
    entry, slot, _occurrence, contact = load_group_fulfillment(
        db,
        professional_id,
        entry_id=entry_id,
        recurring_slot_id=recurring_slot_id,
        occurrence_date=occurrence_date,
        enrollment_scope=enrollment_scope,
    )
    if enrollment_scope == "occurrence":
        recurring_slot_occurrence_participants.add_participant(
            db, professional_id, slot, contact, occurrence_date
        )
    else:
        recurring_participants.add_participant(db, professional_id, slot, contact)
    entry.status = "fulfilled"
    entry.fulfilled_appointment_id = None
    entry.fulfilled_recurring_slot_id = slot.id
    entry.fulfilled_occurrence_date = occurrence_date
    entry.fulfillment_scope = enrollment_scope
    db.flush()
    return entry


def find_matches(
    db: Session,
    professional_id: uuid.UUID,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """For each open entry, check whether current capacity has an opening
    covering its exact desired date/time(/place) — reuses the same
    free-capacity computation `find_instructor_openings` uses
    (`financial_capacity.compute_free_ranges_by_place`), never re-derives
    it (waitlist roadmap v0.1, Phase 2 — "reuse, don't rebuild").

    Read-only: on-demand check, does not change any entry's status. A match is
    either a genuinely free place range or a joinable group occurrence; the
    latter is never represented as instructor free time.
    """
    entries = list_entries(db, professional_id, status="open")
    if date_from is not None:
        entries = [entry for entry in entries if entry.desired_date >= date_from]
    if date_to is not None:
        entries = [entry for entry in entries if entry.desired_date <= date_to]
    if not entries:
        return []

    entries_by_date: dict[date, list[WaitlistEntry]] = {}
    for entry in entries:
        entries_by_date.setdefault(entry.desired_date, []).append(entry)

    all_places = financial_capacity.load_places(db, professional_id, None)
    places_by_id = {place.id: place for place in all_places}

    matches: list[dict] = []
    for target_date, day_entries in entries_by_date.items():
        free_by_place = financial_capacity.compute_free_ranges_by_place(
            db, professional_id, target_date, all_places
        )
        for entry in day_entries:
            desired_start = (
                entry.desired_start_time.hour * 60 + entry.desired_start_time.minute
            )
            desired_end = entry.desired_end_time.hour * 60 + entry.desired_end_time.minute
            candidate_place_ids = [entry.place_id] if entry.place_id else list(places_by_id)
            for place_id in candidate_place_ids:
                if place_id not in places_by_id:
                    continue
                for free_start, free_end in free_by_place.get(place_id, []):
                    if free_start <= desired_start and free_end >= desired_end:
                        matches.append(
                            {
                                "entry": entry,
                                "place_id": place_id,
                                "place_name": places_by_id[place_id].name,
                                "match_type": "free_time",
                            }
                        )
                        break
                else:
                    continue
                break
        group_occurrences = list_schedule_occurrences(
            db, professional_id, target_date, target_date
        )
        for entry in day_entries:
            if entry.class_type not in (None, "group"):
                continue
            for occurrence in group_occurrences:
                if (
                    occurrence.class_type != "group"
                    or occurrence.available_seats <= 0
                    or (entry.place_id is not None and occurrence.place_id != entry.place_id)
                    or occurrence.starts_at.time() > entry.desired_start_time
                    or occurrence.ends_at.time() < entry.desired_end_time
                ):
                    continue
                matches.append(
                    {
                        "entry": entry,
                        "place_id": occurrence.place_id,
                        "place_name": occurrence.place_name,
                        "match_type": "group_occurrence",
                        "source_type": occurrence.source_type,
                        "source_id": occurrence.source_id,
                        "occurrence_date": occurrence.occurrence_date,
                        "available_seats": occurrence.available_seats,
                    }
                )
    return matches


def mark_matches_for_date(
    db: Session, professional_id: uuid.UUID, target_date: date
) -> list[WaitlistEntry]:
    """Event-driven auto-matching (waitlist roadmap v0.1, Phase 5) — call
    right after freeing calendar capacity on a date (currently: a
    cancellation, see agent/mutations.py::_execute_cancel_schedule) so any
    open entry that now fits is flagged without the instructor having to
    manually check. Reuses find_matches; only "open" entries are updated
    (already matched/fulfilled ones are left alone).

    Does not commit — the caller's own transaction (already in progress,
    e.g. candidates.confirm()) owns that, same convention as
    schedule_overrides.cancel_occurrence."""
    matches = find_matches(db, professional_id, date_from=target_date, date_to=target_date)
    newly_matched: list[WaitlistEntry] = []
    for match in matches:
        entry = match["entry"]
        if entry.status != "open":
            continue
        entry.status = "matched"
        entry.matched_at = datetime.now(TIMEZONE)
        newly_matched.append(entry)
    if newly_matched:
        db.flush()
    return newly_matched

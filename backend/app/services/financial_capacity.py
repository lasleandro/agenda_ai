"""Tenant-scoped capacity segmentation and financial pricing.

Occurrence expansion and interval math now live in `app.services.scheduling`
(operational ontology roadmap v0.2, Phase 1) — this module consumes them and
keeps only pricing/prime-rate resolution, which is specific to the financial
domain.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.models import (
    InstructorEvent,
    MakeupClassCredit,
    Place,
    PlaceFinancialRate,
    PrimeTimeWindow,
    ProfessionalFinancialSettings,
    WorkJourneyInterval,
)
from app.services.scheduling import (
    TIMEZONE,
    _load_place_availability_ranges,
    intersect_ranges,
    iter_dates,
    list_schedule_occurrences,
    merge_ranges,
    split_range,
    subtract_ranges,
    time_to_minutes,
    weekly_dates,
)

PART_OF_DAY_RANGES = (
    ("morning", "Manhã", 0, 12 * 60),
    ("afternoon", "Tarde", 12 * 60, 18 * 60),
    ("evening", "Noite", 18 * 60, 24 * 60),
)


@dataclass(frozen=True)
class CapacitySegment:
    local_date: date
    place_id: uuid.UUID | None
    place_name: str
    start_minute: int
    end_minute: int
    time_category: str
    part_of_day: str

    @property
    def duration_minutes(self) -> int:
        return self.end_minute - self.start_minute


@dataclass(frozen=True)
class BookingOccurrence:
    local_date: date
    place_id: uuid.UUID
    start_minute: int
    end_minute: int
    participant_count: int
    is_redeemed_makeup: bool = False


@dataclass(frozen=True)
class PricingRules:
    """Unified rate matrix: keys are ``(place_id, time_category,
    participant_count)``. A ``None`` place_id row is the default rate,
    used both directly (no place) and as the fallback for a place with no
    explicit override."""

    rates: dict[tuple[uuid.UUID | None, str, int], int]

    def resolve(
        self,
        place_id: uuid.UUID | None,
        time_category: str,
        participant_count: int,
    ) -> int | None:
        explicit = self.rates.get((place_id, time_category, participant_count))
        if explicit is not None:
            return explicit
        return self.rates.get((None, time_category, participant_count))


def load_places(
    db: Session,
    professional_id: uuid.UUID,
    place_ids: list[uuid.UUID] | None = None,
) -> list[Place]:
    query = db.query(Place).filter(Place.professional_id == professional_id)
    if place_ids is not None:
        query = query.filter(Place.id.in_(place_ids))
    return query.order_by(Place.name).all()


def assert_all_places_found(
    places: list[Place],
    requested_place_ids: list[uuid.UUID] | None,
) -> None:
    if requested_place_ids is None:
        return
    found = {place.id for place in places}
    if found != set(requested_place_ids):
        raise ValueError("One or more places were not found")


def load_prime_ranges(
    db: Session,
    professional_id: uuid.UUID,
) -> dict[int, list[tuple[int, int]]]:
    settings = (
        db.query(ProfessionalFinancialSettings)
        .filter(ProfessionalFinancialSettings.professional_id == professional_id)
        .first()
    )
    if settings is None or not settings.prime_time_configured:
        defaults = [(5 * 60, 8 * 60), (18 * 60, 21 * 60)]
        return {day: defaults for day in range(7)}

    ranges = {day: [] for day in range(7)}
    rows = (
        db.query(PrimeTimeWindow)
        .filter(PrimeTimeWindow.professional_id == professional_id)
        .all()
    )
    for row in rows:
        for day in row.days_of_week:
            ranges[day].append(
                (time_to_minutes(row.start_time), time_to_minutes(row.end_time))
            )
    return ranges


def load_pricing_rules(
    db: Session,
    professional_id: uuid.UUID,
) -> PricingRules:
    rates = {
        (row.place_id, row.time_category, row.participant_count): (
            row.hourly_rate_cents
        )
        for row in (
            db.query(PlaceFinancialRate)
            .filter(PlaceFinancialRate.professional_id == professional_id)
            .all()
        )
    }
    return PricingRules(rates=rates)


def _load_net_work_ranges_by_day(
    db: Session,
    professional_id: uuid.UUID,
) -> dict[int, list[tuple[int, int]]]:
    """Work journey intervals minus break intervals, per weekday. Place-
    agnostic: WorkJourneyInterval has no place_id, so this is the
    instructor's raw declared availability before any per-place
    RecurringSlot attribution."""
    journey_rows = (
        db.query(WorkJourneyInterval)
        .filter(WorkJourneyInterval.professional_id == professional_id)
        .all()
    )
    work_by_day = {day: [] for day in range(7)}
    breaks_by_day = {day: [] for day in range(7)}
    for row in journey_rows:
        target = work_by_day if row.interval_type == "work" else breaks_by_day
        target[row.day_of_week].append(
            (time_to_minutes(row.start_time), time_to_minutes(row.end_time))
        )
    return {
        day: subtract_ranges(sorted(work_by_day[day]), sorted(breaks_by_day[day]))
        for day in range(7)
    }


def load_net_work_ranges(
    db: Session,
    professional_id: uuid.UUID,
    target_date: date,
) -> list[tuple[int, int]]:
    """The declared Work Journey (work minus breaks) for a single date's
    weekday. Callers use it to tell "no journey configured for this weekday"
    apart from "journey fully booked" — two very different answers to
    "when am I free?" that an empty free-range list alone can't distinguish."""
    return _load_net_work_ranges_by_day(db, professional_id)[target_date.weekday()]


def total_work_journey_minutes(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> int:
    """Aggregate net work-journey minutes (work minus break) across the
    date range, independent of place attribution. Used for the
    dashboard's top-line available/booked/occupancy figures so they
    aren't zeroed out for tenants who haven't declared per-place
    RecurringSlot availability windows — see
    docs/business_rules.md 'Financial capacity vs. work journey'."""
    net_by_day = _load_net_work_ranges_by_day(db, professional_id)
    return sum(
        end - start
        for local_date in iter_dates(date_from, date_to)
        for start, end in net_by_day[local_date.weekday()]
    )


def build_uncovered_capacity_minutes(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
    places: list[Place],
    prime_ranges: dict[int, list[tuple[int, int]]],
) -> dict[str, int]:
    """Work-journey minutes not covered by any place's RecurringSlot
    availability, bucketed by time_category (regular/prime) only — no
    place or part-of-day breakdown, since there's no place to attribute
    this time to. Used to price the "potential at 100% capacity" presets
    against the global rate for the portion of the work journey the
    instructor hasn't (yet) opened at a specific place — see
    docs/business_rules.md 'Financial capacity vs. work journey'."""
    net_by_day = _load_net_work_ranges_by_day(db, professional_id)
    availability = _load_place_availability_ranges(
        db,
        professional_id,
        date_from,
        date_to,
        {place.id for place in places},
    )
    totals = {"regular": 0, "prime": 0}
    for local_date in iter_dates(date_from, date_to):
        weekday = local_date.weekday()
        covered = merge_ranges(
            [
                place_range
                for place in places
                for place_range in availability.get((local_date, place.id), [])
            ]
        )
        uncovered = subtract_ranges(net_by_day[weekday], covered)
        prime = prime_ranges[weekday]
        boundaries = {
            boundary for start, end in prime for boundary in (start, end)
        }
        for start_minute, end_minute in uncovered:
            for segment_start, segment_end in split_range(
                start_minute,
                end_minute,
                boundaries,
            ):
                midpoint = (segment_start + segment_end) / 2
                category = (
                    "prime"
                    if any(start <= midpoint < end for start, end in prime)
                    else "regular"
                )
                totals[category] += segment_end - segment_start
    return totals


def build_capacity_segments(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
    places: list[Place],
    prime_ranges: dict[int, list[tuple[int, int]]],
) -> list[CapacitySegment]:
    net_by_day = _load_net_work_ranges_by_day(db, professional_id)

    availability = _load_place_availability_ranges(
        db,
        professional_id,
        date_from,
        date_to,
        {place.id for place in places},
    )
    segments: list[CapacitySegment] = []
    day_boundaries = {
        boundary
        for _, _, start, end in PART_OF_DAY_RANGES
        for boundary in (start, end)
    }
    for local_date in iter_dates(date_from, date_to):
        weekday = local_date.weekday()
        net_ranges = net_by_day[weekday]
        prime = prime_ranges[weekday]
        boundaries = day_boundaries | {
            boundary for start, end in prime for boundary in (start, end)
        }
        for place in places:
            place_ranges = merge_ranges(
                availability.get((local_date, place.id), [])
            )
            for start_minute, end_minute in intersect_ranges(
                net_ranges,
                place_ranges,
            ):
                for segment_start, segment_end in split_range(
                    start_minute,
                    end_minute,
                    boundaries,
                ):
                    midpoint = (segment_start + segment_end) / 2
                    category = (
                        "prime"
                        if any(start <= midpoint < end for start, end in prime)
                        else "regular"
                    )
                    part = next(
                        key
                        for key, _, start, end in PART_OF_DAY_RANGES
                        if start <= midpoint < end
                    )
                    segments.append(
                        CapacitySegment(
                            local_date=local_date,
                            place_id=place.id,
                            place_name=place.name,
                            start_minute=segment_start,
                            end_minute=segment_end,
                            time_category=category,
                            part_of_day=part,
                        )
                    )
    return segments


def build_uncovered_capacity_segments(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
    places: list[Place],
    prime_ranges: dict[int, list[tuple[int, int]]],
) -> list[CapacitySegment]:
    """Return place-agnostic work time as calendar-ready capacity segments."""
    net_by_day = _load_net_work_ranges_by_day(db, professional_id)
    availability = _load_place_availability_ranges(
        db,
        professional_id,
        date_from,
        date_to,
        {place.id for place in places},
    )
    segments: list[CapacitySegment] = []
    day_boundaries = {
        boundary
        for _, _, start, end in PART_OF_DAY_RANGES
        for boundary in (start, end)
    }
    for local_date in iter_dates(date_from, date_to):
        weekday = local_date.weekday()
        covered = merge_ranges(
            [
                place_range
                for place in places
                for place_range in availability.get((local_date, place.id), [])
            ]
        )
        boundaries = day_boundaries | {
            boundary for start, end in prime_ranges[weekday] for boundary in (start, end)
        }
        for start_minute, end_minute in subtract_ranges(
            net_by_day[weekday], covered
        ):
            for segment_start, segment_end in split_range(
                start_minute, end_minute, boundaries
            ):
                midpoint = (segment_start + segment_end) / 2
                category = (
                    "prime"
                    if any(
                        start <= midpoint < end
                        for start, end in prime_ranges[weekday]
                    )
                    else "regular"
                )
                part = next(
                    key
                    for key, _, start, end in PART_OF_DAY_RANGES
                    if start <= midpoint < end
                )
                segments.append(
                    CapacitySegment(
                        local_date=local_date,
                        place_id=None,
                        place_name="Sem local definido",
                        start_minute=segment_start,
                        end_minute=segment_end,
                        time_category=category,
                        part_of_day=part,
                    )
                )
    return segments


def load_booking_occurrences(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
    places: list[Place],
) -> list[BookingOccurrence]:
    """Bookings that occupy capacity: tentative/confirmed occurrences only
    (unlike `scheduling.list_schedule_occurrences`'s default, `completed`
    appointments don't consume future capacity)."""
    place_ids = {place.id for place in places}
    if not place_ids:
        return []
    occurrences = list_schedule_occurrences(
        db,
        professional_id,
        date_from,
        date_to,
        statuses=("tentative", "confirmed"),
    )
    redeemed_appointment_ids = {
        appointment_id
        for (appointment_id,) in (
            db.query(MakeupClassCredit.redeemed_appointment_id)
            .filter(
                MakeupClassCredit.professional_id == professional_id,
                MakeupClassCredit.status == "redeemed",
                MakeupClassCredit.redeemed_appointment_id.isnot(None),
            )
            .all()
        )
    }
    bookings: list[BookingOccurrence] = []
    for occurrence in occurrences:
        if occurrence.place_id not in place_ids:
            continue
        start_minute = time_to_minutes(occurrence.starts_at.time())
        duration_minutes = int(
            (occurrence.ends_at - occurrence.starts_at).total_seconds() // 60
        )
        bookings.append(
            BookingOccurrence(
                local_date=occurrence.occurrence_date,
                place_id=occurrence.place_id,
                start_minute=start_minute,
                end_minute=start_minute + duration_minutes,
                participant_count=min(len(occurrence.participants), 4),
                is_redeemed_makeup=(
                    occurrence.source_type == "appointment"
                    and occurrence.source_id in redeemed_appointment_ids
                ),
            )
        )
    return bookings


def load_event_busy_ranges(
    db: Session,
    professional_id: uuid.UUID,
    target_date: date,
) -> list[tuple[int, int]]:
    """Confirmed instructor-event time that blocks the shared calendar."""
    day_start = datetime.combine(target_date, time.min, tzinfo=TIMEZONE)
    day_end = day_start + timedelta(days=1)
    events = (
        db.query(InstructorEvent)
        .filter(
            InstructorEvent.professional_id == professional_id,
            InstructorEvent.status == "confirmed",
            InstructorEvent.start_at < day_end,
            InstructorEvent.end_at > day_start,
        )
        .all()
    )

    ranges: list[tuple[int, int]] = []
    for event in events:
        start_at = max(event.start_at.astimezone(TIMEZONE), day_start)
        end_at = min(event.end_at.astimezone(TIMEZONE), day_end)
        end_minute = 24 * 60 if end_at == day_end else time_to_minutes(end_at.time())
        ranges.append((time_to_minutes(start_at.time()), end_minute))
    return ranges


def compute_free_ranges_by_place(
    db: Session,
    professional_id: uuid.UUID,
    target_date: date,
    places: list[Place],
) -> dict[uuid.UUID, list[tuple[int, int]]]:
    """Open (unbooked) capacity ranges per place on a single date, in
    minutes-since-midnight. The "what's actually free" computation shared by
    `agent.tools.find_instructor_openings` and the waitlist matcher
    (`services.waitlist.find_matches`) — reused rather than re-derived, per
    the waitlist roadmap's explicit "reuse, don't rebuild" decision."""
    prime_ranges = load_prime_ranges(db, professional_id)
    segments = build_capacity_segments(
        db, professional_id, target_date, target_date, places, prime_ranges
    )
    bookings = load_booking_occurrences(db, professional_id, target_date, target_date, places)
    event_busy_ranges = load_event_busy_ranges(db, professional_id, target_date)

    free_by_place: dict[uuid.UUID, list[tuple[int, int]]] = {}
    for place in places:
        place_ranges = merge_ranges(
            [
                (segment.start_minute, segment.end_minute)
                for segment in segments
                if segment.place_id == place.id
            ]
        )
        booked_ranges = [
            (booking.start_minute, booking.end_minute)
            for booking in bookings
            if booking.place_id == place.id and booking.local_date == target_date
        ]
        free_by_place[place.id] = subtract_ranges(
            place_ranges, [*booked_ranges, *event_busy_ranges]
        )
    return free_by_place


def compute_free_calendar_ranges(
    db: Session,
    professional_id: uuid.UUID,
    target_date: date,
) -> list[tuple[int, int]]:
    """Place-agnostic free time on a single date: raw Work Journey (work
    minus break) minus every real booking across all of the professional's
    places. Fallback for `agent.tools.find_instructor_openings` when no
    place has RecurringSlot coverage for the date/weekday — mirrors the
    top-line dashboard's Work Journey fallback (docs/business_rules.md 3.5
    "Financial Capacity vs. Work Journey") so the agent doesn't report "no
    openings" just because per-place availability windows haven't been
    configured, even though the instructor's actual booked calendar has
    open gaps."""
    net_ranges = load_net_work_ranges(db, professional_id, target_date)
    all_places = load_places(db, professional_id, None)
    bookings = load_booking_occurrences(db, professional_id, target_date, target_date, all_places)
    booked_ranges = [
        (booking.start_minute, booking.end_minute)
        for booking in bookings
        if booking.local_date == target_date
    ]
    return subtract_ranges(
        net_ranges,
        [*booked_ranges, *load_event_busy_ranges(db, professional_id, target_date)],
    )

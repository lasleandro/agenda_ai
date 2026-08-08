"""Tenant-scoped capacity segmentation and financial pricing.

Occurrence expansion and interval math now live in `app.services.scheduling`
(operational ontology roadmap v0.2, Phase 1) — this module consumes them and
keeps only pricing/prime-rate resolution, which is specific to the financial
domain.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.models import (
    FinancialRate,
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
    place_id: uuid.UUID
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


@dataclass(frozen=True)
class PricingRules:
    global_rates: dict[int, int]
    place_rates: dict[tuple[uuid.UUID, str, int], int]

    def resolve(
        self,
        place_id: uuid.UUID,
        time_category: str,
        participant_count: int,
    ) -> int | None:
        return self.place_rates.get(
            (place_id, time_category, participant_count),
            self.global_rates.get(participant_count),
        )


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
    global_rates = {
        row.participant_count: row.hourly_rate_cents
        for row in (
            db.query(FinancialRate)
            .filter(FinancialRate.professional_id == professional_id)
            .all()
        )
    }
    place_rates = {
        (row.place_id, row.time_category, row.participant_count): (
            row.hourly_rate_cents
        )
        for row in (
            db.query(PlaceFinancialRate)
            .filter(PlaceFinancialRate.professional_id == professional_id)
            .all()
        )
    }
    return PricingRules(global_rates=global_rates, place_rates=place_rates)


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
            )
        )
    return bookings

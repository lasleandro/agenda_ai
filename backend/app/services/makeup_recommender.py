"""
Phase 4 — Make-up class slot recommender (heuristic, not ML).

Given a contact with available make-up credits, rank candidate capacity
segments over the next N days using a weighted combination of cost score
(lower hourly rate = better), flow score (historically quieter
weekday+hour buckets = better), a preferred-place bonus, and a
level-match bonus (the slot coincides with a recurring class at the
student's usual level).
"""

import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    Contact,
    Professional,
    RecurringSlot,
    RecurringSlotParticipant,
)
from app.services import financial_capacity, scheduling
from app.services.makeup_credits import get_available_credits_count

DEFAULT_LOOKAHEAD_DAYS = 14
DEFAULT_FLOW_WEEKS = 4
DEFAULT_COST_WEIGHT = 0.5
DEFAULT_FLOW_WEIGHT = 0.5


def _percentile_rank(value: float, all_values: list[float]) -> float:
    """Fraction of values in *all_values* that are strictly greater than
    *value*.  Returns 0.0–100.0; higher = better (fewer values are above
    this one)."""
    if not all_values:
        return 50.0
    return sum(1.0 for v in all_values if v > value) / len(all_values) * 100.0


def _contact_duration_places_and_level(
    db: Session,
    contact_id: uuid.UUID,
    professional_id: uuid.UUID,
) -> tuple[int, set[uuid.UUID], str | None]:
    """Return the contact's typical session duration (minutes), the set of
    place-ids they attend, and their most common class level from recurring
    slot memberships.  Falls back to the professional's default duration if
    the contact has no memberships."""
    rows = (
        db.query(RecurringSlot)
        .join(
            RecurringSlotParticipant,
            RecurringSlotParticipant.recurring_slot_id == RecurringSlot.id,
        )
        .filter(
            RecurringSlotParticipant.contact_id == contact_id,
            RecurringSlot.professional_id == professional_id,
            RecurringSlot.slot_kind == "class",
        )
        .all()
    )

    durations: list[int] = []
    places: set[uuid.UUID] = set()
    levels: list[str] = []

    for slot in rows:
        if slot.start_time and slot.end_time:
            start_min = scheduling.time_to_minutes(slot.start_time)
            end_min = scheduling.time_to_minutes(slot.end_time)
            if end_min > start_min:
                durations.append(end_min - start_min)
        if slot.place_id:
            places.add(slot.place_id)
        if slot.level:
            levels.append(slot.level)

    if durations:
        # Use the most common duration; fall back to median-ish
        from collections import Counter

        duration = Counter(durations).most_common(1)[0][0]
    else:
        professional = (
            db.query(Professional)
            .filter(Professional.id == professional_id)
            .first()
        )
        duration = (
            professional.default_duration_minutes
            if professional and professional.default_duration_minutes
            else 60
        )

    level = Counter(levels).most_common(1)[0][0] if levels else None
    return duration, places, level


def _load_levels_by_place_weekday(
    db: Session,
    professional_id: uuid.UUID,
    place_ids: set[uuid.UUID],
) -> dict[tuple[uuid.UUID, int], list[tuple[int, int, str]]]:
    """For each (place_id, weekday), the list of (start_minute, end_minute,
    level) covered by an active RecurringSlot with a level set. Used to
    bonus candidate slots that line up with the student's usual level."""
    if not place_ids:
        return {}
    rows = (
        db.query(RecurringSlot)
        .filter(
            RecurringSlot.professional_id == professional_id,
            RecurringSlot.place_id.in_(place_ids),
            RecurringSlot.status == "active",
            RecurringSlot.slot_kind == "class",
            RecurringSlot.level.isnot(None),
        )
        .all()
    )
    by_place_weekday: dict[tuple[uuid.UUID, int], list[tuple[int, int, str]]] = defaultdict(list)
    for slot in rows:
        by_place_weekday[(slot.place_id, slot.day_of_week)].append(
            (
                scheduling.time_to_minutes(slot.start_time),
                scheduling.time_to_minutes(slot.end_time),
                slot.level,
            )
        )
    return by_place_weekday


def _level_matches(
    levels_by_place_weekday: dict[tuple[uuid.UUID, int], list[tuple[int, int, str]]],
    place_id: uuid.UUID,
    weekday: int,
    start_minute: int,
    end_minute: int,
    preferred_level: str | None,
) -> bool:
    """True if the candidate's time range overlaps a RecurringSlot at this
    place/weekday whose level matches the student's preferred_level."""
    if preferred_level is None:
        return False
    for slot_start, slot_end, level in levels_by_place_weekday.get((place_id, weekday), []):
        if level == preferred_level and start_minute < slot_end and end_minute > slot_start:
            return True
    return False


def _compute_flow_ratios(
    db: Session,
    professional_id: uuid.UUID,
    lookback_weeks: int,
) -> dict[tuple[int, int], float]:
    """Compute historical booked-participants-per-hour for each
    (weekday, hour_bucket) over the trailing *lookback_weeks*.

    Returns a dict mapping (weekday, hour_bucket) -> participants_per_hour.
    Lower values mean historically quieter buckets.
    """
    today = date.today()
    date_from = today - timedelta(weeks=lookback_weeks)
    date_to = today - timedelta(days=1)

    occurrences = scheduling.list_schedule_occurrences(
        db,
        professional_id,
        date_from,
        date_to,
        statuses=(
            "tentative",
            "confirmed",
            "completed",
            "no_show",
            "cancelled",
        ),
    )

    # Aggregate: (weekday, hour_bucket) -> (total_participants, total_duration_minutes)
    buckets: dict[tuple[int, int], tuple[int, int]] = defaultdict(lambda: (0, 0))
    for occ in occurrences:
        weekday = occ.starts_at.weekday()
        hour_bucket = occ.starts_at.hour
        key = (weekday, hour_bucket)
        duration_min = int(
            (occ.ends_at - occ.starts_at).total_seconds() // 60
        )
        participants = len(occ.participants)
        prev_participants, prev_duration = buckets[key]
        buckets[key] = (
            prev_participants + participants,
            prev_duration + duration_min,
        )

    ratios: dict[tuple[int, int], float] = {}
    for key, (total_participants, total_duration_min) in buckets.items():
        if total_duration_min > 0:
            ratios[key] = total_participants / (total_duration_min / 60.0)
        else:
            ratios[key] = 0.0

    return ratios


def recommend_makeup_slots(
    db: Session,
    professional_id: uuid.UUID,
    contact_id: uuid.UUID,
    *,
    max_recommendations: int = 5,
    lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
    flow_lookback_weeks: int = DEFAULT_FLOW_WEEKS,
    cost_weight: float = DEFAULT_COST_WEIGHT,
    flow_weight: float = DEFAULT_FLOW_WEIGHT,
) -> list[dict[str, Any]]:
    """Rank available capacity segments for a make-up class.

    Returns a list of dicts, each describing a ranked candidate:
      - date, place_id, place_name, start_time, end_time
      - time_category ("prime" | "regular")
      - hourly_rate_cents (int or null)
      - cost_score, flow_score, combined_score (0-100, higher=better)
    """
    credits = get_available_credits_count(db, professional_id, contact_id)
    if credits <= 0:
        return []

    contact = (
        db.query(Contact)
        .filter(
            Contact.id == contact_id,
            Contact.professional_id == professional_id,
        )
        .first()
    )
    if contact is None:
        return []

    duration, preferred_places, preferred_level = _contact_duration_places_and_level(
        db, contact_id, professional_id
    )

    today = date.today()
    date_from = today + timedelta(days=1)  # start tomorrow
    date_to = today + timedelta(days=lookahead_days)

    places = financial_capacity.load_places(db, professional_id)
    if not places:
        return []

    prime_ranges = financial_capacity.load_prime_ranges(db, professional_id)
    segments = financial_capacity.build_capacity_segments(
        db, professional_id, date_from, date_to, places, prime_ranges
    )
    bookings = financial_capacity.load_booking_occurrences(
        db, professional_id, date_from, date_to, places
    )
    pricing = financial_capacity.load_pricing_rules(db, professional_id)
    flow_ratios = _compute_flow_ratios(db, professional_id, flow_lookback_weeks)
    levels_by_place_weekday = _load_levels_by_place_weekday(
        db, professional_id, {place.id for place in places}
    )

    # Build set of booked intervals keyed by (date, place_id)
    booked: dict[
        tuple[date, uuid.UUID], list[financial_capacity.BookingOccurrence]
    ] = defaultdict(list)
    for b in bookings:
        booked[(b.local_date, b.place_id)].append(b)

    # 1. Pre-sort places so preferred places come first (not an exclusion)
    sorted_places = sorted(
        places,
        key=lambda p: 0 if p.id in preferred_places else 1,
    )

    # 2. Build candidates
    candidates: list[dict[str, Any]] = []
    for place in sorted_places:
        for segment in segments:
            if segment.place_id != place.id:
                continue
            if segment.duration_minutes < duration:
                continue

            # Subtract booked intervals from this segment for this date
            place_booked = [
                booking
                for booking in booked.get((segment.local_date, place.id), [])
                if not booking.has_open_group_seat
            ]
            free_ranges = scheduling.subtract_ranges(
                [(segment.start_minute, segment.end_minute)],
                sorted((booking.start_minute, booking.end_minute) for booking in place_booked),
            )

            for range_start, range_end in free_ranges:
                first_start = ((range_start + 59) // 60) * 60
                for start_min in range(first_start, range_end - duration + 1, 60):
                    end_min = start_min + duration

                    # Cost score: resolve hourly rate
                    rate = pricing.resolve(
                        place.id,
                        segment.time_category,
                        participant_count=1,
                    )

                    # Flow score: look up (weekday, hour_bucket)
                    weekday = segment.local_date.weekday()
                    start_hour = start_min // 60
                    flow_key = (weekday, start_hour)
                    flow_ratio = flow_ratios.get(flow_key)

                    level_match = _level_matches(
                        levels_by_place_weekday,
                        place.id,
                        weekday,
                        start_min,
                        end_min,
                        preferred_level,
                    )

                    candidates.append(
                        {
                            "date": segment.local_date.isoformat(),
                            "place_id": str(place.id),
                            "place_name": place.name,
                            "start_time": f"{start_min // 60:02d}:{start_min % 60:02d}",
                            "end_time": f"{end_min // 60:02d}:{end_min % 60:02d}",
                            "duration_minutes": duration,
                            "time_category": segment.time_category,
                            "part_of_day": segment.part_of_day,
                            "hourly_rate_cents": rate,
                            "flow_ratio": flow_ratio,
                            "preferred_place": place.id in preferred_places,
                            "level_match": level_match,
                        }
                    )

    if not candidates:
        return []

    # 3. Compute percentile scores
    rates = [c["hourly_rate_cents"] for c in candidates if c["hourly_rate_cents"] is not None]
    flows = [c["flow_ratio"] for c in candidates if c["flow_ratio"] is not None]

    for c in candidates:
        # Cost score: lower rate = better (higher percentile)
        cost_percentile = 50.0
        if c["hourly_rate_cents"] is not None and rates:
            cost_percentile = _percentile_rank(c["hourly_rate_cents"], rates)
        # Prime time penalty (ranking by rate already captures this,
        # but we add a small boost for regular over prime to match spec)
        if c["time_category"] == "regular" and c["hourly_rate_cents"] is not None:
            cost_percentile = min(100.0, cost_percentile + 5.0)

        # Flow score: lower ratio = better (higher percentile)
        flow_percentile = 50.0
        if c["flow_ratio"] is not None and flows:
            flow_percentile = _percentile_rank(c["flow_ratio"], flows)

        # Preferred place bonus
        place_bonus = 5.0 if c["preferred_place"] else 0.0

        # Level-match bonus: this slot coincides with a recurring class at
        # the student's usual level (see _level_matches)
        level_bonus = 5.0 if c["level_match"] else 0.0

        combined = (
            cost_weight * cost_percentile
            + flow_weight * flow_percentile
            + place_bonus
            + level_bonus
        )
        c["cost_score"] = round(cost_percentile, 1)
        c["flow_score"] = round(flow_percentile, 1)
        c["combined_score"] = round(combined, 1)

    # 4. Sort descending by combined score, return top N
    candidates.sort(key=lambda c: c["combined_score"], reverse=True)

    result: list[dict[str, Any]] = []
    for c in candidates[:max_recommendations]:
        result.append(
            {
                "date": c["date"],
                "place_id": c["place_id"],
                "place_name": c["place_name"],
                "start_time": c["start_time"],
                "end_time": c["end_time"],
                "duration_minutes": c["duration_minutes"],
                "time_category": c["time_category"],
                "part_of_day": c["part_of_day"],
                "hourly_rate_cents": c["hourly_rate_cents"],
                "cost_score": c["cost_score"],
                "flow_score": c["flow_score"],
                "level_match": c["level_match"],
                "combined_score": c["combined_score"],
            }
        )

    return result

"""Explainable dashboard and what-if calculations for financial planning."""

import uuid
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.schemas.financial import (
    CapacityPresetDetail,
    CapacitySourceDetail,
    FinancialAnalyticsAssumptions,
    FinancialDashboardDetail,
    FinancialMetricBreakdown,
    FinancialScenarioInput,
    FinancialScenarioMetric,
    FinancialScenarioResult,
    FinancialScenarioScheduleEvent,
    FinancialTimeSeriesPoint,
    FinancialTradeoffDetail,
    ParticipantMixItem,
)
from app.services.scenario_customer_demand import estimate_customer_range
from app.services.financial_capacity import (
    PART_OF_DAY_RANGES,
    BookingOccurrence,
    CapacitySegment,
    PricingRules,
    assert_all_places_found,
    build_capacity_segments,
    build_uncovered_capacity_segments,
    build_uncovered_capacity_minutes,
    iter_dates,
    load_booking_occurrences,
    load_places,
    load_pricing_rules,
    load_prime_ranges,
    split_range,
    total_work_journey_minutes,
)

WEEKDAY_LABELS = (
    "Segunda",
    "Terça",
    "Quarta",
    "Quinta",
    "Sexta",
    "Sábado",
    "Domingo",
)
PART_LABELS = {key: label for key, label, _, _ in PART_OF_DAY_RANGES}
CATEGORY_LABELS = {"regular": "Horário regular", "prime": "Horário nobre"}


@dataclass
class MetricBucket:
    available_minutes: int = 0
    booked_minutes: int = 0
    projected_revenue_cents: int = 0


@dataclass(frozen=True)
class AnalyticsContext:
    places: list
    prime_ranges: dict[int, list[tuple[int, int]]]
    pricing: PricingRules
    capacity: list[CapacitySegment]
    simulation_capacity: list[CapacitySegment]
    bookings: list[BookingOccurrence]
    uncovered_minutes: dict[str, int]


def _round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _percentage(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0
    return round(float(numerator) / float(denominator) * 100, 1)


def _assumptions(
    date_from: date,
    date_to: date,
) -> FinancialAnalyticsAssumptions:
    return FinancialAnalyticsAssumptions(
        period_start=date_from,
        period_end=date_to,
        timezone="America/Sao_Paulo",
        revenue_basis=(
            "Agendamentos e grupos ativos valorizados pelas regras atuais; "
            "não representa receita reconhecida."
        ),
        capacity_basis=(
            "Total geral: jornada líquida (jornada menos pausas), independente "
            "de local. A capacidade coberta por permanências é atribuída aos "
            "respectivos locais; o restante aparece como Sem local definido. "
            "Quebras por local/dia/período/categoria mostram somente a "
            "interseção entre a jornada e permanências ativas."
        ),
        excluded_constraints=[
            "presença, cancelamentos e faltas",
            "impostos, custos e inadimplência",
            "deslocamento entre locais",
            "preferências e disponibilidade futura dos clientes",
        ],
    )


def _load_context(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
    place_ids: list[uuid.UUID] | None,
) -> AnalyticsContext:
    places = load_places(db, professional_id, place_ids)
    assert_all_places_found(places, place_ids)
    prime_ranges = load_prime_ranges(db, professional_id)
    # Uncovered (place-agnostic) work-journey time only makes sense to
    # fold into potential-revenue calculations for the "all places" view
    # — with a place filter, time not covered by the filtered place(s)
    # may well be covered by a place the user filtered out, so crediting
    # it to the filtered place(s) would overstate their potential.
    uncovered_minutes = (
        build_uncovered_capacity_minutes(
            db,
            professional_id,
            date_from,
            date_to,
            places,
            prime_ranges,
        )
        if place_ids is None
        else {"regular": 0, "prime": 0}
    )
    capacity = build_capacity_segments(
        db,
        professional_id,
        date_from,
        date_to,
        places,
        prime_ranges,
    )
    uncovered_capacity = (
        build_uncovered_capacity_segments(
            db,
            professional_id,
            date_from,
            date_to,
            places,
            prime_ranges,
        )
        if place_ids is None
        else []
    )
    return AnalyticsContext(
        places=places,
        prime_ranges=prime_ranges,
        pricing=load_pricing_rules(db, professional_id),
        capacity=capacity,
        simulation_capacity=[*capacity, *uncovered_capacity],
        bookings=load_booking_occurrences(
            db,
            professional_id,
            date_from,
            date_to,
            places,
        ),
        uncovered_minutes=uncovered_minutes,
    )


def _booking_segments(
    booking: BookingOccurrence,
    prime_ranges: dict[int, list[tuple[int, int]]],
) -> list[tuple[int, int, str, str]]:
    start_minute = max(0, booking.start_minute)
    end_minute = min(24 * 60, booking.end_minute)
    if end_minute <= start_minute:
        return []
    prime = prime_ranges[booking.local_date.weekday()]
    boundaries = {
        boundary
        for _, _, part_start, part_end in PART_OF_DAY_RANGES
        for boundary in (part_start, part_end)
    } | {boundary for start, end in prime for boundary in (start, end)}
    segments = []
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
            for key, _, part_start, part_end in PART_OF_DAY_RANGES
            if part_start <= midpoint < part_end
        )
        segments.append((segment_start, segment_end, category, part))
    return segments


def _capacity_overlap(
    capacity_by_date_place: dict[
        tuple[date, uuid.UUID],
        list[CapacitySegment],
    ],
    booking: BookingOccurrence,
    start_minute: int,
    end_minute: int,
) -> int:
    return sum(
        max(
            0,
            min(end_minute, segment.end_minute)
            - max(start_minute, segment.start_minute),
        )
        for segment in capacity_by_date_place.get(
            (booking.local_date, booking.place_id),
            [],
        )
    )


def _finalize_bucket(
    key: str,
    label: str,
    bucket: MetricBucket,
) -> FinancialMetricBreakdown:
    return FinancialMetricBreakdown(
        key=key,
        label=label,
        available_minutes=bucket.available_minutes,
        booked_minutes=bucket.booked_minutes,
        unused_minutes=max(0, bucket.available_minutes - bucket.booked_minutes),
        occupancy_pct=_percentage(
            bucket.booked_minutes,
            bucket.available_minutes,
        ),
        projected_revenue_cents=bucket.projected_revenue_cents,
    )


def _normalize_mix(weights: dict[int, int]) -> list[ParticipantMixItem]:
    total = sum(weights.values())
    if total == 0:
        return [
            ParticipantMixItem(
                participant_count=1,
                percentage=100,
            )
        ]
    return [
        ParticipantMixItem(
            participant_count=count,
            percentage=round(weight / total * 100, 2),
        )
        for count, weight in sorted(weights.items())
        if weight > 0
    ]


def _resolve_rate(
    pricing: PricingRules,
    segment: CapacitySegment,
    participant_count: int,
    overrides: dict[tuple[str, int], int] | None = None,
) -> int | None:
    if overrides is not None:
        override = overrides.get((segment.time_category, participant_count))
        if override is not None:
            return override
    return pricing.resolve(
        segment.place_id,
        segment.time_category,
        participant_count,
    )


def _potential_metric(
    capacity: list[CapacitySegment],
    pricing: PricingRules,
    mixes: dict[str, list[ParticipantMixItem]],
    occupancy_pct: float,
    overrides: dict[tuple[str, int], int] | None = None,
    uncovered_minutes: dict[str, int] | None = None,
) -> FinancialScenarioMetric:
    occupancy = Decimal(str(occupancy_pct)) / Decimal(100)
    revenue = Decimal(0)
    participant_minutes = Decimal(0)
    for segment in capacity:
        for item in mixes[segment.time_category]:
            participant_minutes += (
                Decimal(item.participant_count)
                * Decimal(segment.duration_minutes)
                * Decimal(str(item.percentage))
                / Decimal(100)
                * occupancy
            )
            rate = _resolve_rate(
                pricing,
                segment,
                item.participant_count,
                overrides,
            )
            if rate is None:
                continue
            revenue += (
                Decimal(rate)
                * Decimal(item.participant_count)
                * Decimal(segment.duration_minutes)
                / Decimal(60)
                * Decimal(str(item.percentage))
                / Decimal(100)
                * occupancy
            )
    # Work-journey time not attributed to any place uses the generic-location
    # matrix, then the tenant-global fallback. Scenario overrides remain first.
    for category, minutes in (uncovered_minutes or {}).items():
        if minutes <= 0:
            continue
        for item in mixes[category]:
            participant_minutes += (
                Decimal(item.participant_count)
                * Decimal(minutes)
                * Decimal(str(item.percentage))
                / Decimal(100)
                * occupancy
            )
            rate = None
            if overrides is not None:
                rate = overrides.get((category, item.participant_count))
            if rate is None:
                rate = pricing.resolve(
                    None,
                    category,
                    item.participant_count,
                )
            if rate is None:
                continue
            revenue += (
                Decimal(rate)
                * Decimal(item.participant_count)
                * Decimal(minutes)
                / Decimal(60)
                * Decimal(str(item.percentage))
                / Decimal(100)
                * occupancy
            )
    available = sum(segment.duration_minutes for segment in capacity) + sum(
        (uncovered_minutes or {}).values()
    )
    utilized = int(
        (Decimal(available) * occupancy).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )
    return FinancialScenarioMetric(
        available_minutes=available,
        utilized_minutes=utilized,
        occupancy_pct=occupancy_pct,
        participant_hours=round(float(participant_minutes / Decimal(60)), 2),
        projected_revenue_cents=_round_cents(revenue),
    )


def _capacity_presets(
    context: AnalyticsContext,
    observed_mix: list[ParticipantMixItem],
) -> list[CapacityPresetDetail]:
    presets = (
        (
            "all_individual",
            "Todos os horários individuais",
            [ParticipantMixItem(participant_count=1, percentage=100)],
        ),
        ("observed_demand", "Mix da demanda observada", observed_mix),
        (
            "full_groups",
            "Todos os horários com grupos de 4",
            [ParticipantMixItem(participant_count=4, percentage=100)],
        ),
    )
    return [
        CapacityPresetDetail(
            key=key,
            label=label,
            participant_mix=mix,
            occupancy_pct=100,
            participant_hours=metric.participant_hours,
            projected_revenue_cents=metric.projected_revenue_cents,
        )
        for key, label, mix in presets
        for metric in [
            _potential_metric(
                context.capacity,
                context.pricing,
                {"regular": mix, "prime": mix},
                100,
                uncovered_minutes=context.uncovered_minutes,
            )
        ]
    ]


def _capacity_sources(
    context: AnalyticsContext,
    observed_mix: list[ParticipantMixItem],
) -> list[CapacitySourceDetail]:
    mixes = {"regular": observed_mix, "prime": observed_mix}
    total = _potential_metric(
        context.capacity,
        context.pricing,
        mixes,
        100,
        uncovered_minutes=context.uncovered_minutes,
    )
    defined_places = _potential_metric(
        context.capacity,
        context.pricing,
        mixes,
        100,
    )
    return [
        CapacitySourceDetail(
            key="defined_places",
            label="Em locais definidos",
            available_minutes=defined_places.available_minutes,
            projected_revenue_cents=defined_places.projected_revenue_cents,
        ),
        CapacitySourceDetail(
            key="without_defined_place",
            label="Sem local definido",
            available_minutes=(
                total.available_minutes - defined_places.available_minutes
            ),
            projected_revenue_cents=(
                total.projected_revenue_cents
                - defined_places.projected_revenue_cents
            ),
        ),
    ]


def build_financial_dashboard(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
    place_ids: list[uuid.UUID] | None = None,
) -> FinancialDashboardDetail:
    context = _load_context(
        db,
        professional_id,
        date_from,
        date_to,
        place_ids,
    )
    place_labels = {str(place.id): place.name for place in context.places}
    by_place = {key: MetricBucket() for key in place_labels}
    by_weekday = {str(day): MetricBucket() for day in range(7)}
    by_part = {key: MetricBucket() for key in PART_LABELS}
    by_category = {key: MetricBucket() for key in CATEGORY_LABELS}
    by_date = {
        local_date: MetricBucket() for local_date in iter_dates(date_from, date_to)
    }
    capacity_by_date_place: dict[
        tuple[date, uuid.UUID],
        list[CapacitySegment],
    ] = {}
    total = MetricBucket()
    for segment in context.capacity:
        duration = segment.duration_minutes
        total.available_minutes += duration
        by_place[str(segment.place_id)].available_minutes += duration
        by_weekday[str(segment.local_date.weekday())].available_minutes += duration
        by_part[segment.part_of_day].available_minutes += duration
        by_category[segment.time_category].available_minutes += duration
        by_date[segment.local_date].available_minutes += duration
        capacity_by_date_place.setdefault(
            (segment.local_date, segment.place_id),
            [],
        ).append(segment)

    participant_minutes = 0
    raw_booked_minutes = 0
    participant_mix_weights: dict[int, int] = {}
    unpriced_booking_count = 0
    makeup_booking_count = 0
    makeup_booked_minutes = 0
    makeup_opportunity_cost_cents = 0
    for booking in context.bookings:
        occurrence_unpriced = False
        occurrence_minutes = max(0, booking.end_minute - booking.start_minute)
        if booking.is_redeemed_makeup:
            makeup_booking_count += 1
            makeup_booked_minutes += occurrence_minutes
        participant_minutes += occurrence_minutes * booking.participant_count
        raw_booked_minutes += occurrence_minutes
        participant_mix_weights[booking.participant_count] = (
            participant_mix_weights.get(booking.participant_count, 0)
            + occurrence_minutes
        )
        for start_minute, end_minute, category, part in _booking_segments(
            booking,
            context.prime_ranges,
        ):
            duration = end_minute - start_minute
            overlap = _capacity_overlap(
                capacity_by_date_place,
                booking,
                start_minute,
                end_minute,
            )
            rate = context.pricing.resolve(
                booking.place_id,
                category,
                booking.participant_count,
            )
            revenue = 0
            if rate is None:
                occurrence_unpriced = not booking.is_redeemed_makeup
            else:
                revenue = _round_cents(
                    Decimal(rate)
                    * Decimal(booking.participant_count)
                    * Decimal(duration)
                    / Decimal(60)
                )
                if booking.is_redeemed_makeup:
                    makeup_opportunity_cost_cents += revenue
                    revenue = 0

            total.booked_minutes += overlap
            total.projected_revenue_cents += revenue
            place_bucket = by_place[str(booking.place_id)]
            place_bucket.booked_minutes += overlap
            place_bucket.projected_revenue_cents += revenue
            weekday_bucket = by_weekday[str(booking.local_date.weekday())]
            weekday_bucket.booked_minutes += overlap
            weekday_bucket.projected_revenue_cents += revenue
            by_part[part].booked_minutes += overlap
            by_part[part].projected_revenue_cents += revenue
            by_category[category].booked_minutes += overlap
            by_category[category].projected_revenue_cents += revenue
            by_date[booking.local_date].booked_minutes += overlap
            by_date[booking.local_date].projected_revenue_cents += revenue
        if occurrence_unpriced:
            unpriced_booking_count += 1

    observed_mix = _normalize_mix(participant_mix_weights)
    # Top-line figures are place-agnostic (raw work journey) only when no
    # place filter narrows the view — with a place filter, booked_minutes
    # is already scoped to that place, so available_minutes must be too
    # (the place-scoped, RecurringSlot-based total) or the ratio would
    # compare a filtered numerator against a tenant-wide denominator.
    if place_ids is None:
        top_available_minutes = total_work_journey_minutes(
            db, professional_id, date_from, date_to
        )
        top_booked_minutes = raw_booked_minutes
    else:
        top_available_minutes = total.available_minutes
        top_booked_minutes = total.booked_minutes
    return FinancialDashboardDetail(
        assumptions=_assumptions(date_from, date_to),
        available_minutes=top_available_minutes,
        booked_minutes=top_booked_minutes,
        unused_minutes=max(0, top_available_minutes - top_booked_minutes),
        occupancy_pct=_percentage(
            top_booked_minutes,
            top_available_minutes,
        ),
        participant_hours=round(participant_minutes / 60, 2),
        projected_revenue_cents=total.projected_revenue_cents,
        unpriced_booking_count=unpriced_booking_count,
        makeup_booking_count=makeup_booking_count,
        makeup_booked_minutes=makeup_booked_minutes,
        makeup_opportunity_cost_cents=makeup_opportunity_cost_cents,
        observed_participant_mix=observed_mix,
        time_series=[
            FinancialTimeSeriesPoint(
                date=local_date,
                available_minutes=bucket.available_minutes,
                booked_minutes=bucket.booked_minutes,
                projected_revenue_cents=bucket.projected_revenue_cents,
            )
            for local_date, bucket in by_date.items()
        ],
        by_place=[
            _finalize_bucket(key, place_labels[key], bucket)
            for key, bucket in by_place.items()
        ],
        by_part_of_day=[
            _finalize_bucket(key, PART_LABELS[key], bucket)
            for key, bucket in by_part.items()
        ],
        by_weekday=[
            _finalize_bucket(key, WEEKDAY_LABELS[int(key)], bucket)
            for key, bucket in by_weekday.items()
        ],
        by_time_category=[
            _finalize_bucket(key, CATEGORY_LABELS[key], bucket)
            for key, bucket in by_category.items()
        ],
        capacity_presets=_capacity_presets(context, observed_mix),
        capacity_sources=_capacity_sources(context, observed_mix),
    )


def _scenario_mixes(
    body: FinancialScenarioInput,
    observed_mix: list[ParticipantMixItem],
) -> dict[str, list[ParticipantMixItem]]:
    individual = [ParticipantMixItem(participant_count=1, percentage=100)]
    groups = [ParticipantMixItem(participant_count=4, percentage=100)]
    if body.mode == "all_individual":
        return {"regular": individual, "prime": individual}
    if body.mode == "full_groups":
        return {"regular": groups, "prime": groups}
    if body.mode == "individual_regular_groups_prime":
        return {"regular": individual, "prime": groups}
    if body.mode == "groups_regular_individual_prime":
        return {"regular": groups, "prime": individual}
    if body.mode == "custom":
        return {"regular": body.participant_mix or [], "prime": body.participant_mix or []}
    return {"regular": observed_mix, "prime": observed_mix}


def _tradeoffs(
    capacity: list[CapacitySegment],
    pricing: PricingRules,
    overrides: dict[tuple[str, int], int],
) -> list[FinancialTradeoffDetail]:
    total_capacity = sum(segment.duration_minutes for segment in capacity)
    average_rates: dict[int, int | None] = {}
    for participant_count in range(1, 5):
        weighted_rate = 0
        complete = total_capacity > 0
        for segment in capacity:
            rate = _resolve_rate(
                pricing,
                segment,
                participant_count,
                overrides,
            )
            if rate is None:
                complete = False
                break
            weighted_rate += rate * segment.duration_minutes
        average_rates[participant_count] = (
            round(weighted_rate / total_capacity) if complete else None
        )

    individual_rate = average_rates[1]
    individual_revenue = individual_rate if individual_rate is not None else None
    tradeoffs = []
    for participant_count in range(1, 5):
        rate = average_rates[participant_count]
        full_revenue = rate * participant_count if rate is not None else None
        versus = None
        break_even = None
        if individual_revenue is not None and full_revenue is not None:
            versus = _percentage(full_revenue, individual_revenue)
            if full_revenue > 0:
                break_even = round(individual_revenue / full_revenue * 100, 1)
        tradeoffs.append(
            FinancialTradeoffDetail(
                participant_count=participant_count,
                average_hourly_rate_cents=rate,
                full_class_revenue_cents=full_revenue,
                revenue_vs_individual_pct=versus,
                break_even_occupancy_pct=break_even,
            )
        )
    return tradeoffs


def _minutes_to_time(value: int) -> time:
    return time(hour=value // 60, minute=value % 60)


def _hourly_capacity_slots(
    capacity: list[CapacitySegment],
) -> list[tuple[CapacitySegment, int]]:
    return [
        (segment, start_minute)
        for segment in capacity
        for start_minute in range(
            segment.start_minute,
            segment.start_minute + (segment.duration_minutes // 60) * 60,
            60,
        )
    ]


def _evenly_selected_slots(
    slots: list[tuple[CapacitySegment, int]],
    occupancy_pct: float,
) -> list[tuple[CapacitySegment, int]]:
    target = round(len(slots) * occupancy_pct / 100)
    if target == 0:
        return []
    return [slots[index * len(slots) // target] for index in range(target)]


def _participant_counts(
    mix: list[ParticipantMixItem],
    slot_count: int,
) -> list[int]:
    quantities = [
        int(slot_count * item.percentage // 100)
        for item in mix
    ]
    remaining = slot_count - sum(quantities)
    ranked = sorted(
        range(len(mix)),
        key=lambda index: (
            slot_count * mix[index].percentage / 100 - quantities[index],
            -mix[index].participant_count,
        ),
        reverse=True,
    )
    for index in ranked[:remaining]:
        quantities[index] += 1
    return [
        item.participant_count
        for item, quantity in zip(mix, quantities)
        for _ in range(quantity)
    ]


def _simulated_schedule(
    capacity: list[CapacitySegment],
    mixes: dict[str, list[ParticipantMixItem]],
    occupancy_pct: float,
    pricing: PricingRules,
    overrides: dict[tuple[str, int], int],
) -> list[FinancialScenarioScheduleEvent]:
    """Allocate capacity to complete, evenly spread, one-hour class blocks."""
    events: list[FinancialScenarioScheduleEvent] = []
    slots_by_category = {"regular": [], "prime": []}
    for slot in _hourly_capacity_slots(capacity):
        slots_by_category[slot[0].time_category].append(slot)
    for category, slots in slots_by_category.items():
        selected = _evenly_selected_slots(slots, occupancy_pct)
        counts = _participant_counts(mixes[category], len(selected))
        for index, ((segment, start_minute), participant_count) in enumerate(
            zip(selected, counts)
        ):
            rate = _resolve_rate(pricing, segment, participant_count, overrides)
            events.append(
                FinancialScenarioScheduleEvent(
                    id=(
                        f"{segment.local_date.isoformat()}-{segment.place_id}-"
                        f"{start_minute}-{index}"
                    ),
                    local_date=segment.local_date,
                    place_name=segment.place_name,
                    start_time=_minutes_to_time(start_minute),
                    end_time=_minutes_to_time(start_minute + 60),
                    participant_count=participant_count,
                    time_category=segment.time_category,
                    hourly_rate_cents=rate,
                    total_revenue_cents=(
                        rate * participant_count if rate is not None else None
                    ),
                )
            )
    return events


def _scenario_metric_from_schedule(
    capacity: list[CapacitySegment],
    schedule: list[FinancialScenarioScheduleEvent],
) -> FinancialScenarioMetric:
    available_minutes = len(_hourly_capacity_slots(capacity)) * 60
    projected_revenue_cents = sum(
        event.total_revenue_cents or 0 for event in schedule
    )
    participant_hours = sum(event.participant_count for event in schedule)
    return FinancialScenarioMetric(
        available_minutes=available_minutes,
        utilized_minutes=len(schedule) * 60,
        occupancy_pct=_percentage(len(schedule), available_minutes / 60),
        participant_hours=participant_hours,
        projected_revenue_cents=projected_revenue_cents,
    )


def evaluate_financial_scenario(
    db: Session,
    professional_id: uuid.UUID,
    body: FinancialScenarioInput,
) -> FinancialScenarioResult:
    context = _load_context(
        db,
        professional_id,
        body.date_from,
        body.date_to,
        body.place_ids,
    )
    dashboard = build_financial_dashboard(
        db,
        professional_id,
        body.date_from,
        body.date_to,
        body.place_ids,
    )
    mixes = _scenario_mixes(body, dashboard.observed_participant_mix)
    overrides = {
        (rate.time_category, rate.participant_count): rate.hourly_rate_cents
        for rate in body.rate_overrides
    }
    schedule = _simulated_schedule(
        context.simulation_capacity,
        mixes,
        body.occupancy_pct,
        context.pricing,
        overrides,
    )
    scenario = _scenario_metric_from_schedule(context.simulation_capacity, schedule)
    mix = _normalize_mix(
        {
            participant_count: sum(
                1
                for event in schedule
                if event.participant_count == participant_count
            )
            for participant_count in range(1, 5)
        }
    )
    baseline = FinancialScenarioMetric(
        available_minutes=dashboard.available_minutes,
        utilized_minutes=dashboard.booked_minutes,
        occupancy_pct=dashboard.occupancy_pct,
        participant_hours=dashboard.participant_hours,
        projected_revenue_cents=dashboard.projected_revenue_cents,
    )
    return FinancialScenarioResult(
        assumptions=dashboard.assumptions,
        mode=body.mode,
        participant_mix=mix,
        baseline=baseline,
        scenario=scenario,
        incremental_revenue_cents=(
            scenario.projected_revenue_cents
            - baseline.projected_revenue_cents
        ),
        incremental_participant_hours=round(
            scenario.participant_hours - baseline.participant_hours,
            2,
        ),
        tradeoffs=_tradeoffs(
            context.capacity,
            context.pricing,
            overrides,
        ),
        simulated_schedule=schedule,
        customer_estimate=estimate_customer_range(
            scenario.participant_hours,
            body.date_from,
            body.date_to,
        ),
    )

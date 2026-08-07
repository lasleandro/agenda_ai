"""Confirm schedule occurrences into immutable recognized-revenue snapshots."""

import uuid
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models import (
    RevenueOccurrence,
    RevenueOccurrenceLine,
    RevenueOccurrenceParticipant,
)
from app.schemas.financial import (
    RevenueCandidateDetail,
    RevenueCandidateParticipant,
    RevenueOccurrenceCreate,
    RevenueOccurrenceDetail,
    RevenueOccurrenceParticipantDetail,
    RevenuePricingLineDetail,
    RevenueSummaryBreakdown,
    RevenueSummaryDetail,
    RevenueSummaryTimePoint,
)
from app.services.financial_capacity import (
    TIMEZONE,
    load_pricing_rules,
    load_prime_ranges,
    split_range,
    time_to_minutes,
)
from app.services.scheduling import (
    ScheduleOccurrence,
    ScheduleParticipant,
    get_schedule_occurrence,
    list_schedule_occurrences,
)


class RevenueOccurrenceNotFoundError(ValueError):
    pass


class RevenueOccurrenceConflictError(ValueError):
    pass


class RevenueOccurrenceValidationError(ValueError):
    pass


def _round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _minutes_to_time(value: int) -> time:
    normalized = value % (24 * 60)
    return time(hour=normalized // 60, minute=normalized % 60)


def list_revenue_candidates(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> list[RevenueCandidateDetail]:
    occurrences = list_schedule_occurrences(
        db,
        professional_id,
        date_from,
        date_to,
    )
    recognized = {
        (row.source_type, row.source_id, row.occurrence_date): row.id
        for row in (
            db.query(RevenueOccurrence)
            .filter(
                RevenueOccurrence.professional_id == professional_id,
                RevenueOccurrence.occurrence_date >= date_from,
                RevenueOccurrence.occurrence_date <= date_to,
            )
            .all()
        )
    }
    now = datetime.now(TIMEZONE)
    return [
        RevenueCandidateDetail(
            source_type=occurrence.source_type,
            source_id=occurrence.source_id,
            occurrence_date=occurrence.occurrence_date,
            starts_at=occurrence.starts_at,
            ends_at=occurrence.ends_at,
            source_label=occurrence.source_label,
            place_id=occurrence.place_id,
            place_name=occurrence.place_name,
            participants=[
                RevenueCandidateParticipant(
                    contact_id=participant.contact_id,
                    contact_name=participant.contact_name,
                )
                for participant in occurrence.participants
            ],
            recognized_occurrence_id=recognized.get(
                (
                    occurrence.source_type,
                    occurrence.source_id,
                    occurrence.occurrence_date,
                )
            ),
            can_confirm=occurrence.ends_at <= now,
        )
        for occurrence in occurrences
    ]


def _pricing_segments(
    occurrence: ScheduleOccurrence,
    prime_ranges: dict[int, list[tuple[int, int]]],
) -> list[tuple[int, int, str]]:
    local_start = occurrence.starts_at.astimezone(TIMEZONE)
    local_end = occurrence.ends_at.astimezone(TIMEZONE)
    if local_start.date() != local_end.date():
        raise RevenueOccurrenceValidationError(
            "Cross-midnight revenue occurrences are not supported"
        )
    start_minute = time_to_minutes(local_start.time())
    end_minute = time_to_minutes(local_end.time())
    if end_minute <= start_minute:
        raise RevenueOccurrenceValidationError(
            "Revenue occurrence must end after it starts"
        )
    prime = prime_ranges[occurrence.occurrence_date.weekday()]
    boundaries = {
        boundary for start, end in prime for boundary in (start, end)
    }
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
        segments.append((segment_start, segment_end, category))
    return segments


def _participant_rate(
    participant: ScheduleParticipant,
    occurrence: ScheduleOccurrence,
    category: str,
    participant_count: int,
    pricing,
) -> tuple[int | None, str]:
    if participant.hourly_rate_cents is not None:
        return participant.hourly_rate_cents, "customer"
    if occurrence.group_hourly_rate_cents is not None:
        return occurrence.group_hourly_rate_cents, "group"
    place_rule = (
        occurrence.place_id,
        category,
        participant_count,
    )
    if occurrence.place_id is not None and place_rule in pricing.place_rates:
        return pricing.place_rates[place_rule], "place"
    if participant_count in pricing.global_rates:
        return pricing.global_rates[participant_count], "tenant"
    return None, "unset"


def _outcome_status(body: RevenueOccurrenceCreate) -> str:
    statuses = {
        outcome.attendance_status for outcome in body.participant_outcomes
    }
    return statuses.pop() if len(statuses) == 1 else "mixed"


def create_revenue_occurrence(
    db: Session,
    professional_id: uuid.UUID,
    confirmed_by_user_id: uuid.UUID,
    body: RevenueOccurrenceCreate,
) -> RevenueOccurrence:
    existing = (
        db.query(RevenueOccurrence.id)
        .filter(
            RevenueOccurrence.professional_id == professional_id,
            RevenueOccurrence.source_type == body.source_type,
            RevenueOccurrence.source_id == body.source_id,
            RevenueOccurrence.occurrence_date == body.occurrence_date,
        )
        .first()
    )
    if existing is not None:
        raise RevenueOccurrenceConflictError(
            "This schedule occurrence has already been recognized"
        )
    if body.occurrence_date > datetime.now(TIMEZONE).date():
        raise RevenueOccurrenceValidationError(
            "Future schedule occurrences cannot be recognized"
        )

    schedule = get_schedule_occurrence(
        db,
        professional_id,
        body.source_type,
        body.source_id,
        body.occurrence_date,
    )
    if schedule is None:
        raise RevenueOccurrenceNotFoundError(
            "Schedule occurrence was not found"
        )
    if schedule.ends_at > datetime.now(TIMEZONE):
        raise RevenueOccurrenceValidationError(
            "Schedule occurrence must end before revenue recognition"
        )
    outcomes = {
        outcome.contact_id: outcome for outcome in body.participant_outcomes
    }
    scheduled_contact_ids = {
        participant.contact_id for participant in schedule.participants
    }
    if set(outcomes) != scheduled_contact_ids:
        raise RevenueOccurrenceValidationError(
            "Participant outcomes must match the scheduled participants"
        )

    billable_count = sum(
        1 for outcome in outcomes.values() if outcome.billable
    )
    pricing_count = billable_count or len(schedule.participants)
    pricing = load_pricing_rules(db, professional_id)
    segments = _pricing_segments(
        schedule,
        load_prime_ranges(db, professional_id),
    )
    participant_snapshots = []
    participant_lines: list[
        tuple[RevenueOccurrenceParticipant, list[RevenueOccurrenceLine]]
    ] = []
    quoted_total = 0
    subtotal = 0
    for participant in schedule.participants:
        outcome = outcomes[participant.contact_id]
        quoted_amount = 0
        billed_amount = 0
        lines = []
        for segment_start, segment_end, category in segments:
            rate, source = _participant_rate(
                participant,
                schedule,
                category,
                pricing_count,
                pricing,
            )
            if rate is None and outcome.billable:
                raise RevenueOccurrenceValidationError(
                    f"Missing price for billable participant "
                    f"{participant.contact_name}"
                )
            duration = segment_end - segment_start
            quoted = (
                _round_cents(
                    Decimal(rate) * Decimal(duration) / Decimal(60)
                )
                if rate is not None
                else 0
            )
            billed = quoted if outcome.billable else 0
            quoted_amount += quoted
            billed_amount += billed
            lines.append(
                RevenueOccurrenceLine(
                    start_time=_minutes_to_time(segment_start),
                    end_time=_minutes_to_time(segment_end),
                    duration_minutes=duration,
                    time_category=category,
                    hourly_rate_cents=rate,
                    rate_source=source,
                    billable=outcome.billable,
                    quoted_amount_cents=quoted,
                    billed_amount_cents=billed,
                    pricing_context={
                        "participant_count": pricing_count,
                        "place_id": (
                            str(schedule.place_id)
                            if schedule.place_id is not None
                            else None
                        ),
                        "time_category": category,
                    },
                )
            )
        participant_snapshot = RevenueOccurrenceParticipant(
            contact_id=participant.contact_id,
            contact_name_snapshot=participant.contact_name,
            attendance_status=outcome.attendance_status,
            billable=outcome.billable,
            quoted_amount_cents=quoted_amount,
            billed_amount_cents=billed_amount,
        )
        participant_snapshots.append(participant_snapshot)
        participant_lines.append((participant_snapshot, lines))
        quoted_total += quoted_amount
        subtotal += billed_amount

    total = subtotal + body.adjustment_cents
    occurrence = RevenueOccurrence(
        professional_id=professional_id,
        source_type=schedule.source_type,
        source_id=schedule.source_id,
        occurrence_date=schedule.occurrence_date,
        starts_at=schedule.starts_at,
        ends_at=schedule.ends_at,
        timezone=str(TIMEZONE),
        source_label_snapshot=schedule.source_label,
        place_id=schedule.place_id,
        place_name_snapshot=schedule.place_name,
        outcome_status=_outcome_status(body),
        participant_count=len(schedule.participants),
        billable_participant_count=billable_count,
        currency="BRL",
        quoted_total_cents=quoted_total,
        subtotal_cents=subtotal,
        adjustment_cents=body.adjustment_cents,
        total_cents=total,
        note=body.note,
        confirmed_by_user_id=confirmed_by_user_id,
    )
    db.add(occurrence)
    db.flush()
    for participant_snapshot, lines in participant_lines:
        participant_snapshot.occurrence_id = occurrence.id
        db.add(participant_snapshot)
        db.flush()
        for line in lines:
            line.participant_snapshot_id = participant_snapshot.id
            db.add(line)
    return occurrence


def revenue_occurrence_detail(
    db: Session,
    occurrence: RevenueOccurrence,
) -> RevenueOccurrenceDetail:
    participant_rows = (
        db.query(RevenueOccurrenceParticipant)
        .filter(
            RevenueOccurrenceParticipant.occurrence_id == occurrence.id
        )
        .order_by(RevenueOccurrenceParticipant.contact_name_snapshot)
        .all()
    )
    participant_ids = [participant.id for participant in participant_rows]
    line_rows = (
        db.query(RevenueOccurrenceLine)
        .filter(
            RevenueOccurrenceLine.participant_snapshot_id.in_(
                participant_ids
            )
        )
        .order_by(RevenueOccurrenceLine.start_time)
        .all()
        if participant_ids
        else []
    )
    lines_by_participant: dict[
        uuid.UUID,
        list[RevenueOccurrenceLine],
    ] = {}
    for line in line_rows:
        lines_by_participant.setdefault(
            line.participant_snapshot_id,
            [],
        ).append(line)
    return RevenueOccurrenceDetail(
        id=occurrence.id,
        source_type=occurrence.source_type,
        source_id=occurrence.source_id,
        occurrence_date=occurrence.occurrence_date,
        starts_at=occurrence.starts_at,
        ends_at=occurrence.ends_at,
        timezone=occurrence.timezone,
        source_label=occurrence.source_label_snapshot,
        place_id=occurrence.place_id,
        place_name=occurrence.place_name_snapshot,
        outcome_status=occurrence.outcome_status,
        participant_count=occurrence.participant_count,
        billable_participant_count=occurrence.billable_participant_count,
        currency=occurrence.currency,
        quoted_total_cents=occurrence.quoted_total_cents,
        subtotal_cents=occurrence.subtotal_cents,
        adjustment_cents=occurrence.adjustment_cents,
        total_cents=occurrence.total_cents,
        note=occurrence.note,
        confirmed_at=occurrence.confirmed_at,
        participants=[
            RevenueOccurrenceParticipantDetail(
                id=participant.id,
                contact_id=participant.contact_id,
                contact_name=participant.contact_name_snapshot,
                attendance_status=participant.attendance_status,
                billable=participant.billable,
                quoted_amount_cents=participant.quoted_amount_cents,
                billed_amount_cents=participant.billed_amount_cents,
                pricing_lines=[
                    RevenuePricingLineDetail(
                        id=line.id,
                        start_time=line.start_time,
                        end_time=line.end_time,
                        duration_minutes=line.duration_minutes,
                        time_category=line.time_category,
                        hourly_rate_cents=line.hourly_rate_cents,
                        rate_source=line.rate_source,
                        billable=line.billable,
                        quoted_amount_cents=line.quoted_amount_cents,
                        billed_amount_cents=line.billed_amount_cents,
                        pricing_context=line.pricing_context,
                    )
                    for line in lines_by_participant.get(participant.id, [])
                ],
            )
            for participant in participant_rows
        ],
    )


def _breakdown(
    values: dict[str, tuple[str, int, int]],
) -> list[RevenueSummaryBreakdown]:
    return [
        RevenueSummaryBreakdown(
            key=key,
            label=label,
            occurrence_count=count,
            total_cents=total,
        )
        for key, (label, count, total) in sorted(
            values.items(),
            key=lambda item: item[1][2],
            reverse=True,
        )
    ]


def build_revenue_summary(
    db: Session,
    professional_id: uuid.UUID,
    date_from: date,
    date_to: date,
    occurrence_limit: int = 100,
) -> RevenueSummaryDetail:
    rows = (
        db.query(RevenueOccurrence)
        .filter(
            RevenueOccurrence.professional_id == professional_id,
            RevenueOccurrence.occurrence_date >= date_from,
            RevenueOccurrence.occurrence_date <= date_to,
        )
        .order_by(
            RevenueOccurrence.occurrence_date.desc(),
            RevenueOccurrence.starts_at.desc(),
        )
        .all()
    )
    details = [revenue_occurrence_detail(db, row) for row in rows]
    by_place: dict[str, tuple[str, int, int]] = {}
    by_group: dict[str, tuple[str, int, int]] = {}
    by_customer: dict[str, tuple[str, int, int]] = {}
    by_date: dict[date, tuple[int, int]] = {
        current: (0, 0)
        for current in (
            date_from.fromordinal(day)
            for day in range(date_from.toordinal(), date_to.toordinal() + 1)
        )
    }
    for detail in details:
        place_key = str(detail.place_id) if detail.place_id else "without_place"
        place_label = detail.place_name or "Sem local"
        _, place_count, place_total = by_place.get(
            place_key,
            (place_label, 0, 0),
        )
        by_place[place_key] = (
            place_label,
            place_count + 1,
            place_total + detail.total_cents,
        )
        if detail.source_type == "recurring_slot":
            group_key = str(detail.source_id)
            _, group_count, group_total = by_group.get(
                group_key,
                (detail.source_label, 0, 0),
            )
            by_group[group_key] = (
                detail.source_label,
                group_count + 1,
                group_total + detail.total_cents,
            )
        for participant in detail.participants:
            customer_key = str(participant.contact_id)
            _, customer_count, customer_total = by_customer.get(
                customer_key,
                (participant.contact_name, 0, 0),
            )
            by_customer[customer_key] = (
                participant.contact_name,
                customer_count + 1,
                customer_total + participant.billed_amount_cents,
            )
        date_count, date_total = by_date[detail.occurrence_date]
        by_date[detail.occurrence_date] = (
            date_count + 1,
            date_total + detail.total_cents,
        )

    return RevenueSummaryDetail(
        period_start=date_from,
        period_end=date_to,
        currency="BRL",
        revenue_basis=(
            "Somente ocorrências confirmadas explicitamente, usando snapshots "
            "imutáveis de participantes, duração e preço."
        ),
        occurrence_count=len(rows),
        participant_count=sum(row.participant_count for row in rows),
        billable_participant_count=sum(
            row.billable_participant_count for row in rows
        ),
        quoted_total_cents=sum(row.quoted_total_cents for row in rows),
        subtotal_cents=sum(row.subtotal_cents for row in rows),
        adjustment_cents=sum(row.adjustment_cents for row in rows),
        total_cents=sum(row.total_cents for row in rows),
        by_place=_breakdown(by_place),
        by_customer=_breakdown(by_customer),
        by_group=_breakdown(by_group),
        time_series=[
            RevenueSummaryTimePoint(
                date=current,
                occurrence_count=count,
                total_cents=total,
            )
            for current, (count, total) in by_date.items()
        ],
        occurrences=details[:occurrence_limit],
    )

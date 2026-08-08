"""Feature-guarded commercial overrides, inheritance, and global rates."""

import uuid
from datetime import time
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.dependencies import require_authenticated, require_commercial_financials
from app.database import SessionLocal
from app.models import (
    Contact,
    FinancialRate,
    Place,
    PlaceFinancialRate,
    PrimeTimeWindow,
    ProfessionalFinancialSettings,
    RecurringSlot,
    RecurringSlotParticipant,
    WorkJourneyInterval,
)
from app.schemas.financial import (
    CommercialOverrideUpdate,
    CustomerFinancialDetail,
    FinancialConfigurationDetail,
    FinancialSettingsDetail,
    FinancialSettingsUpdate,
    GlobalRateDetail,
    GroupFinancialDetail,
    GroupParticipantFinancialDetail,
    PlaceRateDetail,
    PlaceRateMatrixDetail,
    PlaceRatesReplace,
    PrimeTimeWindowDetail,
    PrimeTimeWindowsReplace,
    PricingQuoteDetail,
    PricingQuoteInput,
    PricingQuoteSegment,
    WorkJourneyIntervalDetail,
    WorkJourneyReplace,
)
from app.services.financial_audit import add_financial_audit
from app.services.financial_resolver import (
    get_default_commercial_status,
    get_global_hourly_rate,
    resolve_commercial_status,
    resolve_hourly_rate,
)

router = APIRouter(prefix="/api/financial", tags=["financial"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _request_origin(request: Request) -> tuple[str | None, str | None]:
    source_ip = request.client.host if request.client else None
    return source_ip, request.headers.get("user-agent")


def _get_contact(
    db: Session,
    contact_id: uuid.UUID,
    professional_id: uuid.UUID,
) -> Contact:
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == contact_id,
            Contact.professional_id == professional_id,
        )
        .first()
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return contact


def _get_group(
    db: Session,
    group_id: uuid.UUID,
    professional_id: uuid.UUID,
) -> RecurringSlot:
    group = (
        db.query(RecurringSlot)
        .filter(
            RecurringSlot.id == group_id,
            RecurringSlot.professional_id == professional_id,
            RecurringSlot.class_type == "group",
        )
        .first()
    )
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


def _customer_detail(
    db: Session,
    *,
    contact: Contact,
    professional_id: uuid.UUID,
    group: RecurringSlot | None = None,
    participant_count: int = 1,
) -> CustomerFinancialDetail:
    tenant_status = get_default_commercial_status(db, professional_id)
    tenant_rate = get_global_hourly_rate(db, professional_id, participant_count)
    place_rate = None
    if contact.home_place_id is not None:
        place_rate = (
            db.query(PlaceFinancialRate.hourly_rate_cents)
            .filter(
                PlaceFinancialRate.professional_id == professional_id,
                PlaceFinancialRate.place_id == contact.home_place_id,
                PlaceFinancialRate.time_category == "regular",
                PlaceFinancialRate.participant_count == participant_count,
            )
            .scalar()
        )
    effective_status, status_source = resolve_commercial_status(
        customer_status=contact.commercial_status,
        group_status=group.commercial_status if group else None,
        tenant_status=tenant_status,
    )
    effective_rate, rate_source = resolve_hourly_rate(
        customer_rate_cents=contact.hourly_rate_cents,
        group_rate_cents=group.hourly_rate_cents if group else None,
        place_rate_cents=place_rate,
        tenant_rate_cents=tenant_rate,
    )
    return CustomerFinancialDetail(
        contact_id=contact.id,
        contact_name=contact.display_name,
        commercial_status=contact.commercial_status,
        hourly_rate_cents=contact.hourly_rate_cents,
        effective_commercial_status=effective_status,
        commercial_status_source=status_source,
        effective_hourly_rate_cents=effective_rate,
        hourly_rate_source=rate_source,
    )


def _group_detail(
    db: Session,
    *,
    group: RecurringSlot,
    professional_id: uuid.UUID,
) -> GroupFinancialDetail:
    contacts = (
        db.query(Contact)
        .join(
            RecurringSlotParticipant,
            RecurringSlotParticipant.contact_id == Contact.id,
        )
        .filter(
            RecurringSlotParticipant.recurring_slot_id == group.id,
            Contact.professional_id == professional_id,
        )
        .order_by(Contact.display_name)
        .all()
    )
    participant_count = len(contacts)
    tenant_status = get_default_commercial_status(db, professional_id)
    tenant_rate = get_global_hourly_rate(db, professional_id, participant_count)
    place_rate = (
        db.query(PlaceFinancialRate.hourly_rate_cents)
        .filter(
            PlaceFinancialRate.professional_id == professional_id,
            PlaceFinancialRate.place_id == group.place_id,
            PlaceFinancialRate.time_category == "regular",
            PlaceFinancialRate.participant_count == participant_count,
        )
        .scalar()
    )
    effective_status, status_source = resolve_commercial_status(
        customer_status=None,
        group_status=group.commercial_status,
        tenant_status=tenant_status,
    )
    effective_rate, rate_source = resolve_hourly_rate(
        customer_rate_cents=None,
        group_rate_cents=group.hourly_rate_cents,
        place_rate_cents=place_rate,
        tenant_rate_cents=tenant_rate,
    )
    return GroupFinancialDetail(
        group_id=group.id,
        label=group.label,
        participant_count=participant_count,
        commercial_status=group.commercial_status,
        hourly_rate_cents=group.hourly_rate_cents,
        effective_commercial_status=effective_status,
        commercial_status_source=status_source,
        effective_hourly_rate_cents=effective_rate,
        hourly_rate_source=rate_source,
        participants=[
            GroupParticipantFinancialDetail(
                **_customer_detail(
                    db,
                    contact=contact,
                    professional_id=professional_id,
                    group=group,
                    participant_count=participant_count,
                ).model_dump()
            )
            for contact in contacts
        ],
    )


def _assert_prime_windows_do_not_overlap(
    body: PrimeTimeWindowsReplace,
) -> None:
    for day in range(7):
        ranges = sorted(
            (
                window.start_time,
                window.end_time,
            )
            for window in body.windows
            if day in window.days_of_week
        )
        if any(current[0] < previous[1] for previous, current in zip(ranges, ranges[1:])):
            raise HTTPException(
                status_code=422,
                detail="Prime-time ranges must not overlap on the same weekday",
            )


def _assert_work_journey_is_valid(body: WorkJourneyReplace) -> None:
    for day in range(7):
        day_intervals = [
            interval for interval in body.intervals if interval.day_of_week == day
        ]
        work_ranges = sorted(
            (interval.start_time, interval.end_time)
            for interval in day_intervals
            if interval.interval_type == "work"
        )
        break_ranges = sorted(
            (interval.start_time, interval.end_time)
            for interval in day_intervals
            if interval.interval_type == "break"
        )
        for ranges in (work_ranges, break_ranges):
            if any(
                current[0] < previous[1]
                for previous, current in zip(ranges, ranges[1:])
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Journey intervals of the same type must not overlap",
                )
        for break_start, break_end in break_ranges:
            if not any(
                work_start <= break_start and work_end >= break_end
                for work_start, work_end in work_ranges
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Break intervals must be contained in a work interval",
                )


def _time_to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _minutes_to_time(value: int) -> time:
    return time(hour=value // 60, minute=value % 60)


def _configuration_detail(
    db: Session,
    professional_id: uuid.UUID,
) -> FinancialConfigurationDetail:
    settings = (
        db.query(ProfessionalFinancialSettings)
        .filter(ProfessionalFinancialSettings.professional_id == professional_id)
        .first()
    )
    prime_rows = (
        db.query(PrimeTimeWindow)
        .filter(PrimeTimeWindow.professional_id == professional_id)
        .order_by(PrimeTimeWindow.start_time)
        .all()
    )
    if settings is None or not settings.prime_time_configured:
        prime_windows = [
            PrimeTimeWindowDetail(
                id=None,
                days_of_week=list(range(7)),
                start_time="05:00:00",
                end_time="08:00:00",
                is_default=True,
            ),
            PrimeTimeWindowDetail(
                id=None,
                days_of_week=list(range(7)),
                start_time="18:00:00",
                end_time="21:00:00",
                is_default=True,
            ),
        ]
    else:
        prime_windows = [
            PrimeTimeWindowDetail(
                id=window.id,
                days_of_week=window.days_of_week,
                start_time=window.start_time,
                end_time=window.end_time,
                is_default=False,
            )
            for window in prime_rows
        ]

    global_rates = {
        rate.participant_count: rate.hourly_rate_cents
        for rate in (
            db.query(FinancialRate)
            .filter(FinancialRate.professional_id == professional_id)
            .all()
        )
    }
    place_rate_rows = (
        db.query(PlaceFinancialRate)
        .filter(PlaceFinancialRate.professional_id == professional_id)
        .all()
    )
    place_rates = {
        (rate.place_id, rate.time_category, rate.participant_count): rate.hourly_rate_cents
        for rate in place_rate_rows
    }
    places = (
        db.query(Place)
        .filter(Place.professional_id == professional_id)
        .order_by(Place.name)
        .all()
    )
    place_matrices = []
    for place in places:
        rates = []
        for time_category in ("regular", "prime"):
            for participant_count in range(1, 5):
                explicit_rate = place_rates.get(
                    (place.id, time_category, participant_count)
                )
                fallback_rate = global_rates.get(participant_count)
                rates.append(
                    PlaceRateDetail(
                        time_category=time_category,
                        participant_count=participant_count,
                        hourly_rate_cents=explicit_rate,
                        effective_hourly_rate_cents=(
                            explicit_rate if explicit_rate is not None else fallback_rate
                        ),
                        source=(
                            "place"
                            if explicit_rate is not None
                            else "tenant"
                            if fallback_rate is not None
                            else "unset"
                        ),
                    )
                )
        place_matrices.append(
            PlaceRateMatrixDetail(
                place_id=place.id,
                place_name=place.name,
                rates=rates,
            )
        )

    journey_rows = (
        db.query(WorkJourneyInterval)
        .filter(WorkJourneyInterval.professional_id == professional_id)
        .order_by(
            WorkJourneyInterval.day_of_week,
            WorkJourneyInterval.start_time,
        )
        .all()
    )
    return FinancialConfigurationDetail(
        prime_time_windows=prime_windows,
        places=place_matrices,
        work_journey=[
            WorkJourneyIntervalDetail(
                id=interval.id,
                day_of_week=interval.day_of_week,
                interval_type=interval.interval_type,
                start_time=interval.start_time,
                end_time=interval.end_time,
            )
            for interval in journey_rows
        ],
    )


@router.get("/settings", response_model=FinancialSettingsDetail)
def get_financial_settings(
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
):
    settings = (
        db.query(ProfessionalFinancialSettings)
        .filter(ProfessionalFinancialSettings.professional_id == professional_id)
        .first()
    )
    rates = {
        rate.participant_count: rate.hourly_rate_cents
        for rate in (
            db.query(FinancialRate)
            .filter(FinancialRate.professional_id == professional_id)
            .all()
        )
    }
    return FinancialSettingsDetail(
        default_commercial_status=(
            settings.default_commercial_status if settings else "active"
        ),
        currency=settings.currency if settings else "BRL",
        cancellation_notice_hours=(
            settings.cancellation_notice_hours if settings else 24
        ),
        rates=[
            GlobalRateDetail(
                participant_count=participant_count,
                hourly_rate_cents=rates.get(participant_count),
            )
            for participant_count in range(1, 5)
        ],
    )


@router.patch("/settings", response_model=FinancialSettingsDetail)
def update_financial_settings(
    body: FinancialSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
    user: dict = Depends(require_authenticated),
):
    changes: dict = {}
    if "default_commercial_status" in body.model_fields_set:
        settings = (
            db.query(ProfessionalFinancialSettings)
            .filter(ProfessionalFinancialSettings.professional_id == professional_id)
            .first()
        )
        previous_status = (
            settings.default_commercial_status if settings else "active"
        )
        if body.default_commercial_status != previous_status:
            if settings is None:
                settings = ProfessionalFinancialSettings(
                    professional_id=professional_id,
                )
                db.add(settings)
            settings.default_commercial_status = body.default_commercial_status
            changes["default_commercial_status"] = {
                "before": previous_status,
                "after": body.default_commercial_status,
            }

    if "cancellation_notice_hours" in body.model_fields_set:
        settings = (
            db.query(ProfessionalFinancialSettings)
            .filter(ProfessionalFinancialSettings.professional_id == professional_id)
            .first()
        )
        previous_hours = (
            settings.cancellation_notice_hours if settings else 24
        )
        if body.cancellation_notice_hours != previous_hours:
            if settings is None:
                settings = ProfessionalFinancialSettings(
                    professional_id=professional_id,
                )
                db.add(settings)
            settings.cancellation_notice_hours = body.cancellation_notice_hours
            changes["cancellation_notice_hours"] = {
                "before": previous_hours,
                "after": body.cancellation_notice_hours,
            }

    if body.rates is not None:
        existing_rates = {
            rate.participant_count: rate
            for rate in (
                db.query(FinancialRate)
                .filter(FinancialRate.professional_id == professional_id)
                .all()
            )
        }
        for rate_input in body.rates:
            existing = existing_rates.get(rate_input.participant_count)
            previous_rate = existing.hourly_rate_cents if existing else None
            if previous_rate == rate_input.hourly_rate_cents:
                continue
            if rate_input.hourly_rate_cents is None:
                if existing is not None:
                    db.delete(existing)
            elif existing is None:
                db.add(
                    FinancialRate(
                        professional_id=professional_id,
                        participant_count=rate_input.participant_count,
                        hourly_rate_cents=rate_input.hourly_rate_cents,
                    )
                )
            else:
                existing.hourly_rate_cents = rate_input.hourly_rate_cents
            changes[f"rate_{rate_input.participant_count}"] = {
                "before": previous_rate,
                "after": rate_input.hourly_rate_cents,
            }

    source_ip, user_agent = _request_origin(request)
    add_financial_audit(
        db,
        professional_id=professional_id,
        actor_user_id=uuid.UUID(user["user_id"]),
        entity_type="tenant_financial_settings",
        entity_id=professional_id,
        action="update",
        changes=changes,
        source_ip=source_ip,
        user_agent=user_agent,
    )
    db.commit()
    return get_financial_settings(db, professional_id)


@router.get("/configuration", response_model=FinancialConfigurationDetail)
def get_financial_configuration(
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
):
    return _configuration_detail(db, professional_id)


@router.post("/quote", response_model=PricingQuoteDetail)
def quote_configured_price(
    body: PricingQuoteInput,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
):
    place_exists = (
        db.query(Place.id)
        .filter(
            Place.id == body.place_id,
            Place.professional_id == professional_id,
        )
        .first()
    )
    if place_exists is None:
        raise HTTPException(status_code=404, detail="Place not found")

    configuration = _configuration_detail(db, professional_id)
    prime_ranges = [
        (
            _time_to_minutes(window.start_time),
            _time_to_minutes(window.end_time),
        )
        for window in configuration.prime_time_windows
        if body.day_of_week in window.days_of_week
    ]
    start_minute = _time_to_minutes(body.start_time)
    end_minute = _time_to_minutes(body.end_time)
    boundaries = {start_minute, end_minute}
    for prime_start, prime_end in prime_ranges:
        if start_minute < prime_start < end_minute:
            boundaries.add(prime_start)
        if start_minute < prime_end < end_minute:
            boundaries.add(prime_end)

    global_rate = get_global_hourly_rate(
        db,
        professional_id,
        body.participant_count,
    )
    place_rates = {
        rate.time_category: rate.hourly_rate_cents
        for rate in (
            db.query(PlaceFinancialRate)
            .filter(
                PlaceFinancialRate.professional_id == professional_id,
                PlaceFinancialRate.place_id == body.place_id,
                PlaceFinancialRate.participant_count == body.participant_count,
            )
            .all()
        )
    }
    segments = []
    ordered_boundaries = sorted(boundaries)
    for segment_start, segment_end in zip(
        ordered_boundaries,
        ordered_boundaries[1:],
    ):
        midpoint = (segment_start + segment_end) / 2
        category = (
            "prime"
            if any(start <= midpoint < end for start, end in prime_ranges)
            else "regular"
        )
        explicit_rate = place_rates.get(category)
        hourly_rate = explicit_rate if explicit_rate is not None else global_rate
        source = (
            "place"
            if explicit_rate is not None
            else "tenant"
            if global_rate is not None
            else "unset"
        )
        duration = segment_end - segment_start
        segment_total = None
        if hourly_rate is not None:
            segment_total = int(
                (
                    Decimal(hourly_rate)
                    * Decimal(duration)
                    * Decimal(body.participant_count)
                    / Decimal(60)
                ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
        segments.append(
            PricingQuoteSegment(
                start_time=_minutes_to_time(segment_start),
                end_time=_minutes_to_time(segment_end),
                duration_minutes=duration,
                time_category=category,
                hourly_rate_cents=hourly_rate,
                source=source,
                segment_total_cents=segment_total,
            )
        )
    complete = all(segment.segment_total_cents is not None for segment in segments)
    return PricingQuoteDetail(
        participant_count=body.participant_count,
        segments=segments,
        total_cents=(
            sum(segment.segment_total_cents or 0 for segment in segments)
            if complete
            else None
        ),
    )


@router.put(
    "/prime-time-windows",
    response_model=list[PrimeTimeWindowDetail],
)
def replace_prime_time_windows(
    body: PrimeTimeWindowsReplace,
    request: Request,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
    user: dict = Depends(require_authenticated),
):
    _assert_prime_windows_do_not_overlap(body)
    previous = [
        window.model_dump(mode="json")
        for window in _configuration_detail(
            db,
            professional_id,
        ).prime_time_windows
    ]
    db.query(PrimeTimeWindow).filter(
        PrimeTimeWindow.professional_id == professional_id
    ).delete(synchronize_session=False)
    db.add_all(
        [
            PrimeTimeWindow(
                professional_id=professional_id,
                days_of_week=window.days_of_week,
                start_time=window.start_time,
                end_time=window.end_time,
            )
            for window in body.windows
        ]
    )
    settings = (
        db.query(ProfessionalFinancialSettings)
        .filter(ProfessionalFinancialSettings.professional_id == professional_id)
        .first()
    )
    if settings is None:
        settings = ProfessionalFinancialSettings(professional_id=professional_id)
        db.add(settings)
    settings.prime_time_configured = True

    source_ip, user_agent = _request_origin(request)
    add_financial_audit(
        db,
        professional_id=professional_id,
        actor_user_id=uuid.UUID(user["user_id"]),
        entity_type="prime_time_windows",
        entity_id=professional_id,
        action="replace",
        changes={
            "windows": {
                "before": previous,
                "after": [
                    window.model_dump(mode="json") for window in body.windows
                ],
            }
        },
        source_ip=source_ip,
        user_agent=user_agent,
    )
    db.commit()
    return _configuration_detail(db, professional_id).prime_time_windows


@router.put(
    "/places/{place_id}/rates",
    response_model=PlaceRateMatrixDetail,
)
def replace_place_rates(
    place_id: uuid.UUID,
    body: PlaceRatesReplace,
    request: Request,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
    user: dict = Depends(require_authenticated),
):
    place = (
        db.query(Place)
        .filter(
            Place.id == place_id,
            Place.professional_id == professional_id,
        )
        .first()
    )
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")

    previous_rows = (
        db.query(PlaceFinancialRate)
        .filter(
            PlaceFinancialRate.professional_id == professional_id,
            PlaceFinancialRate.place_id == place_id,
        )
        .all()
    )
    previous = [
        {
            "time_category": rate.time_category,
            "participant_count": rate.participant_count,
            "hourly_rate_cents": rate.hourly_rate_cents,
        }
        for rate in previous_rows
    ]
    db.query(PlaceFinancialRate).filter(
        PlaceFinancialRate.professional_id == professional_id,
        PlaceFinancialRate.place_id == place_id,
    ).delete(synchronize_session=False)
    db.add_all(
        [
            PlaceFinancialRate(
                professional_id=professional_id,
                place_id=place_id,
                time_category=rate.time_category,
                participant_count=rate.participant_count,
                hourly_rate_cents=rate.hourly_rate_cents,
            )
            for rate in body.rates
            if rate.hourly_rate_cents is not None
        ]
    )

    source_ip, user_agent = _request_origin(request)
    add_financial_audit(
        db,
        professional_id=professional_id,
        actor_user_id=uuid.UUID(user["user_id"]),
        entity_type="place_financial_rates",
        entity_id=place_id,
        action="replace",
        changes={
            "rates": {
                "before": previous,
                "after": [
                    rate.model_dump(mode="json")
                    for rate in body.rates
                    if rate.hourly_rate_cents is not None
                ],
            }
        },
        source_ip=source_ip,
        user_agent=user_agent,
    )
    db.commit()
    configuration = _configuration_detail(db, professional_id)
    return next(matrix for matrix in configuration.places if matrix.place_id == place_id)


@router.put(
    "/work-journey",
    response_model=list[WorkJourneyIntervalDetail],
)
def replace_work_journey(
    body: WorkJourneyReplace,
    request: Request,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
    user: dict = Depends(require_authenticated),
):
    _assert_work_journey_is_valid(body)
    previous_rows = (
        db.query(WorkJourneyInterval)
        .filter(WorkJourneyInterval.professional_id == professional_id)
        .all()
    )
    previous = [
        {
            "day_of_week": interval.day_of_week,
            "interval_type": interval.interval_type,
            "start_time": interval.start_time.isoformat(),
            "end_time": interval.end_time.isoformat(),
        }
        for interval in previous_rows
    ]
    db.query(WorkJourneyInterval).filter(
        WorkJourneyInterval.professional_id == professional_id
    ).delete(synchronize_session=False)
    db.add_all(
        [
            WorkJourneyInterval(
                professional_id=professional_id,
                day_of_week=interval.day_of_week,
                interval_type=interval.interval_type,
                start_time=interval.start_time,
                end_time=interval.end_time,
            )
            for interval in body.intervals
        ]
    )

    source_ip, user_agent = _request_origin(request)
    add_financial_audit(
        db,
        professional_id=professional_id,
        actor_user_id=uuid.UUID(user["user_id"]),
        entity_type="work_journey",
        entity_id=professional_id,
        action="replace",
        changes={
            "intervals": {
                "before": previous,
                "after": [
                    interval.model_dump(mode="json")
                    for interval in body.intervals
                ],
            }
        },
        source_ip=source_ip,
        user_agent=user_agent,
    )
    db.commit()
    return _configuration_detail(db, professional_id).work_journey


@router.get("/customers/{contact_id}", response_model=CustomerFinancialDetail)
def get_customer_financials(
    contact_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
):
    contact = _get_contact(db, contact_id, professional_id)
    return _customer_detail(
        db,
        contact=contact,
        professional_id=professional_id,
    )


@router.patch("/customers/{contact_id}", response_model=CustomerFinancialDetail)
def update_customer_financials(
    contact_id: uuid.UUID,
    body: CommercialOverrideUpdate,
    request: Request,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
    user: dict = Depends(require_authenticated),
):
    contact = _get_contact(db, contact_id, professional_id)
    changes = {}
    for field, value in body.model_dump(exclude_unset=True).items():
        previous = getattr(contact, field)
        if previous == value:
            continue
        setattr(contact, field, value)
        changes[field] = {"before": previous, "after": value}

    source_ip, user_agent = _request_origin(request)
    add_financial_audit(
        db,
        professional_id=professional_id,
        actor_user_id=uuid.UUID(user["user_id"]),
        entity_type="customer",
        entity_id=contact.id,
        action="update_commercial_overrides",
        changes=changes,
        source_ip=source_ip,
        user_agent=user_agent,
    )
    db.commit()
    return _customer_detail(
        db,
        contact=contact,
        professional_id=professional_id,
    )


@router.get("/groups/{group_id}", response_model=GroupFinancialDetail)
def get_group_financials(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
):
    group = _get_group(db, group_id, professional_id)
    return _group_detail(db, group=group, professional_id=professional_id)


@router.patch("/groups/{group_id}", response_model=GroupFinancialDetail)
def update_group_financials(
    group_id: uuid.UUID,
    body: CommercialOverrideUpdate,
    request: Request,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_commercial_financials),
    user: dict = Depends(require_authenticated),
):
    group = _get_group(db, group_id, professional_id)
    changes = {}
    for field, value in body.model_dump(exclude_unset=True).items():
        previous = getattr(group, field)
        if previous == value:
            continue
        setattr(group, field, value)
        changes[field] = {"before": previous, "after": value}

    source_ip, user_agent = _request_origin(request)
    add_financial_audit(
        db,
        professional_id=professional_id,
        actor_user_id=uuid.UUID(user["user_id"]),
        entity_type="group",
        entity_id=group.id,
        action="update_commercial_overrides",
        changes=changes,
        source_ip=source_ip,
        user_agent=user_agent,
    )
    db.commit()
    return _group_detail(db, group=group, professional_id=professional_id)

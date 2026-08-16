"""Deterministic place-stay resolution for calendar item creation and moves."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import Place, RecurringSlot
from app.services.scheduling import TIMEZONE

PlaceStayOutcome = Literal["resolved", "ambiguous", "uncovered", "invalid_place"]


@dataclass(frozen=True)
class PlaceStayResolution:
    """Result of resolving one local date/time interval against active stays."""

    outcome: PlaceStayOutcome
    place_id: uuid.UUID | None
    stay_id: uuid.UUID | None
    matching_place_ids: tuple[uuid.UUID, ...]
    is_explicit_exception: bool = False


def resolve_place_stay(
    db: Session,
    professional_id: uuid.UUID,
    *,
    start_at: datetime,
    end_at: datetime,
    requested_place_id: uuid.UUID | None = None,
) -> PlaceStayResolution:
    """Resolve a place from fully containing active place stays.

    An explicit tenant-owned place is always retained. If no stay covers it,
    the result marks an explicit exception instead of silently inferring a
    different place. Without an explicit place, only one covering stay can
    resolve the interval.
    """
    local_start = start_at.astimezone(TIMEZONE)
    local_end = end_at.astimezone(TIMEZONE)
    if end_at <= start_at or local_start.date() != local_end.date():
        return PlaceStayResolution("uncovered", None, None, ())

    if requested_place_id is not None:
        place_exists = (
            db.query(Place.id)
            .filter(
                Place.id == requested_place_id,
                Place.professional_id == professional_id,
            )
            .first()
            is not None
        )
        if not place_exists:
            return PlaceStayResolution("invalid_place", None, None, ())

    target_date = local_start.date()
    matching_stays = (
        db.query(RecurringSlot)
        .filter(
            RecurringSlot.professional_id == professional_id,
            RecurringSlot.slot_kind == "availability",
            RecurringSlot.status == "active",
            RecurringSlot.day_of_week == target_date.weekday(),
            RecurringSlot.start_time <= local_start.time().replace(tzinfo=None),
            RecurringSlot.end_time >= local_end.time().replace(tzinfo=None),
            or_(
                and_(
                    RecurringSlot.recurrence_type == "weekly",
                    or_(
                        RecurringSlot.valid_from.is_(None),
                        RecurringSlot.valid_from <= target_date,
                    ),
                    or_(
                        RecurringSlot.valid_until.is_(None),
                        RecurringSlot.valid_until >= target_date,
                    ),
                ),
                and_(
                    RecurringSlot.recurrence_type == "once",
                    RecurringSlot.scheduled_date == target_date,
                ),
            ),
        )
        .order_by(RecurringSlot.id)
        .all()
    )
    matching_place_ids = tuple(sorted({stay.place_id for stay in matching_stays}, key=str))

    if requested_place_id is not None:
        requested_stay = next(
            (stay for stay in matching_stays if stay.place_id == requested_place_id),
            None,
        )
        if requested_stay is not None:
            return PlaceStayResolution(
                "resolved",
                requested_place_id,
                requested_stay.id,
                matching_place_ids,
            )
        return PlaceStayResolution(
            "resolved",
            requested_place_id,
            None,
            matching_place_ids,
            is_explicit_exception=True,
        )

    if len(matching_stays) == 1:
        stay = matching_stays[0]
        return PlaceStayResolution("resolved", stay.place_id, stay.id, matching_place_ids)
    if len(matching_stays) > 1:
        return PlaceStayResolution("ambiguous", None, None, matching_place_ids)
    return PlaceStayResolution("uncovered", None, None, ())

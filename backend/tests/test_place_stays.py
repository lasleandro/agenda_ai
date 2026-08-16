"""Unit tests for deterministic place-stay resolution."""

from datetime import date, datetime, time, timedelta
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Place, Professional, RecurringSlot
from app.services.place_stays import resolve_place_stay
from app.services.scheduling import TIMEZONE

MONDAY = date(2026, 8, 3)


def _phone() -> str:
    return f"+55119{uuid.uuid4().hex[:8]}"


def _professional(db, name: str) -> Professional:
    professional = Professional(name=name, assistant_phone=_phone())
    db.add(professional)
    db.commit()
    return professional


def _place(db, professional: Professional, name: str) -> Place:
    place = Place(
        professional_id=professional.id,
        name=name,
        normalized_name=name.lower(),
    )
    db.add(place)
    db.commit()
    return place


def _stay(
    db,
    professional: Professional,
    place: Place,
    *,
    start: time = time(10),
    end: time = time(12),
    status: str = "active",
    valid_from: date | None = None,
    valid_until: date | None = None,
) -> RecurringSlot:
    stay = RecurringSlot(
        professional_id=professional.id,
        place_id=place.id,
        day_of_week=MONDAY.weekday(),
        start_time=start,
        end_time=end,
        slot_kind="availability",
        status=status,
        valid_from=valid_from,
        valid_until=valid_until,
    )
    db.add(stay)
    db.commit()
    return stay


def _cleanup(db, professionals: list[Professional]) -> None:
    professional_ids = [professional.id for professional in professionals]
    db.query(RecurringSlot).filter(
        RecurringSlot.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(Place).filter(Place.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.commit()


def _interval(start_hour: int, end_hour: int) -> tuple[datetime, datetime]:
    start = datetime.combine(MONDAY, time(start_hour), tzinfo=TIMEZONE)
    return start, start + timedelta(hours=end_hour - start_hour)


def test_resolve_place_stay_requires_full_containment_and_active_date_range() -> None:
    db = SessionLocal()
    professional = _professional(db, "Resolver tenant")
    try:
        place = _place(db, professional, "Clube")
        stay = _stay(
            db,
            professional,
            place,
            valid_from=MONDAY,
            valid_until=MONDAY + timedelta(days=14),
        )
        start_at, end_at = _interval(10, 11)

        resolved = resolve_place_stay(
            db, professional.id, start_at=start_at, end_at=end_at
        )
        assert resolved.outcome == "resolved"
        assert resolved.place_id == place.id
        assert resolved.stay_id == stay.id

        partial_start, partial_end = _interval(9, 11)
        assert resolve_place_stay(
            db, professional.id, start_at=partial_start, end_at=partial_end
        ).outcome == "uncovered"

        before_start = start_at - timedelta(days=7)
        before_end = end_at - timedelta(days=7)
        assert resolve_place_stay(
            db, professional.id, start_at=before_start, end_at=before_end
        ).outcome == "uncovered"
    finally:
        _cleanup(db, [professional])
        db.close()


def test_resolve_place_stay_requires_choice_for_multiple_matches() -> None:
    db = SessionLocal()
    professional = _professional(db, "Resolver tenant")
    other_professional = _professional(db, "Other tenant")
    try:
        first_place = _place(db, professional, "Clube A")
        second_place = _place(db, professional, "Clube B")
        other_place = _place(db, other_professional, "Outro clube")
        _stay(db, professional, first_place)
        _stay(db, professional, second_place)
        start_at, end_at = _interval(10, 11)

        ambiguous = resolve_place_stay(
            db, professional.id, start_at=start_at, end_at=end_at
        )
        assert ambiguous.outcome == "ambiguous"
        assert set(ambiguous.matching_place_ids) == {first_place.id, second_place.id}

        explicit = resolve_place_stay(
            db,
            professional.id,
            start_at=start_at,
            end_at=end_at,
            requested_place_id=first_place.id,
        )
        assert explicit.outcome == "resolved"
        assert explicit.place_id == first_place.id
        assert explicit.is_explicit_exception is False

        invalid = resolve_place_stay(
            db,
            professional.id,
            start_at=start_at,
            end_at=end_at,
            requested_place_id=other_place.id,
        )
        assert invalid.outcome == "invalid_place"
    finally:
        _cleanup(db, [professional, other_professional])
        db.close()


def test_resolve_place_stay_marks_uncovered_explicit_place_as_exception() -> None:
    db = SessionLocal()
    professional = _professional(db, "Resolver tenant")
    try:
        place = _place(db, professional, "Clube")
        _stay(db, professional, place, status="inactive")
        start_at, end_at = _interval(10, 11)

        resolution = resolve_place_stay(
            db,
            professional.id,
            start_at=start_at,
            end_at=end_at,
            requested_place_id=place.id,
        )

        assert resolution.outcome == "resolved"
        assert resolution.place_id == place.id
        assert resolution.stay_id is None
        assert resolution.is_explicit_exception is True
    finally:
        _cleanup(db, [professional])
        db.close()

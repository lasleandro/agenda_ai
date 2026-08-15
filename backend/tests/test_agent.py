"""Tests for the instructor agent's deterministic building blocks
(operational ontology roadmap v0.2, Phase 2): entity resolution, temporal
phrase resolution, and the read tools. No LLM call is made — the
orchestrator's tool-call loop is out of scope for automated tests."""

from pathlib import Path
import sys
import uuid
from datetime import date, datetime, time, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import entity_resolution, temporal, tools
from app.database import SessionLocal
from app.models import (
    Appointment,
    Contact,
    InstructorEvent,
    Place,
    Professional,
    RecurringSlot,
    RecurringSlotParticipant,
    WorkJourneyInterval,
)
from app.services.scheduling import TIMEZONE

MONDAY = date(2026, 8, 3)  # a known Monday


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().hex[:8]}"


def _make_professional(db) -> Professional:
    professional = Professional(name="Tenant Agent", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    return professional


def _make_contact(db, professional_id, display_name: str) -> Contact:
    contact = Contact(
        professional_id=professional_id,
        phone=_random_phone(),
        display_name=display_name,
        normalized_name=display_name.casefold(),
    )
    db.add(contact)
    db.commit()
    return contact


def _make_place(db, professional_id, name: str) -> Place:
    place = Place(professional_id=professional_id, name=name, normalized_name=name.casefold())
    db.add(place)
    db.commit()
    return place


def _cleanup(db, *, professionals: list[Professional]) -> None:
    professional_ids = [p.id for p in professionals]
    if not professional_ids:
        return
    db.query(WorkJourneyInterval).filter(
        WorkJourneyInterval.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(RecurringSlotParticipant).filter(
        RecurringSlotParticipant.recurring_slot_id.in_(
            db.query(RecurringSlot.id).filter(
                RecurringSlot.professional_id.in_(professional_ids)
            )
        )
    ).delete(synchronize_session=False)
    db.query(RecurringSlot).filter(
        RecurringSlot.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(Appointment).filter(
        Appointment.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(InstructorEvent).filter(
        InstructorEvent.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(Contact).filter(Contact.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(Place).filter(Place.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.commit()


# ---------------------------------------------------------------------------
# Temporal resolution (pure, no DB)
# ---------------------------------------------------------------------------

def test_temporal_resolves_closed_vocabulary_phrases() -> None:
    ref = date(2026, 8, 3)  # Monday
    assert temporal.resolve_temporal_phrase("hoje", reference_date=ref).resolved_date == ref
    assert temporal.resolve_temporal_phrase(
        "amanhã", reference_date=ref
    ).resolved_date == ref + timedelta(days=1)
    assert temporal.resolve_temporal_phrase(
        "ontem", reference_date=ref
    ).resolved_date == ref - timedelta(days=1)

    afternoon = temporal.resolve_temporal_phrase("amanhã de tarde", reference_date=ref)
    assert afternoon.resolved_date == ref + timedelta(days=1)
    assert afternoon.period == (time(12, 0), time(18, 0))


def test_temporal_resolves_week_range_phrases() -> None:
    ref = date(2026, 8, 5)  # a Wednesday

    this_week = temporal.resolve_temporal_phrase("essa semana", reference_date=ref)
    assert this_week.resolved_date_from == date(2026, 8, 3)  # Monday
    assert this_week.resolved_date_to == date(2026, 8, 9)  # Sunday
    assert this_week.resolved_date is None
    assert this_week.recognized is True

    next_week_accented = temporal.resolve_temporal_phrase(
        "próxima semana", reference_date=ref
    )
    assert next_week_accented.resolved_date_from == date(2026, 8, 10)
    assert next_week_accented.resolved_date_to == date(2026, 8, 16)

    next_week_unaccented = temporal.resolve_temporal_phrase(
        "quais horarios do leandro na proxima semana", reference_date=ref
    )
    assert next_week_unaccented.resolved_date_from == date(2026, 8, 10)
    assert next_week_unaccented.resolved_date_to == date(2026, 8, 16)

    coming_week = temporal.resolve_temporal_phrase("semana que vem", reference_date=ref)
    assert coming_week.resolved_date_from == date(2026, 8, 10)
    assert coming_week.resolved_date_to == date(2026, 8, 16)


def test_temporal_unrecognized_phrase_returns_unresolved() -> None:
    resolution = temporal.resolve_temporal_phrase("xyz não reconhecido", reference_date=MONDAY)
    assert resolution.resolved_date is None
    assert resolution.period is None
    assert resolution.recognized is False


# ---------------------------------------------------------------------------
# Entity resolution
# ---------------------------------------------------------------------------

def test_resolve_contacts_returns_disambiguation_candidates() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        _make_contact(db, professional.id, "Maria Silva")
        _make_contact(db, professional.id, "Marcos Silva")

        many = entity_resolution.resolve_contacts(db, professional.id, "Mar")
        assert len(many) == 2

        one = entity_resolution.resolve_contacts(db, professional.id, "Maria")
        assert len(one) == 1
        assert one[0].display_name == "Maria Silva"

        none = entity_resolution.resolve_contacts(db, professional.id, "Zzz")
        assert none == []
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_resolve_contacts_tolerates_a_typo() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        _make_contact(db, professional.id, "Fernanda")

        typo = entity_resolution.resolve_contacts(db, professional.id, "Fernandaa")
        assert len(typo) == 1
        assert typo[0].display_name == "Fernanda"

        unrelated = entity_resolution.resolve_contacts(db, professional.id, "Xyzabc")
        assert unrelated == []
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_resolve_places_tolerates_a_typo() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        _make_place(db, professional.id, "Silva Tennis")

        typo = entity_resolution.resolve_places(db, professional.id, "Silva Tenis")
        assert len(typo) == 1
        assert typo[0].name == "Silva Tennis"
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_resolve_contacts_is_tenant_scoped() -> None:
    db = SessionLocal()
    professional_a = _make_professional(db)
    professional_b = _make_professional(db)
    try:
        _make_contact(db, professional_a.id, "Ana Souza")
        matches = entity_resolution.resolve_places(db, professional_b.id, "ana")
        assert matches == []
        matches_contacts = entity_resolution.resolve_contacts(db, professional_b.id, "Ana")
        assert matches_contacts == []
    finally:
        _cleanup(db, professionals=[professional_a, professional_b])
        db.close()


def test_resolve_groups_filters_by_weekday_and_member() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id, "Clube")
        contact = _make_contact(db, professional.id, "Aluno Grupo")
        created_at = datetime.combine(MONDAY, time(8, 0), tzinfo=TIMEZONE)

        group_slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=0,
            start_time=time(18, 0),
            end_time=time(19, 0),
            group_name="Grupo da Maria",
            class_type="group",
            slot_kind="class",
            max_participants=4,
            recurrence_type="weekly",
            created_at=created_at,
        )
        db.add(group_slot)
        db.flush()
        db.add(
            RecurringSlotParticipant(recurring_slot_id=group_slot.id, contact_id=contact.id)
        )
        db.commit()

        by_weekday = entity_resolution.resolve_groups(db, professional.id, weekday=0)
        assert len(by_weekday) == 1
        assert by_weekday[0].group_name == "Grupo da Maria"
        assert by_weekday[0].participant_names == ["Aluno Grupo"]

        by_other_weekday = entity_resolution.resolve_groups(db, professional.id, weekday=2)
        assert by_other_weekday == []

        by_member = entity_resolution.resolve_groups(
            db, professional.id, member_contact_id=contact.id
        )
        assert len(by_member) == 1
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def test_get_schedule_rejects_oversized_range() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        result = tools.get_schedule(
            db,
            professional.id,
            date_from="2026-01-01",
            date_to="2026-03-01",
        )
        assert "error" in result
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_get_next_session_finds_nearest_future_occurrence() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        contact = _make_contact(db, professional.id, "Aluno Proxima Sessao")
        today = datetime.now(TIMEZONE).date()
        near = datetime.combine(today + timedelta(days=3), time(10, 0), tzinfo=TIMEZONE)
        far = datetime.combine(today + timedelta(days=10), time(10, 0), tzinfo=TIMEZONE)

        db.add_all(
            [
                Appointment(
                    professional_id=professional.id,
                    contact_id=contact.id,
                    service="Aula",
                    start_at=far,
                    end_at=far + timedelta(hours=1),
                    status="confirmed",
                    source="dashboard",
                ),
                Appointment(
                    professional_id=professional.id,
                    contact_id=contact.id,
                    service="Aula",
                    start_at=near,
                    end_at=near + timedelta(hours=1),
                    status="confirmed",
                    source="dashboard",
                ),
            ]
        )
        db.commit()

        result = tools.get_next_session(db, professional.id, contact_id=str(contact.id))
        assert result["next_session"] is not None
        assert result["next_session"]["starts_at"].startswith(
            (today + timedelta(days=3)).isoformat()
        )
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_get_next_session_skips_already_finished_session_today() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        contact = _make_contact(db, professional.id, "Aluno Sessao Passada")
        now = datetime.now(TIMEZONE)
        already_finished = now - timedelta(hours=2)
        upcoming = now + timedelta(hours=2)

        db.add_all(
            [
                Appointment(
                    professional_id=professional.id,
                    contact_id=contact.id,
                    service="Aula",
                    start_at=already_finished,
                    end_at=already_finished + timedelta(minutes=30),
                    status="confirmed",
                    source="dashboard",
                ),
                Appointment(
                    professional_id=professional.id,
                    contact_id=contact.id,
                    service="Aula",
                    start_at=upcoming,
                    end_at=upcoming + timedelta(minutes=30),
                    status="confirmed",
                    source="dashboard",
                ),
            ]
        )
        db.commit()

        result = tools.get_next_session(db, professional.id, contact_id=str(contact.id))
        assert result["next_session"] is not None
        assert result["next_session"]["starts_at"] == upcoming.isoformat()
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_get_schedule_marks_past_and_future_occurrences() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        contact = _make_contact(db, professional.id, "Aluno Passado Futuro")
        now = datetime.now(TIMEZONE)
        past_start = now - timedelta(hours=2)
        future_start = now + timedelta(hours=2)

        db.add_all(
            [
                Appointment(
                    professional_id=professional.id,
                    contact_id=contact.id,
                    service="Aula passada",
                    start_at=past_start,
                    end_at=past_start + timedelta(minutes=30),
                    status="confirmed",
                    source="dashboard",
                ),
                Appointment(
                    professional_id=professional.id,
                    contact_id=contact.id,
                    service="Aula futura",
                    start_at=future_start,
                    end_at=future_start + timedelta(minutes=30),
                    status="confirmed",
                    source="dashboard",
                ),
            ]
        )
        db.commit()

        date_from = min(past_start.date(), future_start.date())
        date_to = max(past_start.date(), future_start.date())
        result = tools.get_schedule(
            db, professional.id, date_from=date_from.isoformat(), date_to=date_to.isoformat()
        )
        by_label = {o["label"]: o for o in result["occurrences"]}
        assert by_label["Aula passada"]["is_past"] is True
        assert by_label["Aula futura"]["is_past"] is False
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_find_instructor_openings_subtracts_bookings() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id, "Quadra Central")
        contact = _make_contact(db, professional.id, "Aluno Openings")
        created_at = datetime.combine(MONDAY, time(6, 0), tzinfo=TIMEZONE)

        db.add(
            WorkJourneyInterval(
                professional_id=professional.id,
                day_of_week=0,
                interval_type="work",
                start_time=time(8, 0),
                end_time=time(18, 0),
            )
        )
        db.add(
            RecurringSlot(
                professional_id=professional.id,
                place_id=place.id,
                day_of_week=0,
                start_time=time(8, 0),
                end_time=time(18, 0),
                recurrence_type="weekly",
                slot_kind="availability",
                created_at=created_at,
            )
        )
        booked_start = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        db.add(
            Appointment(
                professional_id=professional.id,
                contact_id=contact.id,
                place_id=place.id,
                service="Aula",
                start_at=booked_start,
                end_at=booked_start + timedelta(hours=1),
                status="confirmed",
                source="dashboard",
            )
        )
        db.commit()

        result = tools.find_instructor_openings(
            db,
            professional.id,
            date=MONDAY.isoformat(),
            duration_minutes=60,
        )
        windows = {(o["start_time"], o["end_time"]) for o in result["openings"]}
        assert ("08:00", "10:00") in windows
        assert ("11:00", "18:00") in windows
        assert not any(start < "11:00" <= end and start >= "10:00" for start, end in windows)
        by_window = {(o["start_time"], o["end_time"]): o for o in result["openings"]}
        assert by_window[("08:00", "10:00")]["places"] == [
            {
                "place_id": str(place.id),
                "place_name": "Quadra Central",
                "start_time": "08:00",
                "end_time": "10:00",
            }
        ]

        morning_only = tools.find_instructor_openings(
            db,
            professional.id,
            date=MONDAY.isoformat(),
            duration_minutes=60,
            period="morning",
        )
        morning_windows = {(o["start_time"], o["end_time"]) for o in morning_only["openings"]}
        assert morning_windows == {("08:00", "10:00"), ("11:00", "12:00")}
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_find_instructor_openings_subtracts_confirmed_events() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id, "Quadra Central")
        db.add(
            WorkJourneyInterval(
                professional_id=professional.id,
                day_of_week=0,
                interval_type="work",
                start_time=time(8, 0),
                end_time=time(18, 0),
            )
        )
        db.add(
            InstructorEvent(
                professional_id=professional.id,
                place_id=place.id,
                event_type="clinic",
                start_at=datetime.combine(MONDAY, time(13, 0), tzinfo=TIMEZONE),
                end_at=datetime.combine(MONDAY, time(16, 30), tzinfo=TIMEZONE),
                status="confirmed",
            )
        )
        db.commit()

        result = tools.find_instructor_openings(
            db,
            professional.id,
            date=MONDAY.isoformat(),
            duration_minutes=60,
        )

        assert {(o["start_time"], o["end_time"]) for o in result["openings"]} == {
            ("08:00", "13:00"),
            ("16:30", "18:00"),
        }
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_find_instructor_openings_reports_gaps_without_recurring_slot() -> None:
    """No place has a RecurringSlot covering the date, so no place-specific
    availability window exists — but the professional does have a Work
    Journey and real bookings, so the tool should still report the actual
    open gaps, with an empty 'places' list on each."""
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id, "Quadra Central")
        contact = _make_contact(db, professional.id, "Aluno Fallback")

        db.add(
            WorkJourneyInterval(
                professional_id=professional.id,
                day_of_week=0,
                interval_type="work",
                start_time=time(8, 0),
                end_time=time(18, 0),
            )
        )
        booked_start = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        db.add(
            Appointment(
                professional_id=professional.id,
                contact_id=contact.id,
                place_id=place.id,
                service="Aula",
                start_at=booked_start,
                end_at=booked_start + timedelta(hours=1),
                status="confirmed",
                source="dashboard",
            )
        )
        db.commit()

        result = tools.find_instructor_openings(
            db,
            professional.id,
            date=MONDAY.isoformat(),
            duration_minutes=60,
        )
        windows = {(o["start_time"], o["end_time"]) for o in result["openings"]}
        assert ("08:00", "10:00") in windows
        assert ("11:00", "18:00") in windows
        assert all(o["places"] == [] for o in result["openings"])
        assert "note" in result
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_find_instructor_openings_reports_gaps_outside_narrow_place_window() -> None:
    """The regression behind "amanhã só das 10 às 12": a place whose
    recurring availability covers only part of the work journey must not
    hide the free hours outside that window."""
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id, "Quadra Central")
        contact = _make_contact(db, professional.id, "Aluno Janela")
        created_at = datetime.combine(MONDAY, time(6, 0), tzinfo=TIMEZONE)

        db.add(
            WorkJourneyInterval(
                professional_id=professional.id,
                day_of_week=0,
                interval_type="work",
                start_time=time(6, 0),
                end_time=time(22, 0),
            )
        )
        db.add(
            RecurringSlot(
                professional_id=professional.id,
                place_id=place.id,
                day_of_week=0,
                start_time=time(8, 0),
                end_time=time(12, 0),
                recurrence_type="weekly",
                slot_kind="availability",
                created_at=created_at,
            )
        )
        booked_start = datetime.combine(MONDAY, time(8, 0), tzinfo=TIMEZONE)
        db.add(
            Appointment(
                professional_id=professional.id,
                contact_id=contact.id,
                place_id=place.id,
                service="Aula",
                start_at=booked_start,
                end_at=booked_start + timedelta(hours=2),
                status="confirmed",
                source="dashboard",
            )
        )
        db.commit()

        result = tools.find_instructor_openings(
            db, professional.id, date=MONDAY.isoformat(), duration_minutes=60
        )
        windows = {(o["start_time"], o["end_time"]) for o in result["openings"]}
        assert windows == {("06:00", "08:00"), ("10:00", "22:00")}

        by_window = {(o["start_time"], o["end_time"]): o for o in result["openings"]}
        assert by_window[("10:00", "22:00")]["places"] == [
            {
                "place_id": str(place.id),
                "place_name": "Quadra Central",
                "start_time": "10:00",
                "end_time": "12:00",
            }
        ]
        assert by_window[("06:00", "08:00")]["places"] == []
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_find_instructor_openings_explains_weekday_without_work_journey() -> None:
    """An empty result must say why: no journey configured for that weekday
    is a different answer from a fully booked day, and the agent can only
    relay the difference if the tool states it."""
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        _make_place(db, professional.id, "Quadra Central")
        db.add(
            WorkJourneyInterval(
                professional_id=professional.id,
                day_of_week=0,
                interval_type="work",
                start_time=time(8, 0),
                end_time=time(18, 0),
            )
        )
        db.commit()

        sunday = MONDAY - timedelta(days=1)
        result = tools.find_instructor_openings(
            db, professional.id, date=sunday.isoformat(), duration_minutes=60
        )
        assert result["openings"] == []
        assert "jornada de trabalho cadastrada" in result["note"]
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_resolve_date_phrase_tool_wraps_temporal_module() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        result = tools.resolve_date_phrase(db, professional.id, phrase="hoje")
        assert result["recognized"] is True
        assert result["date"] == datetime.now(TIMEZONE).date().isoformat()
        assert result["date_from"] is None
        assert result["date_to"] is None

        week_result = tools.resolve_date_phrase(db, professional.id, phrase="proxima semana")
        assert week_result["recognized"] is True
        assert week_result["date"] is None
        assert week_result["date_from"] is not None
        assert week_result["date_to"] is not None

        unresolved = tools.resolve_date_phrase(db, professional.id, phrase="algo aleatorio")
        assert unresolved["recognized"] is False
    finally:
        _cleanup(db, professionals=[professional])
        db.close()

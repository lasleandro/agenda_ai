"""Tests for the instructor agent's deterministic building blocks
(operational ontology roadmap v0.2, Phase 2): entity resolution, temporal
phrase resolution, and the read tools. No LLM call is made — the
orchestrator's tool-call loop is out of scope for automated tests."""

from pathlib import Path
import json
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
    RecurringSlotOccurrenceParticipant,
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
    db.query(RecurringSlotOccurrenceParticipant).filter(
        RecurringSlotOccurrenceParticipant.recurring_slot_id.in_(
            db.query(RecurringSlot.id).filter(
                RecurringSlot.professional_id.in_(professional_ids)
            )
        )
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


def test_temporal_depois_de_amanha_does_not_match_amanha() -> None:
    ref = date(2026, 8, 23)  # Sunday
    assert temporal.resolve_temporal_phrase(
        "depois de amanhã", reference_date=ref
    ).resolved_date == date(2026, 8, 25)
    assert temporal.resolve_temporal_phrase(
        "amanhã", reference_date=ref
    ).resolved_date == date(2026, 8, 24)
    assert temporal.resolve_temporal_phrase(
        "anteontem", reference_date=ref
    ).resolved_date == date(2026, 8, 21)


def test_temporal_proxima_weekday_is_strictly_future_on_same_weekday() -> None:
    ref = date(2026, 8, 28)  # Friday
    assert temporal.resolve_temporal_phrase(
        "próxima sexta", reference_date=ref
    ).resolved_date == date(2026, 9, 4)
    assert temporal.resolve_temporal_phrase(
        "sexta que vem", reference_date=ref
    ).resolved_date == date(2026, 9, 4)


def test_temporal_essa_weekday_may_resolve_to_today() -> None:
    ref = date(2026, 8, 28)  # Friday
    assert temporal.resolve_temporal_phrase(
        "essa sexta", reference_date=ref
    ).resolved_date == date(2026, 8, 28)
    assert temporal.resolve_temporal_phrase(
        "sexta", reference_date=ref
    ).resolved_date == date(2026, 8, 28)


def test_temporal_parses_brazilian_numeric_date() -> None:
    ref = date(2026, 8, 23)
    assert temporal.resolve_temporal_phrase(
        "dia 28", reference_date=ref
    ).resolved_date == date(2026, 8, 28)
    assert temporal.resolve_temporal_phrase(
        "28/08/2026", reference_date=ref
    ).resolved_date == date(2026, 8, 28)
    assert temporal.resolve_temporal_phrase(
        "28/08", reference_date=ref
    ).resolved_date == date(2026, 8, 28)
    assert temporal.resolve_temporal_phrase(
        "dia 28 de agosto", reference_date=ref
    ).resolved_date == date(2026, 8, 28)


def test_temporal_combines_relative_date_and_evening() -> None:
    ref = date(2026, 8, 28)
    resolution = temporal.resolve_temporal_phrase("na outra sexta à noite", reference_date=ref)
    assert resolution.resolved_date == date(2026, 9, 4)
    assert resolution.period == (time(18, 0), time(23, 59))


def test_temporal_rejects_invalid_calendar_date() -> None:
    ref = date(2026, 8, 23)
    resolution = temporal.resolve_temporal_phrase("31/02/2026", reference_date=ref)
    assert resolution.resolved_date is None
    assert resolution.ambiguity_reason == "Data inválida"


def test_temporal_parses_bounded_offsets() -> None:
    ref = date(2026, 8, 23)
    assert temporal.resolve_temporal_phrase(
        "daqui a 2 dias", reference_date=ref
    ).resolved_date == date(2026, 8, 25)
    assert temporal.resolve_temporal_phrase(
        "daqui a duas semanas", reference_date=ref
    ).resolved_date == date(2026, 9, 6)


def test_temporal_parses_month_ranges() -> None:
    ref = date(2026, 8, 23)
    this_month = temporal.resolve_temporal_phrase("esse mês", reference_date=ref)
    assert this_month.resolved_date_from == date(2026, 8, 1)
    assert this_month.resolved_date_to == date(2026, 8, 31)

    next_month = temporal.resolve_temporal_phrase("mês que vem", reference_date=ref)
    assert next_month.resolved_date_from == date(2026, 9, 1)
    assert next_month.resolved_date_to == date(2026, 9, 30)


def test_resolve_date_phrase_surfaces_ambiguity_without_guessing(monkeypatch) -> None:
    import app.agent.tools as tools_module

    class _FrozenDatetime:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 8, 28, 10, 0, tzinfo=TIMEZONE)

    monkeypatch.setattr(tools_module, "datetime", _FrozenDatetime)

    db = SessionLocal()
    professional = _make_professional(db)
    try:
        result = tools.resolve_date_phrase(db, professional.id, phrase="dia 28")
        assert result["recognized"] is False
        assert result["ambiguity_reason"] is not None
        assert result["alternatives"] == ["2026-08-28", "2026-09-28"]
        assert result["date"] is None
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


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


def test_find_group_openings_returns_joinable_occurrence_not_free_time() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id, "Clube")
        member = _make_contact(db, professional.id, "Aluno Grupo")
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            class_type="group",
            slot_kind="class",
            max_participants=3,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        db.add(slot)
        db.flush()
        db.add(RecurringSlotParticipant(recurring_slot_id=slot.id, contact_id=member.id))
        db.commit()

        result = tools.find_group_openings(
            db, professional.id, date=MONDAY.isoformat(), start_time="18:00"
        )

        assert result["joinable_groups"] == [
            {
                "source_type": "recurring_slot",
                "source_id": str(slot.id),
                "occurrence_date": MONDAY.isoformat(),
                "starts_at": datetime.combine(MONDAY, time(18, 0), tzinfo=TIMEZONE).isoformat(),
                "ends_at": datetime.combine(MONDAY, time(19, 0), tzinfo=TIMEZONE).isoformat(),
                "label": "Grupo",
                "place_id": str(place.id),
                "place_name": "Clube",
                "status": "scheduled",
                "class_type": "group",
                "is_exception": False,
                "is_past": True,
                "participants": [
                    {
                        "contact_id": str(member.id),
                        "contact_name": "Aluno Grupo",
                        "enrollment_scope": "series",
                    }
                ],
                "participant_count": 1,
                "max_participants": 3,
                "available_seats": 2,
                "enrollment_scopes": ["occurrence", "series"],
            }
        ]
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_empty_group_opening_is_found_without_filtering_by_new_student() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id, "Clube")
        new_student = _make_contact(db, professional.id, "Fernanda")
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            class_type="group",
            slot_kind="class",
            max_participants=4,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        db.add(slot)
        db.commit()

        existing_membership_matches = tools.find_groups(
            db,
            professional.id,
            member_contact_id=str(new_student.id),
            weekday=MONDAY.weekday(),
        )
        opening_matches = tools.find_group_openings(
            db,
            professional.id,
            date=MONDAY.isoformat(),
            start_time="18:00",
        )

        assert existing_membership_matches["matches"] == []
        assert [item["source_id"] for item in opening_matches["joinable_groups"]] == [
            str(slot.id)
        ]
        assert opening_matches["joinable_groups"][0]["available_seats"] == 4
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_find_group_openings_filters_by_evening_overlap() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id, "Clube")
        evening = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            class_type="group",
            slot_kind="class",
            max_participants=4,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        crossing = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(17, 30),
            end_time=time(18, 30),
            class_type="group",
            slot_kind="class",
            max_participants=4,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        morning = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(9, 0),
            end_time=time(10, 0),
            class_type="group",
            slot_kind="class",
            max_participants=4,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        db.add_all([evening, crossing, morning])
        db.commit()

        result = tools.find_group_openings(
            db, professional.id, date=MONDAY.isoformat(), period="evening"
        )

        source_ids = {item["source_id"] for item in result["joinable_groups"]}
        assert source_ids == {str(evening.id), str(crossing.id)}
        assert result["period"] == "evening"
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_find_group_openings_uses_effective_dated_capacity() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id, "Clube")
        permanent = _make_contact(db, professional.id, "Aluno Permanente")
        dated_guest = _make_contact(db, professional.id, "Aluno Avulso")
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            class_type="group",
            slot_kind="class",
            max_participants=2,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        db.add(slot)
        db.flush()
        db.add(RecurringSlotParticipant(recurring_slot_id=slot.id, contact_id=permanent.id))
        db.add(
            RecurringSlotOccurrenceParticipant(
                professional_id=professional.id,
                recurring_slot_id=slot.id,
                contact_id=dated_guest.id,
                occurrence_date=MONDAY,
            )
        )
        db.commit()

        full_date_result = tools.find_group_openings(
            db, professional.id, date=MONDAY.isoformat()
        )
        next_week_result = tools.find_group_openings(
            db, professional.id, date=(MONDAY + timedelta(days=7)).isoformat()
        )

        assert full_date_result["joinable_groups"] == []
        assert [item["source_id"] for item in next_week_result["joinable_groups"]] == [
            str(slot.id)
        ]
        assert next_week_result["joinable_groups"][0]["participant_count"] == 1
        assert next_week_result["joinable_groups"][0]["available_seats"] == 1
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_find_group_openings_ignores_work_journey() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id, "Clube")
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            class_type="group",
            slot_kind="class",
            max_participants=4,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        db.add(slot)
        db.commit()

        result = tools.find_group_openings(
            db, professional.id, date=MONDAY.isoformat()
        )

        assert [item["source_id"] for item in result["joinable_groups"]] == [str(slot.id)]
        assert result["joinable_groups"][0]["available_seats"] == 4
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


# ---------------------------------------------------------------------------
# Tool-spec contract tests (recurring individual booking roadmap v0.1)
# ---------------------------------------------------------------------------


def test_appointment_tool_spec_includes_is_recurring() -> None:
    from app.agent.mutations import MUTATION_TOOL_SPECS

    spec = next(s for s in MUTATION_TOOL_SPECS if s["function"]["name"] == "propose_create_appointment")
    params = spec["function"]["parameters"]["properties"]
    assert "is_recurring" in params
    assert params["is_recurring"]["type"] == "boolean"


def test_group_slot_tool_spec_forbids_named_customers() -> None:
    from app.agent.mutations import MUTATION_TOOL_SPECS

    spec = next(s for s in MUTATION_TOOL_SPECS if s["function"]["name"] == "propose_create_group_slot")
    description = spec["function"]["description"]
    assert "EMPTY" in description or "empty" in description.lower() or "vazia" in description.lower()
    assert "named customer" in description.lower() or "cliente" in description.lower()


def test_appointment_tool_spec_description_supports_weekly() -> None:
    from app.agent.mutations import MUTATION_TOOL_SPECS

    spec = next(s for s in MUTATION_TOOL_SPECS if s["function"]["name"] == "propose_create_appointment")
    description = spec["function"]["description"]
    assert "weekly" in description.lower() or "recurring" in description.lower() or "semanal" in description.lower()


def test_orchestrator_prompt_contains_precedence_rule() -> None:
    from app.agent.orchestrator import SYSTEM_PROMPT_TEMPLATE

    assert "propose_create_appointment" in SYSTEM_PROMPT_TEMPLATE
    assert "is_recurring" in SYSTEM_PROMPT_TEMPLATE
    assert "turma" in SYSTEM_PROMPT_TEMPLATE
    assert "grupo" in SYSTEM_PROMPT_TEMPLATE
    assert "precedência" in SYSTEM_PROMPT_TEMPLATE.lower() or "precedencia" in SYSTEM_PROMPT_TEMPLATE.lower()


def test_orchestrator_prompt_contains_followup_inheritance_rule() -> None:
    from app.agent.orchestrator import SYSTEM_PROMPT_TEMPLATE

    assert "pode seguir" in SYSTEM_PROMPT_TEMPLATE
    assert "confirme" in SYSTEM_PROMPT_TEMPLATE


def test_remove_participant_routing_rule_distinguishes_three_scopes() -> None:
    from app.agent.mutations import MUTATION_TOOL_SPECS
    from app.agent.orchestrator import SYSTEM_PROMPT_TEMPLATE

    spec = next(
        s for s in MUTATION_TOOL_SPECS
        if s["function"]["name"] == "propose_remove_group_occurrence_participant"
    )
    description = spec["function"]["description"]
    assert "propose_note_participant_absence" in description
    assert "propose_remove_group_member" in description

    assert "propose_remove_group_occurrence_participant" in SYSTEM_PROMPT_TEMPLATE
    assert "propose_note_participant_absence" in SYSTEM_PROMPT_TEMPLATE
    assert "propose_remove_group_member" in SYSTEM_PROMPT_TEMPLATE
    assert "enrollment_scope" in SYSTEM_PROMPT_TEMPLATE
    assert "É só nesta aula ou ela vai sair da turma fixa?" in SYSTEM_PROMPT_TEMPLATE


def test_group_lookup_tool_specs_explain_new_student_flow() -> None:
    from app.agent.tools import TOOL_SPECS

    groups_spec = next(spec for spec in TOOL_SPECS if spec["function"]["name"] == "find_groups")
    openings_spec = next(
        spec for spec in TOOL_SPECS if spec["function"]["name"] == "find_group_openings"
    )

    description = openings_spec["function"]["description"].lower()
    assert "already" in groups_spec["function"]["description"].lower()
    assert "vagas" in description or "vacancy" in description
    assert "empty" in description
    assert "free instructor time" in description
    assert "recurring_slot_id" in description
    assert "do not use" in groups_spec["function"]["parameters"]["properties"][
        "member_contact_id"
    ]["description"].lower()


def test_orchestrator_prompt_routes_new_student_to_group_openings() -> None:
    from app.agent.orchestrator import SYSTEM_PROMPT_TEMPLATE

    assert "find_group_openings" in SYSTEM_PROMPT_TEMPLATE
    assert "member_contact_id" in SYSTEM_PROMPT_TEMPLATE
    assert "turmas vazias" in SYSTEM_PROMPT_TEMPLATE


def test_group_vacancy_tool_spec_supports_period() -> None:
    from app.agent.tools import TOOL_SPECS

    spec = next(s for s in TOOL_SPECS if s["function"]["name"] == "find_group_openings")
    params = spec["function"]["parameters"]["properties"]
    assert "period" in params
    assert params["period"]["enum"] == ["morning", "afternoon", "evening"]
    description = spec["function"]["description"]
    assert "vagas" in description or "vacancy" in description.lower()
    assert "never reports free instructor time" in description.lower()


def test_orchestrator_prompt_routes_group_vacancy_questions() -> None:
    from app.agent.orchestrator import SYSTEM_PROMPT_TEMPLATE

    assert "find_group_openings PRIMEIRO" in SYSTEM_PROMPT_TEMPLATE
    assert "NUNCA chame" in SYSTEM_PROMPT_TEMPLATE
    assert "find_instructor_openings" in SYSTEM_PROMPT_TEMPLATE
    assert "vagas" in SYSTEM_PROMPT_TEMPLATE
    assert "HOJE" in SYSTEM_PROMPT_TEMPLATE


def test_agent_group_vacancy_question_uses_group_openings_not_free_time(monkeypatch) -> None:
    import app.agent.orchestrator as orchestrator

    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id, "Clube")
        today = datetime.now(TIMEZONE).date()
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=today.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            class_type="group",
            slot_kind="class",
            max_participants=4,
            recurrence_type="weekly",
            valid_from=today,
        )
        db.add(slot)
        db.commit()

        class _FakeFunction:
            def __init__(self, name: str, arguments: str) -> None:
                self.name = name
                self.arguments = arguments

        class _FakeToolCall:
            def __init__(self, call_id: str, name: str, arguments: str) -> None:
                self.id = call_id
                self.function = _FakeFunction(name, arguments)

        class _FakeMessage:
            def __init__(self, content: str = "", tool_calls: list | None = None) -> None:
                self.content = content
                self.tool_calls = tool_calls or []

        class _FakeChoice:
            def __init__(self, message: _FakeMessage) -> None:
                self.message = message

        class _FakeResponse:
            def __init__(self, message: _FakeMessage) -> None:
                self.choices = [_FakeChoice(message)]

        class _FakeCompletions:
            def __init__(self, script: list) -> None:
                self._script = script
                self._index = 0

            def create(self, **kwargs):
                response = self._script[self._index]
                self._index += 1
                return response

        class _FakeChat:
            def __init__(self, script: list) -> None:
                self.completions = _FakeCompletions(script)

        class _FakeClient:
            def __init__(self, script: list) -> None:
                self.chat = _FakeChat(script)

        script = [
            _FakeResponse(
                _FakeMessage(
                    "",
                    [_FakeToolCall("call_1", "resolve_date_phrase", json.dumps({"phrase": "hoje à noite"}))],
                )
            ),
            _FakeResponse(
                _FakeMessage(
                    "",
                    [_FakeToolCall("call_2", "find_group_openings", json.dumps({"date": today.isoformat(), "period": "evening"}))],
                )
            ),
            _FakeResponse(_FakeMessage("Hoje à noite há uma turma com vaga.")),
        ]
        monkeypatch.setattr(orchestrator, "get_azure_client", lambda: _FakeClient(script))

        response = orchestrator.run_agent_turn(
            db,
            professional.id,
            uuid.uuid4(),
            [{"role": "user", "content": "quais vagas tenho em grupos à noite?"}],
        )

        names = [call.name for call in response.tool_calls]
        assert names == ["resolve_date_phrase", "find_group_openings"]
        assert "find_instructor_openings" not in names

        openings_call = response.tool_calls[1]
        assert openings_call.arguments["period"] == "evening"
        assert openings_call.arguments["date"] == today.isoformat()
    finally:
        _cleanup(db, professionals=[professional])
        db.close()

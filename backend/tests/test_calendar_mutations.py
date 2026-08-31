"""Tests for the Phase 5 calendar mutation tools (operational ontology
roadmap v0.2): propose_create_appointment, propose_cancel_schedule,
propose_reschedule_occurrence — propose step, confirm/execute, and
conflict re-validation."""

from pathlib import Path
import sys
import uuid
from datetime import date, datetime, time, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.agent import candidates, mutations
from app.core.security import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import (
    Appointment,
    AppointmentParticipant,
    AppointmentTransition,
    Contact,
    OperationalEvent,
    OperatorActionCandidate,
    Place,
    Professional,
    RecurringSlot,
    RecurringSlotOccurrenceParticipant,
    RecurringSlotParticipant,
    ScheduleOccurrenceOverride,
    ScheduleOccurrenceClassOverride,
    User,
    WorkJourneyInterval,
)
from app.services.scheduling import TIMEZONE, list_schedule_occurrences

MONDAY = date(2026, 8, 3)


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().hex[:8]}"


def _random_email() -> str:
    return f"calmut_{uuid.uuid4().hex[:10]}@agenda.ai"


def _make_tenant(db) -> tuple[Professional, User]:
    professional = Professional(name="Tenant Calendar Mutations", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    user = User(
        email=_random_email(),
        hashed_password=hash_password("correct-password"),
        role="professional",
        professional_id=professional.id,
    )
    db.add(user)
    db.commit()
    return professional, user


def _make_place(db, professional_id) -> Place:
    place = Place(professional_id=professional_id, name="Clube", normalized_name="clube")
    db.add(place)
    db.commit()
    return place


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


def _cleanup(db, *, professionals: list[Professional], users: list[User]) -> None:
    professional_ids = [p.id for p in professionals]
    user_ids = [u.id for u in users]
    if professional_ids:
        db.query(WorkJourneyInterval).filter(
            WorkJourneyInterval.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(OperationalEvent).filter(
            OperationalEvent.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(OperatorActionCandidate).filter(
            OperatorActionCandidate.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(ScheduleOccurrenceOverride).filter(
            ScheduleOccurrenceOverride.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(ScheduleOccurrenceClassOverride).filter(
            ScheduleOccurrenceClassOverride.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(RecurringSlotOccurrenceParticipant).filter(
            RecurringSlotOccurrenceParticipant.professional_id.in_(professional_ids)
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
        db.query(AppointmentTransition).filter(
            AppointmentTransition.appointment_id.in_(
                db.query(Appointment.id).filter(
                    Appointment.professional_id.in_(professional_ids)
                )
            )
        ).delete(synchronize_session=False)
        db.query(AppointmentParticipant).filter(
            AppointmentParticipant.appointment_id.in_(
                db.query(Appointment.id).filter(
                    Appointment.professional_id.in_(professional_ids)
                )
            )
        ).delete(synchronize_session=False)
        db.query(Appointment).filter(
            Appointment.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(Contact).filter(Contact.professional_id.in_(professional_ids)).delete(
            synchronize_session=False
        )
        db.query(Place).filter(Place.professional_id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    if professional_ids:
        db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    db.commit()


# ---------------------------------------------------------------------------
# propose_create_appointment
# ---------------------------------------------------------------------------

def test_propose_create_appointment_full_cycle() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id, "Marcelo")
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)

        result = mutations.propose_create_appointment(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(contact.id),
            place_id=str(place.id),
            start_at=start_at.isoformat(),
            end_at=(start_at + timedelta(hours=1)).isoformat(),
            service="Aula individual",
        )
        assert result["requires_confirmation"] is True
        assert "Marcelo" in result["preview_text"]

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        appointment = (
            db.query(Appointment).filter(Appointment.professional_id == professional.id).first()
        )
        assert appointment is not None
        assert appointment.status == "confirmed"
        assert appointment.contact_id == contact.id

        event = (
            db.query(OperationalEvent)
            .filter(OperationalEvent.event_type == "schedule.appointment.created")
            .first()
        )
        assert event is not None
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_create_appointment_inherits_stay_for_group() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        primary = _make_contact(db, professional.id, "Marcelo")
        extra = _make_contact(db, professional.id, "Larissa")
        db.add(
            RecurringSlot(
                professional_id=professional.id,
                place_id=place.id,
                day_of_week=MONDAY.weekday(),
                start_time=time(10, 0),
                end_time=time(12, 0),
                slot_kind="availability",
            )
        )
        db.commit()
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)

        result = mutations.propose_create_appointment(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(primary.id),
            contact_ids=[str(primary.id), str(extra.id)],
            class_type="group",
            start_at=start_at.isoformat(),
            end_at=(start_at + timedelta(hours=1)).isoformat(),
            service="Grupo iniciante",
        )

        assert result["requires_confirmation"] is True
        assert "local inferido pela permanência" in result["preview_text"]
        assert candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        ).ok is True

        appointment = db.query(Appointment).filter_by(professional_id=professional.id).one()
        assert appointment.place_id == place.id
        assert appointment.class_type == "group"
        assert (
            db.query(AppointmentParticipant)
            .filter(AppointmentParticipant.appointment_id == appointment.id)
            .count()
            == 1
        )
    finally:
        db.query(RecurringSlot).filter(
            RecurringSlot.professional_id == professional.id
        ).delete(synchronize_session=False)
        db.commit()
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_create_appointment_rejects_conflict() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact_a = _make_contact(db, professional.id, "Aluno A")
        contact_b = _make_contact(db, professional.id, "Aluno B")
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        db.add(
            Appointment(
                professional_id=professional.id,
                contact_id=contact_a.id,
                place_id=place.id,
                service="Aula",
                start_at=start_at,
                end_at=start_at + timedelta(hours=1),
                status="confirmed",
                source="dashboard",
            )
        )
        db.commit()

        result = mutations.propose_create_appointment(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(contact_b.id),
            place_id=str(place.id),
            start_at=start_at.isoformat(),
            end_at=(start_at + timedelta(hours=1)).isoformat(),
            service="Aula individual",
        )
        assert "error" in result
        assert (
            db.query(OperatorActionCandidate)
            .filter(OperatorActionCandidate.professional_id == professional.id)
            .count()
            == 0
        )
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_create_appointment_rejects_outside_configured_work_journey() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id, "Aluno Fora Do Horario")
        db.add(
            WorkJourneyInterval(
                professional_id=professional.id,
                day_of_week=MONDAY.weekday(),
                interval_type="work",
                start_time=time(8, 0),
                end_time=time(12, 0),
            )
        )
        db.commit()

        start_at = datetime.combine(MONDAY, time(15, 0), tzinfo=TIMEZONE)
        result = mutations.propose_create_appointment(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(contact.id),
            place_id=str(place.id),
            start_at=start_at.isoformat(),
            end_at=(start_at + timedelta(hours=1)).isoformat(),
            service="Aula individual",
        )
        assert "error" in result
        assert (
            db.query(OperatorActionCandidate)
            .filter(OperatorActionCandidate.professional_id == professional.id)
            .count()
            == 0
        )
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_create_appointment_allows_time_within_configured_work_journey() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id, "Aluno Dentro Do Horario")
        db.add(
            WorkJourneyInterval(
                professional_id=professional.id,
                day_of_week=MONDAY.weekday(),
                interval_type="work",
                start_time=time(8, 0),
                end_time=time(20, 0),
            )
        )
        db.commit()

        start_at = datetime.combine(MONDAY, time(15, 0), tzinfo=TIMEZONE)
        result = mutations.propose_create_appointment(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(contact.id),
            place_id=str(place.id),
            start_at=start_at.isoformat(),
            end_at=(start_at + timedelta(hours=1)).isoformat(),
            service="Aula individual",
        )
        assert result["requires_confirmation"] is True
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


# ---------------------------------------------------------------------------
# propose_cancel_schedule
# ---------------------------------------------------------------------------

def test_propose_cancel_schedule_full_cycle() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id, "Marcelo")
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            place_id=place.id,
            service="Aula",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
        )
        db.add(appointment)
        db.commit()

        result = mutations.propose_cancel_schedule(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            target_type="appointment",
            target_id=str(appointment.id),
            occurrence_date=MONDAY.isoformat(),
        )
        assert result["requires_confirmation"] is True

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        override = (
            db.query(ScheduleOccurrenceOverride)
            .filter(ScheduleOccurrenceOverride.appointment_id == appointment.id)
            .first()
        )
        assert override is not None
        assert override.override_type == "cancelled"

        occurrences = list_schedule_occurrences(db, professional.id, MONDAY, MONDAY)
        assert occurrences == []
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_confirmed_cancel_disappears_from_calendar_api() -> None:
    """Regression test: GET /api/calendar previously queried Appointment
    directly and never consulted ScheduleOccurrenceOverride, so a chat-
    confirmed cancellation never showed up on the dashboard calendar grid."""
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id, "Mariana")
        start_at = datetime.combine(MONDAY, time(17, 0), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            place_id=place.id,
            service="tennis_lesson",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
        )
        db.add(appointment)
        db.commit()

        client = TestClient(app)
        login = client.post(
            "/api/auth/login", json={"email": user.email, "password": "correct-password"}
        )
        assert login.status_code == 200

        before = client.get(
            f"/api/calendar?start_date={MONDAY.isoformat()}&end_date={MONDAY.isoformat()}",
            cookies=login.cookies,
        )
        assert before.status_code == 200
        assert len(before.json()["appointments"]) == 1
        assert before.json()["appointments"][0]["contact_name"] == "Mariana"

        result = mutations.propose_cancel_schedule(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            target_type="appointment",
            target_id=str(appointment.id),
            occurrence_date=MONDAY.isoformat(),
        )
        assert result["requires_confirmation"] is True
        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True
        db.commit()

        after = client.get(
            f"/api/calendar?start_date={MONDAY.isoformat()}&end_date={MONDAY.isoformat()}",
            cookies=login.cookies,
        )
        assert after.status_code == 200
        assert after.json()["appointments"] == []
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_cancel_schedule_rejects_missing_occurrence() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id, "Marcelo")
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            place_id=place.id,
            service="Aula",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
        )
        db.add(appointment)
        db.commit()

        result = mutations.propose_cancel_schedule(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            target_type="appointment",
            target_id=str(appointment.id),
            occurrence_date=(MONDAY + timedelta(days=30)).isoformat(),
        )
        assert "error" in result
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


# ---------------------------------------------------------------------------
# propose_reschedule_occurrence
# ---------------------------------------------------------------------------

def test_propose_reschedule_occurrence_full_cycle() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id, "Marcelo")
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            place_id=place.id,
            service="Aula",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
        )
        db.add(appointment)
        db.commit()

        new_start = datetime.combine(MONDAY + timedelta(days=1), time(14, 0), tzinfo=TIMEZONE)
        result = mutations.propose_reschedule_occurrence(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            target_type="appointment",
            target_id=str(appointment.id),
            occurrence_date=MONDAY.isoformat(),
            new_start_at=new_start.isoformat(),
            new_end_at=(new_start + timedelta(hours=1)).isoformat(),
            new_place_id=str(place.id),
        )
        assert result["requires_confirmation"] is True

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        occurrences = list_schedule_occurrences(
            db, professional.id, MONDAY, MONDAY + timedelta(days=1)
        )
        assert len(occurrences) == 1
        assert occurrences[0].is_exception is True
        assert occurrences[0].starts_at == new_start
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_confirmed_reschedule_reflects_in_appointment_detail() -> None:
    """Regression test: GET /api/appointments/{id} previously always
    returned the appointment's original start_at/place, ignoring any
    confirmed reschedule — opening the detail panel on a moved occurrence
    showed stale data even though the calendar grid showed the new time."""
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        new_place = Place(
            professional_id=professional.id, name="Quadra 2", normalized_name="quadra 2"
        )
        db.add(new_place)
        db.commit()
        contact = _make_contact(db, professional.id, "Marcelo")
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            place_id=place.id,
            service="Aula",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
        )
        db.add(appointment)
        db.commit()

        client = TestClient(app)
        login = client.post(
            "/api/auth/login", json={"email": user.email, "password": "correct-password"}
        )
        assert login.status_code == 200

        new_start = datetime.combine(MONDAY + timedelta(days=1), time(14, 0), tzinfo=TIMEZONE)
        result = mutations.propose_reschedule_occurrence(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            target_type="appointment",
            target_id=str(appointment.id),
            occurrence_date=MONDAY.isoformat(),
            new_start_at=new_start.isoformat(),
            new_end_at=(new_start + timedelta(hours=1)).isoformat(),
            new_place_id=str(new_place.id),
        )
        assert result["requires_confirmation"] is True
        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True
        db.commit()

        stale = client.get(
            f"/api/appointments/{appointment.id}", cookies=login.cookies
        )
        assert stale.status_code == 200
        assert stale.json()["start_at"].startswith(MONDAY.isoformat())
        assert stale.json()["place_id"] == str(place.id)

        resolved = client.get(
            f"/api/appointments/{appointment.id}"
            f"?occurrence_date={MONDAY.isoformat()}",
            cookies=login.cookies,
        )
        assert resolved.status_code == 200
        body = resolved.json()
        assert body["start_at"].startswith(str(MONDAY + timedelta(days=1)))
        assert body["place_id"] == str(new_place.id)
        assert body["place_name"] == "Quadra 2"
        assert body["is_exception"] is True
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_reschedule_occurrence_rejects_conflict_at_propose_time() -> None:
    """The conflict check now runs upfront (propose_reschedule_occurrence),
    not only at confirm — so the preview never promises a move that's
    already predictably impossible."""
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact_a = _make_contact(db, professional.id, "Aluno A")
        contact_b = _make_contact(db, professional.id, "Aluno B")
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        movable = Appointment(
            professional_id=professional.id,
            contact_id=contact_a.id,
            place_id=place.id,
            service="Aula",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
        )
        blocker_start = datetime.combine(MONDAY + timedelta(days=1), time(14, 0), tzinfo=TIMEZONE)
        blocker = Appointment(
            professional_id=professional.id,
            contact_id=contact_b.id,
            place_id=place.id,
            service="Aula",
            start_at=blocker_start,
            end_at=blocker_start + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
        )
        db.add_all([movable, blocker])
        db.commit()

        result = mutations.propose_reschedule_occurrence(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            target_type="appointment",
            target_id=str(movable.id),
            occurrence_date=MONDAY.isoformat(),
            new_start_at=blocker_start.isoformat(),
            new_end_at=(blocker_start + timedelta(hours=1)).isoformat(),
        )
        assert "error" in result
        assert (
            db.query(OperatorActionCandidate)
            .filter(OperatorActionCandidate.professional_id == professional.id)
            .count()
            == 0
        )
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_reschedule_occurrence_confirm_fails_on_race_condition() -> None:
    """A conflict that appears in the gap between propose and confirm (a
    genuine race, not something knowable upfront) must still fail safely
    at confirm — this is what assert_new_time_available's confirm-time
    re-validation call covers, distinct from the propose-time check."""
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact_a = _make_contact(db, professional.id, "Aluno A")
        contact_b = _make_contact(db, professional.id, "Aluno B")
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        movable = Appointment(
            professional_id=professional.id,
            contact_id=contact_a.id,
            place_id=place.id,
            service="Aula",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
        )
        db.add(movable)
        db.commit()

        new_start = datetime.combine(MONDAY + timedelta(days=1), time(14, 0), tzinfo=TIMEZONE)
        result = mutations.propose_reschedule_occurrence(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            target_type="appointment",
            target_id=str(movable.id),
            occurrence_date=MONDAY.isoformat(),
            new_start_at=new_start.isoformat(),
            new_end_at=(new_start + timedelta(hours=1)).isoformat(),
            new_place_id=str(place.id),
        )
        assert result["requires_confirmation"] is True

        # A conflicting booking lands after the proposal was made.
        blocker = Appointment(
            professional_id=professional.id,
            contact_id=contact_b.id,
            place_id=place.id,
            service="Aula",
            start_at=new_start,
            end_at=new_start + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
        )
        db.add(blocker)
        db.commit()

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is False

        candidate = (
            db.query(OperatorActionCandidate)
            .filter(OperatorActionCandidate.id == uuid.UUID(result["candidate_id"]))
            .first()
        )
        assert candidate.status == "failed"
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_calendar_mutation_tools_are_tenant_scoped() -> None:
    db = SessionLocal()
    professional_a, user_a = _make_tenant(db)
    professional_b, user_b = _make_tenant(db)
    try:
        place = _make_place(db, professional_a.id)
        contact = _make_contact(db, professional_a.id, "Marcelo")

        result = mutations.propose_create_appointment(
            db,
            professional_b.id,
            user_b.id,
            uuid.uuid4(),
            contact_id=str(contact.id),
            place_id=str(place.id),
            start_at=datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE).isoformat(),
            end_at=datetime.combine(MONDAY, time(11, 0), tzinfo=TIMEZONE).isoformat(),
            service="Aula",
        )
        assert "error" in result
    finally:
        _cleanup(
            db,
            professionals=[professional_a, professional_b],
            users=[user_a, user_b],
        )
        db.close()


# ---------------------------------------------------------------------------
# propose_set_appointment_format / appointment participants
# ---------------------------------------------------------------------------

def _make_appointment(
    db,
    professional_id,
    place_id,
    contact_id,
    start_at,
    *,
    class_type: str = "individual",
    max_participants: int = 1,
) -> Appointment:
    appointment = Appointment(
        professional_id=professional_id,
        contact_id=contact_id,
        place_id=place_id,
        service="Aula individual",
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
        status="confirmed",
        source="dashboard",
        class_type=class_type,
        max_participants=max_participants,
    )
    db.add(appointment)
    db.commit()
    return appointment


def test_propose_set_appointment_format_promotes_existing_appointment() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        primary = _make_contact(db, professional.id, "Leandro")
        start_at = datetime.combine(MONDAY, time(15, 0), tzinfo=TIMEZONE)
        appointment = _make_appointment(db, professional.id, place.id, primary.id, start_at)

        result = mutations.propose_set_appointment_format(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            appointment_id=str(appointment.id),
            class_type="group",
            max_participants=3,
        )

        assert result["requires_confirmation"] is True
        assert "grupo" in result["preview_text"].lower()

        assert candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        ).ok is True

        db.refresh(appointment)
        assert appointment.class_type == "group"
        assert appointment.max_participants == 3

        event = (
            db.query(OperationalEvent)
            .filter(
                OperationalEvent.event_type == "schedule.appointment.updated",
                OperationalEvent.entity_id == appointment.id,
            )
            .one()
        )
        assert event.payload["operation"] == "class_format_updated"
        assert event.before_state == {"class_type": "individual", "max_participants": 1}
        assert event.after_state == {"class_type": "group", "max_participants": 3}
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_add_group_occurrence_participant_keeps_roster_permanent() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        permanent = _make_contact(db, professional.id, "Leandro")
        guest = _make_contact(db, professional.id, "Larissa")
        occurrence_date = MONDAY + timedelta(days=7)
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            slot_kind="class",
            class_type="group",
            max_participants=3,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        db.add(slot)
        db.flush()
        db.add(RecurringSlotParticipant(recurring_slot_id=slot.id, contact_id=permanent.id))
        db.commit()

        result = mutations.propose_add_group_occurrence_participant(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(guest.id),
            recurring_slot_id=str(slot.id),
            occurrence_date=occurrence_date.isoformat(),
        )
        assert result["requires_confirmation"] is True
        assert "permanente" in result["preview_text"]

        assert candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        ).ok is True
        assert (
            db.query(RecurringSlotParticipant)
            .filter(RecurringSlotParticipant.recurring_slot_id == slot.id)
            .count()
            == 1
        )
        assert (
            db.query(RecurringSlotOccurrenceParticipant)
            .filter(
                RecurringSlotOccurrenceParticipant.recurring_slot_id == slot.id,
                RecurringSlotOccurrenceParticipant.contact_id == guest.id,
                RecurringSlotOccurrenceParticipant.occurrence_date == occurrence_date,
            )
            .count()
            == 1
        )
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_remove_group_occurrence_participant_full_cycle() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        permanent = _make_contact(db, professional.id, "Leandro")
        guest = _make_contact(db, professional.id, "Fernanda")
        occurrence_date = MONDAY + timedelta(days=7)
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            slot_kind="class",
            class_type="group",
            max_participants=3,
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
                contact_id=guest.id,
                occurrence_date=occurrence_date,
            )
        )
        db.commit()

        result = mutations.propose_remove_group_occurrence_participant(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(guest.id),
            recurring_slot_id=str(slot.id),
            occurrence_date=occurrence_date.isoformat(),
        )
        assert result["requires_confirmation"] is True
        assert "Fernanda" in result["preview_text"]

        assert candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        ).ok is True

        assert (
            db.query(RecurringSlotOccurrenceParticipant)
            .filter(
                RecurringSlotOccurrenceParticipant.recurring_slot_id == slot.id,
                RecurringSlotOccurrenceParticipant.contact_id == guest.id,
                RecurringSlotOccurrenceParticipant.occurrence_date == occurrence_date,
            )
            .count()
            == 0
        )
        assert (
            db.query(RecurringSlotParticipant)
            .filter(RecurringSlotParticipant.recurring_slot_id == slot.id)
            .count()
            == 1
        )

        event = (
            db.query(OperationalEvent)
            .filter(
                OperationalEvent.event_type == "schedule.participant.removed",
                OperationalEvent.entity_id == slot.id,
            )
            .one()
        )
        assert event.payload["scope"] == "occurrence"
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_remove_group_occurrence_participant_keeps_other_dates() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        guest = _make_contact(db, professional.id, "Fernanda")
        date_a = MONDAY + timedelta(days=7)
        date_b = MONDAY + timedelta(days=14)
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            slot_kind="class",
            class_type="group",
            max_participants=3,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        db.add(slot)
        db.flush()
        for occurrence_date in (date_a, date_b):
            db.add(
                RecurringSlotOccurrenceParticipant(
                    professional_id=professional.id,
                    recurring_slot_id=slot.id,
                    contact_id=guest.id,
                    occurrence_date=occurrence_date,
                )
            )
        db.commit()

        result = mutations.propose_remove_group_occurrence_participant(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(guest.id),
            recurring_slot_id=str(slot.id),
            occurrence_date=date_a.isoformat(),
        )
        assert candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        ).ok is True

        remaining = (
            db.query(RecurringSlotOccurrenceParticipant.occurrence_date)
            .filter(
                RecurringSlotOccurrenceParticipant.recurring_slot_id == slot.id,
                RecurringSlotOccurrenceParticipant.contact_id == guest.id,
            )
            .all()
        )
        assert [row.occurrence_date for row in remaining] == [date_b]
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_remove_group_occurrence_participant_rejects_permanent_member() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        permanent = _make_contact(db, professional.id, "Leandro")
        occurrence_date = MONDAY + timedelta(days=7)
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            slot_kind="class",
            class_type="group",
            max_participants=3,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        db.add(slot)
        db.flush()
        db.add(RecurringSlotParticipant(recurring_slot_id=slot.id, contact_id=permanent.id))
        db.commit()

        result = mutations.propose_remove_group_occurrence_participant(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(permanent.id),
            recurring_slot_id=str(slot.id),
            occurrence_date=occurrence_date.isoformat(),
        )
        assert "error" in result
        assert "propose_note_participant_absence" in result["error"]
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_remove_group_occurrence_participant_is_tenant_scoped() -> None:
    db = SessionLocal()
    professional_a, user_a = _make_tenant(db)
    professional_b, user_b = _make_tenant(db)
    try:
        place = _make_place(db, professional_a.id)
        guest = _make_contact(db, professional_a.id, "Fernanda")
        occurrence_date = MONDAY + timedelta(days=7)
        slot = RecurringSlot(
            professional_id=professional_a.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            slot_kind="class",
            class_type="group",
            max_participants=3,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        db.add(slot)
        db.flush()
        db.add(
            RecurringSlotOccurrenceParticipant(
                professional_id=professional_a.id,
                recurring_slot_id=slot.id,
                contact_id=guest.id,
                occurrence_date=occurrence_date,
            )
        )
        db.commit()

        result = mutations.propose_remove_group_occurrence_participant(
            db,
            professional_b.id,
            user_b.id,
            uuid.uuid4(),
            contact_id=str(guest.id),
            recurring_slot_id=str(slot.id),
            occurrence_date=occurrence_date.isoformat(),
        )
        assert "error" in result
    finally:
        _cleanup(db, professionals=[professional_a, professional_b], users=[user_a, user_b])
        db.close()


def test_propose_remove_group_occurrence_participant_confirm_fails_after_concurrent_removal() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        guest = _make_contact(db, professional.id, "Fernanda")
        occurrence_date = MONDAY + timedelta(days=7)
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            slot_kind="class",
            class_type="group",
            max_participants=3,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        db.add(slot)
        db.flush()
        db.add(
            RecurringSlotOccurrenceParticipant(
                professional_id=professional.id,
                recurring_slot_id=slot.id,
                contact_id=guest.id,
                occurrence_date=occurrence_date,
            )
        )
        db.commit()

        result = mutations.propose_remove_group_occurrence_participant(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(guest.id),
            recurring_slot_id=str(slot.id),
            occurrence_date=occurrence_date.isoformat(),
        )
        assert result["requires_confirmation"] is True

        db.query(RecurringSlotOccurrenceParticipant).filter(
            RecurringSlotOccurrenceParticipant.recurring_slot_id == slot.id,
            RecurringSlotOccurrenceParticipant.contact_id == guest.id,
            RecurringSlotOccurrenceParticipant.occurrence_date == occurrence_date,
        ).delete(synchronize_session=False)
        db.commit()

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is False
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_create_group_slot_creates_empty_recurring_class() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        start_at = datetime.combine(MONDAY, time(18, 0), tzinfo=TIMEZONE)
        result = mutations.propose_create_group_slot(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            place_id=str(place.id),
            start_at=start_at.isoformat(),
            end_at=(start_at + timedelta(hours=1)).isoformat(),
            is_recurring=True,
        )
        assert result["requires_confirmation"] is True
        assert "0/4" in result["preview_text"]

        assert candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        ).ok is True
        slot = db.query(RecurringSlot).filter_by(professional_id=professional.id).one()
        assert slot.slot_kind == "class"
        assert slot.class_type == "group"
        assert slot.max_participants == 4
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_set_occurrence_class_format_updates_only_selected_date() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        occurrence_date = MONDAY + timedelta(days=7)
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            slot_kind="class",
            class_type="individual",
            max_participants=1,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        db.add(slot)
        db.commit()

        result = mutations.propose_set_occurrence_class_format(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            target_type="recurring_slot",
            target_id=str(slot.id),
            occurrence_date=occurrence_date.isoformat(),
            class_type="group",
            max_participants=3,
        )
        assert result["requires_confirmation"] is True
        assert "somente" in result["preview_text"]
        assert candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        ).ok is True

        override = (
            db.query(ScheduleOccurrenceClassOverride)
            .filter(ScheduleOccurrenceClassOverride.recurring_slot_id == slot.id)
            .one()
        )
        assert override.occurrence_date == occurrence_date
        assert override.class_type == "group"
        assert override.max_participants == 3
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_add_appointment_participant_turns_individual_into_group() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        primary = _make_contact(db, professional.id, "Leandro")
        extra = _make_contact(db, professional.id, "Larissa")
        start_at = datetime.combine(MONDAY, time(15, 0), tzinfo=TIMEZONE)
        appointment = _make_appointment(db, professional.id, place.id, primary.id, start_at)
        assert appointment.class_type == "individual"

        result = mutations.propose_add_appointment_participant(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(extra.id),
            appointment_id=str(appointment.id),
        )
        assert result["requires_confirmation"] is True
        assert "Larissa" in result["preview_text"]
        assert "individual para grupo" in result["preview_text"]

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        db.refresh(appointment)
        assert appointment.class_type == "group"
        assert (
            db.query(AppointmentParticipant)
            .filter(
                AppointmentParticipant.appointment_id == appointment.id,
                AppointmentParticipant.contact_id == extra.id,
            )
            .first()
            is not None
        )

        event = (
            db.query(OperationalEvent)
            .filter(
                OperationalEvent.event_type == "schedule.participant.added",
                OperationalEvent.entity_id == appointment.id,
            )
            .first()
        )
        assert event is not None
        assert event.payload["class_type_changed"] is True
        assert event.before_state == {"class_type": "individual"}
        assert event.after_state == {"class_type": "group", "contact_id": str(extra.id)}
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_add_appointment_participant_rejects_primary_and_duplicate() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        primary = _make_contact(db, professional.id, "Leandro")
        start_at = datetime.combine(MONDAY, time(15, 0), tzinfo=TIMEZONE)
        appointment = _make_appointment(db, professional.id, place.id, primary.id, start_at)

        result = mutations.propose_add_appointment_participant(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(primary.id),
            appointment_id=str(appointment.id),
        )
        assert "error" in result

        extra = _make_contact(db, professional.id, "Larissa")
        first = mutations.propose_add_appointment_participant(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(extra.id),
            appointment_id=str(appointment.id),
        )
        candidates.confirm(db, professional.id, user.id, uuid.UUID(first["candidate_id"]))

        duplicate = mutations.propose_add_appointment_participant(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(extra.id),
            appointment_id=str(appointment.id),
        )
        assert "error" in duplicate
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_add_appointment_participant_respects_configured_capacity() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        primary = _make_contact(db, professional.id, "Leandro")
        first_extra = _make_contact(db, professional.id, "Larissa")
        second_extra = _make_contact(db, professional.id, "Marina")
        start_at = datetime.combine(MONDAY, time(15, 0), tzinfo=TIMEZONE)
        appointment = _make_appointment(
            db,
            professional.id,
            place.id,
            primary.id,
            start_at,
            class_type="group",
            max_participants=2,
        )

        first = mutations.propose_add_appointment_participant(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(first_extra.id),
            appointment_id=str(appointment.id),
        )
        assert candidates.confirm(
            db, professional.id, user.id, uuid.UUID(first["candidate_id"])
        ).ok is True

        full = mutations.propose_add_appointment_participant(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(second_extra.id),
            appointment_id=str(appointment.id),
        )
        assert full == {"error": "This appointment is at full capacity"}
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_remove_appointment_participant_keeps_explicit_group_format() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        primary = _make_contact(db, professional.id, "Leandro")
        extra = _make_contact(db, professional.id, "Larissa")
        start_at = datetime.combine(MONDAY, time(15, 0), tzinfo=TIMEZONE)
        appointment = _make_appointment(db, professional.id, place.id, primary.id, start_at)
        db.add(AppointmentParticipant(appointment_id=appointment.id, contact_id=extra.id))
        appointment.class_type = "group"
        db.commit()

        result = mutations.propose_remove_appointment_participant(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(extra.id),
            appointment_id=str(appointment.id),
        )
        assert result["requires_confirmation"] is True
        assert "grupo para individual" not in result["preview_text"]

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        db.refresh(appointment)
        assert appointment.class_type == "group"
        assert (
            db.query(AppointmentParticipant)
            .filter(AppointmentParticipant.appointment_id == appointment.id)
            .count()
            == 0
        )
        event = (
            db.query(OperationalEvent)
            .filter(
                OperationalEvent.event_type == "schedule.participant.removed",
                OperationalEvent.entity_id == appointment.id,
            )
            .one()
        )
        assert event.payload["class_type_changed"] is False
        assert event.before_state == {"contact_id": str(extra.id), "class_type": "group"}
        assert event.after_state == {"class_type": "group"}
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_remove_appointment_participant_rejects_primary_contact() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        primary = _make_contact(db, professional.id, "Leandro")
        start_at = datetime.combine(MONDAY, time(15, 0), tzinfo=TIMEZONE)
        appointment = _make_appointment(db, professional.id, place.id, primary.id, start_at)

        result = mutations.propose_remove_appointment_participant(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(primary.id),
            appointment_id=str(appointment.id),
        )
        assert "error" in result
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


# ---------------------------------------------------------------------------
# Recurring individual booking correction (roadmap v0.1)
# ---------------------------------------------------------------------------


def test_propose_create_recurring_individual_appointment_retains_contact_and_format() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id, "Carlos")
        thursday = date(2026, 8, 6)  # a Thursday
        start_at = datetime.combine(thursday, time(19, 0), tzinfo=TIMEZONE)

        result = mutations.propose_create_appointment(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(contact.id),
            place_id=str(place.id),
            start_at=start_at.isoformat(),
            end_at=(start_at + timedelta(hours=1)).isoformat(),
            service="Aula individual",
            class_type="individual",
            is_recurring=True,
        )
        assert result["requires_confirmation"] is True
        preview = result["preview_text"]
        assert "Carlos" in preview
        assert "individual" in preview
        assert "semanal" in preview
        assert "quinta" in preview

        candidate = (
            db.query(OperatorActionCandidate)
            .filter(OperatorActionCandidate.professional_id == professional.id)
            .one()
        )
        args = candidate.resolved_arguments
        assert args["is_recurring"] is True
        assert args["class_type"] == "individual"
        assert args["contact_id"] == str(contact.id)
        assert args["contact_ids"] == [str(contact.id)]
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_confirm_recurring_individual_appointment_creates_weekly_appointment() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id, "Carlos")
        thursday = date(2026, 8, 6)
        start_at = datetime.combine(thursday, time(19, 0), tzinfo=TIMEZONE)

        result = mutations.propose_create_appointment(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(contact.id),
            place_id=str(place.id),
            start_at=start_at.isoformat(),
            end_at=(start_at + timedelta(hours=1)).isoformat(),
            service="Aula individual",
            is_recurring=True,
        )
        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        appointment = (
            db.query(Appointment).filter(Appointment.professional_id == professional.id).one()
        )
        assert appointment.contact_id == contact.id
        assert appointment.class_type == "individual"
        assert appointment.max_participants == 1
        assert appointment.recurrence_rule == "FREQ=WEEKLY"

        slots = (
            db.query(RecurringSlot).filter(RecurringSlot.professional_id == professional.id).all()
        )
        assert len(slots) == 0

        event = (
            db.query(OperationalEvent)
            .filter(
                OperationalEvent.professional_id == professional.id,
                OperationalEvent.event_type == "schedule.appointment.created",
            )
            .one()
        )
        assert event.payload["is_recurring"] is True
        assert event.payload["recurrence_rule"] == "FREQ=WEEKLY"
        assert event.payload["class_type"] == "individual"
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_create_non_recurring_appointment_defaults() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id, "Ana")
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)

        result = mutations.propose_create_appointment(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(contact.id),
            place_id=str(place.id),
            start_at=start_at.isoformat(),
            end_at=(start_at + timedelta(hours=1)).isoformat(),
            service="Aula individual",
        )
        assert result["requires_confirmation"] is True
        assert "semanal" not in result["preview_text"]

        candidate = (
            db.query(OperatorActionCandidate)
            .filter(OperatorActionCandidate.professional_id == professional.id)
            .one()
        )
        assert candidate.resolved_arguments["is_recurring"] is False

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        appointment = (
            db.query(Appointment).filter(Appointment.professional_id == professional.id).one()
        )
        assert appointment.recurrence_rule is None
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()

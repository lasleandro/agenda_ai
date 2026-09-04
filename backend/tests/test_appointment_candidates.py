"""Tests for the passive-observer candidate review API (waitlist roadmap
v0.1, Phase 4) and the waitlist_request extraction action."""

from pathlib import Path
import sys
import uuid
from datetime import date, datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import Appointment, AppointmentCandidate, AppointmentTransition, Contact, OperationalEvent, PassiveEscalation, Place, Professional, RecurringSlot, User, WaitlistEntry
from app.schemas.extraction import SchedulingEvent

client = TestClient(app)


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().int % 100_000_000:08d}"


def _random_email() -> str:
    return f"candidates_{uuid.uuid4().hex[:10]}@agenda.ai"


def _make_tenant(db) -> tuple[Professional, User]:
    professional = Professional(name="Tenant Candidates", assistant_phone=_random_phone())
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


def _login_new_tenant(db):
    professional, user = _make_tenant(db)
    login_res = client.post(
        "/api/auth/login", json={"email": user.email, "password": "correct-password"}
    )
    assert login_res.status_code == 200
    return professional, user, login_res.cookies


def _make_contact(db, professional_id, name: str = "Aluno") -> Contact:
    contact = Contact(
        professional_id=professional_id,
        phone=_random_phone(),
        display_name=name,
        normalized_name=name.casefold(),
    )
    db.add(contact)
    db.commit()
    return contact


def _make_candidate(
    db, professional_id, contact_id, *, action: str = "waitlist_request", status: str = "detected"
) -> AppointmentCandidate:
    candidate = AppointmentCandidate(
        professional_id=professional_id,
        contact_id=contact_id,
        action=action,
        operation=action,
        confirmation_status="not_confirmed",
        status=status,
        confidence=0.8,
        ambiguities=[],
        extraction_version="v0.1",
    )
    db.add(candidate)
    db.commit()
    return candidate


def _cleanup(db, *, professionals: list[Professional]) -> None:
    professional_ids = [p.id for p in professionals]
    if not professional_ids:
        return
    db.query(OperationalEvent).filter(
        OperationalEvent.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(WaitlistEntry).filter(WaitlistEntry.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(PassiveEscalation).filter(
        PassiveEscalation.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(AppointmentCandidate).filter(
        AppointmentCandidate.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(AppointmentTransition).filter(
        AppointmentTransition.appointment_id.in_(
            db.query(Appointment.id).filter(Appointment.professional_id.in_(professional_ids))
        )
    ).delete(synchronize_session=False)
    db.query(Appointment).filter(
        Appointment.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(RecurringSlot).filter(
        RecurringSlot.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(Contact).filter(Contact.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(Place).filter(Place.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(User).filter(User.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.commit()


def test_scheduling_event_accepts_waitlist_request_operation() -> None:
    event = SchedulingEvent(
        operation="waitlist_request",
        customer_name="Marcelo",
        confidence=0.7,
        explanation="Profissional disse que nao tem horario e vai avisar.",
    )
    assert event.operation == "waitlist_request"
    assert event.confirmation_status == "not_confirmed"
    assert event.start_at is None


def test_appointment_candidate_status_check_constraint_rejects_invalid_value() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    contact = _make_contact(db, professional.id)
    try:
        candidate = AppointmentCandidate(
            professional_id=professional.id,
            contact_id=contact.id,
            action="waitlist_request",
            status="bogus",
            ambiguities=[],
        )
        db.add(candidate)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_list_candidates_defaults_to_detected_and_is_tenant_scoped() -> None:
    db = SessionLocal()
    pro_a, _, cookies_a = _login_new_tenant(db)
    pro_b, _, cookies_b = _login_new_tenant(db)
    contact_a = _make_contact(db, pro_a.id, "Cliente A")
    try:
        _make_candidate(db, pro_a.id, contact_a.id)
        _make_candidate(db, pro_a.id, contact_a.id, status="dismissed")

        res_a = client.get("/api/appointment-candidates", cookies=cookies_a)
        assert res_a.status_code == 200
        candidates = res_a.json()["candidates"]
        assert len(candidates) == 1
        assert candidates[0]["contact_name"] == "Cliente A"
        assert candidates[0]["action"] == "waitlist_request"
        assert candidates[0]["operation"] == "waitlist_request"
        assert candidates[0]["confirmation_status"] == "not_confirmed"

        res_b = client.get("/api/appointment-candidates", cookies=cookies_b)
        assert res_b.json()["candidates"] == []
    finally:
        _cleanup(db, professionals=[pro_a, pro_b])
        db.close()


def test_dismiss_candidate_transitions_status_and_rejects_twice() -> None:
    db = SessionLocal()
    pro, _, cookies = _login_new_tenant(db)
    contact = _make_contact(db, pro.id)
    try:
        candidate = _make_candidate(db, pro.id, contact.id)

        res = client.post(f"/api/appointment-candidates/{candidate.id}/dismiss", cookies=cookies)
        assert res.status_code == 200
        assert res.json()["status"] == "dismissed"

        again = client.post(f"/api/appointment-candidates/{candidate.id}/dismiss", cookies=cookies)
        assert again.status_code == 409
    finally:
        _cleanup(db, professionals=[pro])
        db.close()


def test_fulfill_waitlist_from_candidate_creates_entry_and_marks_fulfilled() -> None:
    db = SessionLocal()
    pro, _, cookies = _login_new_tenant(db)
    contact = _make_contact(db, pro.id, "Marcelo")
    try:
        candidate = _make_candidate(db, pro.id, contact.id, action="waitlist_request")

        res = client.post(
            f"/api/appointment-candidates/{candidate.id}/fulfill-waitlist",
            json={
                "desired_date": (date.today().isoformat()),
                "desired_start_time": "19:00:00",
                "desired_end_time": "20:00:00",
            },
            cookies=cookies,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["contact_name"] == "Marcelo"
        assert body["status"] == "open"

        db.refresh(candidate)
        assert candidate.status == "fulfilled"

        entries = db.query(WaitlistEntry).filter(WaitlistEntry.professional_id == pro.id).all()
        assert len(entries) == 1
        assert entries[0].contact_id == contact.id
    finally:
        _cleanup(db, professionals=[pro])
        db.close()


def test_fulfill_waitlist_rejects_non_waitlist_action() -> None:
    db = SessionLocal()
    pro, _, cookies = _login_new_tenant(db)
    contact = _make_contact(db, pro.id)
    try:
        candidate = _make_candidate(db, pro.id, contact.id, action="create")

        res = client.post(
            f"/api/appointment-candidates/{candidate.id}/fulfill-waitlist",
            json={
                "desired_date": date.today().isoformat(),
                "desired_start_time": "19:00:00",
                "desired_end_time": "20:00:00",
            },
            cookies=cookies,
        )
        assert res.status_code == 422
    finally:
        _cleanup(db, professionals=[pro])
        db.close()


def test_fulfill_waitlist_rejects_already_fulfilled() -> None:
    db = SessionLocal()
    pro, _, cookies = _login_new_tenant(db)
    contact = _make_contact(db, pro.id, "Marcelo")
    try:
        candidate = _make_candidate(db, pro.id, contact.id, action="waitlist_request")
        body = {
            "desired_date": date.today().isoformat(),
            "desired_start_time": "19:00:00",
            "desired_end_time": "20:00:00",
        }
        first = client.post(
            f"/api/appointment-candidates/{candidate.id}/fulfill-waitlist",
            json=body,
            cookies=cookies,
        )
        assert first.status_code == 200

        second = client.post(
            f"/api/appointment-candidates/{candidate.id}/fulfill-waitlist",
            json=body,
            cookies=cookies,
        )
        assert second.status_code == 409
    finally:
        _cleanup(db, professionals=[pro])
        db.close()


def test_confirm_create_candidate_creates_appointment_and_fulfills_candidate() -> None:
    db = SessionLocal()
    pro, _, cookies = _login_new_tenant(db)
    contact = _make_contact(db, pro.id, "Mariana")
    try:
        place = Place(professional_id=pro.id, name="Clube", normalized_name="clube")
        db.add(place)
        db.flush()
        contact.home_place_id = place.id
        candidate = AppointmentCandidate(
            professional_id=pro.id,
            contact_id=contact.id,
            action="create",
            operation="create",
            confirmation_status="instructor_confirmed",
            proposed_start_at=datetime(2030, 1, 10, 17, tzinfo=timezone.utc),
            proposed_end_at=datetime(2030, 1, 10, 18, tzinfo=timezone.utc),
            service="tennis_lesson",
            status="detected",
            ambiguities=[],
        )
        db.add(candidate)
        db.commit()
        db.add(
            RecurringSlot(
                professional_id=pro.id,
                place_id=place.id,
                day_of_week=3,
                start_time=datetime(2030, 1, 10, 14).time(),
                end_time=datetime(2030, 1, 10, 15).time(),
                slot_kind="availability",
                status="active",
            )
        )
        db.commit()
        escalation = PassiveEscalation(
            appointment_candidate_id=candidate.id,
            professional_id=pro.id,
            status="needs_place_review",
            next_attempt_at=datetime(2030, 1, 10, 17, tzinfo=timezone.utc),
        )
        db.add(escalation)
        db.commit()

        response = client.post(
            f"/api/appointment-candidates/{candidate.id}/confirm-appointment",
            json={},
            cookies=cookies,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "fulfilled"
        assert response.json()["resulting_appointment_id"] is not None
        assert response.json()["resolved_place_id"] == str(place.id)
        assert response.json()["place_resolution"] == "resolved"
        assert response.json()["place_source"] == "unique_stay"
        db.refresh(candidate)
        db.refresh(escalation)
        assert candidate.resulting_appointment_id is not None
        assert escalation.status == "expired"
        appointment = db.query(Appointment).filter_by(id=candidate.resulting_appointment_id).one()
        assert appointment.contact_id == contact.id
        assert appointment.place_id == place.id
        assert appointment.source == "passive_candidate"
    finally:
        _cleanup(db, professionals=[pro])
        db.close()

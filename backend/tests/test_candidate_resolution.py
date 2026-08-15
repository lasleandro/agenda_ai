"""Unit tests for deterministic passive-candidate resolution."""

from datetime import datetime, timedelta
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.chat.pipeline import _auto_execute_authoritative_create
from app.models import Appointment, AppointmentCandidate, AppointmentTransition, Contact, OperationalEvent, Place, Professional, User
from app.services.candidate_resolution import resolve_candidate


def _phone() -> str:
    return f"+55119{uuid.uuid4().hex[:8]}"


def _setup_candidate(operation: str = "create"):
    db = SessionLocal()
    professional = Professional(name="Resolver", assistant_phone=_phone())
    db.add(professional)
    db.commit()
    contact = Contact(
        professional_id=professional.id,
        phone=_phone(),
        display_name="Aluno",
        normalized_name="aluno",
    )
    db.add(contact)
    db.commit()
    candidate = AppointmentCandidate(
        professional_id=professional.id,
        contact_id=contact.id,
        action=operation,
        operation=operation,
        confirmation_status="instructor_confirmed",
        proposed_start_at=datetime.now().astimezone() + timedelta(days=2),
        proposed_end_at=datetime.now().astimezone() + timedelta(days=2, hours=1),
        service="tennis_lesson",
        status="detected",
        ambiguities=[],
    )
    db.add(candidate)
    db.commit()
    return db, professional, contact, candidate


def _cleanup(db, professional: Professional) -> None:
    db.query(OperationalEvent).filter_by(professional_id=professional.id).delete()
    db.query(AppointmentCandidate).filter_by(professional_id=professional.id).delete()
    db.query(AppointmentTransition).filter(
        AppointmentTransition.appointment_id.in_(
            db.query(Appointment.id).filter_by(professional_id=professional.id)
        )
    ).delete(synchronize_session=False)
    db.query(Appointment).filter_by(professional_id=professional.id).delete()
    db.query(Contact).filter_by(professional_id=professional.id).delete()
    db.query(Place).filter_by(professional_id=professional.id).delete()
    db.query(User).filter_by(professional_id=professional.id).delete()
    db.query(Professional).filter_by(id=professional.id).delete()
    db.commit()
    db.close()


def test_resolve_candidate_create_uses_contact_home_place() -> None:
    db, professional, contact, candidate = _setup_candidate()
    try:
        place = Place(
            professional_id=professional.id,
            name="Clube",
            normalized_name="clube",
        )
        db.add(place)
        db.flush()
        contact.home_place_id = place.id
        db.commit()

        resolution = resolve_candidate(db, candidate)

        assert resolution.is_resolved
        assert resolution.operation == "create"
        assert resolution.arguments["contact_id"] == str(contact.id)
        assert resolution.arguments["place_id"] == str(place.id)
    finally:
        _cleanup(db, professional)


def test_resolve_candidate_create_reports_missing_place() -> None:
    db, professional, _, candidate = _setup_candidate()
    try:
        resolution = resolve_candidate(db, candidate)

        assert not resolution.is_resolved
        assert resolution.operation == "create"
        assert resolution.missing_fields == ["place_id"]
    finally:
        _cleanup(db, professional)


def test_authoritative_resolved_create_is_auto_executed() -> None:
    db, professional, contact, candidate = _setup_candidate()
    try:
        place = Place(professional_id=professional.id, name="Clube", normalized_name="clube")
        db.add(place)
        db.flush()
        contact.home_place_id = place.id
        db.add(
            User(
                professional_id=professional.id,
                email=f"{uuid.uuid4().hex}@example.test",
                hashed_password="not-used-in-this-test",
                role="professional",
            )
        )
        db.commit()

        assert _auto_execute_authoritative_create(db, candidate)
        db.commit()
        db.refresh(candidate)

        assert candidate.status == "fulfilled"
        assert candidate.resulting_appointment_id is not None
        assert db.query(Appointment).filter_by(id=candidate.resulting_appointment_id).one().source == "passive_candidate"
    finally:
        _cleanup(db, professional)


def test_resolve_candidate_reschedule_maps_existing_appointment() -> None:
    db, professional, contact, candidate = _setup_candidate("reschedule")
    try:
        place = Place(
            professional_id=professional.id,
            name="Clube",
            normalized_name="clube",
        )
        db.add(place)
        db.flush()
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            place_id=place.id,
            service="tennis_lesson",
            start_at=datetime.now().astimezone() + timedelta(days=1),
            end_at=datetime.now().astimezone() + timedelta(days=1, hours=1),
            status="confirmed",
            source="dashboard",
        )
        db.add(appointment)
        db.flush()
        candidate.existing_appointment_id = appointment.id
        db.commit()

        resolution = resolve_candidate(db, candidate)

        assert resolution.is_resolved
        assert resolution.operation == "reschedule"
        assert resolution.arguments["target_id"] == str(appointment.id)
        assert resolution.arguments["target_type"] == "appointment"
    finally:
        _cleanup(db, professional)


def test_resolve_candidate_reschedule_requires_appointment_reference() -> None:
    db, professional, _, candidate = _setup_candidate("reschedule")
    try:
        resolution = resolve_candidate(db, candidate)

        assert not resolution.is_resolved
        assert resolution.missing_fields == ["existing_appointment_id"]
    finally:
        _cleanup(db, professional)

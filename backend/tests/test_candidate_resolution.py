"""Unit tests for deterministic passive-candidate resolution."""

from datetime import datetime, timedelta
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.chat.pipeline import _auto_execute_authoritative_candidate
from app.models import Appointment, AppointmentCandidate, AppointmentTransition, Contact, OperationalEvent, Place, Professional, RecurringSlot, ScheduleOccurrenceOverride, User
from app.services.candidate_resolution import CandidateOverrides, resolve_candidate
from app.services.scheduling import TIMEZONE


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
    candidate_start = (datetime.now(TIMEZONE) + timedelta(days=2)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    candidate = AppointmentCandidate(
        professional_id=professional.id,
        contact_id=contact.id,
        action=operation,
        operation=operation,
        confirmation_status="instructor_confirmed",
        proposed_start_at=candidate_start,
        proposed_end_at=candidate_start + timedelta(hours=1),
        service="tennis_lesson",
        status="detected",
        ambiguities=[],
    )
    db.add(candidate)
    db.commit()
    return db, professional, contact, candidate


def _cleanup(db, professional: Professional) -> None:
    db.query(OperationalEvent).filter_by(professional_id=professional.id).delete()
    db.query(ScheduleOccurrenceOverride).filter_by(professional_id=professional.id).delete()
    db.query(AppointmentCandidate).filter_by(professional_id=professional.id).delete()
    db.query(AppointmentTransition).filter(
        AppointmentTransition.appointment_id.in_(
            db.query(Appointment.id).filter_by(professional_id=professional.id)
        )
    ).delete(synchronize_session=False)
    db.query(Appointment).filter_by(professional_id=professional.id).delete()
    db.query(RecurringSlot).filter_by(professional_id=professional.id).delete()
    db.query(Contact).filter_by(professional_id=professional.id).delete()
    db.query(Place).filter_by(professional_id=professional.id).delete()
    db.query(User).filter_by(professional_id=professional.id).delete()
    db.query(Professional).filter_by(id=professional.id).delete()
    db.commit()
    db.close()


def _add_covering_stay(
    db, professional: Professional, place: Place, candidate: AppointmentCandidate
) -> None:
    local_start = candidate.proposed_start_at.astimezone(TIMEZONE)
    local_end = candidate.proposed_end_at.astimezone(TIMEZONE)
    db.add(
        RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=local_start.weekday(),
            start_time=local_start.time().replace(tzinfo=None),
            end_time=local_end.time().replace(tzinfo=None),
            slot_kind="availability",
            status="active",
        )
    )
    db.commit()


def test_resolve_candidate_create_uses_home_place_only_to_break_stay_tie() -> None:
    db, professional, contact, candidate = _setup_candidate()
    try:
        place = Place(
            professional_id=professional.id,
            name="Clube",
            normalized_name="clube",
        )
        db.add(place)
        db.flush()
        other_place = Place(
            professional_id=professional.id,
            name="Outro Clube",
            normalized_name="outro-clube",
        )
        db.add(other_place)
        db.flush()
        contact.home_place_id = place.id
        db.commit()
        _add_covering_stay(db, professional, place, candidate)
        _add_covering_stay(db, professional, other_place, candidate)

        resolution = resolve_candidate(db, candidate)

        assert resolution.is_resolved
        assert resolution.operation == "create"
        assert resolution.arguments["contact_id"] == str(contact.id)
        assert resolution.arguments["place_id"] == str(place.id)
        assert resolution.place_source == "home_place_tiebreak"
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


def test_resolve_candidate_does_not_treat_home_place_as_covering_stay() -> None:
    db, professional, contact, candidate = _setup_candidate()
    try:
        place = Place(professional_id=professional.id, name="Clube", normalized_name="clube")
        db.add(place)
        db.flush()
        contact.home_place_id = place.id
        db.commit()

        resolution = resolve_candidate(db, candidate)

        assert not resolution.is_resolved
        assert resolution.missing_fields == ["place_id"]
        assert resolution.place_resolution is not None
        assert resolution.place_resolution.outcome == "uncovered"
    finally:
        _cleanup(db, professional)


def test_resolve_candidate_accepts_reviewed_place_exception() -> None:
    db, professional, _, candidate = _setup_candidate()
    try:
        place = Place(professional_id=professional.id, name="Clube", normalized_name="clube")
        db.add(place)
        db.commit()

        resolution = resolve_candidate(
            db, candidate, CandidateOverrides(place_id=place.id)
        )

        assert resolution.is_resolved
        assert resolution.arguments["place_id"] == str(place.id)
        assert resolution.place_source == "review_override"
        assert resolution.place_resolution is not None
        assert resolution.place_resolution.is_explicit_exception is True
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
        _add_covering_stay(db, professional, place, candidate)

        assert _auto_execute_authoritative_candidate(db, candidate)
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
        _add_covering_stay(db, professional, place, candidate)

        resolution = resolve_candidate(db, candidate)

        assert resolution.is_resolved
        assert resolution.operation == "reschedule"
        assert resolution.arguments["target_id"] == str(appointment.id)
        assert resolution.arguments["target_type"] == "appointment"
    finally:
        _cleanup(db, professional)


def test_authoritative_resolved_reschedule_is_auto_executed() -> None:
    db, professional, contact, candidate = _setup_candidate("reschedule")
    try:
        place = Place(professional_id=professional.id, name="Clube", normalized_name="clube")
        user = User(
            professional_id=professional.id,
            email=f"{uuid.uuid4().hex}@example.test",
            hashed_password="not-used-in-this-test",
            role="professional",
        )
        db.add_all([place, user])
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
        _add_covering_stay(db, professional, place, candidate)

        assert _auto_execute_authoritative_candidate(db, candidate)
        db.commit()
        db.refresh(candidate)

        assert candidate.status == "fulfilled"
        assert candidate.resulting_appointment_id == appointment.id
        override = db.query(ScheduleOccurrenceOverride).filter_by(
            professional_id=professional.id,
            appointment_id=appointment.id,
        ).one()
        assert override.replacement_start_at == candidate.proposed_start_at
        assert override.replacement_end_at == candidate.proposed_end_at
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

"""Tests for the Fila de Espera (waitlist) feature — waitlist roadmap v0.1,
Phase 1: service layer, dashboard REST API, and active-agent tools."""

from pathlib import Path
import sys
import uuid
from datetime import date, time, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from datetime import datetime

from app.agent import candidates, mutations, tools
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
    User,
    WaitlistEntry,
    WorkJourneyInterval,
)
from app.services import waitlist as waitlist_service
from app.services.scheduling import TIMEZONE

MONDAY = date(2026, 8, 3)  # a known Monday, matches test_agent.py's fixture convention

client = TestClient(app)


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().int % 100_000_000:08d}"


def _random_email() -> str:
    return f"waitlist_{uuid.uuid4().hex[:10]}@agenda.ai"


def _make_tenant(db) -> tuple[Professional, User]:
    professional = Professional(name="Tenant Waitlist", assistant_phone=_random_phone())
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


def _make_place(db, professional_id, name: str = "Clube") -> Place:
    place = Place(professional_id=professional_id, name=name, normalized_name=name.casefold())
    db.add(place)
    db.commit()
    return place


def _cleanup(db, *, professionals: list[Professional]) -> None:
    professional_ids = [p.id for p in professionals]
    if not professional_ids:
        return
    db.query(OperationalEvent).filter(
        OperationalEvent.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(OperatorActionCandidate).filter(
        OperatorActionCandidate.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(WaitlistEntry).filter(WaitlistEntry.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(ScheduleOccurrenceOverride).filter(
        ScheduleOccurrenceOverride.professional_id.in_(professional_ids)
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
    db.query(Appointment).filter(Appointment.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(RecurringSlot).filter(RecurringSlot.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(WorkJourneyInterval).filter(
        WorkJourneyInterval.professional_id.in_(professional_ids)
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


TOMORROW = date.today() + timedelta(days=1)


# ---------------------------------------------------------------------------
# Service layer
# ---------------------------------------------------------------------------

def test_create_entry_defaults_duration_from_time_range() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    contact = _make_contact(db, professional.id)
    try:
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            desired_date=TOMORROW,
            desired_start_time=time(19, 0),
            desired_end_time=time(20, 0),
        )
        assert entry.duration_minutes == 60
        assert entry.status == "open"
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_create_entry_rejects_unknown_contact() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    try:
        try:
            waitlist_service.create_entry(
                db,
                professional.id,
                contact_id=uuid.uuid4(),
                desired_date=TOMORROW,
                desired_start_time=time(19, 0),
                desired_end_time=time(20, 0),
            )
            assert False, "expected WaitlistValidationError"
        except waitlist_service.WaitlistValidationError as exc:
            assert "Contact not found" in str(exc)
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_create_entry_rejects_end_before_start() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    contact = _make_contact(db, professional.id)
    try:
        try:
            waitlist_service.create_entry(
                db,
                professional.id,
                contact_id=contact.id,
                desired_date=TOMORROW,
                desired_start_time=time(20, 0),
                desired_end_time=time(19, 0),
            )
            assert False, "expected WaitlistValidationError"
        except waitlist_service.WaitlistValidationError:
            pass
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_list_entries_filters_by_status() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    contact = _make_contact(db, professional.id)
    try:
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            desired_date=TOMORROW,
            desired_start_time=time(19, 0),
            desired_end_time=time(20, 0),
        )
        waitlist_service.cancel_entry(db, professional.id, entry.id)

        open_entries = waitlist_service.list_entries(db, professional.id, status="open")
        cancelled_entries = waitlist_service.list_entries(db, professional.id, status="cancelled")
        assert open_entries == []
        assert [e.id for e in cancelled_entries] == [entry.id]
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_cancel_entry_rejects_already_cancelled() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    contact = _make_contact(db, professional.id)
    try:
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            desired_date=TOMORROW,
            desired_start_time=time(19, 0),
            desired_end_time=time(20, 0),
        )
        waitlist_service.cancel_entry(db, professional.id, entry.id)
        try:
            waitlist_service.cancel_entry(db, professional.id, entry.id)
            assert False, "expected WaitlistValidationError"
        except waitlist_service.WaitlistValidationError as exc:
            assert "not cancellable" in str(exc)
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_fulfill_entry_sets_status_and_appointment_link() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    contact = _make_contact(db, professional.id)
    try:
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            desired_date=TOMORROW,
            desired_start_time=time(19, 0),
            desired_end_time=time(20, 0),
        )
        booked_at = datetime.combine(TOMORROW, time(19, 0), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            service="Aula",
            start_at=booked_at,
            end_at=booked_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
        )
        db.add(appointment)
        db.commit()

        fulfilled = waitlist_service.fulfill_entry(db, professional.id, entry.id, appointment.id)

        assert fulfilled.status == "fulfilled"
        assert fulfilled.fulfilled_appointment_id == appointment.id
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_fulfill_entry_rejects_already_cancelled() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    contact = _make_contact(db, professional.id)
    try:
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            desired_date=TOMORROW,
            desired_start_time=time(19, 0),
            desired_end_time=time(20, 0),
        )
        waitlist_service.cancel_entry(db, professional.id, entry.id)
        try:
            waitlist_service.fulfill_entry(db, professional.id, entry.id, uuid.uuid4())
            assert False, "expected WaitlistValidationError"
        except waitlist_service.WaitlistValidationError as exc:
            assert "not fulfillable" in str(exc)
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


# ---------------------------------------------------------------------------
# Dashboard REST API
# ---------------------------------------------------------------------------

def test_api_create_list_cancel_and_tenant_isolation() -> None:
    db = SessionLocal()
    pro_a, user_a, cookies_a = _login_new_tenant(db)
    pro_b, user_b, cookies_b = _login_new_tenant(db)
    try:
        contact_a = _make_contact(db, pro_a.id, "Cliente A")

        create_res = client.post(
            "/api/waitlist-entries",
            json={
                "contact_id": str(contact_a.id),
                "desired_date": TOMORROW.isoformat(),
                "desired_start_time": "19:00:00",
                "desired_end_time": "20:00:00",
            },
            cookies=cookies_a,
        )
        assert create_res.status_code == 201
        body = create_res.json()
        assert body["status"] == "open"
        assert body["contact_name"] == "Cliente A"
        entry_id = body["id"]

        list_res_a = client.get("/api/waitlist-entries", cookies=cookies_a)
        assert list_res_a.status_code == 200
        assert [e["id"] for e in list_res_a.json()["entries"]] == [entry_id]

        # Tenant B must not see tenant A's entry.
        list_res_b = client.get("/api/waitlist-entries", cookies=cookies_b)
        assert list_res_b.status_code == 200
        assert list_res_b.json()["entries"] == []

        # Tenant B cannot cancel tenant A's entry.
        cross_cancel = client.post(f"/api/waitlist-entries/{entry_id}/cancel", cookies=cookies_b)
        assert cross_cancel.status_code == 404

        cancel_res = client.post(f"/api/waitlist-entries/{entry_id}/cancel", cookies=cookies_a)
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "cancelled"
    finally:
        _cleanup(db, professionals=[pro_a, pro_b])
        db.close()


def test_api_create_rejects_unknown_place() -> None:
    db = SessionLocal()
    pro, user, cookies = _login_new_tenant(db)
    try:
        contact = _make_contact(db, pro.id)
        res = client.post(
            "/api/waitlist-entries",
            json={
                "contact_id": str(contact.id),
                "place_id": str(uuid.uuid4()),
                "desired_date": TOMORROW.isoformat(),
                "desired_start_time": "19:00:00",
                "desired_end_time": "20:00:00",
            },
            cookies=cookies,
        )
        assert res.status_code == 422
    finally:
        _cleanup(db, professionals=[pro])
        db.close()


def test_api_fulfill_entry() -> None:
    db = SessionLocal()
    pro, user, cookies = _login_new_tenant(db)
    try:
        contact = _make_contact(db, pro.id)
        entry = waitlist_service.create_entry(
            db,
            pro.id,
            contact_id=contact.id,
            desired_date=TOMORROW,
            desired_start_time=time(19, 0),
            desired_end_time=time(20, 0),
        )
        booked_at = datetime.combine(TOMORROW, time(19, 0), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=pro.id,
            contact_id=contact.id,
            service="Aula",
            start_at=booked_at,
            end_at=booked_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
        )
        db.add(appointment)
        db.commit()

        res = client.post(
            f"/api/waitlist-entries/{entry.id}/fulfill",
            json={"appointment_id": str(appointment.id)},
            cookies=cookies,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "fulfilled"
    finally:
        _cleanup(db, professionals=[pro])
        db.close()


def test_api_fulfill_waitlist_entry_with_group_occurrence() -> None:
    db = SessionLocal()
    pro, user, cookies = _login_new_tenant(db)
    try:
        place = _make_place(db, pro.id)
        contact = _make_contact(db, pro.id)
        entry = waitlist_service.create_entry(
            db,
            pro.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=TOMORROW,
            desired_start_time=time(19, 0),
            desired_end_time=time(20, 0),
            class_type="group",
        )
        group = RecurringSlot(
            professional_id=pro.id,
            place_id=place.id,
            day_of_week=TOMORROW.weekday(),
            start_time=time(19, 0),
            end_time=time(20, 0),
            label="Turma noturna",
            slot_kind="class",
            class_type="group",
            max_participants=2,
            recurrence_type="weekly",
        )
        db.add(group)
        db.commit()

        res = client.post(
            f"/api/waitlist-entries/{entry.id}/fulfill-group",
            json={
                "recurring_slot_id": str(group.id),
                "occurrence_date": TOMORROW.isoformat(),
                "enrollment_scope": "occurrence",
            },
            cookies=cookies,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "fulfilled"
        assert body["fulfilled_recurring_slot_id"] == str(group.id)
        assert body["fulfilled_occurrence_date"] == TOMORROW.isoformat()
        assert body["fulfillment_scope"] == "occurrence"
        assert (
            db.query(RecurringSlotOccurrenceParticipant)
            .filter(
                RecurringSlotOccurrenceParticipant.recurring_slot_id == group.id,
                RecurringSlotOccurrenceParticipant.contact_id == contact.id,
                RecurringSlotOccurrenceParticipant.occurrence_date == TOMORROW,
            )
            .count()
            == 1
        )
    finally:
        _cleanup(db, professionals=[pro])
        db.close()


def test_api_fulfill_waitlist_group_rejects_another_tenant_slot() -> None:
    db = SessionLocal()
    pro_a, user_a, cookies_a = _login_new_tenant(db)
    pro_b, user_b, cookies_b = _login_new_tenant(db)
    try:
        place_a = _make_place(db, pro_a.id)
        contact_a = _make_contact(db, pro_a.id)
        entry = waitlist_service.create_entry(
            db,
            pro_a.id,
            contact_id=contact_a.id,
            desired_date=TOMORROW,
            desired_start_time=time(19, 0),
            desired_end_time=time(20, 0),
            class_type="group",
        )
        place_b = _make_place(db, pro_b.id)
        group_b = RecurringSlot(
            professional_id=pro_b.id,
            place_id=place_b.id,
            day_of_week=TOMORROW.weekday(),
            start_time=time(19, 0),
            end_time=time(20, 0),
            slot_kind="class",
            class_type="group",
            max_participants=2,
            recurrence_type="weekly",
        )
        db.add(group_b)
        db.commit()

        res = client.post(
            f"/api/waitlist-entries/{entry.id}/fulfill-group",
            json={
                "recurring_slot_id": str(group_b.id),
                "occurrence_date": TOMORROW.isoformat(),
                "enrollment_scope": "occurrence",
            },
            cookies=cookies_a,
        )
        assert res.status_code == 404
        db.refresh(entry)
        assert entry.status == "open"
    finally:
        _cleanup(db, professionals=[pro_a, pro_b])
        db.close()


def test_api_fulfill_waitlist_entry_into_group_series() -> None:
    db = SessionLocal()
    pro, user, cookies = _login_new_tenant(db)
    try:
        place = _make_place(db, pro.id)
        contact = _make_contact(db, pro.id)
        entry = waitlist_service.create_entry(
            db,
            pro.id,
            contact_id=contact.id,
            desired_date=TOMORROW,
            desired_start_time=time(19, 0),
            desired_end_time=time(20, 0),
            class_type="group",
        )
        group = RecurringSlot(
            professional_id=pro.id,
            place_id=place.id,
            day_of_week=TOMORROW.weekday(),
            start_time=time(19, 0),
            end_time=time(20, 0),
            slot_kind="class",
            class_type="group",
            max_participants=2,
            recurrence_type="weekly",
        )
        db.add(group)
        db.commit()

        res = client.post(
            f"/api/waitlist-entries/{entry.id}/fulfill-group",
            json={
                "recurring_slot_id": str(group.id),
                "occurrence_date": TOMORROW.isoformat(),
                "enrollment_scope": "series",
            },
            cookies=cookies,
        )
        assert res.status_code == 200
        assert res.json()["fulfillment_scope"] == "series"
        assert (
            db.query(RecurringSlotParticipant)
            .filter(
                RecurringSlotParticipant.recurring_slot_id == group.id,
                RecurringSlotParticipant.contact_id == contact.id,
            )
            .count()
            == 1
        )
    finally:
        _cleanup(db, professionals=[pro])
        db.close()


# ---------------------------------------------------------------------------
# Active-agent tools
# ---------------------------------------------------------------------------

def test_propose_add_waitlist_entry_full_cycle() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    contact = _make_contact(db, professional.id, "Marcelo")
    place = _make_place(db, professional.id)
    correlation_id = uuid.uuid4()
    try:
        result = mutations.propose_add_waitlist_entry(
            db,
            professional.id,
            user.id,
            correlation_id,
            contact_id=str(contact.id),
            place_id=str(place.id),
            desired_date=TOMORROW.isoformat(),
            desired_start_time="19:00:00",
            desired_end_time="20:00:00",
        )
        assert result["requires_confirmation"] is True
        assert "Marcelo" in result["preview_text"]
        assert "fila de espera" in result["preview_text"].lower()

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        entries = waitlist_service.list_entries(db, professional.id)
        assert len(entries) == 1
        assert entries[0].contact_id == contact.id
        assert entries[0].place_id == place.id
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_propose_add_waitlist_entry_rejects_unknown_contact() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    correlation_id = uuid.uuid4()
    try:
        result = mutations.propose_add_waitlist_entry(
            db,
            professional.id,
            user.id,
            correlation_id,
            contact_id=str(uuid.uuid4()),
            desired_date=TOMORROW.isoformat(),
            desired_start_time="19:00:00",
            desired_end_time="20:00:00",
        )
        assert "error" in result
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_propose_remove_waitlist_entry_full_cycle() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    contact = _make_contact(db, professional.id, "Marcelo")
    correlation_id = uuid.uuid4()
    try:
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            desired_date=TOMORROW,
            desired_start_time=time(19, 0),
            desired_end_time=time(20, 0),
        )

        result = mutations.propose_remove_waitlist_entry(
            db, professional.id, user.id, correlation_id, waitlist_entry_id=str(entry.id)
        )
        assert result["requires_confirmation"] is True

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        db.refresh(entry)
        assert entry.status == "cancelled"
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_propose_remove_waitlist_entry_rejects_already_cancelled() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    contact = _make_contact(db, professional.id)
    correlation_id = uuid.uuid4()
    try:
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            desired_date=TOMORROW,
            desired_start_time=time(19, 0),
            desired_end_time=time(20, 0),
        )
        waitlist_service.cancel_entry(db, professional.id, entry.id)

        result = mutations.propose_remove_waitlist_entry(
            db, professional.id, user.id, correlation_id, waitlist_entry_id=str(entry.id)
        )
        assert "error" in result
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_list_waitlist_entries_tool_is_tenant_scoped() -> None:
    db = SessionLocal()
    pro_a, user_a = _make_tenant(db)
    pro_b, user_b = _make_tenant(db)
    contact_a = _make_contact(db, pro_a.id, "Cliente A")
    try:
        waitlist_service.create_entry(
            db,
            pro_a.id,
            contact_id=contact_a.id,
            desired_date=TOMORROW,
            desired_start_time=time(19, 0),
            desired_end_time=time(20, 0),
        )

        result_a = tools.list_waitlist_entries(db, pro_a.id)
        result_b = tools.list_waitlist_entries(db, pro_b.id)

        assert len(result_a["entries"]) == 1
        assert result_a["entries"][0]["contact_name"] == "Cliente A"
        assert result_b["entries"] == []
    finally:
        _cleanup(db, professionals=[pro_a, pro_b])
        db.close()


# ---------------------------------------------------------------------------
# Phase 2 — on-demand matching
# ---------------------------------------------------------------------------

def _give_capacity(db, professional_id, place_id) -> None:
    """A full Monday 08:00-18:00 work journey + place availability, matching
    test_agent.py's find_instructor_openings fixture convention."""
    db.add(
        WorkJourneyInterval(
            professional_id=professional_id,
            day_of_week=0,
            interval_type="work",
            start_time=time(8, 0),
            end_time=time(18, 0),
        )
    )
    db.add(
        RecurringSlot(
            professional_id=professional_id,
            place_id=place_id,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(18, 0),
            recurrence_type="weekly",
            slot_kind="availability",
            created_at=datetime.combine(MONDAY, time(6, 0), tzinfo=TIMEZONE),
        )
    )
    db.commit()


def test_find_matches_reports_entry_with_a_free_opening() -> None:
    db = SessionLocal()
    professional = _make_tenant(db)[0]
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id, "Marcelo")
    try:
        _give_capacity(db, professional.id, place.id)
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
        )

        matches = waitlist_service.find_matches(db, professional.id)

        assert len(matches) == 1
        assert matches[0]["entry"].id == entry.id
        assert matches[0]["place_id"] == place.id
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_find_matches_reports_joinable_group_without_calling_it_free_time() -> None:
    db = SessionLocal()
    professional = _make_tenant(db)[0]
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id, "Marcelo")
    try:
        group = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(10, 0),
            end_time=time(11, 0),
            slot_kind="class",
            class_type="group",
            max_participants=2,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        db.add(group)
        db.commit()
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
            class_type="group",
        )

        matches = waitlist_service.find_matches(db, professional.id)

        assert len(matches) == 1
        assert matches[0]["entry"].id == entry.id
        assert matches[0]["match_type"] == "group_occurrence"
        assert matches[0]["source_id"] == group.id
        assert matches[0]["available_seats"] == 2
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_find_matches_excludes_entry_whose_slot_is_booked() -> None:
    db = SessionLocal()
    professional = _make_tenant(db)[0]
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id, "Marcelo")
    other_contact = _make_contact(db, professional.id, "Outro Aluno")
    try:
        _give_capacity(db, professional.id, place.id)
        waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
        )
        booked_start = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        db.add(
            Appointment(
                professional_id=professional.id,
                contact_id=other_contact.id,
                place_id=place.id,
                service="Aula",
                start_at=booked_start,
                end_at=booked_start + timedelta(hours=1),
                status="confirmed",
                source="dashboard",
            )
        )
        db.commit()

        matches = waitlist_service.find_matches(db, professional.id)

        assert matches == []
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_find_matches_ignores_non_open_entries() -> None:
    db = SessionLocal()
    professional = _make_tenant(db)[0]
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id, "Marcelo")
    try:
        _give_capacity(db, professional.id, place.id)
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
        )
        waitlist_service.cancel_entry(db, professional.id, entry.id)

        matches = waitlist_service.find_matches(db, professional.id)

        assert matches == []
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_find_waitlist_matches_tool_is_tenant_scoped_and_read_only() -> None:
    db = SessionLocal()
    pro_a, _ = _make_tenant(db)
    pro_b, _ = _make_tenant(db)
    place_a = _make_place(db, pro_a.id)
    contact_a = _make_contact(db, pro_a.id, "Cliente A")
    try:
        _give_capacity(db, pro_a.id, place_a.id)
        entry = waitlist_service.create_entry(
            db,
            pro_a.id,
            contact_id=contact_a.id,
            place_id=place_a.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
        )

        result_a = tools.find_waitlist_matches(db, pro_a.id)
        result_b = tools.find_waitlist_matches(db, pro_b.id)

        assert len(result_a["matches"]) == 1
        assert result_a["matches"][0]["contact_name"] == "Cliente A"
        assert result_b["matches"] == []

        # Read-only — the entry's status must be untouched by the check.
        db.refresh(entry)
        assert entry.status == "open"
    finally:
        _cleanup(db, professionals=[pro_a, pro_b])
        db.close()


# ---------------------------------------------------------------------------
# Phase 5 — event-driven auto-matching
# ---------------------------------------------------------------------------

def test_mark_matches_for_date_flags_open_entries_as_matched() -> None:
    db = SessionLocal()
    professional = _make_tenant(db)[0]
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id, "Marcelo")
    try:
        _give_capacity(db, professional.id, place.id)
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
        )

        newly_matched = waitlist_service.mark_matches_for_date(db, professional.id, MONDAY)
        db.commit()

        assert [e.id for e in newly_matched] == [entry.id]
        db.refresh(entry)
        assert entry.status == "matched"
        assert entry.matched_at is not None
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_mark_matches_for_date_ignores_non_open_entries() -> None:
    db = SessionLocal()
    professional = _make_tenant(db)[0]
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id, "Marcelo")
    try:
        _give_capacity(db, professional.id, place.id)
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
        )
        waitlist_service.cancel_entry(db, professional.id, entry.id)

        newly_matched = waitlist_service.mark_matches_for_date(db, professional.id, MONDAY)

        assert newly_matched == []
        db.refresh(entry)
        assert entry.status == "cancelled"
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_cancelling_an_occurrence_auto_matches_and_surfaces_in_summary() -> None:
    """End-to-end: cancelling an appointment via the agent frees that slot,
    and an open waitlist entry for the same date/time/place is automatically
    flagged and mentioned in the confirmation summary the instructor sees."""
    db = SessionLocal()
    professional, user = _make_tenant(db)
    place = _make_place(db, professional.id)
    booked_contact = _make_contact(db, professional.id, "Joao")
    waiting_contact = _make_contact(db, professional.id, "Marcelo")
    correlation_id = uuid.uuid4()
    try:
        _give_capacity(db, professional.id, place.id)
        waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=waiting_contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
        )

        booked_start = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=booked_contact.id,
            place_id=place.id,
            service="Aula",
            start_at=booked_start,
            end_at=booked_start + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
        )
        db.add(appointment)
        db.commit()

        propose_result = mutations.propose_cancel_schedule(
            db,
            professional.id,
            user.id,
            correlation_id,
            target_type="appointment",
            target_id=str(appointment.id),
            occurrence_date=MONDAY.isoformat(),
        )
        assert propose_result["requires_confirmation"] is True

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(propose_result["candidate_id"])
        )

        assert exec_result.ok is True
        assert "Marcelo" in exec_result.summary
        assert "fila de espera" in exec_result.summary.lower()

        matched_entry = waitlist_service.list_entries(db, professional.id, status="matched")
        assert len(matched_entry) == 1
        assert matched_entry[0].contact_id == waiting_contact.id
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


# ---------------------------------------------------------------------------
# Phase 4 — atomic waitlist fulfillment
# ---------------------------------------------------------------------------

def _make_group_for_fulfillment(
    db, professional_id, place_id, *, occurrence_date, max_participants: int = 2
) -> RecurringSlot:
    group = RecurringSlot(
        professional_id=professional_id,
        place_id=place_id,
        day_of_week=occurrence_date.weekday(),
        start_time=time(10, 0),
        end_time=time(11, 0),
        slot_kind="class",
        class_type="group",
        max_participants=max_participants,
        recurrence_type="weekly",
        valid_from=occurrence_date,
    )
    db.add(group)
    db.commit()
    return group


def test_propose_fulfill_waitlist_with_appointment_creates_and_links_one_appointment() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id, "Ana")
    correlation_id = uuid.uuid4()
    try:
        _give_capacity(db, professional.id, place.id)
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
        )

        result = mutations.propose_fulfill_waitlist_with_appointment(
            db,
            professional.id,
            user.id,
            correlation_id,
            waitlist_entry_id=str(entry.id),
            place_id=str(place.id),
        )
        assert result["requires_confirmation"] is True
        assert "Ana" in result["preview_text"]
        assert "fila de espera" in result["preview_text"].lower()

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        db.refresh(entry)
        assert entry.status == "fulfilled"
        assert entry.fulfilled_appointment_id is not None

        appointment = (
            db.query(Appointment)
            .filter(Appointment.id == entry.fulfilled_appointment_id)
            .one()
        )
        assert appointment.contact_id == contact.id
        assert appointment.place_id == place.id
        assert appointment.source == "assistant"
        assert appointment.class_type == "individual"
        assert (
            db.query(Appointment).filter(Appointment.professional_id == professional.id).count()
            == 1
        )

        event_types = [
            e.event_type
            for e in db.query(OperationalEvent)
            .filter(
                OperationalEvent.operator_action_candidate_id
                == uuid.UUID(result["candidate_id"])
            )
            .all()
        ]
        assert "schedule.appointment.created" in event_types
        assert "waitlist.entry.fulfilled" in event_types
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_propose_fulfill_waitlist_with_appointment_conflict_race_leaves_entry_open() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id, "Ana")
    other = _make_contact(db, professional.id, "Outro Aluno")
    try:
        _give_capacity(db, professional.id, place.id)
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
        )

        result = mutations.propose_fulfill_waitlist_with_appointment(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            waitlist_entry_id=str(entry.id),
            place_id=str(place.id),
        )
        assert result["requires_confirmation"] is True

        booked_start = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        db.add(
            Appointment(
                professional_id=professional.id,
                contact_id=other.id,
                place_id=place.id,
                service="Aula",
                start_at=booked_start,
                end_at=booked_start + timedelta(hours=1),
                status="confirmed",
                source="dashboard",
            )
        )
        db.commit()

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is False

        db.refresh(entry)
        assert entry.status == "open"
        assert entry.fulfilled_appointment_id is None
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_propose_fulfill_waitlist_with_group_occurrence_scope() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id, "Ana")
    try:
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
            class_type="group",
        )
        group = _make_group_for_fulfillment(db, professional.id, place.id, occurrence_date=MONDAY)

        result = mutations.propose_fulfill_waitlist_with_group(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            waitlist_entry_id=str(entry.id),
            recurring_slot_id=str(group.id),
            occurrence_date=MONDAY.isoformat(),
            enrollment_scope="occurrence",
        )
        assert result["requires_confirmation"] is True
        assert "somente" in result["preview_text"].lower()

        assert candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        ).ok is True

        db.refresh(entry)
        assert entry.status == "fulfilled"
        assert entry.fulfilled_recurring_slot_id == group.id
        assert entry.fulfilled_occurrence_date == MONDAY
        assert entry.fulfillment_scope == "occurrence"
        assert (
            db.query(RecurringSlotOccurrenceParticipant)
            .filter(
                RecurringSlotOccurrenceParticipant.recurring_slot_id == group.id,
                RecurringSlotOccurrenceParticipant.contact_id == contact.id,
                RecurringSlotOccurrenceParticipant.occurrence_date == MONDAY,
            )
            .count()
            == 1
        )
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_propose_fulfill_waitlist_with_group_series_scope() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id, "Ana")
    try:
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
            class_type="group",
        )
        group = _make_group_for_fulfillment(db, professional.id, place.id, occurrence_date=MONDAY)

        result = mutations.propose_fulfill_waitlist_with_group(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            waitlist_entry_id=str(entry.id),
            recurring_slot_id=str(group.id),
            occurrence_date=MONDAY.isoformat(),
            enrollment_scope="series",
        )
        assert result["requires_confirmation"] is True
        assert "turma fixa" in result["preview_text"].lower()

        assert candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        ).ok is True

        db.refresh(entry)
        assert entry.status == "fulfilled"
        assert entry.fulfillment_scope == "series"
        assert (
            db.query(RecurringSlotParticipant)
            .filter(
                RecurringSlotParticipant.recurring_slot_id == group.id,
                RecurringSlotParticipant.contact_id == contact.id,
            )
            .count()
            == 1
        )
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_propose_fulfill_waitlist_with_group_capacity_race_leaves_entry_open() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id, "Ana")
    filler = _make_contact(db, professional.id, "Aluno A")
    try:
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
            class_type="group",
        )
        group = _make_group_for_fulfillment(
            db, professional.id, place.id, occurrence_date=MONDAY, max_participants=1
        )

        result = mutations.propose_fulfill_waitlist_with_group(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            waitlist_entry_id=str(entry.id),
            recurring_slot_id=str(group.id),
            occurrence_date=MONDAY.isoformat(),
            enrollment_scope="occurrence",
        )
        assert result["requires_confirmation"] is True

        # The single seat is taken by another participant after the proposal.
        db.add(
            RecurringSlotOccurrenceParticipant(
                professional_id=professional.id,
                recurring_slot_id=group.id,
                contact_id=filler.id,
                occurrence_date=MONDAY,
            )
        )
        db.commit()

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is False

        db.refresh(entry)
        assert entry.status == "open"
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_propose_fulfill_waitlist_rejects_cancelled_entry() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id, "Ana")
    try:
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
        )
        waitlist_service.cancel_entry(db, professional.id, entry.id)

        result = mutations.propose_fulfill_waitlist_with_appointment(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            waitlist_entry_id=str(entry.id),
            place_id=str(place.id),
        )
        assert "error" in result
        assert "not fulfillable" in result["error"]
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_propose_fulfill_waitlist_tools_are_tenant_scoped() -> None:
    db = SessionLocal()
    pro_a, user_a = _make_tenant(db)
    pro_b, user_b = _make_tenant(db)
    try:
        place_a = _make_place(db, pro_a.id)
        contact_a = _make_contact(db, pro_a.id, "Ana")
        entry = waitlist_service.create_entry(
            db,
            pro_a.id,
            contact_id=contact_a.id,
            place_id=place_a.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
        )

        appointment_result = mutations.propose_fulfill_waitlist_with_appointment(
            db,
            pro_b.id,
            user_b.id,
            uuid.uuid4(),
            waitlist_entry_id=str(entry.id),
            place_id=str(place_a.id),
        )
        assert "error" in appointment_result

        group = _make_group_for_fulfillment(db, pro_a.id, place_a.id, occurrence_date=MONDAY)
        group_result = mutations.propose_fulfill_waitlist_with_group(
            db,
            pro_b.id,
            user_b.id,
            uuid.uuid4(),
            waitlist_entry_id=str(entry.id),
            recurring_slot_id=str(group.id),
            occurrence_date=MONDAY.isoformat(),
            enrollment_scope="occurrence",
        )
        assert "error" in group_result
    finally:
        _cleanup(db, professionals=[pro_a, pro_b])
        db.close()


def test_waitlist_fulfillment_confirm_retry_is_idempotent() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id, "Ana")
    try:
        _give_capacity(db, professional.id, place.id)
        entry = waitlist_service.create_entry(
            db,
            professional.id,
            contact_id=contact.id,
            place_id=place.id,
            desired_date=MONDAY,
            desired_start_time=time(10, 0),
            desired_end_time=time(11, 0),
        )
        result = mutations.propose_fulfill_waitlist_with_appointment(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            waitlist_entry_id=str(entry.id),
            place_id=str(place.id),
        )
        assert candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        ).ok is True

        with pytest.raises(candidates.CandidateNotPendingError):
            candidates.confirm(
                db, professional.id, user.id, uuid.UUID(result["candidate_id"])
            )

        assert (
            db.query(Appointment).filter(Appointment.professional_id == professional.id).count()
            == 1
        )
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_waitlist_tool_descriptions_do_not_recommend_cancellation_after_booking() -> None:
    match_spec = next(
        spec
        for spec in tools.TOOL_SPECS
        if spec["function"]["name"] == "find_waitlist_matches"
    )
    description = match_spec["function"]["description"]
    assert "propose_fulfill_waitlist_with_appointment" in description
    assert "propose_fulfill_waitlist_with_group" in description
    assert "cancelled" in description
    assert "propose_create_appointment" not in description

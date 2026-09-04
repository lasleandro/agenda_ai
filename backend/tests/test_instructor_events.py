"""Tests for InstructorEvent — instructor events roadmap v0.1, Phase 1:
service layer (validation, conflict checks), dashboard REST API, and the
GET /api/calendar integration."""

from pathlib import Path
import sys
import uuid
from datetime import date, datetime, time, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import SessionLocal
from app.main import app
from app.agent import candidates, mutations, tools
from app.models import (
    Appointment,
    Contact,
    InstructorEvent,
    OperationalEvent,
    OperatorActionCandidate,
    Place,
    Professional,
    RecurringSlot,
    TenantFeature,
    User,
    WorkJourneyInterval,
)
from app.services import instructor_events as instructor_events_service
from app.services.scheduling import TIMEZONE

client = TestClient(app)

MONDAY = date(2026, 8, 3)  # a known Monday, matches other tests' convention


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().int % 100_000_000:08d}"


def _random_email() -> str:
    return f"events_{uuid.uuid4().hex[:10]}@agenda.ai"


def _make_tenant(db) -> tuple[Professional, User]:
    professional = Professional(name="Tenant Events", assistant_phone=_random_phone())
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


def _make_place(db, professional_id, name: str = "Clube") -> Place:
    place = Place(professional_id=professional_id, name=name, normalized_name=name.casefold())
    db.add(place)
    db.commit()
    return place


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


def _cleanup(db, *, professionals: list[Professional]) -> None:
    professional_ids = [p.id for p in professionals]
    if not professional_ids:
        return
    db.query(TenantFeature).filter(
        TenantFeature.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(OperationalEvent).filter(
        OperationalEvent.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(OperatorActionCandidate).filter(
        OperatorActionCandidate.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(InstructorEvent).filter(
        InstructorEvent.professional_id.in_(professional_ids)
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


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(MONDAY, time(hour, minute), tzinfo=TIMEZONE)


# ---------------------------------------------------------------------------
# Service layer — validation
# ---------------------------------------------------------------------------

def test_create_event_rejects_unknown_event_type() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    try:
        try:
            instructor_events_service.create_event(
                db,
                professional.id,
                event_type="bogus",
                start_at=_dt(15),
                end_at=_dt(20),
            )
            assert False, "expected InstructorEventValidationError"
        except instructor_events_service.InstructorEventValidationError:
            pass
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_create_event_rejects_end_before_start() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    try:
        try:
            instructor_events_service.create_event(
                db,
                professional.id,
                event_type="clinic",
                start_at=_dt(20),
                end_at=_dt(15),
            )
            assert False, "expected InstructorEventValidationError"
        except instructor_events_service.InstructorEventValidationError:
            pass
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_create_event_succeeds_with_income_and_place() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    place = _make_place(db, professional.id)
    try:
        event = instructor_events_service.create_event(
            db,
            professional.id,
            event_type="clinic",
            start_at=_dt(15),
            end_at=_dt(20),
            place_id=place.id,
            title="Clínica de saque",
            income_cents=200000,
        )
        assert event.status == "confirmed"
        assert event.income_cents == 200000
        assert event.place_id == place.id
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


# ---------------------------------------------------------------------------
# Conflict checking
# ---------------------------------------------------------------------------

def test_event_creation_rejects_overlap_with_existing_appointment() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    place = _make_place(db, professional.id)
    contact = _make_contact(db, professional.id)
    try:
        db.add(
            Appointment(
                professional_id=professional.id,
                contact_id=contact.id,
                place_id=place.id,
                service="Aula",
                start_at=_dt(16),
                end_at=_dt(17),
                status="confirmed",
                source="dashboard",
            )
        )
        db.commit()

        try:
            instructor_events_service.create_event(
                db,
                professional.id,
                event_type="tournament_referee",
                start_at=_dt(15),
                end_at=_dt(20),
            )
            assert False, "expected a conflict error"
        except Exception as exc:  # HTTPException
            assert getattr(exc, "status_code", None) == 409
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_appointment_creation_rejects_overlap_with_existing_event() -> None:
    """Symmetric: an existing InstructorEvent must block a class from being
    created on top of it — one shared busy-time set."""
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    place = _make_place(db, professional.id)
    try:
        instructor_events_service.create_event(
            db,
            professional.id,
            event_type="tournament_referee",
            start_at=_dt(15),
            end_at=_dt(20),
        )

        from app.services.appointments import assert_no_conflict

        try:
            assert_no_conflict(db, professional.id, start_at=_dt(16), end_at=_dt(17))
            assert False, "expected a conflict error"
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 409
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_event_creation_ignores_cancelled_events_and_appointments() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    contact = _make_contact(db, professional.id)
    try:
        cancelled_appt = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            service="Aula",
            start_at=_dt(16),
            end_at=_dt(17),
            status="cancelled",
            source="dashboard",
        )
        db.add(cancelled_appt)
        db.commit()

        # Must not raise — a cancelled appointment doesn't occupy the slot.
        event = instructor_events_service.create_event(
            db,
            professional.id,
            event_type="workshop",
            start_at=_dt(15),
            end_at=_dt(20),
        )
        assert event.status == "confirmed"

        # And cancelling that event frees the slot for a new one.
        instructor_events_service.cancel_event(db, professional.id, event.id)
        event2 = instructor_events_service.create_event(
            db,
            professional.id,
            event_type="clinic",
            start_at=_dt(15),
            end_at=_dt(20),
        )
        assert event2.status == "confirmed"
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_event_creation_not_restricted_by_work_journey() -> None:
    """Events remain valid outside usual work preferences."""
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    try:
        db.add(
            WorkJourneyInterval(
                professional_id=professional.id,
                day_of_week=0,  # Monday
                interval_type="work",
                start_time=time(8, 0),
                end_time=time(12, 0),
            )
        )
        db.commit()

        # 15h-20h is outside the configured 8h-12h work journey — a class
        # would be rejected here, but an event must not be.
        event = instructor_events_service.create_event(
            db,
            professional.id,
            event_type="tournament_referee",
            start_at=_dt(15),
            end_at=_dt(20),
        )
        assert event.status == "confirmed"
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_cancel_event_rejects_already_cancelled() -> None:
    db = SessionLocal()
    professional, _ = _make_tenant(db)
    try:
        event = instructor_events_service.create_event(
            db, professional.id, event_type="other", start_at=_dt(15), end_at=_dt(20)
        )
        instructor_events_service.cancel_event(db, professional.id, event.id)
        try:
            instructor_events_service.cancel_event(db, professional.id, event.id)
            assert False, "expected InstructorEventValidationError"
        except instructor_events_service.InstructorEventValidationError:
            pass
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


# ---------------------------------------------------------------------------
# Dashboard REST API
# ---------------------------------------------------------------------------

def test_api_create_list_cancel_and_tenant_isolation() -> None:
    db = SessionLocal()
    pro_a, _, cookies_a = _login_new_tenant(db)
    pro_b, _, cookies_b = _login_new_tenant(db)
    try:
        create_res = client.post(
            "/api/instructor-events",
            json={
                "event_type": "clinic",
                "title": "Clínica de saque",
                "start_at": _dt(15).isoformat(),
                "end_at": _dt(20).isoformat(),
                "income_cents": 200000,
            },
            cookies=cookies_a,
        )
        assert create_res.status_code == 201
        body = create_res.json()
        assert body["status"] == "confirmed"
        assert body["income_cents"] == 200000
        event_id = body["id"]

        list_res_a = client.get("/api/instructor-events", cookies=cookies_a)
        assert list_res_a.status_code == 200
        assert [e["id"] for e in list_res_a.json()["events"]] == [event_id]

        list_res_b = client.get("/api/instructor-events", cookies=cookies_b)
        assert list_res_b.json()["events"] == []

        cross_cancel = client.post(
            f"/api/instructor-events/{event_id}/cancel", cookies=cookies_b
        )
        assert cross_cancel.status_code == 404

        cancel_res = client.post(f"/api/instructor-events/{event_id}/cancel", cookies=cookies_a)
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "cancelled"
    finally:
        _cleanup(db, professionals=[pro_a, pro_b])
        db.close()


def test_api_create_rejects_unknown_place() -> None:
    db = SessionLocal()
    pro, _, cookies = _login_new_tenant(db)
    try:
        res = client.post(
            "/api/instructor-events",
            json={
                "event_type": "workshop",
                "place_id": str(uuid.uuid4()),
                "start_at": _dt(15).isoformat(),
                "end_at": _dt(20).isoformat(),
            },
            cookies=cookies,
        )
        assert res.status_code == 422
    finally:
        _cleanup(db, professionals=[pro])
        db.close()


def test_calendar_endpoint_includes_confirmed_events() -> None:
    db = SessionLocal()
    pro, _, cookies = _login_new_tenant(db)
    try:
        instructor_events_service.create_event(
            db, pro.id, event_type="clinic", start_at=_dt(15), end_at=_dt(20)
        )

        res = client.get(
            f"/api/calendar?start_date={MONDAY.isoformat()}&end_date={MONDAY.isoformat()}",
            cookies=cookies,
        )
        assert res.status_code == 200
        events = res.json()["events"]
        assert len(events) == 1
        assert events[0]["event_type"] == "clinic"
    finally:
        _cleanup(db, professionals=[pro])
        db.close()


# ---------------------------------------------------------------------------
# Phase 2 — revenue summary integration
# ---------------------------------------------------------------------------

def test_revenue_summary_includes_confirmed_event_income() -> None:
    db = SessionLocal()
    professional, owner, cookies, admin = None, None, None, None
    try:
        professional, owner = _make_tenant(db)
        admin = User(
            email=_random_email(),
            hashed_password=hash_password("correct-password"),
            role="platform_admin",
        )
        db.add(admin)
        db.commit()
        db.add(
            TenantFeature(
                professional_id=professional.id,
                feature_key="commercial_financials",
                enabled=True,
                configured_by_user_id=admin.id,
            )
        )
        db.commit()
        login = client.post(
            "/api/auth/login",
            json={"email": owner.email, "password": "correct-password"},
        )
        cookies = login.cookies

        instructor_events_service.create_event(
            db,
            professional.id,
            event_type="clinic",
            start_at=_dt(15),
            end_at=_dt(20),
            income_cents=200000,
        )
        # A cancelled event's income must not count.
        cancelled = instructor_events_service.create_event(
            db,
            professional.id,
            event_type="workshop",
            start_at=_dt(9),
            end_at=_dt(10),
            income_cents=50000,
        )
        instructor_events_service.cancel_event(db, professional.id, cancelled.id)

        res = client.get(
            "/api/financial/revenue/summary",
            params={"date_from": MONDAY.isoformat(), "date_to": MONDAY.isoformat()},
            cookies=cookies,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["event_income_cents"] == 200000
        assert body["event_count"] == 1
    finally:
        if professional is not None:
            _cleanup(db, professionals=[professional])
        if admin is not None:
            db.query(User).filter(User.id == admin.id).delete(synchronize_session=False)
            db.commit()
        db.close()


# ---------------------------------------------------------------------------
# Phase 3 — agent tools
# ---------------------------------------------------------------------------

def test_propose_create_event_full_cycle() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    correlation_id = uuid.uuid4()
    try:
        result = mutations.propose_create_event(
            db,
            professional.id,
            user.id,
            correlation_id,
            event_type="clinic",
            start_at=_dt(15).isoformat(),
            end_at=_dt(20).isoformat(),
            title="Clínica de saque",
            income_cents=200000,
        )
        assert result["requires_confirmation"] is True
        assert "evento" in result["preview_text"].lower()

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        events = instructor_events_service.list_events(db, professional.id)
        assert len(events) == 1
        assert events[0].event_type == "clinic"
        assert events[0].income_cents == 200000
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_propose_create_event_rejects_unknown_event_type() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    correlation_id = uuid.uuid4()
    try:
        result = mutations.propose_create_event(
            db,
            professional.id,
            user.id,
            correlation_id,
            event_type="bogus",
            start_at=_dt(15).isoformat(),
            end_at=_dt(20).isoformat(),
        )
        assert "error" in result
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_propose_create_event_rejects_conflict_with_appointment() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    contact = _make_contact(db, professional.id)
    correlation_id = uuid.uuid4()
    try:
        db.add(
            Appointment(
                professional_id=professional.id,
                contact_id=contact.id,
                service="Aula",
                start_at=_dt(16),
                end_at=_dt(17),
                status="confirmed",
                source="dashboard",
            )
        )
        db.commit()

        result = mutations.propose_create_event(
            db,
            professional.id,
            user.id,
            correlation_id,
            event_type="tournament_referee",
            start_at=_dt(15).isoformat(),
            end_at=_dt(20).isoformat(),
        )
        assert "error" in result
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_list_events_tool_is_tenant_scoped() -> None:
    db = SessionLocal()
    pro_a, _ = _make_tenant(db)
    pro_b, _ = _make_tenant(db)
    try:
        instructor_events_service.create_event(
            db, pro_a.id, event_type="workshop", start_at=_dt(15), end_at=_dt(20)
        )

        result_a = tools.list_events(db, pro_a.id)
        result_b = tools.list_events(db, pro_b.id)

        assert len(result_a["events"]) == 1
        assert result_a["events"][0]["event_type"] == "workshop"
        assert result_b["events"] == []
    finally:
        _cleanup(db, professionals=[pro_a, pro_b])
        db.close()

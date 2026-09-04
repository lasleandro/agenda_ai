"""Tests for the instructor assistant chat API, focused on trusted
confirmation continuity (pt-BR conversational resilience roadmap v0.1,
Phase 2): the browser sends recent candidate IDs and the server resolves
authoritative outcomes/entities without leaking cross-tenant data."""

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
    Contact,
    OperationalEvent,
    OperatorActionCandidate,
    Place,
    Professional,
    RecurringSlot,
    RecurringSlotParticipant,
    RecurringSlotOccurrenceParticipant,
    ScheduleOccurrenceOverride,
    User,
    WaitlistEntry,
    WorkJourneyInterval,
)
from app.services.scheduling import TIMEZONE

client = TestClient(app)


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().int % 100_000_000:08d}"


def _random_email() -> str:
    return f"assistant_api_{uuid.uuid4().hex[:10]}@agenda.ai"


def _make_tenant(db) -> tuple[Professional, User]:
    professional = Professional(name="Tenant Assistant API", assistant_phone=_random_phone())
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


def _make_place(db, professional_id, name: str = "Silva Tennis") -> Place:
    place = Place(professional_id=professional_id, name=name, normalized_name=name.casefold())
    db.add(place)
    db.commit()
    return place


def _executed_group_slot(db, professional, user) -> tuple[uuid.UUID, RecurringSlot]:
    place = _make_place(db, professional.id)
    start = datetime.combine(date(2026, 8, 28), time(18, 0), tzinfo=TIMEZONE)
    result = mutations.propose_create_group_slot(
        db,
        professional.id,
        user.id,
        uuid.uuid4(),
        place_id=str(place.id),
        start_at=start.isoformat(),
        end_at=(start + timedelta(hours=1)).isoformat(),
        is_recurring=True,
        max_participants=4,
    )
    candidate_id = uuid.UUID(result["candidate_id"])
    assert candidates.confirm(db, professional.id, user.id, candidate_id).ok is True
    slot = db.query(RecurringSlot).filter(RecurringSlot.professional_id == professional.id).one()
    return candidate_id, slot


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


def _patch_run_agent_turn(monkeypatch, captured):
    import app.api.assistant as assistant_api
    from app.agent.orchestrator import AgentResponse

    def _fake_run_agent_turn(
        db, professional_id, actor_user_id, messages, channel="web", recent_action_context=None
    ):
        captured.append(recent_action_context)
        return AgentResponse(reply="ok")

    monkeypatch.setattr(assistant_api, "run_agent_turn", _fake_run_agent_turn)


def test_messages_passes_resolved_recent_action_context(monkeypatch) -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        candidate_id, slot = _executed_group_slot(db, professional, user)

        captured: list = []
        _patch_run_agent_turn(monkeypatch, captured)

        response = client.post(
            "/api/assistant/messages",
            json={
                "messages": [{"role": "user", "content": "agora põe a Fernanda nessa turma"}],
                "recent_candidate_ids": [str(candidate_id)],
            },
            cookies=cookies,
        )
        assert response.status_code == 200
        assert len(captured) == 1
        contexts = captured[0]
        assert len(contexts) == 1
        context = contexts[0]
        assert context.status == "executed"
        assert context.tool_name == "propose_create_group_slot"
        assert context.entities == [
            {"entity_type": "recurring_slot", "entity_id": str(slot.id)}
        ]
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_messages_ignores_cross_tenant_candidate_id(monkeypatch) -> None:
    db = SessionLocal()
    professional_a, _, cookies_a = _login_new_tenant(db)
    professional_b, user_b, _ = _login_new_tenant(db)
    try:
        candidate_b, _ = _executed_group_slot(db, professional_b, user_b)

        captured: list = []
        _patch_run_agent_turn(monkeypatch, captured)

        response = client.post(
            "/api/assistant/messages",
            json={
                "messages": [{"role": "user", "content": "continua"}],
                "recent_candidate_ids": [str(candidate_b)],
            },
            cookies=cookies_a,
        )
        assert response.status_code == 200
        assert captured[0] == []
    finally:
        _cleanup(db, professionals=[professional_a, professional_b])
        db.close()


def test_messages_rejected_candidate_has_no_entities(monkeypatch) -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place = _make_place(db, professional.id)
        start = datetime.combine(date(2026, 8, 28), time(18, 0), tzinfo=TIMEZONE)
        result = mutations.propose_create_group_slot(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            place_id=str(place.id),
            start_at=start.isoformat(),
            end_at=(start + timedelta(hours=1)).isoformat(),
            is_recurring=True,
            max_participants=4,
        )
        candidate_id = uuid.UUID(result["candidate_id"])
        candidates.reject(db, professional.id, user.id, candidate_id)

        captured: list = []
        _patch_run_agent_turn(monkeypatch, captured)

        response = client.post(
            "/api/assistant/messages",
            json={
                "messages": [{"role": "user", "content": "ok, deixa pra lá"}],
                "recent_candidate_ids": [str(candidate_id)],
            },
            cookies=cookies,
        )
        assert response.status_code == 200
        assert len(captured[0]) == 1
        context = captured[0][0]
        assert context.status == "rejected"
        assert context.entities == []
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_messages_ignores_stale_candidate_id(monkeypatch) -> None:
    db = SessionLocal()
    professional, _, cookies = _login_new_tenant(db)
    try:
        captured: list = []
        _patch_run_agent_turn(monkeypatch, captured)

        response = client.post(
            "/api/assistant/messages",
            json={
                "messages": [{"role": "user", "content": "continua"}],
                "recent_candidate_ids": [str(uuid.uuid4())],
            },
            cookies=cookies,
        )
        assert response.status_code == 200
        assert captured[0] == []
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_messages_rejects_more_than_five_candidate_ids(monkeypatch) -> None:
    db = SessionLocal()
    professional, _, cookies = _login_new_tenant(db)
    try:
        captured: list = []
        _patch_run_agent_turn(monkeypatch, captured)

        response = client.post(
            "/api/assistant/messages",
            json={
                "messages": [{"role": "user", "content": "continua"}],
                "recent_candidate_ids": [str(uuid.uuid4()) for _ in range(6)],
            },
            cookies=cookies,
        )
        assert response.status_code == 422
        assert captured == []
    finally:
        _cleanup(db, professionals=[professional])
        db.close()

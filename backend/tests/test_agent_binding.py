"""Unit/integration coverage for the agent-channel binding handshake."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import AgentBindingChallenge, OperationalEvent, Professional, User
from app.services import agent_binding

PLATFORM_NUMBER = "+5511970000000"


@pytest.fixture(autouse=True)
def _platform_agent_number(monkeypatch):
    monkeypatch.setenv("PLATFORM_AGENT_WHATSAPP_NUMBER", PLATFORM_NUMBER)


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().int % 100_000_000:08d}"


def _setup(db):
    professional = Professional(name="Bind", assistant_phone=_random_phone())
    db.add(professional)
    db.flush()
    user = User(
        professional_id=professional.id,
        email=f"{uuid.uuid4().hex}@example.test",
        hashed_password="x",
        role="professional",
    )
    db.add(user)
    db.commit()
    return professional, user


def _cleanup(db, professional_id):
    db.query(AgentBindingChallenge).filter_by(professional_id=professional_id).delete()
    db.query(OperationalEvent).filter_by(professional_id=professional_id).delete()
    db.query(User).filter_by(professional_id=professional_id).delete()
    db.query(Professional).filter_by(id=professional_id).delete()
    db.commit()


def test_issue_challenge_rotates_pending_code() -> None:
    db = SessionLocal()
    professional, _ = _setup(db)
    try:
        first = agent_binding.issue_challenge(db, professional.id)
        second = agent_binding.issue_challenge(db, professional.id)
        assert first.code != second.code
        assert first.platform_number == PLATFORM_NUMBER
        pending = db.query(AgentBindingChallenge).filter_by(
            professional_id=professional.id, consumed_at=None
        ).all()
        assert len(pending) == 1
    finally:
        _cleanup(db, professional.id)
        db.close()


def test_confirm_from_message_binds_and_audits() -> None:
    db = SessionLocal()
    professional, user = _setup(db)
    try:
        issued = agent_binding.issue_challenge(db, professional.id)
        ok = agent_binding.confirm_from_message(
            db, professional, user.id, f"quero ativar {issued.code}"
        )
        assert ok is True
        db.refresh(professional)
        assert professional.agent_binding_confirmed_at is not None
        assert professional.agent_binding_confirmed_by == user.id
        assert (
            db.query(OperationalEvent)
            .filter_by(
                professional_id=professional.id, event_type="agent.binding.confirmed"
            )
            .count()
            == 1
        )
        # single-use
        assert (
            agent_binding.confirm_from_message(
                db, professional, user.id, issued.code
            )
            is False
        )
    finally:
        _cleanup(db, professional.id)
        db.close()


def test_confirm_from_message_rejects_wrong_and_expired_codes() -> None:
    db = SessionLocal()
    professional, user = _setup(db)
    try:
        agent_binding.issue_challenge(db, professional.id)
        assert (
            agent_binding.confirm_from_message(
                db, professional, user.id, "ATIVAR-000000"
            )
            is False
        )
        # expire the live one
        db.query(AgentBindingChallenge).filter_by(
            professional_id=professional.id
        ).update({"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)})
        db.commit()
        issued = agent_binding.issue_challenge(db, professional.id)
        db.query(AgentBindingChallenge).filter_by(
            professional_id=professional.id, consumed_at=None
        ).update({"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
        db.commit()
        assert (
            agent_binding.confirm_from_message(db, professional, user.id, issued.code)
            is False
        )
        db.refresh(professional)
        assert professional.agent_binding_confirmed_at is None
    finally:
        _cleanup(db, professional.id)
        db.close()


def test_confirm_from_message_ignores_a_message_with_no_code() -> None:
    db = SessionLocal()
    professional, user = _setup(db)
    try:
        agent_binding.issue_challenge(db, professional.id)
        assert (
            agent_binding.confirm_from_message(db, professional, user.id, "bom dia")
            is False
        )
    finally:
        _cleanup(db, professional.id)
        db.close()


def test_revoke_clears_binding_and_pending_challenges() -> None:
    db = SessionLocal()
    professional, user = _setup(db)
    try:
        issued = agent_binding.issue_challenge(db, professional.id)
        agent_binding.confirm_from_message(db, professional, user.id, issued.code)
        agent_binding.issue_challenge(db, professional.id)

        cleared = agent_binding.revoke(
            db,
            professional.id,
            actor_user_id=user.id,
            actor_type="user",
            source_channel="web",
        )
        assert cleared is True
        db.refresh(professional)
        assert professional.agent_binding_confirmed_at is None
        assert (
            db.query(AgentBindingChallenge)
            .filter_by(professional_id=professional.id, consumed_at=None)
            .count()
            == 0
        )
        assert (
            db.query(OperationalEvent)
            .filter_by(
                professional_id=professional.id, event_type="agent.binding.revoked"
            )
            .count()
            == 1
        )
        # idempotent
        assert (
            agent_binding.revoke(
                db,
                professional.id,
                actor_user_id=user.id,
                actor_type="user",
                source_channel="web",
            )
            is False
        )
    finally:
        _cleanup(db, professional.id)
        db.close()


def test_issue_challenge_requires_configured_platform_number(monkeypatch) -> None:
    monkeypatch.delenv("PLATFORM_AGENT_WHATSAPP_NUMBER", raising=False)
    db = SessionLocal()
    professional, _ = _setup(db)
    try:
        with pytest.raises(agent_binding.AgentBindingUnavailableError):
            agent_binding.issue_challenge(db, professional.id)
    finally:
        _cleanup(db, professional.id)
        db.close()

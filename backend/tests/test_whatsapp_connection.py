"""Integration tests for the manual WhatsApp connection request endpoint."""

from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import SessionLocal
from app.integrations.email.contracts import EmailRetryableError
from app.main import app
from app.models import Professional, TenantFeature, TenantFeatureAuditLog, User

client = TestClient(app)


def _random_email() -> str:
    return f"test_{uuid.uuid4().hex[:10]}@agenda.ai"


def _create_professional(db) -> Professional:
    professional = Professional(name="Test Tenant", assistant_phone=f"+55119{uuid.uuid4().hex[:8]}")
    db.add(professional)
    db.commit()
    return professional


def _create_user(db, professional_id, password: str = "correct-password") -> User:
    user = User(
        email=_random_email(),
        hashed_password=hash_password(password),
        role="professional",
        professional_id=professional_id,
    )
    db.add(user)
    db.commit()
    return user


def _login(user: User, password: str = "correct-password"):
    res = client.post("/api/auth/login", json={"email": user.email, "password": password})
    assert res.status_code == 200
    return res.cookies


def _cleanup(db, *, users=(), professionals=()):
    user_ids = [u.id for u in users]
    professional_ids = [p.id for p in professionals]
    if user_ids:
        db.query(TenantFeatureAuditLog).filter(
            TenantFeatureAuditLog.admin_user_id.in_(user_ids)
        ).delete(synchronize_session=False)
    if professional_ids:
        db.query(TenantFeatureAuditLog).filter(
            TenantFeatureAuditLog.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(TenantFeature).filter(
            TenantFeature.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    if professional_ids:
        db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    db.commit()


def test_connection_request_requires_authentication() -> None:
    res = client.get("/api/whatsapp/connection-request")
    assert res.status_code == 401

    res = client.post("/api/whatsapp/connection-request")
    assert res.status_code == 401


def test_first_request_sends_notification_and_persists_flag() -> None:
    db = SessionLocal()
    professional = _create_professional(db)
    user = _create_user(db, professional.id)
    try:
        cookies = _login(user)

        initial = client.get("/api/whatsapp/connection-request", cookies=cookies)
        assert initial.status_code == 200
        assert initial.json()["requested"] is False

        res = client.post("/api/whatsapp/connection-request", cookies=cookies)
        assert res.status_code == 200
        assert res.json()["requested"] is True

        feature = (
            db.query(TenantFeature)
            .filter(
                TenantFeature.professional_id == professional.id,
                TenantFeature.feature_key == "whatsapp_connection_requested",
            )
            .first()
        )
        assert feature is not None
        assert feature.enabled is True

        follow_up = client.get("/api/whatsapp/connection-request", cookies=cookies)
        assert follow_up.json()["requested"] is True
    finally:
        _cleanup(db, users=[user], professionals=[professional])
        db.close()


def test_repeated_request_is_idempotent() -> None:
    db = SessionLocal()
    professional = _create_professional(db)
    user = _create_user(db, professional.id)
    try:
        cookies = _login(user)

        first = client.post("/api/whatsapp/connection-request", cookies=cookies)
        assert first.status_code == 200

        audit_count_before = (
            db.query(TenantFeatureAuditLog)
            .filter(TenantFeatureAuditLog.professional_id == professional.id)
            .count()
        )

        second = client.post("/api/whatsapp/connection-request", cookies=cookies)
        assert second.status_code == 200
        assert second.json()["requested"] is True

        audit_count_after = (
            db.query(TenantFeatureAuditLog)
            .filter(TenantFeatureAuditLog.professional_id == professional.id)
            .count()
        )
        assert audit_count_after == audit_count_before
    finally:
        _cleanup(db, users=[user], professionals=[professional])
        db.close()


def test_failed_notification_does_not_persist_flag(monkeypatch) -> None:
    def _raise(self, message) -> None:
        raise EmailRetryableError("SMTPConnectError")

    monkeypatch.setattr("app.api.whatsapp_connection.SmtpEmailSender.send", _raise)

    db = SessionLocal()
    professional = _create_professional(db)
    user = _create_user(db, professional.id)
    try:
        cookies = _login(user)

        res = client.post("/api/whatsapp/connection-request", cookies=cookies)
        assert res.status_code == 502
        assert res.json()["error"]["code"] == "WHATSAPP_CONNECTION_REQUEST_FAILED"

        feature = (
            db.query(TenantFeature)
            .filter(
                TenantFeature.professional_id == professional.id,
                TenantFeature.feature_key == "whatsapp_connection_requested",
            )
            .first()
        )
        assert feature is None
    finally:
        _cleanup(db, users=[user], professionals=[professional])
        db.close()

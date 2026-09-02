"""Integration coverage for activation, reset, and durable mail delivery."""

import re
import sys
import uuid
from pathlib import Path

import bcrypt
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.security import SESSION_COOKIE_NAME, hash_password
from app.database import SessionLocal
from app.main import app
from app.models import AuthActionToken, EmailDelivery, User
from app.services.auth_emails import enqueue_auth_email, process_due_email_deliveries
from app.services.auth_tokens import issue_action_token

client = TestClient(app)


class FakeEmailSender:
    """Captures rendered messages without invoking SMTP."""

    enabled = True

    def __init__(self) -> None:
        self.messages = []

    def send(self, message) -> None:
        self.messages.append(message)


def _email() -> str:
    return f"auth_{uuid.uuid4().hex[:12]}@agenda.ai"


def _token_from(message) -> str:
    match = re.search(r"token=([A-Za-z0-9_-]+)", message.html_body)
    assert match
    return match.group(1)


def _cleanup(db, user: User) -> None:
    db.query(EmailDelivery).filter(EmailDelivery.user_id == user.id).delete(synchronize_session=False)
    db.query(AuthActionToken).filter(AuthActionToken.user_id == user.id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.commit()


def test_activation_email_token_activates_user_and_rejects_weak_password() -> None:
    db = SessionLocal()
    user = User(email=_email(), hashed_password=None, role="platform_admin", status="pending_activation")
    db.add(user)
    db.commit()
    sender = FakeEmailSender()
    try:
        enqueue_auth_email(db, user=user, purpose="account_activation")
        db.commit()
        assert process_due_email_deliveries(db, sender=sender) == 1
        assert len(sender.messages) == 1
        token = _token_from(sender.messages[0])

        weak = client.post(
            "/api/auth/activate",
            json={"token": token, "password": "short", "password_confirmation": "short"},
        )
        assert weak.status_code == 400
        assert weak.json()["error"]["code"] == "PASSWORD_TOO_SHORT"

        activated = client.post(
            "/api/auth/activate",
            json={
                "token": token,
                "password": "Minha frase longa e segura 2026",
                "password_confirmation": "Minha frase longa e segura 2026",
            },
        )
        assert activated.status_code == 200
        db.refresh(user)
        assert user.status == "active"
        assert user.email_verified_at is not None

        reused = client.post(
            "/api/auth/activate",
            json={
                "token": token,
                "password": "Outra frase longa e segura 2026",
                "password_confirmation": "Outra frase longa e segura 2026",
            },
        )
        assert reused.status_code == 400
        assert reused.json()["error"]["code"] == "TOKEN_INVALID_OR_EXPIRED"
    finally:
        _cleanup(db, user)
        db.close()


def test_reset_email_invalidates_existing_session_and_does_not_enumerate_users(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_EMAIL_MAX_SENDS_PER_HOUR", "1000")
    db = SessionLocal()
    user = User(
        email=_email(),
        hashed_password=hash_password("Minha frase longa e segura 2026"),
        role="platform_admin",
        status="active",
    )
    db.add(user)
    db.commit()
    sender = FakeEmailSender()
    try:
        signed_in = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "Minha frase longa e segura 2026"},
        )
        assert signed_in.status_code == 200
        session_cookie = signed_in.cookies[SESSION_COOKIE_NAME]

        known = client.post("/api/auth/forgot-password", json={"email": user.email})
        unknown = client.post("/api/auth/forgot-password", json={"email": _email()})
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()

        assert process_due_email_deliveries(db, sender=sender) == 1
        token = _token_from(sender.messages[0])
        reset = client.post(
            "/api/auth/reset-password",
            json={
                "token": token,
                "password": "Outra frase longa e segura 2026",
                "password_confirmation": "Outra frase longa e segura 2026",
            },
        )
        assert reset.status_code == 200

        old_session = client.get("/api/auth/me", cookies={SESSION_COOKIE_NAME: session_cookie})
        assert old_session.status_code == 401

        changed_login = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "Outra frase longa e segura 2026"},
        )
        assert changed_login.status_code == 200
        assert (
            db.query(EmailDelivery)
            .filter(
                EmailDelivery.user_id == user.id,
                EmailDelivery.purpose == "password_changed_notice",
            )
            .count()
            == 1
        )
    finally:
        _cleanup(db, user)
        db.close()


def test_successful_legacy_bcrypt_login_rehashes_to_argon2id() -> None:
    db = SessionLocal()
    password = "Minha frase longa e segura 2026"
    user = User(
        email=_email(),
        hashed_password=bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        role="platform_admin",
        status="active",
    )
    db.add(user)
    db.commit()
    try:
        response = client.post("/api/auth/login", json={"email": user.email, "password": password})
        assert response.status_code == 200
        db.refresh(user)
        assert user.hashed_password is not None
        assert user.hashed_password.startswith("$argon2id$")
    finally:
        _cleanup(db, user)
        db.close()


def test_reset_tokens_are_superseded_before_they_can_be_consumed() -> None:
    db = SessionLocal()
    user = User(
        email=_email(),
        hashed_password=hash_password("Minha frase longa e segura 2026"),
        role="platform_admin",
        status="active",
    )
    db.add(user)
    db.commit()
    try:
        first_token = issue_action_token(db, user=user, purpose="password_reset")
        latest_token = issue_action_token(db, user=user, purpose="password_reset")
        db.commit()

        expired_by_reissue = client.post(
            "/api/auth/reset-password",
            json={
                "token": first_token,
                "password": "Outra frase longa e segura 2026",
                "password_confirmation": "Outra frase longa e segura 2026",
            },
        )
        assert expired_by_reissue.status_code == 400
        assert expired_by_reissue.json()["error"]["code"] == "TOKEN_INVALID_OR_EXPIRED"

        latest = client.post(
            "/api/auth/reset-password",
            json={
                "token": latest_token,
                "password": "Outra frase longa e segura 2026",
                "password_confirmation": "Outra frase longa e segura 2026",
            },
        )
        assert latest.status_code == 200
    finally:
        _cleanup(db, user)
        db.close()

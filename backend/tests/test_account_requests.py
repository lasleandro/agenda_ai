"""Public account-request and platform-admin onboarding contracts."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import (
    AccountAccessRequest,
    AuthActionToken,
    AuthSecurityEvent,
    EmailDelivery,
    OperationalEvent,
    Professional,
    User,
)
from app.services.account_requests import purge_rejected_account_requests
from app.services.auth_security import digest_identifier

client = TestClient(app)
PASSWORD = "Minha frase longa e segura 2026"


def _email(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}@agenda.ai"


def _admin(db) -> User:
    admin = User(
        email=_email("request_admin"),
        hashed_password=hash_password(PASSWORD),
        role="platform_admin",
        status="active",
    )
    db.add(admin)
    db.commit()
    return admin


def _professional_user(db) -> tuple[Professional, User]:
    professional = Professional(name=f"Tenant {uuid.uuid4().hex[:8]}")
    db.add(professional)
    db.flush()
    user = User(
        email=_email("request_professional"),
        hashed_password=hash_password(PASSWORD),
        role="professional",
        professional_id=professional.id,
        status="active",
    )
    db.add(user)
    db.commit()
    return professional, user


def _cookies(user: User):
    response = client.post(
        "/api/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert response.status_code == 200
    return response.cookies


def _submit(
    email: str,
    *,
    name: str = "João Silva",
    whatsapp: str = "11987654321",
    message: str | None = None,
):
    return client.post(
        "/api/account-requests",
        json={
            "proposed_tenant_name": name,
            "email": email,
            "whatsapp": whatsapp,
            "message": message,
        },
    )


def _cleanup(db, *, emails: list[str], user_ids: list[uuid.UUID] | None = None) -> None:
    requests = db.query(AccountAccessRequest).filter(
        AccountAccessRequest.email.in_(emails)
    ).all()
    request_user_ids = [row.owner_user_id for row in requests if row.owner_user_id]
    professional_ids = [row.professional_id for row in requests if row.professional_id]
    db.query(AccountAccessRequest).filter(AccountAccessRequest.email.in_(emails)).delete(
        synchronize_session=False
    )
    all_user_ids = list(dict.fromkeys((user_ids or []) + request_user_ids))
    if all_user_ids:
        db.query(AuthActionToken).filter(AuthActionToken.user_id.in_(all_user_ids)).delete(
            synchronize_session=False
        )
        db.query(EmailDelivery).filter(EmailDelivery.user_id.in_(all_user_ids)).delete(
            synchronize_session=False
        )
        db.query(AuthSecurityEvent).filter(
            AuthSecurityEvent.user_id.in_(all_user_ids)
        ).delete(synchronize_session=False)
    for email in emails:
        db.query(AuthSecurityEvent).filter(
            AuthSecurityEvent.email_digest == digest_identifier(email)
        ).delete(synchronize_session=False)
    if professional_ids:
        db.query(OperationalEvent).filter(
            OperationalEvent.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
    if all_user_ids:
        db.query(User).filter(User.id.in_(all_user_ids)).delete(synchronize_session=False)
    if professional_ids:
        db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    db.commit()


def test_submit_account_request_persists_normalized_pending_request(monkeypatch) -> None:
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY", "1000")
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR", "1000")
    db = SessionLocal()
    email = _email("public_request")
    try:
        response = _submit(
            f"  {email.upper()}  ",
            name="  João Silva Tennis  ",
            whatsapp="(11) 98765-4321",
            message="  Quero conhecer a plataforma.  ",
        )
        assert response.status_code == 202
        row = db.query(AccountAccessRequest).filter_by(email=email).one()
        assert row.proposed_tenant_name == "João Silva Tennis"
        assert row.whatsapp == "+5511987654321"
        assert row.message == "Quero conhecer a plataforma."
        assert row.status == "pending"
        assert row.reviewed_at is None
    finally:
        _cleanup(db, emails=[email])
        db.close()


def test_submit_account_request_is_generic_for_duplicate_and_existing_user(monkeypatch) -> None:
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY", "1000")
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR", "1000")
    db = SessionLocal()
    requested_email = _email("duplicate_request")
    existing_email = _email("existing_request")
    existing = User(
        email=existing_email,
        hashed_password=hash_password(PASSWORD),
        role="platform_admin",
        status="active",
    )
    db.add(existing)
    db.commit()
    try:
        created = _submit(requested_email)
        duplicate = _submit(requested_email, name="Attempted replacement")
        owned = _submit(existing_email)
        assert created.status_code == duplicate.status_code == owned.status_code == 202
        assert created.json() == duplicate.json() == owned.json()
        assert (
            db.query(AccountAccessRequest).filter_by(email=requested_email).count() == 1
        )
        assert db.query(AccountAccessRequest).filter_by(email=existing_email).count() == 0
        row = db.query(AccountAccessRequest).filter_by(email=requested_email).one()
        assert row.proposed_tenant_name == "João Silva"
    finally:
        _cleanup(db, emails=[requested_email, existing_email], user_ids=[existing.id])
        db.close()


def test_admin_request_list_and_summary_require_platform_admin(monkeypatch) -> None:
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY", "1000")
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR", "1000")
    db = SessionLocal()
    email = _email("listed_request")
    admin = _admin(db)
    professional, professional_user = _professional_user(db)
    try:
        assert _submit(email).status_code == 202
        unauthenticated = client.get("/api/admin/account-requests")
        forbidden = client.get(
            "/api/admin/account-requests", cookies=_cookies(professional_user)
        )
        listed = client.get(
            "/api/admin/account-requests?status=pending&page=1&page_size=10",
            cookies=_cookies(admin),
        )
        summary = client.get(
            "/api/admin/account-requests/summary", cookies=_cookies(admin)
        )
        assert unauthenticated.status_code == 401
        assert forbidden.status_code == 403
        assert listed.status_code == summary.status_code == 200
        assert any(item["email"] == email for item in listed.json()["requests"])
        assert listed.json()["status_counts"]["pending"] >= 1
        assert summary.json()["pending"] >= 1
    finally:
        _cleanup(
            db,
            emails=[email, admin.email, professional_user.email],
            user_ids=[admin.id, professional_user.id],
        )
        db.query(Professional).filter(Professional.id == professional.id).delete()
        db.commit()
        db.close()


def test_approve_request_atomically_creates_tenant_owner_and_activation(monkeypatch) -> None:
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY", "1000")
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR", "1000")
    monkeypatch.setenv("ACCOUNT_REQUEST_APPROVAL_MAX_PER_ADMIN_PER_HOUR", "1000")
    db = SessionLocal()
    email = _email("approved_request")
    admin = _admin(db)
    try:
        assert _submit(email).status_code == 202
        request_row = db.query(AccountAccessRequest).filter_by(email=email).one()
        response = client.post(
            f"/api/admin/account-requests/{request_row.id}/approve",
            json={"tenant_name": "  Approved Tennis  ", "whatsapp": "11987654321", "timezone": "America/Sao_Paulo"},
            cookies=_cookies(admin),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["request"]["status"] == "approved"
        assert body["tenant"]["name"] == "Approved Tennis"

        db.expire_all()
        request_row = db.get(AccountAccessRequest, request_row.id)
        assert request_row is not None
        assert request_row.reviewed_by_user_id == admin.id
        assert request_row.professional_id is not None
        assert request_row.owner_user_id is not None
        owner = db.get(User, request_row.owner_user_id)
        assert owner is not None
        assert owner.email == email
        assert owner.status == "pending_activation"
        assert owner.professional_id == request_row.professional_id
        assert (
            db.get(Professional, request_row.professional_id).assistant_phone
            == "+5511987654321"
        )
        assert db.query(EmailDelivery).filter_by(
            user_id=owner.id, purpose="account_activation", status="queued"
        ).count() == 1
        event = db.query(OperationalEvent).filter_by(
            professional_id=request_row.professional_id, event_type="tenant.created"
        ).one()
        assert "source_ip" not in event.payload
        assert event.payload["source"] == "account_request_approval"
        assert event.payload["account_request_id"] == str(request_row.id)

        repeated = client.post(
            f"/api/admin/account-requests/{request_row.id}/approve",
            json={"tenant_name": "Ignored retry", "whatsapp": "11999999999", "timezone": "America/Bahia"},
            cookies=_cookies(admin),
        )
        assert repeated.status_code == 200
        assert repeated.json()["tenant"]["id"] == body["tenant"]["id"]
        assert db.query(User).filter_by(email=email).count() == 1
    finally:
        _cleanup(db, emails=[email, admin.email], user_ids=[admin.id])
        db.close()


def test_reject_request_records_decision_without_provisioning(monkeypatch) -> None:
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY", "1000")
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR", "1000")
    db = SessionLocal()
    email = _email("rejected_request")
    admin = _admin(db)
    try:
        assert _submit(email).status_code == 202
        request_row = db.query(AccountAccessRequest).filter_by(email=email).one()
        response = client.post(
            f"/api/admin/account-requests/{request_row.id}/reject",
            json={"reason": "  Fora do piloto.  "},
            cookies=_cookies(admin),
        )
        assert response.status_code == 200
        assert response.json()["request"]["status"] == "rejected"
        assert response.json()["request"]["decision_reason"] == "Fora do piloto."
        db.expire_all()
        request_row = db.get(AccountAccessRequest, request_row.id)
        assert request_row is not None
        assert request_row.reviewed_by_user_id == admin.id
        assert request_row.professional_id is None
        assert db.query(User).filter_by(email=email).count() == 0

        repeated = client.post(
            f"/api/admin/account-requests/{request_row.id}/reject",
            json={"reason": "Do not overwrite"},
            cookies=_cookies(admin),
        )
        assert repeated.status_code == 200
        assert repeated.json()["request"]["decision_reason"] == "Fora do piloto."
    finally:
        _cleanup(db, emails=[email, admin.email], user_ids=[admin.id])
        db.close()


def test_activation_resend_requeues_failed_delivery(monkeypatch) -> None:
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY", "1000")
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR", "1000")
    monkeypatch.setenv("ACCOUNT_REQUEST_APPROVAL_MAX_PER_ADMIN_PER_HOUR", "1000")
    monkeypatch.setenv("AUTH_EMAIL_MAX_SENDS_PER_HOUR", "1000")
    monkeypatch.setenv("ACCOUNT_ACTIVATION_RESEND_COOLDOWN_SECONDS", "1")
    db = SessionLocal()
    email = _email("resend_request")
    admin = _admin(db)
    try:
        assert _submit(email).status_code == 202
        request_row = db.query(AccountAccessRequest).filter_by(email=email).one()
        approved = client.post(
            f"/api/admin/account-requests/{request_row.id}/approve",
            json={"tenant_name": "Resend Tenant", "whatsapp": "11987654321", "timezone": "America/Sao_Paulo"},
            cookies=_cookies(admin),
        )
        assert approved.status_code == 200
        db.expire_all()
        request_row = db.get(AccountAccessRequest, request_row.id)
        assert request_row is not None and request_row.owner_user_id is not None
        delivery = db.query(EmailDelivery).filter_by(
            user_id=request_row.owner_user_id, purpose="account_activation"
        ).one()
        delivery.status = "failed"
        delivery.updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        db.commit()

        resent = client.post(
            f"/api/admin/account-requests/{request_row.id}/resend-activation",
            cookies=_cookies(admin),
        )
        assert resent.status_code == 200
        assert resent.json()["activation_state"] == "queued"
        assert db.query(EmailDelivery).filter_by(
            user_id=request_row.owner_user_id, purpose="account_activation"
        ).count() == 2
    finally:
        _cleanup(db, emails=[email, admin.email], user_ids=[admin.id])
        db.close()


def test_submit_account_request_enforces_per_email_limit_at_the_boundary(monkeypatch) -> None:
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY", "2")
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR", "1000")
    db = SessionLocal()
    email = _email("limited_request")
    try:
        assert _submit(email).status_code == 202
        # A repeat pending submission is generic 202 and adds no row, but it
        # still records a rate-limit event, so the third attempt is the
        # boundary crossing.
        assert _submit(email).status_code == 202
        blocked = _submit(email)
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "RATE_LIMITED"
        assert db.query(AccountAccessRequest).filter_by(email=email).count() == 1
    finally:
        _cleanup(db, emails=[email])
        db.close()


def test_submit_account_request_rejects_malformed_email(monkeypatch) -> None:
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY", "1000")
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR", "1000")
    db = SessionLocal()
    try:
        response = _submit("not-an-email", name="Nome Válido")
        assert response.status_code == 422
        assert db.query(AccountAccessRequest).filter_by(email="not-an-email").count() == 0
    finally:
        db.close()


def test_submit_account_request_rejects_invalid_whatsapp(monkeypatch) -> None:
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY", "1000")
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR", "1000")
    db = SessionLocal()
    email = _email("bad_whatsapp")
    try:
        response = _submit(email, whatsapp="12345")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_PHONE"
        assert db.query(AccountAccessRequest).filter_by(email=email).count() == 0
    finally:
        _cleanup(db, emails=[email])
        db.close()


def test_previously_rejected_email_can_submit_a_fresh_request(monkeypatch) -> None:
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY", "1000")
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR", "1000")
    db = SessionLocal()
    email = _email("re_request")
    admin = _admin(db)
    try:
        assert _submit(email).status_code == 202
        first = db.query(AccountAccessRequest).filter_by(email=email).one()
        assert (
            client.post(
                f"/api/admin/account-requests/{first.id}/reject",
                json={"reason": "piloto"},
                cookies=_cookies(admin),
            ).status_code
            == 200
        )
        assert _submit(email, name="Segunda tentativa").status_code == 202
        db.expire_all()
        rows = db.query(AccountAccessRequest).filter_by(email=email).all()
        statuses = sorted(row.status for row in rows)
        assert statuses == ["pending", "rejected"]
    finally:
        _cleanup(db, emails=[email, admin.email], user_ids=[admin.id])
        db.close()


def test_terminal_decision_cannot_be_overwritten_by_the_other_action(monkeypatch) -> None:
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY", "1000")
    monkeypatch.setenv("ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR", "1000")
    monkeypatch.setenv("ACCOUNT_REQUEST_APPROVAL_MAX_PER_ADMIN_PER_HOUR", "1000")
    db = SessionLocal()
    email = _email("race_request")
    admin = _admin(db)
    try:
        assert _submit(email).status_code == 202
        request_row = db.query(AccountAccessRequest).filter_by(email=email).one()
        approved = client.post(
            f"/api/admin/account-requests/{request_row.id}/approve",
            json={"tenant_name": "Race Tenant", "whatsapp": "11987654321", "timezone": "America/Sao_Paulo"},
            cookies=_cookies(admin),
        )
        assert approved.status_code == 200
        conflict = client.post(
            f"/api/admin/account-requests/{request_row.id}/reject",
            json={"reason": "too late"},
            cookies=_cookies(admin),
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "ACCOUNT_REQUEST_ALREADY_DECIDED"
        db.expire_all()
        assert db.get(AccountAccessRequest, request_row.id).status == "approved"
    finally:
        _cleanup(db, emails=[email, admin.email], user_ids=[admin.id])
        db.close()


def test_purge_rejected_account_requests_removes_only_expired_rejected() -> None:
    db = SessionLocal()
    old_email = _email("old_rejected")
    fresh_email = _email("fresh_rejected")
    admin = _admin(db)
    now = datetime.now(timezone.utc)
    old = AccountAccessRequest(
        proposed_tenant_name="Old",
        email=old_email,
        status="rejected",
        reviewed_at=now - timedelta(days=181),
        reviewed_by_user_id=admin.id,
    )
    fresh = AccountAccessRequest(
        proposed_tenant_name="Fresh",
        email=fresh_email,
        status="rejected",
        reviewed_at=now - timedelta(days=10),
        reviewed_by_user_id=admin.id,
    )
    db.add_all([old, fresh])
    db.commit()
    old_id = old.id
    fresh_id = fresh.id
    try:
        assert purge_rejected_account_requests(db, now=now, retention_days=180) == 1
        db.commit()
        assert db.get(AccountAccessRequest, old_id) is None
        assert db.get(AccountAccessRequest, fresh_id) is not None
    finally:
        _cleanup(db, emails=[old_email, fresh_email, admin.email], user_ids=[admin.id])
        db.close()

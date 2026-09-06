"""Platform-admin tenant pagination and tenant-owner provisioning contracts."""

from pathlib import Path
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import (
    AuthActionToken,
    AuthSecurityEvent,
    EmailDelivery,
    OperationalEvent,
    Professional,
    User,
)
from app.services.admin_tenants import create_tenant_with_owner

client = TestClient(app)


def _email(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}@agenda.ai"


def _admin(db) -> User:
    user = User(
        email=_email("admin"),
        hashed_password=hash_password("correct-password"),
        role="platform_admin",
    )
    db.add(user)
    db.commit()
    return user


def _owner(db, professional_id: uuid.UUID) -> User:
    user = User(
        email=_email("owner"),
        hashed_password=hash_password("correct-password"),
        role="professional",
        professional_id=professional_id,
    )
    db.add(user)
    db.commit()
    return user


def _cookies(admin: User):
    response = client.post(
        "/api/auth/login", json={"email": admin.email, "password": "correct-password"}
    )
    assert response.status_code == 200
    return response.cookies


def _cleanup(db, *, user_ids: list[uuid.UUID], professional_ids: list[uuid.UUID]) -> None:
    if user_ids:
        db.query(AuthActionToken).filter(AuthActionToken.user_id.in_(user_ids)).delete(
            synchronize_session=False
        )
        db.query(EmailDelivery).filter(EmailDelivery.user_id.in_(user_ids)).delete(
            synchronize_session=False
        )
        db.query(AuthSecurityEvent).filter(AuthSecurityEvent.user_id.in_(user_ids)).delete(
            synchronize_session=False
        )
    if professional_ids:
        db.query(OperationalEvent).filter(
            OperationalEvent.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    if professional_ids:
        db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    db.commit()


def test_list_tenants_returns_bounded_page_metadata_for_platform_admin() -> None:
    db = SessionLocal()
    admin = _admin(db)
    try:
        response = client.get(
            "/api/admin/tenants?page=1&page_size=6", cookies=_cookies(admin)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["page"] == 1
        assert body["page_size"] == 6
        assert body["total"] >= len(body["tenants"])
        assert body["total_pages"] >= 0
        assert len(body["tenants"]) <= 6
        names = [tenant["name"].casefold() for tenant in body["tenants"]]
        assert names == sorted(names)
    finally:
        _cleanup(db, user_ids=[admin.id], professional_ids=[])
        db.close()


def test_create_tenant_creates_pending_owner_activation_delivery_and_audit() -> None:
    db = SessionLocal()
    admin = _admin(db)
    owner_email = _email("new_owner")
    professional_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    try:
        response = client.post(
            "/api/admin/tenants",
            json={
                "name": "  João Silva Tennis  ",
                "owner_email": owner_email.upper(),
                "whatsapp": "11987654321",
                "timezone": "America/Sao_Paulo",
            },
            cookies=_cookies(admin),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["tenant"]["name"] == "João Silva Tennis"
        assert body["tenant"]["status"] == "active"
        assert body["owner_email"] == owner_email

        professional_id = uuid.UUID(body["tenant"]["id"])
        owner = db.query(User).filter(User.email == owner_email).one()
        owner_id = owner.id
        assert owner.role == "professional"
        assert owner.professional_id == professional_id
        assert owner.status == "pending_activation"
        assert db.get(Professional, professional_id).assistant_phone == "+5511987654321"
        assert (
            db.query(EmailDelivery)
            .filter(
                EmailDelivery.user_id == owner.id,
                EmailDelivery.purpose == "account_activation",
                EmailDelivery.status == "queued",
            )
            .count()
            == 1
        )
        assert (
            db.query(OperationalEvent)
            .filter(
                OperationalEvent.professional_id == professional_id,
                OperationalEvent.event_type == "tenant.created",
            )
            .count()
            == 1
        )
    finally:
        _cleanup(
            db,
            user_ids=[admin.id] + ([owner_id] if owner_id else []),
            professional_ids=[professional_id] if professional_id else [],
        )
        db.close()


def test_create_tenant_rejects_duplicate_owner_email_without_new_tenant() -> None:
    db = SessionLocal()
    professional = Professional(name="Existing owner tenant")
    db.add(professional)
    db.commit()
    owner = _owner(db, professional.id)
    admin = _admin(db)
    try:
        response = client.post(
            "/api/admin/tenants",
            json={
                "name": "Another tenant",
                "owner_email": owner.email,
                "whatsapp": "11987654321",
                "timezone": "America/Sao_Paulo",
            },
            cookies=_cookies(admin),
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EMAIL_ALREADY_IN_USE"
        assert db.query(Professional).filter(Professional.name == "Another tenant").count() == 0
    finally:
        _cleanup(
            db,
            user_ids=[admin.id, owner.id],
            professional_ids=[professional.id],
        )
        db.close()


def test_create_tenant_rejects_unsupported_timezone() -> None:
    db = SessionLocal()
    admin = _admin(db)
    try:
        response = client.post(
            "/api/admin/tenants",
            json={
                "name": "Timezone tenant",
                "owner_email": _email("timezone"),
                "whatsapp": "11987654321",
                "timezone": "Europe/Lisbon",
            },
            cookies=_cookies(admin),
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_TIMEZONE"
    finally:
        _cleanup(db, user_ids=[admin.id], professional_ids=[])
        db.close()


def test_create_tenant_rejects_invalid_whatsapp_without_new_tenant() -> None:
    db = SessionLocal()
    admin = _admin(db)
    try:
        response = client.post(
            "/api/admin/tenants",
            json={
                "name": "Bad phone tenant",
                "owner_email": _email("badphone"),
                "whatsapp": "12345",
                "timezone": "America/Sao_Paulo",
            },
            cookies=_cookies(admin),
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_PHONE"
        assert (
            db.query(Professional).filter(Professional.name == "Bad phone tenant").count()
            == 0
        )
    finally:
        _cleanup(db, user_ids=[admin.id], professional_ids=[])
        db.close()


def test_tenant_creation_rolls_back_when_activation_enqueue_fails(monkeypatch) -> None:
    db = SessionLocal()
    name = f"Rollback {uuid.uuid4().hex[:8]}"
    email = _email("rollback")

    def fail_enqueue(*_args, **_kwargs):
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr("app.services.admin_tenants.enqueue_auth_email", fail_enqueue)
    try:
        with pytest.raises(RuntimeError, match="outbox unavailable"):
            create_tenant_with_owner(
                db,
                name=name,
                owner_email=email,
                whatsapp="11987654321",
                tenant_timezone="America/Sao_Paulo",
                admin_user_id=uuid.uuid4(),
                source_ip="127.0.0.1",
                user_agent=None,
            )
        db.rollback()
        assert db.query(Professional).filter(Professional.name == name).count() == 0
        assert db.query(User).filter(User.email == email).count() == 0
    finally:
        db.rollback()
        db.close()


def test_create_tenant_is_forbidden_for_professional_user() -> None:
    db = SessionLocal()
    professional = Professional(name="Owner tenant")
    db.add(professional)
    db.commit()
    owner = _owner(db, professional.id)
    try:
        response = client.post(
            "/api/admin/tenants",
            json={
                "name": "Blocked tenant",
                "owner_email": _email("blocked"),
                "whatsapp": "11987654321",
                "timezone": "America/Sao_Paulo",
            },
            cookies=_cookies(owner),
        )
        assert response.status_code == 403
    finally:
        _cleanup(db, user_ids=[owner.id], professional_ids=[professional.id])
        db.close()


def test_update_whatsapp_number_canonicalizes_and_clears_binding() -> None:
    from datetime import datetime, timezone

    db = SessionLocal()
    admin = _admin(db)
    professional = Professional(
        name="WA tenant",
        assistant_phone="+5511900000000",
        agent_binding_confirmed_at=datetime.now(timezone.utc),
    )
    db.add(professional)
    db.commit()
    try:
        response = client.put(
            f"/api/admin/tenants/{professional.id}/whatsapp-number",
            json={"whatsapp": "(11) 98765-4321"},
            cookies=_cookies(admin),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["assistant_phone"] == "+5511987654321"
        assert body["agent_binding_confirmed_at"] is None

        db.refresh(professional)
        assert professional.assistant_phone == "+5511987654321"
        assert professional.agent_binding_confirmed_at is None
    finally:
        _cleanup(db, user_ids=[admin.id], professional_ids=[professional.id])
        db.close()


def test_update_whatsapp_number_rejects_a_number_held_by_another_tenant() -> None:
    db = SessionLocal()
    admin = _admin(db)
    other = Professional(name="Holder", assistant_phone="+5511987654321")
    target = Professional(name="Target", assistant_phone="+5511900000000")
    db.add_all([other, target])
    db.commit()
    try:
        response = client.put(
            f"/api/admin/tenants/{target.id}/whatsapp-number",
            json={"whatsapp": "+5511987654321"},
            cookies=_cookies(admin),
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "WHATSAPP_NUMBER_ALREADY_IN_USE"
    finally:
        _cleanup(db, user_ids=[admin.id], professional_ids=[other.id, target.id])
        db.close()


def test_update_whatsapp_number_rejects_invalid_input() -> None:
    db = SessionLocal()
    admin = _admin(db)
    professional = Professional(name="WA bad", assistant_phone="+5511900000000")
    db.add(professional)
    db.commit()
    try:
        response = client.put(
            f"/api/admin/tenants/{professional.id}/whatsapp-number",
            json={"whatsapp": "not-a-number"},
            cookies=_cookies(admin),
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_PHONE"
    finally:
        _cleanup(db, user_ids=[admin.id], professional_ids=[professional.id])
        db.close()


def test_update_whatsapp_number_is_forbidden_for_professional_user() -> None:
    db = SessionLocal()
    professional = Professional(name="WA forbidden", assistant_phone="+5511900000000")
    db.add(professional)
    db.commit()
    owner = _owner(db, professional.id)
    try:
        response = client.put(
            f"/api/admin/tenants/{professional.id}/whatsapp-number",
            json={"whatsapp": "+5511987654321"},
            cookies=_cookies(owner),
        )
        assert response.status_code == 403
    finally:
        _cleanup(db, user_ids=[owner.id], professional_ids=[professional.id])
        db.close()

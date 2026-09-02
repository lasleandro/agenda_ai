"""Integration tests for login, session, and tenant impersonation."""

from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.security import SESSION_COOKIE_NAME, hash_password
from app.database import SessionLocal
from app.main import app
from app.models import (
    AssistantSettings,
    ImpersonationLog,
    OperationalEvent,
    Professional,
    TenantFeature,
    TenantFeatureAuditLog,
    User,
)

client = TestClient(app)


def _random_email() -> str:
    return f"test_{uuid.uuid4().hex[:10]}@agenda.ai"


def _create_professional(db) -> Professional:
    professional = Professional(name="Test Tenant", assistant_phone=f"+55119{uuid.uuid4().hex[:8]}")
    db.add(professional)
    db.commit()
    return professional


def _create_user(db, role: str, professional_id=None, password: str = "correct-password") -> User:
    user = User(
        email=_random_email(),
        hashed_password=hash_password(password),
        role=role,
        professional_id=professional_id,
    )
    db.add(user)
    db.commit()
    return user


def _cleanup(db, *, users=(), professionals=()):
    user_ids = [u.id for u in users]
    professional_ids = [p.id for p in professionals]
    if user_ids:
        db.query(TenantFeatureAuditLog).filter(
            TenantFeatureAuditLog.admin_user_id.in_(user_ids)
        ).delete(synchronize_session=False)
        db.query(ImpersonationLog).filter(ImpersonationLog.admin_user_id.in_(user_ids)).delete(
            synchronize_session=False
        )
    if professional_ids:
        db.query(TenantFeatureAuditLog).filter(
            TenantFeatureAuditLog.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(TenantFeature).filter(
            TenantFeature.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(OperationalEvent).filter(
            OperationalEvent.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(AssistantSettings).filter(
            AssistantSettings.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    if professional_ids:
        db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    db.commit()


def test_login_with_valid_credentials_issues_session_cookie() -> None:
    db = SessionLocal()
    professional = _create_professional(db)
    user = _create_user(db, role="professional", professional_id=professional.id)
    try:
        res = client.post("/api/auth/login", json={"email": user.email, "password": "correct-password"})
        assert res.status_code == 200
        assert SESSION_COOKIE_NAME in res.cookies
        assert res.headers["cache-control"] == "no-store"
        assert "default-src 'none'" in res.headers["content-security-policy"]

        me = client.get("/api/auth/me", cookies=res.cookies)
        assert me.status_code == 200
        body = me.json()
        assert body["role"] == "professional"
        assert body["professional_id"] == str(professional.id)
        assert body["professional_name"] == "Test Tenant"

        me_with_unrelated_cookie = client.get(
            "/api/auth/me",
            cookies={
                SESSION_COOKIE_NAME: res.cookies[SESSION_COOKIE_NAME],
                "access_token": "another-localhost-application-token",
            },
        )
        assert me_with_unrelated_cookie.status_code == 200
    finally:
        _cleanup(db, users=[user], professionals=[professional])
        db.close()


def test_login_with_wrong_password_is_rejected() -> None:
    db = SessionLocal()
    user = _create_user(db, role="platform_admin")
    try:
        res = client.post("/api/auth/login", json={"email": user.email, "password": "wrong-password"})
        assert res.status_code == 401
    finally:
        _cleanup(db, users=[user])
        db.close()


def test_platform_admin_can_impersonate_a_tenant_and_it_is_audit_logged() -> None:
    db = SessionLocal()
    professional = _create_professional(db)
    admin = _create_user(db, role="platform_admin")
    try:
        login_res = client.post(
            "/api/auth/login", json={"email": admin.email, "password": "correct-password"}
        )
        assert login_res.json()["role"] == "platform_admin"

        me_before = client.get("/api/auth/me", cookies=login_res.cookies).json()
        assert me_before["professional_id"] is None

        impersonate_res = client.post(
            "/api/auth/impersonate",
            json={"professional_id": str(professional.id)},
            cookies=login_res.cookies,
        )
        assert impersonate_res.status_code == 200
        assert impersonate_res.json()["professional_name"] == "Test Tenant"

        me_after = client.get("/api/auth/me", cookies=impersonate_res.cookies).json()
        assert me_after["professional_id"] == str(professional.id)
        assert me_after["impersonating"] is True

        log_entry = (
            db.query(ImpersonationLog)
            .filter(
                ImpersonationLog.admin_user_id == admin.id,
                ImpersonationLog.professional_id == professional.id,
            )
            .first()
        )
        assert log_entry is not None
    finally:
        _cleanup(db, users=[admin], professionals=[professional])
        db.close()


def test_platform_admin_tenant_list_includes_new_tenant_and_forbids_non_admin() -> None:
    db = SessionLocal()
    professional = _create_professional(db)
    admin = _create_user(db, role="platform_admin")
    owner = _create_user(db, role="professional", professional_id=professional.id)
    try:
        admin_login = client.post(
            "/api/auth/login", json={"email": admin.email, "password": "correct-password"}
        )
        tenants_res = client.get("/api/admin/tenants", cookies=admin_login.cookies)
        assert tenants_res.status_code == 200
        tenant_ids = {t["id"] for t in tenants_res.json()["tenants"]}
        assert str(professional.id) in tenant_ids
        tenant = next(
            item
            for item in tenants_res.json()["tenants"]
            if item["id"] == str(professional.id)
        )
        assert tenant["scheduled_task"]["configured"] is False
        assert tenant["scheduled_task"]["latest_run_status"] is None

        owner_login = client.post(
            "/api/auth/login", json={"email": owner.email, "password": "correct-password"}
        )
        forbidden_res = client.get("/api/admin/tenants", cookies=owner_login.cookies)
        assert forbidden_res.status_code == 403
    finally:
        _cleanup(db, users=[admin, owner], professionals=[professional])
        db.close()


def test_platform_admin_can_toggle_commercial_financials_with_audit() -> None:
    db = SessionLocal()
    professional = _create_professional(db)
    admin = _create_user(db, role="platform_admin")
    owner = _create_user(db, role="professional", professional_id=professional.id)
    path = f"/api/admin/tenants/{professional.id}/features/commercial-financials"
    try:
        admin_login = client.post(
            "/api/auth/login",
            json={"email": admin.email, "password": "correct-password"},
        )
        initial_list = client.get("/api/admin/tenants", cookies=admin_login.cookies)
        tenant = next(
            item
            for item in initial_list.json()["tenants"]
            if item["id"] == str(professional.id)
        )
        assert tenant["commercial_financials_enabled"] is False

        enabled = client.patch(
            path,
            json={"enabled": True},
            headers={"user-agent": "agenda-test-admin"},
            cookies=admin_login.cookies,
        )
        assert enabled.status_code == 200
        assert enabled.json() == {
            "feature_key": "commercial_financials",
            "enabled": True,
        }

        feature = (
            db.query(TenantFeature)
            .filter(
                TenantFeature.professional_id == professional.id,
                TenantFeature.feature_key == "commercial_financials",
            )
            .one()
        )
        assert feature.enabled is True
        assert feature.configured_by_user_id == admin.id

        audit = (
            db.query(TenantFeatureAuditLog)
            .filter(TenantFeatureAuditLog.professional_id == professional.id)
            .one()
        )
        assert audit.admin_user_id == admin.id
        assert audit.previous_enabled is False
        assert audit.new_enabled is True
        assert audit.user_agent == "agenda-test-admin"
        assert audit.source_ip is not None

        impersonated = client.post(
            "/api/auth/impersonate",
            json={"professional_id": str(professional.id)},
            cookies=admin_login.cookies,
        )
        session = client.get("/api/auth/me", cookies=impersonated.cookies)
        assert session.status_code == 200
        assert session.json()["features"] == ["commercial_financials"]

        repeated = client.patch(
            path,
            json={"enabled": True},
            cookies=admin_login.cookies,
        )
        assert repeated.status_code == 200
        assert (
            db.query(TenantFeatureAuditLog)
            .filter(TenantFeatureAuditLog.professional_id == professional.id)
            .count()
            == 1
        )

        owner_login = client.post(
            "/api/auth/login",
            json={"email": owner.email, "password": "correct-password"},
        )
        forbidden = client.patch(
            path,
            json={"enabled": False},
            cookies=owner_login.cookies,
        )
        assert forbidden.status_code == 403

        disabled = client.patch(
            path,
            json={"enabled": False},
            cookies=admin_login.cookies,
        )
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False
        db.refresh(feature)
        assert feature.enabled is False
        audit_changes = (
            db.query(TenantFeatureAuditLog)
            .filter(TenantFeatureAuditLog.professional_id == professional.id)
            .order_by(TenantFeatureAuditLog.created_at)
            .all()
        )
        assert [
            (item.previous_enabled, item.new_enabled)
            for item in audit_changes
        ] == [(False, True), (True, False)]
    finally:
        _cleanup(
            db,
            users=[admin, owner],
            professionals=[professional],
        )
        db.close()


def test_platform_admin_can_tune_assistant_settings_with_audit() -> None:
    db = SessionLocal()
    professional = _create_professional(db)
    admin = _create_user(db, role="platform_admin")
    owner = _create_user(db, role="professional", professional_id=professional.id)
    path = f"/api/admin/tenants/{professional.id}/assistant-settings"
    try:
        admin_login = client.post(
            "/api/auth/login",
            json={"email": admin.email, "password": "correct-password"},
        )
        initial_list = client.get("/api/admin/tenants", cookies=admin_login.cookies)
        tenant = next(
            item
            for item in initial_list.json()["tenants"]
            if item["id"] == str(professional.id)
        )
        assert tenant["assistant_temperature"] == 0.2
        assert tenant["assistant_memory_window_messages"] == 20

        updated = client.put(
            path,
            json={"temperature": 0.5, "memory_window_messages": 12},
            cookies=admin_login.cookies,
        )
        assert updated.status_code == 200
        assert updated.json() == {
            "temperature": 0.5,
            "memory_window_messages": 12,
        }

        row = (
            db.query(AssistantSettings)
            .filter(AssistantSettings.professional_id == professional.id)
            .one()
        )
        assert row.temperature == 0.5
        assert row.memory_window_messages == 12
        assert row.updated_by_user_id == admin.id

        event = (
            db.query(OperationalEvent)
            .filter(
                OperationalEvent.professional_id == professional.id,
                OperationalEvent.event_type == "assistant.settings.updated",
            )
            .one()
        )
        assert event.before_state == {
            "temperature": 0.2,
            "memory_window_messages": 20,
        }
        assert event.after_state == {
            "temperature": 0.5,
            "memory_window_messages": 12,
        }

        out_of_range = client.put(
            path,
            json={"temperature": 3.0, "memory_window_messages": 12},
            cookies=admin_login.cookies,
        )
        assert out_of_range.status_code == 400

        owner_login = client.post(
            "/api/auth/login",
            json={"email": owner.email, "password": "correct-password"},
        )
        forbidden = client.put(
            path,
            json={"temperature": 0.9, "memory_window_messages": 30},
            cookies=owner_login.cookies,
        )
        assert forbidden.status_code == 403
    finally:
        _cleanup(
            db,
            users=[admin, owner],
            professionals=[professional],
        )
        db.close()


def test_non_admin_cannot_impersonate() -> None:
    db = SessionLocal()
    professional = _create_professional(db)
    other_professional = _create_professional(db)
    owner = _create_user(db, role="professional", professional_id=professional.id)
    try:
        login_res = client.post(
            "/api/auth/login", json={"email": owner.email, "password": "correct-password"}
        )
        impersonate_res = client.post(
            "/api/auth/impersonate",
            json={"professional_id": str(other_professional.id)},
            cookies=login_res.cookies,
        )
        assert impersonate_res.status_code == 403
    finally:
        _cleanup(db, users=[owner], professionals=[professional, other_professional])
        db.close()

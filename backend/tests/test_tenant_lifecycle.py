"""Tenant lifecycle: suspend / reactivate / archive / restore.

Covers the service (`set_tenant_status`), the platform-admin endpoints, and
the enforcement points in login / impersonation.
"""

from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import (
    AuthSecurityEvent,
    ImpersonationLog,
    OperationalEvent,
    Professional,
    User,
)
from app.services.tenant_lifecycle import TenantLifecycleError, set_tenant_status

client = TestClient(app)


def _random_email() -> str:
    return f"lifecycle_{uuid.uuid4().hex[:10]}@agenda.ai"


def _make_professional(db, status: str = "active") -> Professional:
    professional = Professional(
        name="Lifecycle Tenant",
        assistant_phone=f"+55119{uuid.uuid4().int % 100_000_000:08d}",
        agent_phone=f"+55118{uuid.uuid4().hex[:8]}",
        status=status,
    )
    db.add(professional)
    db.commit()
    return professional


def _make_user(db, role: str, professional_id=None) -> User:
    user = User(
        email=_random_email(),
        hashed_password=hash_password("correct-password"),
        role=role,
        professional_id=professional_id,
    )
    db.add(user)
    db.commit()
    return user


def _cleanup(db, *, users=(), professionals=()) -> None:
    user_ids = [u.id for u in users]
    professional_ids = [p.id for p in professionals]
    if professional_ids:
        db.query(OperationalEvent).filter(
            OperationalEvent.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(ImpersonationLog).filter(
            ImpersonationLog.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
    if user_ids:
        db.query(AuthSecurityEvent).filter(
            AuthSecurityEvent.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
    # users first (users.professional_id is RESTRICT); professionals.status_changed_by
    # is ON DELETE SET NULL so the admin user can drop without blocking.
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    if professional_ids:
        db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    db.commit()


# --------------------------------------------------------------------------- #
# Service                                                                      #
# --------------------------------------------------------------------------- #


def test_set_tenant_status_active_to_suspended_records_event_and_bumps_auth_version() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    admin = _make_user(db, role="platform_admin")
    owner = _make_user(db, role="professional", professional_id=professional.id)
    baseline_auth_version = owner.auth_version
    try:
        set_tenant_status(
            db,
            professional_id=professional.id,
            target_status="suspended",
            admin_user_id=admin.id,
            reason="  billing lapse  ",
        )
        db.commit()

        db.refresh(professional)
        db.refresh(owner)
        assert professional.status == "suspended"
        assert professional.status_changed_by == admin.id
        assert professional.status_changed_at is not None
        assert professional.status_reason == "billing lapse"
        assert owner.auth_version == baseline_auth_version + 1

        events = (
            db.query(OperationalEvent)
            .filter(OperationalEvent.professional_id == professional.id)
            .all()
        )
        assert [e.event_type for e in events] == ["tenant.suspended"]
        assert events[0].before_state == {"status": "active"}
        assert events[0].after_state == {"status": "suspended"}
    finally:
        _cleanup(db, users=[admin, owner], professionals=[professional])
        db.close()


def test_set_tenant_status_suspended_to_active_uses_reactivated_event() -> None:
    db = SessionLocal()
    professional = _make_professional(db, status="suspended")
    admin = _make_user(db, role="platform_admin")
    try:
        set_tenant_status(
            db,
            professional_id=professional.id,
            target_status="active",
            admin_user_id=admin.id,
        )
        db.commit()

        db.refresh(professional)
        assert professional.status == "active"
        assert professional.status_reason is None
        event_types = [
            e.event_type
            for e in db.query(OperationalEvent)
            .filter(OperationalEvent.professional_id == professional.id)
            .all()
        ]
        assert event_types == ["tenant.reactivated"]
    finally:
        _cleanup(db, users=[admin], professionals=[professional])
        db.close()


def test_set_tenant_status_archived_to_active_uses_restored_event() -> None:
    db = SessionLocal()
    professional = _make_professional(db, status="archived")
    admin = _make_user(db, role="platform_admin")
    try:
        set_tenant_status(
            db,
            professional_id=professional.id,
            target_status="active",
            admin_user_id=admin.id,
        )
        db.commit()

        event_types = [
            e.event_type
            for e in db.query(OperationalEvent)
            .filter(OperationalEvent.professional_id == professional.id)
            .all()
        ]
        assert event_types == ["tenant.restored"]
    finally:
        _cleanup(db, users=[admin], professionals=[professional])
        db.close()


def test_set_tenant_status_noop_when_already_in_target_status() -> None:
    db = SessionLocal()
    professional = _make_professional(db, status="suspended")
    admin = _make_user(db, role="platform_admin")
    try:
        set_tenant_status(
            db,
            professional_id=professional.id,
            target_status="suspended",
            admin_user_id=admin.id,
        )
        db.commit()

        assert (
            db.query(OperationalEvent)
            .filter(OperationalEvent.professional_id == professional.id)
            .count()
            == 0
        )
    finally:
        _cleanup(db, users=[admin], professionals=[professional])
        db.close()


def test_set_tenant_status_unknown_status_raises() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    admin = _make_user(db, role="platform_admin")
    try:
        with pytest.raises(TenantLifecycleError):
            set_tenant_status(
                db,
                professional_id=professional.id,
                target_status="deleted",
                admin_user_id=admin.id,
            )
    finally:
        db.rollback()
        _cleanup(db, users=[admin], professionals=[professional])
        db.close()


def test_set_tenant_status_missing_tenant_raises_lookup_error() -> None:
    db = SessionLocal()
    admin = _make_user(db, role="platform_admin")
    try:
        with pytest.raises(LookupError):
            set_tenant_status(
                db,
                professional_id=uuid.uuid4(),
                target_status="suspended",
                admin_user_id=admin.id,
            )
    finally:
        db.rollback()
        _cleanup(db, users=[admin])
        db.close()


def test_set_tenant_status_auth_version_bump_is_scoped_to_the_tenants_users() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    other_professional = _make_professional(db)
    admin = _make_user(db, role="platform_admin")
    owner = _make_user(db, role="professional", professional_id=professional.id)
    other_owner = _make_user(
        db, role="professional", professional_id=other_professional.id
    )
    other_baseline = other_owner.auth_version
    try:
        set_tenant_status(
            db,
            professional_id=professional.id,
            target_status="archived",
            admin_user_id=admin.id,
        )
        db.commit()

        db.refresh(other_owner)
        assert other_owner.auth_version == other_baseline
    finally:
        _cleanup(
            db,
            users=[admin, owner, other_owner],
            professionals=[professional, other_professional],
        )
        db.close()


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


def _admin_cookies(admin: User):
    res = client.post(
        "/api/auth/login", json={"email": admin.email, "password": "correct-password"}
    )
    assert res.status_code == 200
    return res.cookies


def test_suspend_endpoint_sets_status_and_returns_state() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    admin = _make_user(db, role="platform_admin")
    try:
        res = client.post(
            f"/api/admin/tenants/{professional.id}/suspend",
            json={"reason": "abuse report"},
            cookies=_admin_cookies(admin),
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "suspended"
        assert body["status_reason"] == "abuse report"
        assert body["status_changed_at"] is not None
    finally:
        _cleanup(db, users=[admin], professionals=[professional])
        db.close()


def test_archive_then_restore_endpoint_round_trip() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    admin = _make_user(db, role="platform_admin")
    try:
        cookies = _admin_cookies(admin)
        archive_res = client.post(
            f"/api/admin/tenants/{professional.id}/archive",
            json={},
            cookies=cookies,
        )
        assert archive_res.status_code == 200
        assert archive_res.json()["status"] == "archived"

        restore_res = client.post(
            f"/api/admin/tenants/{professional.id}/restore",
            cookies=cookies,
        )
        assert restore_res.status_code == 200
        assert restore_res.json()["status"] == "active"
    finally:
        _cleanup(db, users=[admin], professionals=[professional])
        db.close()


def test_lifecycle_endpoint_forbidden_for_non_admin() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    owner = _make_user(db, role="professional", professional_id=professional.id)
    try:
        owner_login = client.post(
            "/api/auth/login",
            json={"email": owner.email, "password": "correct-password"},
        )
        res = client.post(
            f"/api/admin/tenants/{professional.id}/suspend",
            json={},
            cookies=owner_login.cookies,
        )
        assert res.status_code == 403
    finally:
        _cleanup(db, users=[owner], professionals=[professional])
        db.close()


def test_lifecycle_endpoint_404_for_unknown_tenant() -> None:
    db = SessionLocal()
    admin = _make_user(db, role="platform_admin")
    try:
        res = client.post(
            f"/api/admin/tenants/{uuid.uuid4()}/suspend",
            json={},
            cookies=_admin_cookies(admin),
        )
        assert res.status_code == 404
    finally:
        _cleanup(db, users=[admin])
        db.close()


def test_tenant_list_hides_archived_unless_include_archived() -> None:
    db = SessionLocal()
    professional = _make_professional(db, status="archived")
    admin = _make_user(db, role="platform_admin")
    try:
        cookies = _admin_cookies(admin)
        default_res = client.get("/api/admin/tenants", cookies=cookies)
        assert default_res.status_code == 200
        assert str(professional.id) not in {
            t["id"] for t in default_res.json()["tenants"]
        }

        with_archived = client.get(
            "/api/admin/tenants?include_archived=true", cookies=cookies
        )
        assert str(professional.id) in {
            t["id"] for t in with_archived.json()["tenants"]
        }
    finally:
        _cleanup(db, users=[admin], professionals=[professional])
        db.close()


# --------------------------------------------------------------------------- #
# Enforcement                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "status,expected_code",
    [("suspended", "TENANT_SUSPENDED"), ("archived", "TENANT_ARCHIVED")],
)
def test_login_blocked_when_tenant_not_active(status: str, expected_code: str) -> None:
    db = SessionLocal()
    professional = _make_professional(db, status=status)
    owner = _make_user(db, role="professional", professional_id=professional.id)
    try:
        res = client.post(
            "/api/auth/login",
            json={"email": owner.email, "password": "correct-password"},
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == expected_code
        assert "access_token" not in res.cookies

        blocked = (
            db.query(AuthSecurityEvent)
            .filter(
                AuthSecurityEvent.user_id == owner.id,
                AuthSecurityEvent.event_type == "login_blocked_tenant_inactive",
            )
            .count()
        )
        assert blocked == 1
    finally:
        _cleanup(db, users=[owner], professionals=[professional])
        db.close()


def test_impersonate_inactive_tenant_requires_confirm() -> None:
    db = SessionLocal()
    professional = _make_professional(db, status="suspended")
    admin = _make_user(db, role="platform_admin")
    try:
        cookies = _admin_cookies(admin)
        res = client.post(
            "/api/auth/impersonate",
            json={"professional_id": str(professional.id)},
            cookies=cookies,
        )
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "TENANT_INACTIVE_CONFIRM_REQUIRED"
    finally:
        _cleanup(db, users=[admin], professionals=[professional])
        db.close()


def test_impersonate_inactive_tenant_with_confirm_succeeds_and_logs_event() -> None:
    db = SessionLocal()
    professional = _make_professional(db, status="suspended")
    admin = _make_user(db, role="platform_admin")
    try:
        cookies = _admin_cookies(admin)
        res = client.post(
            "/api/auth/impersonate",
            json={"professional_id": str(professional.id), "confirm": True},
            cookies=cookies,
        )
        assert res.status_code == 200

        event_types = [
            e.event_type
            for e in db.query(OperationalEvent)
            .filter(OperationalEvent.professional_id == professional.id)
            .all()
        ]
        assert "tenant.impersonated_while_inactive" in event_types
        assert (
            db.query(ImpersonationLog)
            .filter(ImpersonationLog.professional_id == professional.id)
            .count()
            == 1
        )
    finally:
        _cleanup(db, users=[admin], professionals=[professional])
        db.close()

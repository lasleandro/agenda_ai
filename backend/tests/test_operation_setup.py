"""Unit tests for the first-session setup predicate and its exposure on
``/api/auth/me``. A tenant is configured only once it has at least one Local
and at least one ``work`` interval in the weekly journey."""

from datetime import time
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import Place, Professional, User, WorkJourneyInterval
from app.services.operation_setup import operation_is_configured

client = TestClient(app)


def _random_email() -> str:
    return f"opsetup_{uuid.uuid4().hex[:10]}@agenda.ai"


def _create_tenant(db):
    professional = Professional(
        name="Tenant Setup",
        assistant_phone=f"+55119{uuid.uuid4().hex[:8]}",
    )
    db.add(professional)
    db.commit()
    owner = User(
        email=_random_email(),
        hashed_password=hash_password("correct-password"),
        role="professional",
        professional_id=professional.id,
    )
    db.add(owner)
    db.commit()
    login = client.post(
        "/api/auth/login",
        json={"email": owner.email, "password": "correct-password"},
    )
    return professional, owner, login.cookies


def _add_place(db, professional_id) -> None:
    db.add(
        Place(
            professional_id=professional_id,
            name="Clube Central",
            normalized_name="clube central",
        )
    )
    db.commit()


def _add_interval(db, professional_id, *, interval_type: str) -> None:
    db.add(
        WorkJourneyInterval(
            professional_id=professional_id,
            day_of_week=1,
            interval_type=interval_type,
            start_time=time(8, 0),
            end_time=time(17, 0)
            if interval_type == "work"
            else time(13, 0),
        )
    )
    db.commit()


def _cleanup(db, *, professionals, users) -> None:
    professional_ids = [professional.id for professional in professionals]
    user_ids = [user.id for user in users]
    if professional_ids:
        db.query(WorkJourneyInterval).filter(
            WorkJourneyInterval.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(Place).filter(
            Place.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    if professional_ids:
        db.query(Professional).filter(
            Professional.id.in_(professional_ids)
        ).delete(synchronize_session=False)
    db.commit()


def test_operation_is_configured_no_place_no_journey_returns_false() -> None:
    db = SessionLocal()
    professional, owner, _ = _create_tenant(db)
    try:
        assert operation_is_configured(db, professional.id) is False
    finally:
        _cleanup(db, professionals=[professional], users=[owner])
        db.close()


def test_operation_is_configured_place_only_returns_false() -> None:
    db = SessionLocal()
    professional, owner, _ = _create_tenant(db)
    try:
        _add_place(db, professional.id)
        assert operation_is_configured(db, professional.id) is False
    finally:
        _cleanup(db, professionals=[professional], users=[owner])
        db.close()


def test_operation_is_configured_work_interval_only_returns_false() -> None:
    db = SessionLocal()
    professional, owner, _ = _create_tenant(db)
    try:
        _add_interval(db, professional.id, interval_type="work")
        assert operation_is_configured(db, professional.id) is False
    finally:
        _cleanup(db, professionals=[professional], users=[owner])
        db.close()


def test_operation_is_configured_place_and_break_only_returns_false() -> None:
    db = SessionLocal()
    professional, owner, _ = _create_tenant(db)
    try:
        _add_place(db, professional.id)
        _add_interval(db, professional.id, interval_type="break")
        assert operation_is_configured(db, professional.id) is False
    finally:
        _cleanup(db, professionals=[professional], users=[owner])
        db.close()


def test_operation_is_configured_place_and_work_interval_returns_true() -> None:
    db = SessionLocal()
    professional, owner, _ = _create_tenant(db)
    try:
        _add_place(db, professional.id)
        _add_interval(db, professional.id, interval_type="work")
        assert operation_is_configured(db, professional.id) is True
    finally:
        _cleanup(db, professionals=[professional], users=[owner])
        db.close()


def test_me_reports_operation_configured_for_scoped_tenant() -> None:
    db = SessionLocal()
    professional, owner, cookies = _create_tenant(db)
    try:
        unconfigured = client.get("/api/auth/me", cookies=cookies)
        assert unconfigured.status_code == 200
        assert unconfigured.json()["operation_configured"] is False

        _add_place(db, professional.id)
        _add_interval(db, professional.id, interval_type="work")

        configured = client.get("/api/auth/me", cookies=cookies)
        assert configured.json()["operation_configured"] is True
    finally:
        _cleanup(db, professionals=[professional], users=[owner])
        db.close()


def test_me_omits_operation_configured_for_unscoped_platform_admin() -> None:
    db = SessionLocal()
    admin = User(
        email=_random_email(),
        hashed_password=hash_password("correct-password"),
        role="platform_admin",
        professional_id=None,
    )
    db.add(admin)
    db.commit()
    try:
        login = client.post(
            "/api/auth/login",
            json={"email": admin.email, "password": "correct-password"},
        )
        body = client.get("/api/auth/me", cookies=login.cookies).json()
        assert "operation_configured" not in body
    finally:
        db.query(User).filter(User.id == admin.id).delete(synchronize_session=False)
        db.commit()
        db.close()

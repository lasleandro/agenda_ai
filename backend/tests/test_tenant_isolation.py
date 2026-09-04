"""Integration tests: dashboard routes must never leak another tenant's data."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import Appointment, Contact, Conversation, Professional, User

client = TestClient(app)


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().int % 100_000_000:08d}"


def _random_email() -> str:
    return f"test_{uuid.uuid4().hex[:10]}@agenda.ai"


def _setup_tenant(db):
    """Create a Professional with one Contact, one Conversation, one
    Appointment, and an owner User, so it has visible data in every
    dashboard route under test."""
    professional = Professional(name="Tenant", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()

    contact = Contact(
        professional_id=professional.id,
        phone=_random_phone(),
        display_name="Contact",
        normalized_name="contact",
    )
    db.add(contact)
    db.commit()

    conversation = Conversation(professional_id=professional.id, contact_id=contact.id)
    db.add(conversation)
    db.commit()

    start = datetime.now(timezone.utc) + timedelta(days=1)
    appointment = Appointment(
        professional_id=professional.id,
        contact_id=contact.id,
        service="tennis_lesson",
        start_at=start,
        end_at=start + timedelta(hours=1),
    )
    db.add(appointment)
    db.commit()

    user = User(
        email=_random_email(),
        hashed_password=hash_password("correct-password"),
        role="professional",
        professional_id=professional.id,
    )
    db.add(user)
    db.commit()

    return professional, contact, conversation, appointment, user


def _cleanup(db, *, professionals, users):
    professional_ids = [p.id for p in professionals]
    if professional_ids:
        db.query(Appointment).filter(Appointment.professional_id.in_(professional_ids)).delete(
            synchronize_session=False
        )
        db.query(Conversation).filter(Conversation.professional_id.in_(professional_ids)).delete(
            synchronize_session=False
        )
        db.query(Contact).filter(Contact.professional_id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    user_ids = [u.id for u in users]
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    if professional_ids:
        db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    db.commit()


def test_calendar_and_conversations_never_leak_across_tenants() -> None:
    db = SessionLocal()
    pro_a, contact_a, conv_a, appt_a, user_a = _setup_tenant(db)
    pro_b, contact_b, conv_b, appt_b, user_b = _setup_tenant(db)
    try:
        login_a = client.post(
            "/api/auth/login", json={"email": user_a.email, "password": "correct-password"}
        )
        assert login_a.status_code == 200

        start_date = datetime.now(timezone.utc).date().isoformat()
        end_date = (datetime.now(timezone.utc) + timedelta(days=3)).date().isoformat()

        calendar_res = client.get(
            f"/api/calendar?start_date={start_date}&end_date={end_date}",
            cookies=login_a.cookies,
        )
        assert calendar_res.status_code == 200
        appt_ids = {a["id"] for a in calendar_res.json()["appointments"]}
        assert str(appt_a.id) in appt_ids
        assert str(appt_b.id) not in appt_ids

        cross_tenant_appt = client.get(
            f"/api/appointments/{appt_b.id}", cookies=login_a.cookies
        )
        assert cross_tenant_appt.status_code == 404

        conversations_res = client.get("/api/conversations", cookies=login_a.cookies)
        assert conversations_res.status_code == 200
        conv_ids = {c["id"] for c in conversations_res.json()["conversations"]}
        assert str(conv_a.id) in conv_ids
        assert str(conv_b.id) not in conv_ids

        cross_tenant_conv = client.get(
            f"/api/conversations/{conv_b.id}", cookies=login_a.cookies
        )
        assert cross_tenant_conv.status_code == 404
    finally:
        _cleanup(db, professionals=[pro_a, pro_b], users=[user_a, user_b])
        db.close()


def test_platform_admin_without_impersonation_cannot_read_tenant_data() -> None:
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
        login_res = client.post(
            "/api/auth/login", json={"email": admin.email, "password": "correct-password"}
        )
        start_date = datetime.now(timezone.utc).date().isoformat()
        end_date = (datetime.now(timezone.utc) + timedelta(days=3)).date().isoformat()

        res = client.get(
            f"/api/calendar?start_date={start_date}&end_date={end_date}",
            cookies=login_res.cookies,
        )
        assert res.status_code == 403
    finally:
        db.query(User).filter(User.id == admin.id).delete(synchronize_session=False)
        db.commit()
        db.close()

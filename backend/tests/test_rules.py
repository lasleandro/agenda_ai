"""Integration tests for operational rules (work journey, cancellation notice
hours) — verifies they are reachable regardless of the commercial_financials
feature flag, and remain tenant-isolated."""

from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import (
    FinancialChangeAuditLog,
    ProfessionalFinancialSettings,
    Professional,
    User,
    WorkJourneyInterval,
)

client = TestClient(app)


def _random_email() -> str:
    return f"rules_{uuid.uuid4().hex[:10]}@agenda.ai"


def _create_tenant(db):
    professional = Professional(
        name="Tenant Regras",
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


def _cleanup(db, *, professionals, users) -> None:
    professional_ids = [professional.id for professional in professionals]
    user_ids = [user.id for user in users]
    if professional_ids:
        db.query(FinancialChangeAuditLog).filter(
            FinancialChangeAuditLog.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(WorkJourneyInterval).filter(
            WorkJourneyInterval.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(ProfessionalFinancialSettings).filter(
            ProfessionalFinancialSettings.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    if professional_ids:
        db.query(Professional).filter(
            Professional.id.in_(professional_ids)
        ).delete(synchronize_session=False)
    db.commit()


def test_rules_reachable_without_commercial_financials_flag() -> None:
    db = SessionLocal()
    professional, owner, cookies = _create_tenant(db)
    try:
        gated = client.get("/api/financial/settings", cookies=cookies)
        assert gated.status_code == 404

        empty_journey = client.get("/api/rules/work-journey", cookies=cookies)
        assert empty_journey.status_code == 200
        assert empty_journey.json() == []

        default_notice = client.get(
            "/api/rules/cancellation-notice-hours", cookies=cookies
        )
        assert default_notice.status_code == 200
        assert default_notice.json() == {"cancellation_notice_hours": 24}

        invalid_break = client.put(
            "/api/rules/work-journey",
            json={
                "intervals": [
                    {
                        "day_of_week": 1,
                        "interval_type": "break",
                        "start_time": "12:00:00",
                        "end_time": "13:00:00",
                    }
                ]
            },
            cookies=cookies,
        )
        assert invalid_break.status_code == 422

        journey = client.put(
            "/api/rules/work-journey",
            json={
                "intervals": [
                    {
                        "day_of_week": 1,
                        "interval_type": "work",
                        "start_time": "08:00:00",
                        "end_time": "17:00:00",
                    },
                    {
                        "day_of_week": 1,
                        "interval_type": "break",
                        "start_time": "12:00:00",
                        "end_time": "13:00:00",
                    },
                    {
                        "day_of_week": 1,
                        "interval_type": "break",
                        "start_time": "15:00:00",
                        "end_time": "15:30:00",
                    },
                ]
            },
            cookies=cookies,
        )
        assert journey.status_code == 200
        assert len(journey.json()) == 3
        assert [row["interval_type"] for row in journey.json()] == [
            "work",
            "break",
            "break",
        ]

        refetched = client.get("/api/rules/work-journey", cookies=cookies)
        assert refetched.status_code == 200
        assert len(refetched.json()) == 3

        updated_notice = client.patch(
            "/api/rules/cancellation-notice-hours",
            json={"cancellation_notice_hours": 48},
            cookies=cookies,
        )
        assert updated_notice.status_code == 200
        assert updated_notice.json() == {"cancellation_notice_hours": 48}

        refetched_notice = client.get(
            "/api/rules/cancellation-notice-hours", cookies=cookies
        )
        assert refetched_notice.json() == {"cancellation_notice_hours": 48}

        out_of_range = client.patch(
            "/api/rules/cancellation-notice-hours",
            json={"cancellation_notice_hours": 999},
            cookies=cookies,
        )
        assert out_of_range.status_code == 422

        audited_types = {
            row.entity_type
            for row in (
                db.query(FinancialChangeAuditLog)
                .filter(FinancialChangeAuditLog.professional_id == professional.id)
                .all()
            )
        }
        assert {"work_journey", "cancellation_notice_hours"}.issubset(audited_types)
    finally:
        _cleanup(db, professionals=[professional], users=[owner])
        db.close()


def test_rules_are_tenant_isolated() -> None:
    db = SessionLocal()
    professional, owner, cookies = _create_tenant(db)
    other_professional, other_owner, other_cookies = _create_tenant(db)
    try:
        client.put(
            "/api/rules/work-journey",
            json={
                "intervals": [
                    {
                        "day_of_week": 2,
                        "interval_type": "work",
                        "start_time": "09:00:00",
                        "end_time": "10:00:00",
                    }
                ]
            },
            cookies=cookies,
        )
        client.patch(
            "/api/rules/cancellation-notice-hours",
            json={"cancellation_notice_hours": 72},
            cookies=cookies,
        )

        other_journey = client.get("/api/rules/work-journey", cookies=other_cookies)
        assert other_journey.json() == []

        other_notice = client.get(
            "/api/rules/cancellation-notice-hours", cookies=other_cookies
        )
        assert other_notice.json() == {"cancellation_notice_hours": 24}
    finally:
        _cleanup(
            db,
            professionals=[professional, other_professional],
            users=[owner, other_owner],
        )
        db.close()

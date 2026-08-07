"""Integration coverage for immutable recognized-revenue occurrences."""

from pathlib import Path
import sys
import uuid
from datetime import datetime, time, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import (
    Appointment,
    Contact,
    FinancialChangeAuditLog,
    FinancialRate,
    Place,
    PlaceFinancialRate,
    Professional,
    RecurringSlot,
    RecurringSlotParticipant,
    RevenueOccurrence,
    RevenueOccurrenceLine,
    RevenueOccurrenceParticipant,
    TenantFeature,
    User,
)
from app.services.financial_capacity import TIMEZONE

client = TestClient(app)


def _create_tenant(db):
    professional = Professional(
        name="Tenant Receita",
        assistant_phone=f"+55119{uuid.uuid4().hex[:8]}",
    )
    db.add(professional)
    db.commit()
    owner = User(
        email=f"revenue_{uuid.uuid4().hex[:10]}@agenda.ai",
        hashed_password=hash_password("correct-password"),
        role="professional",
        professional_id=professional.id,
    )
    admin = User(
        email=f"admin_{uuid.uuid4().hex[:10]}@agenda.ai",
        hashed_password=hash_password("correct-password"),
        role="platform_admin",
    )
    db.add_all([owner, admin])
    db.commit()
    db.add(
        TenantFeature(
            professional_id=professional.id,
            feature_key="commercial_financials",
            enabled=True,
            configured_by_user_id=admin.id,
        )
    )
    db.commit()
    login = client.post(
        "/api/auth/login",
        json={"email": owner.email, "password": "correct-password"},
    )
    return professional, owner, admin, login.cookies


def _cleanup(db, professionals, users) -> None:
    professional_ids = [professional.id for professional in professionals]
    user_ids = [user.id for user in users]
    occurrence_ids = [
        row[0]
        for row in (
            db.query(RevenueOccurrence.id)
            .filter(RevenueOccurrence.professional_id.in_(professional_ids))
            .all()
        )
    ]
    participant_ids = [
        row[0]
        for row in (
            db.query(RevenueOccurrenceParticipant.id)
            .filter(
                RevenueOccurrenceParticipant.occurrence_id.in_(occurrence_ids)
            )
            .all()
        )
    ]
    if participant_ids:
        db.query(RevenueOccurrenceLine).filter(
            RevenueOccurrenceLine.participant_snapshot_id.in_(participant_ids)
        ).delete(synchronize_session=False)
    if occurrence_ids:
        db.query(RevenueOccurrenceParticipant).filter(
            RevenueOccurrenceParticipant.occurrence_id.in_(occurrence_ids)
        ).delete(synchronize_session=False)
    db.query(RevenueOccurrence).filter(
        RevenueOccurrence.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(FinancialChangeAuditLog).filter(
        FinancialChangeAuditLog.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(PlaceFinancialRate).filter(
        PlaceFinancialRate.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(FinancialRate).filter(
        FinancialRate.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(RecurringSlotParticipant).filter(
        RecurringSlotParticipant.recurring_slot_id.in_(
            db.query(RecurringSlot.id).filter(
                RecurringSlot.professional_id.in_(professional_ids)
            )
        )
    ).delete(synchronize_session=False)
    db.query(RecurringSlot).filter(
        RecurringSlot.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(Appointment).filter(
        Appointment.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(Contact).filter(
        Contact.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(Place).filter(
        Place.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(TenantFeature).filter(
        TenantFeature.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.query(Professional).filter(
        Professional.id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.commit()


def test_revenue_confirmation_snapshots_reporting_and_tenant_scope() -> None:
    db = SessionLocal()
    professional, owner, admin, cookies = _create_tenant(db)
    other_professional, other_owner, other_admin, other_cookies = _create_tenant(
        db
    )
    try:
        place = Place(professional_id=professional.id, name="Clube central", normalized_name="clube central")
        contacts = [
            Contact(
                professional_id=professional.id,
                phone=f"+55119{uuid.uuid4().hex[:8]}",
                display_name=name,
                normalized_name=name.lower(),
                hourly_rate_cents=rate,
            )
            for name, rate in (
                ("Ana", 3000),
                ("Bruno", None),
                ("Carla", None),
            )
        ]
        db.add_all([place, *contacts])
        db.flush()
        today = datetime.now(TIMEZONE).date()
        monday = today - timedelta(days=today.weekday())
        created_at = datetime.combine(
            monday - timedelta(days=7),
            time(12),
            tzinfo=TIMEZONE,
        )
        group = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=0,
            start_time=time(7, 30),
            end_time=time(8, 30),
            label="Grupo manhã",
            class_type="group",
            slot_kind="class",
            max_participants=4,
            recurrence_type="weekly",
            hourly_rate_cents=1200,
            created_at=created_at,
        )
        appointment_start = datetime.combine(
            monday,
            time(10),
            tzinfo=TIMEZONE,
        )
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contacts[2].id,
            place_id=place.id,
            service="Aula individual",
            start_at=appointment_start,
            end_at=appointment_start + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
        )
        db.add_all([group, appointment])
        db.flush()
        db.add_all(
            [
                RecurringSlotParticipant(
                    recurring_slot_id=group.id,
                    contact_id=contact.id,
                )
                for contact in contacts
            ]
        )
        db.add_all(
            [
                FinancialRate(
                    professional_id=professional.id,
                    participant_count=count,
                    hourly_rate_cents=rate,
                )
                for count, rate in ((1, 1000), (2, 800), (3, 700), (4, 600))
            ]
        )
        db.add_all(
            [
                PlaceFinancialRate(
                    professional_id=professional.id,
                    place_id=place.id,
                    time_category=category,
                    participant_count=1,
                    hourly_rate_cents=rate,
                )
                for category, rate in (("regular", 1500), ("prime", 2000))
            ]
        )
        db.commit()

        params = {
            "date_from": monday.isoformat(),
            "date_to": monday.isoformat(),
        }
        candidates = client.get(
            "/api/financial/revenue/candidates",
            params=params,
            cookies=cookies,
        )
        assert candidates.status_code == 200
        candidate_body = candidates.json()
        assert candidate_body["total"] == 2
        assert {
            candidate["source_type"] for candidate in candidate_body["candidates"]
        } == {"appointment", "recurring_slot"}

        group_confirmation = {
            "source_type": "recurring_slot",
            "source_id": str(group.id),
            "occurrence_date": monday.isoformat(),
            "participant_outcomes": [
                {
                    "contact_id": str(contacts[0].id),
                    "attendance_status": "attended",
                    "billable": True,
                },
                {
                    "contact_id": str(contacts[1].id),
                    "attendance_status": "attended",
                    "billable": True,
                },
                {
                    "contact_id": str(contacts[2].id),
                    "attendance_status": "no_show",
                    "billable": False,
                },
            ],
            "adjustment_cents": -200,
            "note": "Desconto acordado",
        }
        confirmed_group = client.post(
            "/api/financial/revenue/occurrences",
            json=group_confirmation,
            cookies=cookies,
        )
        assert confirmed_group.status_code == 201
        group_body = confirmed_group.json()
        assert group_body["outcome_status"] == "mixed"
        assert group_body["participant_count"] == 3
        assert group_body["billable_participant_count"] == 2
        assert group_body["quoted_total_cents"] == 5400
        assert group_body["subtotal_cents"] == 4200
        assert group_body["adjustment_cents"] == -200
        assert group_body["total_cents"] == 4000
        group_participants = {
            participant["contact_name"]: participant
            for participant in group_body["participants"]
        }
        assert group_participants["Ana"]["billed_amount_cents"] == 3000
        assert {
            line["rate_source"]
            for line in group_participants["Ana"]["pricing_lines"]
        } == {"customer"}
        assert group_participants["Bruno"]["billed_amount_cents"] == 1200
        assert {
            line["rate_source"]
            for line in group_participants["Bruno"]["pricing_lines"]
        } == {"group"}
        assert group_participants["Carla"]["quoted_amount_cents"] == 1200
        assert group_participants["Carla"]["billed_amount_cents"] == 0

        duplicate = client.post(
            "/api/financial/revenue/occurrences",
            json=group_confirmation,
            cookies=cookies,
        )
        assert duplicate.status_code == 409

        appointment_confirmation = {
            "source_type": "appointment",
            "source_id": str(appointment.id),
            "occurrence_date": monday.isoformat(),
            "participant_outcomes": [
                {
                    "contact_id": str(contacts[2].id),
                    "attendance_status": "attended",
                    "billable": True,
                }
            ],
        }
        confirmed_appointment = client.post(
            "/api/financial/revenue/occurrences",
            json=appointment_confirmation,
            cookies=cookies,
        )
        assert confirmed_appointment.status_code == 201
        appointment_body = confirmed_appointment.json()
        assert appointment_body["total_cents"] == 1500
        appointment_line = appointment_body["participants"][0]["pricing_lines"][0]
        assert appointment_line["rate_source"] == "place"
        assert appointment_line["time_category"] == "regular"

        contacts[0].hourly_rate_cents = 9999
        group.hourly_rate_cents = 9999
        db.commit()
        frozen = client.get(
            f"/api/financial/revenue/occurrences/{group_body['id']}",
            cookies=cookies,
        )
        assert frozen.status_code == 200
        assert frozen.json()["total_cents"] == 4000
        assert frozen.json()["participants"] == group_body["participants"]

        summary = client.get(
            "/api/financial/revenue/summary",
            params=params,
            cookies=cookies,
        )
        assert summary.status_code == 200
        summary_body = summary.json()
        assert summary_body["occurrence_count"] == 2
        assert summary_body["participant_count"] == 4
        assert summary_body["billable_participant_count"] == 3
        assert summary_body["quoted_total_cents"] == 6900
        assert summary_body["subtotal_cents"] == 5700
        assert summary_body["adjustment_cents"] == -200
        assert summary_body["total_cents"] == 5500
        assert summary_body["by_place"][0]["total_cents"] == 5500
        assert summary_body["by_group"][0]["total_cents"] == 4000
        assert summary_body["time_series"][0]["total_cents"] == 5500

        refreshed_candidates = client.get(
            "/api/financial/revenue/candidates",
            params=params,
            cookies=cookies,
        ).json()["candidates"]
        assert all(
            candidate["recognized_occurrence_id"] is not None
            for candidate in refreshed_candidates
        )
        hidden = client.get(
            f"/api/financial/revenue/occurrences/{group_body['id']}",
            cookies=other_cookies,
        )
        assert hidden.status_code == 404
        other_summary = client.get(
            "/api/financial/revenue/summary",
            params=params,
            cookies=other_cookies,
        )
        assert other_summary.status_code == 200
        assert other_summary.json()["total_cents"] == 0
        assert (
            db.query(FinancialChangeAuditLog)
            .filter(
                FinancialChangeAuditLog.professional_id == professional.id,
                FinancialChangeAuditLog.entity_type == "revenue_occurrence",
            )
            .count()
            == 2
        )
    finally:
        _cleanup(
            db,
            [professional, other_professional],
            [owner, admin, other_owner, other_admin],
        )
        db.close()

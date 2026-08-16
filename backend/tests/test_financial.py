"""Integration tests for optional commercial-financial inheritance."""

from pathlib import Path
import sys
import uuid
from datetime import date, datetime, time, timezone

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
    FinancialScenario,
    Place,
    PlaceFinancialRate,
    PrimeTimeWindow,
    Professional,
    ProfessionalFinancialSettings,
    RecurringSlot,
    RecurringSlotParticipant,
    TenantFeature,
    TenantFeatureAuditLog,
    User,
    WorkJourneyInterval,
)
from app.services.financial_capacity import build_capacity_segments, load_prime_ranges

client = TestClient(app)


def _random_email() -> str:
    return f"financial_{uuid.uuid4().hex[:10]}@agenda.ai"


def _minutes_between(start: str, end: str) -> int:
    start_hour, start_minute, *_ = start.split(":")
    end_hour, end_minute, *_ = end.split(":")
    return (
        int(end_hour) * 60
        + int(end_minute)
        - int(start_hour) * 60
        - int(start_minute)
    )

def _create_tenant(db, *, enabled: bool):
    professional = Professional(
        name="Tenant Financeiro",
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
    admin = User(
        email=_random_email(),
        hashed_password=hash_password("correct-password"),
        role="platform_admin",
    )
    db.add_all([owner, admin])
    db.commit()
    if enabled:
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


def _cleanup(db, *, professionals, users) -> None:
    professional_ids = [professional.id for professional in professionals]
    user_ids = [user.id for user in users]
    if professional_ids:
        db.query(FinancialScenario).filter(
            FinancialScenario.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(FinancialChangeAuditLog).filter(
            FinancialChangeAuditLog.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(PlaceFinancialRate).filter(
            PlaceFinancialRate.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(PrimeTimeWindow).filter(
            PrimeTimeWindow.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(WorkJourneyInterval).filter(
            WorkJourneyInterval.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(FinancialRate).filter(
            FinancialRate.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(ProfessionalFinancialSettings).filter(
            ProfessionalFinancialSettings.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(TenantFeatureAuditLog).filter(
            TenantFeatureAuditLog.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(TenantFeature).filter(
            TenantFeature.professional_id.in_(professional_ids)
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
        db.query(Contact).filter(
            Contact.professional_id.in_(professional_ids)
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


def test_capacity_uses_stays_not_recurring_classes() -> None:
    db = SessionLocal()
    professional, owner, admin, _ = _create_tenant(db, enabled=True)
    try:
        place = Place(
            professional_id=professional.id,
            name="Clube",
            normalized_name="clube",
        )
        contact = Contact(
            professional_id=professional.id,
            phone=f"+55119{uuid.uuid4().hex[:8]}",
            display_name="Aluno",
            normalized_name="aluno",
        )
        db.add_all([place, contact])
        db.flush()
        db.add(
            WorkJourneyInterval(
                professional_id=professional.id,
                day_of_week=0,
                interval_type="work",
                start_time=time(8),
                end_time=time(10),
            )
        )
        stay = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=0,
            start_time=time(8),
            end_time=time(9),
            slot_kind="availability",
            created_at=datetime(2026, 8, 3, 8, tzinfo=timezone.utc),
        )
        recurring_class = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=0,
            start_time=time(9),
            end_time=time(10),
            slot_kind="class",
            class_type="group",
            max_participants=4,
            created_at=datetime(2026, 8, 3, 8, tzinfo=timezone.utc),
        )
        db.add_all([stay, recurring_class])
        db.flush()
        db.add(
            RecurringSlotParticipant(
                recurring_slot_id=recurring_class.id,
                contact_id=contact.id,
            )
        )
        db.commit()

        segments = build_capacity_segments(
            db,
            professional.id,
            date(2026, 8, 10),
            date(2026, 8, 10),
            [place],
            load_prime_ranges(db, professional.id),
        )

        assert sum(segment.duration_minutes for segment in segments) == 60
    finally:
        _cleanup(db, professionals=[professional], users=[owner, admin])
        db.close()


def test_financial_inheritance_zero_and_multi_group_context() -> None:
    db = SessionLocal()
    professional, owner, admin, cookies = _create_tenant(db, enabled=True)
    try:
        place = Place(professional_id=professional.id, name="Clube", normalized_name="clube")
        first = Contact(
            professional_id=professional.id,
            phone=f"+55119{uuid.uuid4().hex[:8]}",
            display_name="Cliente um",
            normalized_name="cliente um",
        )
        second = Contact(
            professional_id=professional.id,
            phone=f"+55119{uuid.uuid4().hex[:8]}",
            display_name="Cliente dois",
            normalized_name="cliente dois",
        )
        db.add_all([place, first, second])
        db.flush()
        group_one = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=0,
            start_time=time(18, 0),
            end_time=time(19, 0),
            class_type="group",
            slot_kind="class",
            max_participants=4,
            label="Grupo um",
        )
        group_two = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=1,
            start_time=time(18, 0),
            end_time=time(19, 0),
            class_type="group",
            slot_kind="class",
            max_participants=4,
            label="Grupo dois",
        )
        db.add_all([group_one, group_two])
        db.flush()
        db.add_all(
            [
                RecurringSlotParticipant(
                    recurring_slot_id=group_one.id,
                    contact_id=first.id,
                ),
                RecurringSlotParticipant(
                    recurring_slot_id=group_one.id,
                    contact_id=second.id,
                ),
                RecurringSlotParticipant(
                    recurring_slot_id=group_two.id,
                    contact_id=first.id,
                ),
            ]
        )
        db.commit()

        settings = client.patch(
            "/api/financial/settings",
            json={
                "default_commercial_status": "active",
                "rates": [
                    {"participant_count": 1, "hourly_rate_cents": 3000},
                    {"participant_count": 2, "hourly_rate_cents": 5000},
                ],
            },
            cookies=cookies,
        )
        assert settings.status_code == 200
        assert settings.json()["rates"] == [
            {"participant_count": 1, "hourly_rate_cents": 3000},
            {"participant_count": 2, "hourly_rate_cents": 5000},
            {"participant_count": 3, "hourly_rate_cents": None},
            {"participant_count": 4, "hourly_rate_cents": None},
        ]

        group_one_update = client.patch(
            f"/api/financial/groups/{group_one.id}",
            json={"commercial_status": "waiting"},
            cookies=cookies,
        )
        assert group_one_update.status_code == 200

        explicit_zero = client.patch(
            f"/api/financial/customers/{second.id}",
            json={"commercial_status": "paused", "hourly_rate_cents": 0},
            cookies=cookies,
        )
        assert explicit_zero.status_code == 200
        assert explicit_zero.json()["effective_hourly_rate_cents"] == 0
        assert explicit_zero.json()["hourly_rate_source"] == "customer"

        group_one_detail = client.get(
            f"/api/financial/groups/{group_one.id}",
            cookies=cookies,
        )
        assert group_one_detail.status_code == 200
        group_one_body = group_one_detail.json()
        assert group_one_body["effective_commercial_status"] == "waiting"
        assert group_one_body["commercial_status_source"] == "group"
        assert group_one_body["effective_hourly_rate_cents"] == 5000
        assert group_one_body["hourly_rate_source"] == "tenant"
        participants = {
            participant["contact_id"]: participant
            for participant in group_one_body["participants"]
        }
        assert participants[str(first.id)]["effective_commercial_status"] == "waiting"
        assert participants[str(first.id)]["effective_hourly_rate_cents"] == 5000
        assert participants[str(second.id)]["effective_commercial_status"] == "paused"
        assert participants[str(second.id)]["commercial_status_source"] == "customer"
        assert participants[str(second.id)]["effective_hourly_rate_cents"] == 0

        group_two_update = client.patch(
            f"/api/financial/groups/{group_two.id}",
            json={"commercial_status": "active", "hourly_rate_cents": 7000},
            cookies=cookies,
        )
        assert group_two_update.status_code == 200
        group_two_first = group_two_update.json()["participants"][0]
        assert group_two_first["contact_id"] == str(first.id)
        assert group_two_first["effective_commercial_status"] == "active"
        assert group_two_first["commercial_status_source"] == "group"
        assert group_two_first["effective_hourly_rate_cents"] == 7000
        assert group_two_first["hourly_rate_source"] == "group"

        outside_group = client.get(
            f"/api/financial/customers/{first.id}",
            cookies=cookies,
        )
        assert outside_group.status_code == 200
        assert outside_group.json()["effective_hourly_rate_cents"] == 3000
        assert outside_group.json()["hourly_rate_source"] == "tenant"

        cleared = client.patch(
            f"/api/financial/customers/{second.id}",
            json={"commercial_status": None, "hourly_rate_cents": None},
            cookies=cookies,
        )
        assert cleared.status_code == 200
        inherited_after_clear = client.get(
            f"/api/financial/groups/{group_one.id}",
            cookies=cookies,
        ).json()["participants"]
        cleared_participant = next(
            participant
            for participant in inherited_after_clear
            if participant["contact_id"] == str(second.id)
        )
        assert cleared_participant["effective_commercial_status"] == "waiting"
        assert cleared_participant["commercial_status_source"] == "group"
        assert cleared_participant["effective_hourly_rate_cents"] == 5000
        assert cleared_participant["hourly_rate_source"] == "tenant"

        audits = (
            db.query(FinancialChangeAuditLog)
            .filter(FinancialChangeAuditLog.professional_id == professional.id)
            .all()
        )
        assert len(audits) == 5
        assert {audit.actor_user_id for audit in audits} == {owner.id}
    finally:
        _cleanup(
            db,
            professionals=[professional],
            users=[owner, admin],
        )
        db.close()


def test_financial_endpoints_require_feature_and_tenant_scope() -> None:
    db = SessionLocal()
    disabled_professional, disabled_owner, disabled_admin, disabled_cookies = (
        _create_tenant(db, enabled=False)
    )
    enabled_professional, enabled_owner, enabled_admin, enabled_cookies = (
        _create_tenant(db, enabled=True)
    )
    try:
        disabled_response = client.get(
            "/api/financial/settings",
            cookies=disabled_cookies,
        )
        assert disabled_response.status_code == 404

        hidden_contact = Contact(
            professional_id=disabled_professional.id,
            phone=f"+55119{uuid.uuid4().hex[:8]}",
            display_name="Cliente oculto",
            normalized_name="cliente oculto",
        )
        db.add(hidden_contact)
        db.commit()
        cross_tenant = client.get(
            f"/api/financial/customers/{hidden_contact.id}",
            cookies=enabled_cookies,
        )
        assert cross_tenant.status_code == 404

        invalid_rate = client.patch(
            "/api/financial/settings",
            json={
                "rates": [
                    {
                        "participant_count": 1,
                        "hourly_rate_cents": 100_000_001,
                    }
                ]
            },
            cookies=enabled_cookies,
        )
        assert invalid_rate.status_code == 422
    finally:
        _cleanup(
            db,
            professionals=[disabled_professional, enabled_professional],
            users=[
                disabled_owner,
                disabled_admin,
                enabled_owner,
                enabled_admin,
            ],
        )
        db.close()


def test_financial_configuration_prime_place_and_journey() -> None:
    db = SessionLocal()
    professional, owner, admin, cookies = _create_tenant(db, enabled=True)
    try:
        place = Place(professional_id=professional.id, name="Arena", normalized_name="arena")
        db.add(place)
        db.commit()

        initial = client.get("/api/financial/configuration", cookies=cookies)
        assert initial.status_code == 200
        assert [
            (window["start_time"], window["end_time"], window["is_default"])
            for window in initial.json()["prime_time_windows"]
        ] == [
            ("05:00:00", "08:00:00", True),
            ("18:00:00", "21:00:00", True),
        ]

        overlap = client.put(
            "/api/financial/prime-time-windows",
            json={
                "windows": [
                    {
                        "days_of_week": [0],
                        "start_time": "05:00:00",
                        "end_time": "08:00:00",
                    },
                    {
                        "days_of_week": [0],
                        "start_time": "07:00:00",
                        "end_time": "09:00:00",
                    },
                ]
            },
            cookies=cookies,
        )
        assert overlap.status_code == 422

        prime = client.put(
            "/api/financial/prime-time-windows",
            json={
                "windows": [
                    {
                        "days_of_week": [0, 1, 2, 3, 4],
                        "start_time": "05:00:00",
                        "end_time": "08:00:00",
                    },
                    {
                        "days_of_week": [0, 1, 2, 3, 4],
                        "start_time": "18:00:00",
                        "end_time": "21:00:00",
                    },
                ]
            },
            cookies=cookies,
        )
        assert prime.status_code == 200
        assert all(window["is_default"] is False for window in prime.json())

        global_rates = client.patch(
            "/api/financial/settings",
            json={
                "rates": [
                    {"participant_count": 1, "hourly_rate_cents": 4000},
                    {"participant_count": 2, "hourly_rate_cents": 3000},
                ]
            },
            cookies=cookies,
        )
        assert global_rates.status_code == 200

        generic_rates = client.put(
            "/api/financial/generic-place/rates",
            json={
                "rates": [
                    {
                        "time_category": "regular",
                        "participant_count": 1,
                        "hourly_rate_cents": 4500,
                    },
                    {
                        "time_category": "prime",
                        "participant_count": 1,
                        "hourly_rate_cents": 5500,
                    },
                ]
            },
            cookies=cookies,
        )
        assert generic_rates.status_code == 200
        generic_matrix = {
            (rate["time_category"], rate["participant_count"]): rate
            for rate in generic_rates.json()["rates"]
        }
        assert generic_matrix[("regular", 1)]["source"] == "generic"
        assert generic_matrix[("regular", 1)]["effective_hourly_rate_cents"] == 4500

        generic_quote = client.post(
            "/api/financial/quote",
            json={
                "day_of_week": 0,
                "start_time": "07:30:00",
                "end_time": "08:30:00",
                "participant_count": 1,
            },
            cookies=cookies,
        )
        assert generic_quote.status_code == 200
        assert [
            (segment["time_category"], segment["hourly_rate_cents"], segment["source"])
            for segment in generic_quote.json()["segments"]
        ] == [
            ("prime", 5500, "generic"),
            ("regular", 4500, "generic"),
        ]

        place_rates = client.put(
            f"/api/financial/places/{place.id}/rates",
            json={
                "rates": [
                    {
                        "time_category": "regular",
                        "participant_count": 1,
                        "hourly_rate_cents": None,
                    },
                    {
                        "time_category": "prime",
                        "participant_count": 1,
                        "hourly_rate_cents": 6000,
                    },
                    {
                        "time_category": "regular",
                        "participant_count": 2,
                        "hourly_rate_cents": 0,
                    },
                ]
            },
            cookies=cookies,
        )
        assert place_rates.status_code == 200
        matrix = {
            (rate["time_category"], rate["participant_count"]): rate
            for rate in place_rates.json()["rates"]
        }
        assert matrix[("regular", 1)]["effective_hourly_rate_cents"] == 4000
        assert matrix[("regular", 1)]["source"] == "tenant"
        assert matrix[("prime", 1)]["effective_hourly_rate_cents"] == 6000
        assert matrix[("prime", 1)]["source"] == "place"
        assert matrix[("regular", 2)]["effective_hourly_rate_cents"] == 0
        assert matrix[("regular", 2)]["source"] == "place"

        quote = client.post(
            "/api/financial/quote",
            json={
                "place_id": str(place.id),
                "day_of_week": 0,
                "start_time": "07:30:00",
                "end_time": "08:30:00",
                "participant_count": 1,
            },
            cookies=cookies,
        )
        assert quote.status_code == 200
        assert [
            (
                segment["time_category"],
                segment["duration_minutes"],
                segment["hourly_rate_cents"],
                segment["source"],
                segment["segment_total_cents"],
            )
            for segment in quote.json()["segments"]
        ] == [
            ("prime", 30, 6000, "place", 3000),
            ("regular", 30, 4000, "tenant", 2000),
        ]
        assert quote.json()["total_cents"] == 5000

        invalid_break = client.put(
            "/api/rules/work-journey",
            json={
                "intervals": [
                    {
                        "day_of_week": 0,
                        "interval_type": "work",
                        "start_time": "08:00:00",
                        "end_time": "17:00:00",
                    },
                    {
                        "day_of_week": 0,
                        "interval_type": "break",
                        "start_time": "17:00:00",
                        "end_time": "18:00:00",
                    },
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
                        "day_of_week": 0,
                        "interval_type": "work",
                        "start_time": "08:00:00",
                        "end_time": "17:00:00",
                    },
                    {
                        "day_of_week": 0,
                        "interval_type": "break",
                        "start_time": "12:00:00",
                        "end_time": "13:00:00",
                    },
                    {
                        "day_of_week": 5,
                        "interval_type": "work",
                        "start_time": "09:00:00",
                        "end_time": "12:00:00",
                    },
                ]
            },
            cookies=cookies,
        )
        assert journey.status_code == 200
        assert len(journey.json()) == 3

        cleared_prime = client.put(
            "/api/financial/prime-time-windows",
            json={"windows": []},
            cookies=cookies,
        )
        assert cleared_prime.status_code == 200
        assert cleared_prime.json() == []
        after_clear = client.get(
            "/api/financial/configuration",
            cookies=cookies,
        )
        assert after_clear.json()["prime_time_windows"] == []

        audited_types = {
            row.entity_type
            for row in (
                db.query(FinancialChangeAuditLog)
                .filter(FinancialChangeAuditLog.professional_id == professional.id)
                .all()
            )
        }
        assert {
            "tenant_financial_settings",
            "prime_time_windows",
            "place_financial_rates",
            "work_journey",
        }.issubset(audited_types)
    finally:
        _cleanup(
            db,
            professionals=[professional],
            users=[owner, admin],
        )
        db.close()


def test_financial_dashboard_capacity_scenarios_and_tenant_scope() -> None:
    db = SessionLocal()
    professional, owner, admin, cookies = _create_tenant(db, enabled=True)
    other_professional, other_owner, other_admin, other_cookies = _create_tenant(
        db,
        enabled=True,
    )
    try:
        place = Place(professional_id=professional.id, name="Arena principal", normalized_name="arena principal")
        other_place = Place(
            professional_id=other_professional.id,
            name="Arena de outro tenant",
            normalized_name="arena de outro tenant",
        )
        first = Contact(
            professional_id=professional.id,
            phone=f"+55119{uuid.uuid4().hex[:8]}",
            display_name="Cliente A",
            normalized_name="cliente a",
        )
        second = Contact(
            professional_id=professional.id,
            phone=f"+55119{uuid.uuid4().hex[:8]}",
            display_name="Cliente B",
            normalized_name="cliente b",
        )
        db.add_all([place, other_place, first, second])
        db.flush()
        slot_start = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)
        availability = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=0,
            start_time=time(8),
            end_time=time(12),
            class_type="individual",
            max_participants=1,
            recurrence_type="weekly",
            created_at=slot_start,
        )
        group = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=0,
            start_time=time(9),
            end_time=time(10),
            class_type="group",
            slot_kind="class",
            max_participants=4,
            recurrence_type="weekly",
            created_at=slot_start,
            label="Dupla",
        )
        db.add_all([availability, group])
        db.flush()
        db.add_all(
            [
                RecurringSlotParticipant(
                    recurring_slot_id=group.id,
                    contact_id=first.id,
                ),
                RecurringSlotParticipant(
                    recurring_slot_id=group.id,
                    contact_id=second.id,
                ),
            ]
        )
        db.commit()

        rates = client.patch(
            "/api/financial/settings",
            json={
                "rates": [
                    {"participant_count": 1, "hourly_rate_cents": 1000},
                    {"participant_count": 2, "hourly_rate_cents": 800},
                    {"participant_count": 3, "hourly_rate_cents": 700},
                    {"participant_count": 4, "hourly_rate_cents": 600},
                ]
            },
            cookies=cookies,
        )
        assert rates.status_code == 200
        journey = client.put(
            "/api/rules/work-journey",
            json={
                "intervals": [
                    {
                        "day_of_week": 0,
                        "interval_type": "work",
                        "start_time": "08:00:00",
                        "end_time": "12:00:00",
                    }
                ]
            },
            cookies=cookies,
        )
        assert journey.status_code == 200
        prime = client.put(
            "/api/financial/prime-time-windows",
            json={
                "windows": [
                    {
                        "days_of_week": [0],
                        "start_time": "10:00:00",
                        "end_time": "11:00:00",
                    }
                ]
            },
            cookies=cookies,
        )
        assert prime.status_code == 200

        dashboard = client.get(
            "/api/financial/dashboard",
            params={"date_from": "2026-08-10", "date_to": "2026-08-10"},
            cookies=cookies,
        )
        assert dashboard.status_code == 200
        body = dashboard.json()
        assert body["available_minutes"] == 240
        assert body["booked_minutes"] == 60
        assert body["unused_minutes"] == 180
        assert body["occupancy_pct"] == 25
        assert body["participant_hours"] == 2
        assert body["projected_revenue_cents"] == 1600
        assert body["unpriced_booking_count"] == 0
        assert body["observed_participant_mix"] == [
            {"participant_count": 2, "percentage": 100}
        ]
        assert body["time_series"] == [
            {
                "date": "2026-08-10",
                "available_minutes": 240,
                "booked_minutes": 60,
                "projected_revenue_cents": 1600,
            }
        ]
        presets = {
            preset["key"]: preset for preset in body["capacity_presets"]
        }
        assert presets["all_individual"]["projected_revenue_cents"] == 4000
        assert presets["full_groups"]["projected_revenue_cents"] == 9600

        group_preview = client.get(
            "/api/financial/revenue/preview",
            params={
                "source_type": "recurring_slot",
                "source_id": str(group.id),
                "occurrence_date": "2026-08-10",
            },
            cookies=cookies,
        )
        assert group_preview.status_code == 200
        assert group_preview.json() == {
            "estimated_revenue_cents": 1600,
            "participant_count": 2,
            "capacity_revenue_cents": 2400,
        }

        scenario_input = {
            "name": "Preço e mix alternativos",
            "date_from": "2026-08-10",
            "date_to": "2026-08-10",
            "place_ids": [str(place.id)],
            "mode": "custom",
            "occupancy_pct": 80,
            "participant_mix": [
                {"participant_count": 1, "percentage": 50},
                {"participant_count": 4, "percentage": 50},
            ],
            "rate_overrides": [
                {
                    "time_category": category,
                    "participant_count": participant_count,
                    "hourly_rate_cents": rate,
                }
                for category in ("regular", "prime")
                for participant_count, rate in ((1, 2000), (4, 500))
            ],
        }
        evaluated = client.post(
            "/api/financial/scenarios/evaluate",
            json=scenario_input,
            cookies=cookies,
        )
        assert evaluated.status_code == 200
        result = evaluated.json()
        assert result["scenario"]["available_minutes"] == 240
        assert result["scenario"]["utilized_minutes"] == 180
        assert result["scenario"]["participant_hours"] == 6
        assert result["scenario"]["projected_revenue_cents"] == 6000
        assert result["incremental_revenue_cents"] == 4400
        assert result["customer_estimate"] == {
            "calendar_weeks": 1,
            "weekly_participant_hours": 6,
            "minimum_customers": 2,
            "maximum_customers": 6,
        }
        simulated_schedule = result["simulated_schedule"]
        assert sum(
            _minutes_between(item["start_time"], item["end_time"])
            for item in simulated_schedule
        ) == 180
        assert {item["participant_count"] for item in simulated_schedule} == {1, 4}
        assert {item["place_name"] for item in simulated_schedule} == {
            "Arena principal"
        }
        assert all(item["hourly_rate_cents"] is not None for item in simulated_schedule)
        assert sum(item["total_revenue_cents"] for item in simulated_schedule) == 6000
        group_tradeoff = next(
            item for item in result["tradeoffs"] if item["participant_count"] == 4
        )
        assert group_tradeoff["full_class_revenue_cents"] == 2000
        assert group_tradeoff["break_even_occupancy_pct"] == 100

        prime_groups = client.post(
            "/api/financial/scenarios/evaluate",
            json={
                **scenario_input,
                "mode": "individual_regular_groups_prime",
                "occupancy_pct": 100,
                "participant_mix": None,
            },
            cookies=cookies,
        )
        assert prime_groups.status_code == 200
        assert prime_groups.json()["scenario"] == {
            "available_minutes": 240,
            "utilized_minutes": 240,
            "occupancy_pct": 100,
            "participant_hours": 7,
            "projected_revenue_cents": 8000,
        }
        assert {
            (event["time_category"], event["participant_count"])
            for event in prime_groups.json()["simulated_schedule"]
        } == {("regular", 1), ("prime", 4)}

        saved = client.post(
            "/api/financial/scenarios",
            json=scenario_input,
            cookies=cookies,
        )
        assert saved.status_code == 201
        assert saved.json()["result_snapshot"] == result
        listed = client.get("/api/financial/scenarios", cookies=cookies)
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["scenarios"]] == [
            saved.json()["id"]
        ]
        other_list = client.get(
            "/api/financial/scenarios",
            cookies=other_cookies,
        )
        assert other_list.status_code == 200
        assert other_list.json()["scenarios"] == []

        hidden_place = client.get(
            "/api/financial/dashboard",
            params={
                "date_from": "2026-08-10",
                "date_to": "2026-08-10",
                "place_id": str(other_place.id),
            },
            cookies=cookies,
        )
        assert hidden_place.status_code == 404
        invalid_period = client.get(
            "/api/financial/dashboard",
            params={"date_from": "2026-08-11", "date_to": "2026-08-10"},
            cookies=cookies,
        )
        assert invalid_period.status_code == 422
        blank_name = client.post(
            "/api/financial/scenarios/evaluate",
            json={**scenario_input, "name": "   "},
            cookies=cookies,
        )
        assert blank_name.status_code == 422

        scenario_row = (
            db.query(FinancialScenario)
            .filter(FinancialScenario.id == uuid.UUID(saved.json()["id"]))
            .one()
        )
        assert scenario_row.created_by_user_id == owner.id
        assert (
            db.query(FinancialChangeAuditLog)
            .filter(
                FinancialChangeAuditLog.entity_type == "financial_scenario",
                FinancialChangeAuditLog.entity_id == scenario_row.id,
            )
            .count()
            == 1
        )
    finally:
        _cleanup(
            db,
            professionals=[professional, other_professional],
            users=[owner, admin, other_owner, other_admin],
        )
        db.close()


def test_financial_dashboard_top_line_uses_work_journey_not_recurring_slots() -> None:
    """Top-line available/booked/occupancy must reflect the instructor's
    declared work journey even when no (or only partial) RecurringSlot
    coverage exists for a place — RecurringSlot is only required for the
    by-place/by-weekday/etc. breakdowns, which need a place to attribute
    hours to. See docs/business_rules.md 'Financial capacity vs. work
    journey'."""
    db = SessionLocal()
    professional, owner, admin, cookies = _create_tenant(db, enabled=True)
    try:
        place = Place(
            professional_id=professional.id,
            name="Quadra única",
            normalized_name="quadra unica",
        )
        contact = Contact(
            professional_id=professional.id,
            phone=f"+55119{uuid.uuid4().hex[:8]}",
            display_name="Cliente Solo",
            normalized_name="cliente solo",
        )
        db.add_all([place, contact])
        db.flush()

        rates = client.patch(
            "/api/financial/settings",
            json={"rates": [{"participant_count": 1, "hourly_rate_cents": 1000}]},
            cookies=cookies,
        )
        assert rates.status_code == 200

        # Full-day work journey, Monday only — no RecurringSlot at all.
        journey = client.put(
            "/api/rules/work-journey",
            json={
                "intervals": [
                    {
                        "day_of_week": 0,
                        "interval_type": "work",
                        "start_time": "08:00:00",
                        "end_time": "12:00:00",
                    }
                ]
            },
            cookies=cookies,
        )
        assert journey.status_code == 200

        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            place_id=place.id,
            start_at=datetime(2026, 8, 10, 9, tzinfo=timezone.utc),
            end_at=datetime(2026, 8, 10, 10, tzinfo=timezone.utc),
            status="confirmed",
            service="Aula individual",
        )
        db.add(appointment)
        db.commit()

        dashboard = client.get(
            "/api/financial/dashboard",
            params={"date_from": "2026-08-10", "date_to": "2026-08-10"},
            cookies=cookies,
        )
        assert dashboard.status_code == 200
        body = dashboard.json()
        # Work journey is 4h (240min); with zero RecurringSlot coverage the
        # old segment-based calculation would have reported 0 here.
        assert body["available_minutes"] == 240
        assert body["booked_minutes"] == 60
        assert body["occupancy_pct"] == 25.0
        assert body["projected_revenue_cents"] == 1000

        preview = client.get(
            "/api/financial/revenue/preview",
            params={
                "source_type": "appointment",
                "source_id": str(appointment.id),
                "occurrence_date": "2026-08-10",
            },
            cookies=cookies,
        )
        assert preview.status_code == 200
        assert preview.json() == {
            "estimated_revenue_cents": 1000,
            "participant_count": 1,
        }

        # The by-place breakdown still correctly reports zero — it needs an
        # explicit RecurringSlot to attribute hours to that place.
        assert all(row["available_minutes"] == 0 for row in body["by_place"])

        # "Potencial com 100% da capacidade" must price the uncovered
        # work-journey time (240min) against the global rate too, not
        # just the (empty) RecurringSlot-scoped segments.
        all_individual = next(
            preset
            for preset in body["capacity_presets"]
            if preset["key"] == "all_individual"
        )
        assert all_individual["projected_revenue_cents"] == 4000

        scenario = client.post(
            "/api/financial/scenarios/evaluate",
            json={
                "name": "Jornada sem local",
                "date_from": "2026-08-10",
                "date_to": "2026-08-10",
                "mode": "all_individual",
                "occupancy_pct": 100,
                "rate_overrides": [],
            },
            cookies=cookies,
        )
        assert scenario.status_code == 200
        assert scenario.json()["scenario"] == {
            "available_minutes": 240,
            "utilized_minutes": 240,
            "occupancy_pct": 100,
            "participant_hours": 4,
            "projected_revenue_cents": 4000,
        }
        assert {event["place_name"] for event in scenario.json()["simulated_schedule"]} == {
            "Sem local definido"
        }

        # With a place filter applied, top-line figures must fall back to
        # the place-scoped (RecurringSlot-based) accounting — otherwise
        # a place-filtered booked_minutes would be compared against a
        # tenant-wide available_minutes.
        filtered = client.get(
            "/api/financial/dashboard",
            params={
                "date_from": "2026-08-10",
                "date_to": "2026-08-10",
                "place_id": str(place.id),
            },
            cookies=cookies,
        )
        assert filtered.status_code == 200
        filtered_body = filtered.json()
        assert filtered_body["available_minutes"] == 0
        assert filtered_body["booked_minutes"] == 0
        assert filtered_body["occupancy_pct"] == 0
    finally:
        db.query(Appointment).filter(
            Appointment.professional_id == professional.id
        ).delete(synchronize_session=False)
        _cleanup(db, professionals=[professional], users=[owner, admin])
        db.close()

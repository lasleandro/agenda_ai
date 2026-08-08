"""Tests for the make-up class credit ledger, the group-vs-single-participant
cancellation distinction (propose_cancel_schedule vs
propose_note_participant_absence), credit discovery/redemption, and
courtesy-billing revenue confirmation.
"""

from pathlib import Path
import sys
import uuid
from datetime import date, datetime, time, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.agent import candidates, mutations, tools
from app.core.security import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import (
    Appointment,
    AppointmentTransition,
    Contact,
    FinancialChangeAuditLog,
    FinancialRate,
    MakeupClassCredit,
    OperationalEvent,
    OperatorActionCandidate,
    Place,
    Professional,
    RecurringSlot,
    RecurringSlotParticipant,
    RevenueOccurrence,
    RevenueOccurrenceLine,
    RevenueOccurrenceParticipant,
    ScheduleOccurrenceOverride,
    TenantFeature,
    User,
)
from app.services.makeup_credits import has_sufficient_cancellation_notice
from app.services.scheduling import TIMEZONE, list_schedule_occurrences

client = TestClient(app)

MONDAY = date(2026, 8, 3)


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().hex[:8]}"


def _random_email() -> str:
    return f"makeup_{uuid.uuid4().hex[:10]}@agenda.ai"


def _make_tenant(db) -> tuple[Professional, User]:
    professional = Professional(name="Tenant Makeup", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    user = User(
        email=_random_email(),
        hashed_password=hash_password("correct-password"),
        role="professional",
        professional_id=professional.id,
    )
    db.add(user)
    db.commit()
    db.add(
        TenantFeature(
            professional_id=professional.id,
            feature_key="commercial_financials",
            enabled=True,
            configured_by_user_id=user.id,
        )
    )
    db.commit()
    return professional, user


def _make_place(db, professional_id) -> Place:
    place = Place(professional_id=professional_id, name="Clube", normalized_name="clube")
    db.add(place)
    db.commit()
    return place


def _make_contact(db, professional_id, display_name: str) -> Contact:
    contact = Contact(
        professional_id=professional_id,
        phone=_random_phone(),
        display_name=display_name,
        normalized_name=display_name.casefold(),
    )
    db.add(contact)
    db.commit()
    return contact


def _make_group_slot(db, professional_id, place_id, *, day_of_week=MONDAY.weekday()) -> RecurringSlot:
    slot = RecurringSlot(
        professional_id=professional_id,
        place_id=place_id,
        day_of_week=day_of_week,
        start_time=time(8, 0),
        end_time=time(9, 0),
        class_type="group",
        slot_kind="class",
        max_participants=4,
        recurrence_type="weekly",
        created_at=datetime.combine(MONDAY - timedelta(days=30), time(8), tzinfo=TIMEZONE),
    )
    db.add(slot)
    db.commit()
    return slot


def _enroll(db, slot_id, contact_id) -> None:
    db.add(RecurringSlotParticipant(recurring_slot_id=slot_id, contact_id=contact_id))
    db.commit()


def _cleanup(db, *, professionals: list[Professional], users: list[User]) -> None:
    professional_ids = [p.id for p in professionals]
    user_ids = [u.id for u in users]
    if professional_ids:
        occurrence_ids = [
            row[0]
            for row in db.query(RevenueOccurrence.id)
            .filter(RevenueOccurrence.professional_id.in_(professional_ids))
            .all()
        ]
        participant_ids = [
            row[0]
            for row in db.query(RevenueOccurrenceParticipant.id)
            .filter(RevenueOccurrenceParticipant.occurrence_id.in_(occurrence_ids))
            .all()
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
        db.query(FinancialRate).filter(
            FinancialRate.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(FinancialChangeAuditLog).filter(
            FinancialChangeAuditLog.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(MakeupClassCredit).filter(
            MakeupClassCredit.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(OperationalEvent).filter(
            OperationalEvent.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(OperatorActionCandidate).filter(
            OperatorActionCandidate.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(ScheduleOccurrenceOverride).filter(
            ScheduleOccurrenceOverride.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(AppointmentTransition).filter(
            AppointmentTransition.appointment_id.in_(
                db.query(Appointment.id).filter(
                    Appointment.professional_id.in_(professional_ids)
                )
            )
        ).delete(synchronize_session=False)
        db.query(Appointment).filter(
            Appointment.professional_id.in_(professional_ids)
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
        db.query(Contact).filter(Contact.professional_id.in_(professional_ids)).delete(
            synchronize_session=False
        )
        db.query(Place).filter(Place.professional_id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    if professional_ids:
        db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    db.commit()


# ---------------------------------------------------------------------------
# has_sufficient_cancellation_notice (pure function)
# ---------------------------------------------------------------------------

def test_has_sufficient_cancellation_notice_boundary() -> None:
    class_start = datetime(2026, 8, 10, 15, 0, tzinfo=TIMEZONE)
    assert has_sufficient_cancellation_notice(
        class_start, class_start - timedelta(hours=25), 24
    ) is True
    assert has_sufficient_cancellation_notice(
        class_start, class_start - timedelta(hours=23), 24
    ) is False
    assert has_sufficient_cancellation_notice(
        class_start, class_start - timedelta(minutes=1), 0
    ) is True


# ---------------------------------------------------------------------------
# propose_cancel_schedule on a group occurrence — grants credit to everyone
# (correct when the whole class doesn't happen)
# ---------------------------------------------------------------------------

def test_cancel_whole_group_occurrence_grants_credit_to_every_participant() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        slot = _make_group_slot(db, professional.id, place.id)
        students = [_make_contact(db, professional.id, name) for name in ("Ana", "Beto", "Cris")]
        for student in students:
            _enroll(db, slot.id, student.id)

        target_date = MONDAY + timedelta(days=14)
        result = mutations.propose_cancel_schedule(
            db, professional.id, user.id, uuid.uuid4(),
            target_type="recurring_slot", target_id=str(slot.id),
            occurrence_date=target_date.isoformat(),
        )
        assert result["requires_confirmation"] is True
        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        credits = (
            db.query(MakeupClassCredit)
            .filter(
                MakeupClassCredit.origin_recurring_slot_id == slot.id,
                MakeupClassCredit.origin_occurrence_date == target_date,
            )
            .all()
        )
        assert {c.contact_id for c in credits} == {s.id for s in students}
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


# ---------------------------------------------------------------------------
# propose_note_participant_absence — the fix: only the named participant
# earns a credit, and the class stays on the calendar for everyone else.
# ---------------------------------------------------------------------------

def test_note_participant_absence_only_credits_that_participant() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        slot = _make_group_slot(db, professional.id, place.id)
        ana = _make_contact(db, professional.id, "Ana")
        beto = _make_contact(db, professional.id, "Beto")
        _enroll(db, slot.id, ana.id)
        _enroll(db, slot.id, beto.id)

        target_date = MONDAY + timedelta(days=14)
        result = mutations.propose_note_participant_absence(
            db, professional.id, user.id, uuid.uuid4(),
            contact_id=str(ana.id), recurring_slot_id=str(slot.id),
            occurrence_date=target_date.isoformat(),
        )
        assert result["requires_confirmation"] is True
        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True
        assert "Crédito de reposição gerado" in exec_result.summary

        credits = (
            db.query(MakeupClassCredit)
            .filter(
                MakeupClassCredit.origin_recurring_slot_id == slot.id,
                MakeupClassCredit.origin_occurrence_date == target_date,
            )
            .all()
        )
        assert len(credits) == 1
        assert credits[0].contact_id == ana.id

        # The occurrence itself is untouched — no override, still on the
        # calendar with both participants (the class runs as normal).
        assert (
            db.query(ScheduleOccurrenceOverride)
            .filter(ScheduleOccurrenceOverride.recurring_slot_id == slot.id)
            .count()
            == 0
        )
        occurrences = list_schedule_occurrences(db, professional.id, target_date, target_date)
        assert len(occurrences) == 1
        assert {p.contact_id for p in occurrences[0].participants} == {ana.id, beto.id}
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_note_participant_absence_respects_notice_window() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        # A class starting in 1h today — well inside the default 24h
        # notice window, so reporting the absence now should not grant a
        # credit. Deterministic (no dependence on which weekday "today" is
        # relative to a fixed anchor date).
        now_local = datetime.now(TIMEZONE)
        soon = now_local + timedelta(hours=1)
        slot = _make_group_slot(
            db, professional.id, place.id, day_of_week=now_local.weekday()
        )
        slot.start_time = soon.time().replace(microsecond=0)
        slot.end_time = (soon + timedelta(hours=1)).time().replace(microsecond=0)
        db.commit()
        ana = _make_contact(db, professional.id, "Ana")
        _enroll(db, slot.id, ana.id)

        result = mutations.propose_note_participant_absence(
            db, professional.id, user.id, uuid.uuid4(),
            contact_id=str(ana.id), recurring_slot_id=str(slot.id),
            occurrence_date=now_local.date().isoformat(),
        )
        assert result["requires_confirmation"] is True
        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True
        assert "Sem crédito de reposição" in exec_result.summary
        assert (
            db.query(MakeupClassCredit)
            .filter(MakeupClassCredit.contact_id == ana.id)
            .count()
            == 0
        )
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


# ---------------------------------------------------------------------------
# list_makeup_credits + propose_redeem_makeup_credit — end to end
# ---------------------------------------------------------------------------

def test_list_and_redeem_makeup_credit_end_to_end() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        slot = _make_group_slot(db, professional.id, place.id)
        ana = _make_contact(db, professional.id, "Ana")
        _enroll(db, slot.id, ana.id)

        target_date = MONDAY + timedelta(days=14)
        absence = mutations.propose_note_participant_absence(
            db, professional.id, user.id, uuid.uuid4(),
            contact_id=str(ana.id), recurring_slot_id=str(slot.id),
            occurrence_date=target_date.isoformat(),
        )
        candidates.confirm(db, professional.id, user.id, uuid.UUID(absence["candidate_id"]))

        listing = tools.list_makeup_credits(db, professional.id, contact_id=str(ana.id))
        assert len(listing["credits"]) == 1
        credit_id = listing["credits"][0]["credit_id"]

        redeem_start = datetime.combine(target_date + timedelta(days=1), time(10, 0), tzinfo=TIMEZONE)
        propose_result = mutations.propose_redeem_makeup_credit(
            db, professional.id, user.id, uuid.uuid4(),
            credit_id=credit_id, place_id=str(place.id),
            start_at=redeem_start.isoformat(),
            end_at=(redeem_start + timedelta(hours=1)).isoformat(),
        )
        assert propose_result["requires_confirmation"] is True
        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(propose_result["candidate_id"])
        )
        assert exec_result.ok is True

        credit = db.query(MakeupClassCredit).filter(MakeupClassCredit.id == uuid.UUID(credit_id)).first()
        assert credit.status == "redeemed"
        assert credit.redeemed_appointment_id is not None

        appointment = db.query(Appointment).filter(Appointment.id == credit.redeemed_appointment_id).first()
        assert appointment is not None
        assert appointment.contact_id == ana.id

        # Credit is gone from the available list now.
        listing_after = tools.list_makeup_credits(db, professional.id, contact_id=str(ana.id))
        assert listing_after["credits"] == []
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_redeem_makeup_credit_rejects_already_redeemed() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        slot = _make_group_slot(db, professional.id, place.id)
        ana = _make_contact(db, professional.id, "Ana")
        _enroll(db, slot.id, ana.id)

        target_date = MONDAY + timedelta(days=14)
        absence = mutations.propose_note_participant_absence(
            db, professional.id, user.id, uuid.uuid4(),
            contact_id=str(ana.id), recurring_slot_id=str(slot.id),
            occurrence_date=target_date.isoformat(),
        )
        candidates.confirm(db, professional.id, user.id, uuid.UUID(absence["candidate_id"]))
        credit = db.query(MakeupClassCredit).filter(MakeupClassCredit.contact_id == ana.id).first()
        credit.status = "redeemed"
        db.commit()

        redeem_start = datetime.combine(target_date + timedelta(days=1), time(10, 0), tzinfo=TIMEZONE)
        result = mutations.propose_redeem_makeup_credit(
            db, professional.id, user.id, uuid.uuid4(),
            credit_id=str(credit.id), place_id=str(place.id),
            start_at=redeem_start.isoformat(),
            end_at=(redeem_start + timedelta(hours=1)).isoformat(),
        )
        assert "error" in result
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

def test_makeup_credit_tools_are_tenant_scoped() -> None:
    db = SessionLocal()
    professional_a, user_a = _make_tenant(db)
    professional_b, user_b = _make_tenant(db)
    try:
        place = _make_place(db, professional_a.id)
        slot = _make_group_slot(db, professional_a.id, place.id)
        ana = _make_contact(db, professional_a.id, "Ana")
        _enroll(db, slot.id, ana.id)

        target_date = MONDAY + timedelta(days=14)
        absence = mutations.propose_note_participant_absence(
            db, professional_a.id, user_a.id, uuid.uuid4(),
            contact_id=str(ana.id), recurring_slot_id=str(slot.id),
            occurrence_date=target_date.isoformat(),
        )
        candidates.confirm(db, professional_a.id, user_a.id, uuid.UUID(absence["candidate_id"]))
        credit = db.query(MakeupClassCredit).filter(MakeupClassCredit.contact_id == ana.id).first()

        # professional_b can't see or redeem professional_a's credit.
        listing = tools.list_makeup_credits(db, professional_b.id, contact_id=str(ana.id))
        assert listing["credits"] == []

        redeem_start = datetime.combine(target_date + timedelta(days=1), time(10, 0), tzinfo=TIMEZONE)
        result = mutations.propose_redeem_makeup_credit(
            db, professional_b.id, user_b.id, uuid.uuid4(),
            credit_id=str(credit.id), place_id=str(place.id),
            start_at=redeem_start.isoformat(),
            end_at=(redeem_start + timedelta(hours=1)).isoformat(),
        )
        assert "error" in result
    finally:
        _cleanup(db, professionals=[professional_a, professional_b], users=[user_a, user_b])
        db.close()


# ---------------------------------------------------------------------------
# Courtesy billing — default non-billable, but overridable at confirmation
# ---------------------------------------------------------------------------

def _login(user) -> dict:
    res = client.post(
        "/api/auth/login", json={"email": user.email, "password": "correct-password"}
    )
    return res.cookies


def test_courtesy_appointment_revenue_confirmation_is_overridable() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id, "Nova Aluna")
        db.add(
            FinancialRate(professional_id=professional.id, participant_count=1, hourly_rate_cents=5000)
        )
        db.commit()

        start_at = datetime.combine(MONDAY - timedelta(days=1), time(10, 0), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            place_id=place.id,
            service="Aula teste",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
            billing_type="courtesy",
        )
        db.add(appointment)
        db.commit()

        cookies = _login(user)
        candidates_res = client.get(
            "/api/financial/revenue/candidates",
            params={"date_from": start_at.date().isoformat(), "date_to": start_at.date().isoformat()},
            cookies=cookies,
        )
        assert candidates_res.status_code == 200
        candidate = candidates_res.json()["candidates"][0]
        assert candidate["billing_type"] == "courtesy"

        # Instructor overrides and bills it anyway.
        confirm_res = client.post(
            "/api/financial/revenue/occurrences",
            json={
                "source_type": "appointment",
                "source_id": str(appointment.id),
                "occurrence_date": start_at.date().isoformat(),
                "participant_outcomes": [
                    {"contact_id": str(contact.id), "attendance_status": "attended", "billable": True}
                ],
                "adjustment_cents": 0,
                "note": None,
            },
            cookies=cookies,
        )
        assert confirm_res.status_code == 201
        body = confirm_res.json()
        assert body["participants"][0]["billable"] is True
        assert body["participants"][0]["non_billable_reason"] is None
        assert body["participants"][0]["billed_amount_cents"] > 0
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_courtesy_appointment_non_billable_gets_reason_tagged() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id, "Nova Aluna")

        start_at = datetime.combine(MONDAY - timedelta(days=1), time(10, 0), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            place_id=place.id,
            service="Aula teste",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
            billing_type="courtesy",
        )
        db.add(appointment)
        db.commit()

        cookies = _login(user)
        confirm_res = client.post(
            "/api/financial/revenue/occurrences",
            json={
                "source_type": "appointment",
                "source_id": str(appointment.id),
                "occurrence_date": start_at.date().isoformat(),
                "participant_outcomes": [
                    {"contact_id": str(contact.id), "attendance_status": "attended", "billable": False}
                ],
                "adjustment_cents": 0,
                "note": None,
            },
            cookies=cookies,
        )
        assert confirm_res.status_code == 201
        body = confirm_res.json()
        assert body["participants"][0]["billable"] is False
        assert body["participants"][0]["non_billable_reason"] == "courtesy"
        assert body["participants"][0]["billed_amount_cents"] == 0
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()

"""Tests for the Phase 4 low-risk write tools (operational ontology
roadmap v0.2): propose_add_group_member, propose_remove_group_member,
propose_update_contact — propose step, confirm/execute, and precondition
re-validation at confirm time."""

from pathlib import Path
import sys
import uuid
from datetime import date, datetime, time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import candidates, mutations
from app.core.security import hash_password
from app.database import SessionLocal
from app.models import (
    Contact,
    OperationalEvent,
    OperatorActionCandidate,
    Place,
    Professional,
    RecurringSlot,
    RecurringSlotParticipant,
    User,
)
from app.services.scheduling import TIMEZONE

MONDAY_CREATED_AT = datetime.combine(date(2026, 8, 3), time(8, 0), tzinfo=TIMEZONE)


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().hex[:8]}"


def _random_email() -> str:
    return f"mutation_{uuid.uuid4().hex[:10]}@agenda.ai"


def _make_tenant(db) -> tuple[Professional, User]:
    professional = Professional(name="Tenant Mutations", assistant_phone=_random_phone())
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


def _make_group_slot(db, professional_id, place_id, *, max_participants: int = 4) -> RecurringSlot:
    slot = RecurringSlot(
        professional_id=professional_id,
        place_id=place_id,
        day_of_week=0,
        start_time=time(18, 0),
        end_time=time(19, 0),
        group_name="Grupo da Maria",
        class_type="group",
        slot_kind="class",
        max_participants=max_participants,
        recurrence_type="weekly",
        created_at=MONDAY_CREATED_AT,
    )
    db.add(slot)
    db.commit()
    return slot


def _cleanup(db, *, professionals: list[Professional], users: list[User]) -> None:
    professional_ids = [p.id for p in professionals]
    user_ids = [u.id for u in users]
    if professional_ids:
        db.query(OperationalEvent).filter(
            OperationalEvent.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(OperatorActionCandidate).filter(
            OperatorActionCandidate.professional_id.in_(professional_ids)
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
# propose_add_group_member
# ---------------------------------------------------------------------------

def test_propose_add_group_member_full_cycle() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id, "Marcelo")
        slot = _make_group_slot(db, professional.id, place.id)
        correlation_id = uuid.uuid4()

        result = mutations.propose_add_group_member(
            db,
            professional.id,
            user.id,
            correlation_id,
            contact_id=str(contact.id),
            recurring_slot_id=str(slot.id),
        )
        assert result["requires_confirmation"] is True
        assert "Marcelo" in result["preview_text"]
        assert "Grupo da Maria" in result["preview_text"]

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        membership = (
            db.query(RecurringSlotParticipant)
            .filter(
                RecurringSlotParticipant.recurring_slot_id == slot.id,
                RecurringSlotParticipant.contact_id == contact.id,
            )
            .first()
        )
        assert membership is not None

        event = (
            db.query(OperationalEvent)
            .filter(
                OperationalEvent.event_type == "schedule.participant.added",
                OperationalEvent.entity_id == slot.id,
            )
            .first()
        )
        assert event is not None
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_add_group_member_rejects_at_capacity() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        slot = _make_group_slot(db, professional.id, place.id, max_participants=1)
        member = _make_contact(db, professional.id, "Membro Atual")
        db.add(RecurringSlotParticipant(recurring_slot_id=slot.id, contact_id=member.id))
        db.commit()

        new_contact = _make_contact(db, professional.id, "Novo Aluno")
        result = mutations.propose_add_group_member(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(new_contact.id),
            recurring_slot_id=str(slot.id),
        )
        assert "error" in result
        assert (
            db.query(OperatorActionCandidate)
            .filter(OperatorActionCandidate.professional_id == professional.id)
            .count()
            == 0
        )
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_add_group_member_confirm_fails_if_filled_concurrently() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        slot = _make_group_slot(db, professional.id, place.id, max_participants=1)
        contact = _make_contact(db, professional.id, "Marcelo")

        result = mutations.propose_add_group_member(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(contact.id),
            recurring_slot_id=str(slot.id),
        )
        assert result["requires_confirmation"] is True

        # Capacity fills up after the proposal, before confirmation.
        other = _make_contact(db, professional.id, "Outro Aluno")
        db.add(RecurringSlotParticipant(recurring_slot_id=slot.id, contact_id=other.id))
        db.commit()

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is False

        candidate = (
            db.query(OperatorActionCandidate)
            .filter(OperatorActionCandidate.id == uuid.UUID(result["candidate_id"]))
            .first()
        )
        assert candidate.status == "failed"
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


# ---------------------------------------------------------------------------
# propose_remove_group_member
# ---------------------------------------------------------------------------

def test_propose_remove_group_member_full_cycle() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        slot = _make_group_slot(db, professional.id, place.id)
        contact = _make_contact(db, professional.id, "Marcelo")
        db.add(RecurringSlotParticipant(recurring_slot_id=slot.id, contact_id=contact.id))
        db.commit()

        result = mutations.propose_remove_group_member(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(contact.id),
            recurring_slot_id=str(slot.id),
        )
        assert result["requires_confirmation"] is True

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        membership = (
            db.query(RecurringSlotParticipant)
            .filter(
                RecurringSlotParticipant.recurring_slot_id == slot.id,
                RecurringSlotParticipant.contact_id == contact.id,
            )
            .first()
        )
        assert membership is None
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_remove_group_member_rejects_non_member() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        place = _make_place(db, professional.id)
        slot = _make_group_slot(db, professional.id, place.id)
        contact = _make_contact(db, professional.id, "Nao Membro")

        result = mutations.propose_remove_group_member(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(contact.id),
            recurring_slot_id=str(slot.id),
        )
        assert "error" in result
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


# ---------------------------------------------------------------------------
# propose_update_contact
# ---------------------------------------------------------------------------

def test_propose_update_contact_full_cycle() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        contact = _make_contact(db, professional.id, "Marcelo")
        result = mutations.propose_update_contact(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(contact.id),
            changes={"level": "advanced", "city": "São Paulo"},
        )
        assert result["requires_confirmation"] is True
        assert "level" in result["preview_text"]

        exec_result = candidates.confirm(
            db, professional.id, user.id, uuid.UUID(result["candidate_id"])
        )
        assert exec_result.ok is True

        db.refresh(contact)
        assert contact.level == "advanced"
        assert contact.city == "São Paulo"

        event = (
            db.query(OperationalEvent)
            .filter(OperationalEvent.event_type == "contact.updated")
            .first()
        )
        assert event.before_state["level"] is None
        assert event.after_state["level"] == "advanced"
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_update_contact_rejects_unknown_field() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        contact = _make_contact(db, professional.id, "Marcelo")
        result = mutations.propose_update_contact(
            db,
            professional.id,
            user.id,
            uuid.uuid4(),
            contact_id=str(contact.id),
            changes={"phone": "+5511900000000"},
        )
        assert "error" in result
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_mutation_tools_are_tenant_scoped() -> None:
    db = SessionLocal()
    professional_a, user_a = _make_tenant(db)
    professional_b, user_b = _make_tenant(db)
    try:
        contact = _make_contact(db, professional_a.id, "Marcelo")
        place = _make_place(db, professional_a.id)
        slot = _make_group_slot(db, professional_a.id, place.id)

        result = mutations.propose_add_group_member(
            db,
            professional_b.id,
            user_b.id,
            uuid.uuid4(),
            contact_id=str(contact.id),
            recurring_slot_id=str(slot.id),
        )
        assert "error" in result
    finally:
        _cleanup(
            db,
            professionals=[professional_a, professional_b],
            users=[user_a, user_b],
        )
        db.close()

"""Tests for the action-candidate state machine (operational ontology
roadmap v0.2, Phase 3): propose -> confirm/reject/expire.

Uses a synthetic executor registered only for these tests — per the
roadmap's Phase 3 release gate, the confirmation/audit lifecycle must be
provable without any production mutation tool existing yet."""

from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.agent import candidates
from app.agent.candidates import ExecutionResult
from app.core.security import hash_password
from app.database import SessionLocal
from app.models import OperationalEvent, OperatorActionCandidate, Professional, User

SYNTHETIC_TOOL = "propose_test_write"


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().int % 100_000_000:08d}"


def _random_email() -> str:
    return f"candidate_{uuid.uuid4().hex[:10]}@agenda.ai"


def _make_tenant(db) -> tuple[Professional, User]:
    professional = Professional(name="Tenant Candidate", assistant_phone=_random_phone())
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
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    if professional_ids:
        db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    db.commit()


@pytest.fixture(autouse=True)
def _synthetic_executor():
    def executor(db, professional_id, candidate):
        return ExecutionResult(ok=True, summary="synthetic write applied")

    candidates.MUTATION_EXECUTORS[SYNTHETIC_TOOL] = executor
    yield
    candidates.MUTATION_EXECUTORS.pop(SYNTHETIC_TOOL, None)


def _propose(db, professional, user, **overrides):
    kwargs = dict(
        tool_name=SYNTHETIC_TOOL,
        arguments={"foo": "bar"},
        preview_text="Fazer uma escrita sintética de teste.",
        affected_entities=[
            {"entity_type": "test", "entity_id": str(uuid.uuid4()), "label": "x"}
        ],
        correlation_id=uuid.uuid4(),
    )
    kwargs.update(overrides)
    return candidates.propose(db, professional.id, user.id, **kwargs)


def test_propose_confirm_executes_and_records_events() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        candidate = _propose(db, professional, user)
        assert candidate.status == "proposed"

        result = candidates.confirm(db, professional.id, user.id, candidate.id)
        assert result.ok is True
        assert result.summary == "synthetic write applied"

        db.refresh(candidate)
        assert candidate.status == "executed"
        assert candidate.executed_at is not None

        event_types = [
            e.event_type
            for e in db.query(OperationalEvent)
            .filter(OperationalEvent.operator_action_candidate_id == candidate.id)
            .order_by(OperationalEvent.sequence)
            .all()
        ]
        assert event_types == [
            "agent.action.proposed",
            "agent.action.confirmed",
            "agent.action.executed",
        ]
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_propose_reject_never_executes() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        candidate = _propose(db, professional, user)
        rejected = candidates.reject(db, professional.id, user.id, candidate.id)
        assert rejected.status == "rejected"

        with pytest.raises(candidates.CandidateNotPendingError):
            candidates.confirm(db, professional.id, user.id, candidate.id)
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_confirm_after_expiry_fails_safely() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        candidate = _propose(db, professional, user, ttl_minutes=-1)
        with pytest.raises(candidates.CandidateNotPendingError) as exc_info:
            candidates.confirm(db, professional.id, user.id, candidate.id)
        assert exc_info.value.status == "expired"

        db.refresh(candidate)
        assert candidate.status == "expired"
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_executor_failure_rolls_back_and_marks_failed() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    failing_tool = "propose_test_write_failing"
    try:
        def failing_executor(db, professional_id, candidate):
            raise ValueError("capacity changed since preview")

        candidates.MUTATION_EXECUTORS[failing_tool] = failing_executor
        candidate = _propose(db, professional, user, tool_name=failing_tool)
        result = candidates.confirm(db, professional.id, user.id, candidate.id)
        assert result.ok is False
        assert "capacity changed" in result.summary

        db.refresh(candidate)
        assert candidate.status == "failed"
        assert candidate.failure_reason is not None
    finally:
        candidates.MUTATION_EXECUTORS.pop(failing_tool, None)
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_idempotency_key_reuses_existing_candidate() -> None:
    db = SessionLocal()
    professional, user = _make_tenant(db)
    try:
        key = f"idem-{uuid.uuid4().hex[:8]}"
        first = _propose(db, professional, user, idempotency_key=key)
        second = _propose(db, professional, user, idempotency_key=key)
        assert first.id == second.id

        count = (
            db.query(OperatorActionCandidate)
            .filter(OperatorActionCandidate.idempotency_key == key)
            .count()
        )
        assert count == 1
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_candidate_operations_are_tenant_scoped() -> None:
    db = SessionLocal()
    professional_a, user_a = _make_tenant(db)
    professional_b, user_b = _make_tenant(db)
    try:
        candidate = _propose(db, professional_a, user_a)
        with pytest.raises(candidates.CandidateNotFoundError):
            candidates.confirm(db, professional_b.id, user_b.id, candidate.id)
    finally:
        _cleanup(
            db,
            professionals=[professional_a, professional_b],
            users=[user_a, user_b],
        )
        db.close()

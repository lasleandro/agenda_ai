"""
Action-candidate state machine (operational ontology roadmap v0.2, Phase 3).

`propose()` creates an `OperatorActionCandidate` with a deterministic,
human-readable preview and records `agent.action.proposed`. `confirm()`
re-validates and executes via the `MUTATION_EXECUTORS` registry inside one
transaction — on failure the whole transaction (candidate status +
whatever the executor started writing) rolls back, and the candidate is
marked `failed` in a fresh, separate transaction so state changes since the
preview never apply silently. `reject()` marks a candidate rejected.
A candidate past `expires_at` is lazily marked `expired` on the next
confirm/reject attempt — no background job.

`MUTATION_EXECUTORS` lives here (not in `app.agent.mutations`) so this
module has no dependency on tool-specific mutation code — `mutations.py`
(Phase 4+) imports `propose` from here and registers its executors into
`MUTATION_EXECUTORS`, not the other way around.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import OperatorActionCandidate
from app.services.operational_events import record_event
from app.services.scheduling import TIMEZONE

DEFAULT_TTL_MINUTES = 10


class CandidateNotFoundError(Exception):
    pass


class CandidateNotPendingError(Exception):
    def __init__(self, status: str):
        self.status = status
        super().__init__(f"Candidate is not pending confirmation (status={status})")


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    summary: str


# Executor(db, professional_id, candidate) -> ExecutionResult. Must raise on
# failure (never return ok=False for a precondition failure) so `confirm()`
# can roll back any partial writes atomically with the candidate status.
Executor = Callable[[Session, uuid.UUID, OperatorActionCandidate], ExecutionResult]
MUTATION_EXECUTORS: dict[str, Executor] = {}


def propose(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    preview_text: str,
    affected_entities: list[dict[str, Any]],
    correlation_id: uuid.UUID,
    channel: str = "web",
    idempotency_key: str | None = None,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
) -> OperatorActionCandidate:
    if idempotency_key is not None:
        existing = (
            db.query(OperatorActionCandidate)
            .filter(
                OperatorActionCandidate.professional_id == professional_id,
                OperatorActionCandidate.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing is not None:
            return existing

    now = datetime.now(TIMEZONE)
    candidate = OperatorActionCandidate(
        professional_id=professional_id,
        actor_user_id=actor_user_id,
        channel=channel,
        tool_name=tool_name,
        resolved_arguments=arguments,
        preview_text=preview_text,
        affected_entities=affected_entities,
        status="proposed",
        expires_at=now + timedelta(minutes=ttl_minutes),
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    db.add(candidate)
    db.flush()
    record_event(
        db,
        professional_id=professional_id,
        event_type="agent.action.proposed",
        occurred_at=now,
        actor_type="user",
        actor_id=actor_user_id,
        source_channel=channel,
        entity_type="operator_action_candidate",
        entity_id=candidate.id,
        correlation_id=correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"tool_name": tool_name, "arguments": arguments},
    )
    db.commit()
    return candidate


def _get_pending_or_expire(
    db: Session, professional_id: uuid.UUID, candidate_id: uuid.UUID
) -> OperatorActionCandidate:
    candidate = (
        db.query(OperatorActionCandidate)
        .filter(
            OperatorActionCandidate.id == candidate_id,
            OperatorActionCandidate.professional_id == professional_id,
        )
        .first()
    )
    if candidate is None:
        raise CandidateNotFoundError()

    now = datetime.now(TIMEZONE)
    if candidate.status == "proposed" and candidate.expires_at <= now:
        candidate.status = "expired"
        db.flush()
        record_event(
            db,
            professional_id=professional_id,
            event_type="agent.action.expired",
            occurred_at=now,
            actor_type="system",
            actor_id=None,
            source_channel=candidate.channel,
            entity_type="operator_action_candidate",
            entity_id=candidate.id,
            correlation_id=candidate.correlation_id,
            operator_action_candidate_id=candidate.id,
            payload={},
        )
        db.commit()

    if candidate.status != "proposed":
        raise CandidateNotPendingError(candidate.status)
    return candidate


def confirm(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    candidate_id: uuid.UUID,
) -> ExecutionResult:
    candidate = _get_pending_or_expire(db, professional_id, candidate_id)
    now = datetime.now(TIMEZONE)

    executor = MUTATION_EXECUTORS.get(candidate.tool_name)
    if executor is None:
        candidate.status = "failed"
        candidate.failure_reason = f"No executor registered for '{candidate.tool_name}'"
        db.commit()
        return ExecutionResult(ok=False, summary=candidate.failure_reason)

    candidate.status = "confirmed"
    db.flush()
    record_event(
        db,
        professional_id=professional_id,
        event_type="agent.action.confirmed",
        occurred_at=now,
        actor_type="user",
        actor_id=actor_user_id,
        source_channel=candidate.channel,
        entity_type="operator_action_candidate",
        entity_id=candidate.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={},
    )

    try:
        result = executor(db, professional_id, candidate)
    except Exception as exc:  # noqa: BLE001 — surfaced as a failed candidate, not a 500
        db.rollback()
        candidate = (
            db.query(OperatorActionCandidate)
            .filter(OperatorActionCandidate.id == candidate_id)
            .first()
        )
        failure_reason = str(exc)[:500]
        candidate.status = "failed"
        candidate.failure_reason = failure_reason
        db.flush()
        record_event(
            db,
            professional_id=professional_id,
            event_type="agent.action.failed",
            occurred_at=now,
            actor_type="user",
            actor_id=actor_user_id,
            source_channel=candidate.channel,
            entity_type="operator_action_candidate",
            entity_id=candidate.id,
            correlation_id=candidate.correlation_id,
            operator_action_candidate_id=candidate.id,
            payload={"error": failure_reason},
        )
        db.commit()
        return ExecutionResult(ok=False, summary=failure_reason)

    candidate.status = "executed"
    candidate.executed_at = now
    db.flush()
    record_event(
        db,
        professional_id=professional_id,
        event_type="agent.action.executed",
        occurred_at=now,
        actor_type="user",
        actor_id=actor_user_id,
        source_channel=candidate.channel,
        entity_type="operator_action_candidate",
        entity_id=candidate.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"summary": result.summary},
    )
    db.commit()
    return result


def reject(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    candidate_id: uuid.UUID,
) -> OperatorActionCandidate:
    candidate = _get_pending_or_expire(db, professional_id, candidate_id)
    now = datetime.now(TIMEZONE)
    candidate.status = "rejected"
    db.flush()
    record_event(
        db,
        professional_id=professional_id,
        event_type="agent.action.rejected",
        occurred_at=now,
        actor_type="user",
        actor_id=actor_user_id,
        source_channel=candidate.channel,
        entity_type="operator_action_candidate",
        entity_id=candidate.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={},
    )
    db.commit()
    return candidate

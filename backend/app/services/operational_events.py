"""Operational event ledger writer (operational ontology roadmap v0.2,
Phase 3). Thin — mirrors `financial_audit.add_financial_audit` — every
caller supplies the full event shape; this just persists it."""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import OperationalEvent


def record_event(
    db: Session,
    *,
    professional_id: uuid.UUID,
    event_type: str,
    occurred_at: datetime,
    actor_type: str,
    actor_id: uuid.UUID | None,
    source_channel: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    correlation_id: uuid.UUID,
    causation_id: uuid.UUID | None = None,
    operator_action_candidate_id: uuid.UUID | None = None,
    payload: dict,
    before_state: dict | None = None,
    after_state: dict | None = None,
    idempotency_key: str | None = None,
) -> OperationalEvent:
    event = OperationalEvent(
        professional_id=professional_id,
        event_type=event_type,
        occurred_at=occurred_at,
        actor_type=actor_type,
        actor_id=actor_id,
        source_channel=source_channel,
        entity_type=entity_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        operator_action_candidate_id=operator_action_candidate_id,
        payload=payload,
        before_state=before_state,
        after_state=after_state,
        idempotency_key=idempotency_key,
    )
    db.add(event)
    db.flush()
    return event

"""
Instructor assistant chat API (operational ontology roadmap v0.2, Phase 2
web-chat adapter; Phase 3 action-candidate confirm/reject).

POST /api/assistant/messages                — send the conversation so far,
                                                get the agent's reply, a
                                                tool-call trace, and an
                                                optional pending action
                                                candidate to confirm/reject.
POST /api/assistant/candidates/{id}/confirm  — execute a proposed action.
POST /api/assistant/candidates/{id}/reject   — discard a proposed action.

Read tools only read domain data. Write tools never write directly — they
create an `OperatorActionCandidate` (see `app.agent.candidates`) that must
be explicitly confirmed here before anything executes. No conversation is
persisted server-side in this pass — the client resends the message
history each turn.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent import candidates
from app.agent.orchestrator import RecentActionContext, run_agent_turn
from app.api.dependencies import require_authenticated, require_professional_id
from app.database import SessionLocal
from app.models import OperationalEvent, OperatorActionCandidate
from app.schemas.assistant import (
    ActionCandidateResultResponse,
    AssistantChatRequest,
    AssistantChatResponse,
    PendingActionCandidate,
    ToolCallTraceDetail,
)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _load_recent_action_context(
    db: Session,
    professional_id: uuid.UUID,
    recent_candidate_ids: list[uuid.UUID],
) -> list[RecentActionContext]:
    candidate_ids = list(recent_candidate_ids)[:5]
    if not candidate_ids:
        return []

    candidates_rows = (
        db.query(OperatorActionCandidate)
        .filter(
            OperatorActionCandidate.professional_id == professional_id,
            OperatorActionCandidate.id.in_(candidate_ids),
        )
        .all()
    )
    candidates_by_id = {candidate.id: candidate for candidate in candidates_rows}

    events = (
        db.query(OperationalEvent)
        .filter(
            OperationalEvent.professional_id == professional_id,
            OperationalEvent.operator_action_candidate_id.in_(candidate_ids),
        )
        .all()
    )
    events_by_candidate: dict[uuid.UUID, list[OperationalEvent]] = {}
    for event in events:
        events_by_candidate.setdefault(event.operator_action_candidate_id, []).append(event)

    contexts: list[RecentActionContext] = []
    for candidate_id in candidate_ids:
        candidate = candidates_by_id.get(candidate_id)
        if candidate is None or candidate.status not in ("executed", "rejected", "failed"):
            continue

        entities: list[dict[str, str]] = []
        summary: str | None = None
        if candidate.status == "executed":
            seen: set[tuple[str, str]] = set()
            for event in events_by_candidate.get(candidate_id, []):
                if event.event_type == "agent.action.executed" and event.payload.get("summary"):
                    summary = event.payload["summary"]
                elif event.entity_id is not None and not event.event_type.startswith("agent.action."):
                    key = (event.entity_type, str(event.entity_id))
                    if key not in seen:
                        seen.add(key)
                        entities.append({"entity_type": event.entity_type, "entity_id": str(event.entity_id)})
        elif candidate.status == "failed":
            summary = candidate.failure_reason or "Falha ao executar a proposta."
        else:
            summary = "Proposta rejeitada."

        contexts.append(
            RecentActionContext(
                status=candidate.status,
                tool_name=candidate.tool_name,
                summary=summary or candidate.preview_text,
                entities=entities,
            )
        )
    return contexts


@router.post("/messages", response_model=AssistantChatResponse)
def send_message(
    body: AssistantChatRequest,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
    user: dict = Depends(require_authenticated),
):
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    recent_action_context = _load_recent_action_context(
        db, professional_id, body.recent_candidate_ids
    )
    response = run_agent_turn(
        db,
        professional_id,
        uuid.UUID(user["user_id"]),
        messages,
        recent_action_context=recent_action_context,
    )
    pending = None
    if response.pending_candidate is not None:
        candidate = response.pending_candidate
        pending = PendingActionCandidate(
            id=candidate.id,
            preview_text=candidate.preview_text,
            advisory_text=candidate.advisory_text,
            affected_entities=candidate.affected_entities,
            expires_at=candidate.expires_at.isoformat(),
        )
    return AssistantChatResponse(
        reply=response.reply,
        tool_calls=[
            ToolCallTraceDetail(
                name=call.name,
                arguments=call.arguments,
                result_summary=call.result_summary,
            )
            for call in response.tool_calls
        ],
        pending_candidate=pending,
    )


@router.post(
    "/candidates/{candidate_id}/confirm", response_model=ActionCandidateResultResponse
)
def confirm_candidate(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
    user: dict = Depends(require_authenticated),
):
    try:
        result = candidates.confirm(
            db, professional_id, uuid.UUID(user["user_id"]), candidate_id
        )
    except candidates.CandidateNotFoundError:
        raise HTTPException(status_code=404, detail="Action candidate not found")
    except candidates.CandidateNotPendingError as exc:
        raise HTTPException(
            status_code=409, detail=f"Action is no longer pending (status={exc.status})"
        )
    return ActionCandidateResultResponse(
        status="executed" if result.ok else "failed", summary=result.summary
    )


@router.post(
    "/candidates/{candidate_id}/reject", response_model=ActionCandidateResultResponse
)
def reject_candidate(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
    user: dict = Depends(require_authenticated),
):
    try:
        candidates.reject(db, professional_id, uuid.UUID(user["user_id"]), candidate_id)
    except candidates.CandidateNotFoundError:
        raise HTTPException(status_code=404, detail="Action candidate not found")
    except candidates.CandidateNotPendingError as exc:
        raise HTTPException(
            status_code=409, detail=f"Action is no longer pending (status={exc.status})"
        )
    return ActionCandidateResultResponse(status="rejected", summary="Ação cancelada.")

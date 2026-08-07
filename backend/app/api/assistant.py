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
from app.agent.orchestrator import run_agent_turn
from app.api.dependencies import require_authenticated, require_professional_id
from app.database import SessionLocal
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


@router.post("/messages", response_model=AssistantChatResponse)
def send_message(
    body: AssistantChatRequest,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
    user: dict = Depends(require_authenticated),
):
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    response = run_agent_turn(
        db, professional_id, uuid.UUID(user["user_id"]), messages
    )
    pending = None
    if response.pending_candidate is not None:
        candidate = response.pending_candidate
        pending = PendingActionCandidate(
            id=candidate.id,
            preview_text=candidate.preview_text,
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

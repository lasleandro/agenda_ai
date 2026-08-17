"""
Dev-only mock WhatsApp chat (not a roadmap phase — testing aid).

Lets a developer simulate both sides of a WhatsApp conversation (the
instructor's own app, and a customer) to exercise the real extraction
pipeline without a live WhatsApp connection. Mock messages are canonical
provider-neutral events and enter the same ingestion path used after every
provider adapter normalizes a webhook.

Scoped to the caller's own tenant (multi-tenancy roadmap Phase C): the mock
"instructor" side of the conversation uses the authenticated professional's
own assistant_phone, so two tenants never share mock conversation data.

Only registered when DEBUG=true (see app/main.py) — never exposed in a
would-be production deployment.
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.conversations import candidate_with_evidence
from app.api.dependencies import require_professional_id
from app.database import SessionLocal
from app.models import (
    AppointmentCandidate,
    AppointmentEvidence,
    Conversation,
    Message,
    PendingProcessing,
    Professional,
)
from app.schemas.api import CandidateDetail
from app.chat.ingestion import (
    get_or_create_contact,
    get_or_create_conversation,
    ingest_normalized_message,
)
from app.integrations.whatsapp.contracts import WhatsAppMessageEvent
from app.chat.pipeline import process_conversation

router = APIRouter(prefix="/api/dev", tags=["dev"])

MOCK_CUSTOMER_PHONE = "+5500000000001"
MOCK_CUSTOMER_NAME = "Cliente Teste (mock)"


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_professional(db: Session, professional_id: uuid.UUID) -> Professional:
    professional = db.query(Professional).filter(Professional.id == professional_id).first()
    if professional is None or not professional.assistant_phone:
        raise HTTPException(
            status_code=400,
            detail="Tenant has no assistant_phone configured — cannot build mock WhatsApp events",
        )
    return professional


class MockMessageRequest(BaseModel):
    sender: Literal["instructor", "customer"]
    text: str


def _build_message(
    instructor_phone: str, sender: Literal["instructor", "customer"], text: str
) -> WhatsAppMessageEvent:
    now = datetime.now(timezone.utc)
    msg_id = f"mock_{uuid.uuid4().hex}"

    if sender == "customer":
        return WhatsAppMessageEvent(
            provider_key="mock",
            provider_message_id=msg_id,
            direction="inbound",
            from_phone=MOCK_CUSTOMER_PHONE,
            to_phone=instructor_phone,
            text=text,
            sent_at=now,
            raw_payload={"mock": True},
            contact_name=MOCK_CUSTOMER_NAME,
        )

    return WhatsAppMessageEvent(
        provider_key="mock",
        provider_message_id=msg_id,
        direction="outbound",
        from_phone=instructor_phone,
        to_phone=MOCK_CUSTOMER_PHONE,
        text=text,
        sent_at=now,
        raw_payload={"mock": True},
    )


@router.get("/mock-conversation")
def get_mock_conversation(
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    """Get-or-create the single mock conversation, so the frontend has a
    conversation_id to poll even before any message has been sent."""
    professional = _get_professional(db, professional_id)
    contact = get_or_create_contact(db, professional.id, MOCK_CUSTOMER_PHONE, MOCK_CUSTOMER_NAME)
    conversation = get_or_create_conversation(db, professional.id, contact.id)
    db.commit()
    return {
        "conversation_id": conversation.id,
        "instructor_phone": professional.assistant_phone,
        "customer_phone": MOCK_CUSTOMER_PHONE,
    }


@router.post("/mock-messages")
def send_mock_message(
    body: MockMessageRequest,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    professional = _get_professional(db, professional_id)
    message = ingest_normalized_message(
        db, _build_message(professional.assistant_phone, body.sender, body.text)
    )
    if message is None:
        raise HTTPException(status_code=500, detail="Failed to ingest mock message")
    return {"message_id": message.id, "conversation_id": message.conversation_id}


@router.post("/mock-conversation/reset")
def reset_mock_conversation(
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    """Clear the dev mock conversation so a new scenario can be tested."""
    professional = _get_professional(db, professional_id)
    contact = get_or_create_contact(db, professional.id, MOCK_CUSTOMER_PHONE, MOCK_CUSTOMER_NAME)
    conversation = get_or_create_conversation(db, professional.id, contact.id)

    candidate_ids = [
        candidate_id
        for (candidate_id,) in db.query(AppointmentCandidate.id)
        .filter(AppointmentCandidate.conversation_id == conversation.id)
        .all()
    ]
    if candidate_ids:
        db.query(AppointmentEvidence).filter(
            AppointmentEvidence.appointment_candidate_id.in_(candidate_ids)
        ).delete(synchronize_session=False)
        db.query(AppointmentCandidate).filter(
            AppointmentCandidate.id.in_(candidate_ids)
        ).delete(synchronize_session=False)

    db.query(PendingProcessing).filter(
        PendingProcessing.conversation_id == conversation.id
    ).delete(synchronize_session=False)
    db.query(Message).filter(Message.conversation_id == conversation.id).delete(
        synchronize_session=False
    )
    conversation.last_message_at = None
    conversation.processing_cursor = None
    db.commit()

    return {"conversation_id": conversation.id}


@router.post("/conversations/{conversation_id}/process-now", response_model=list[CandidateDetail])
def process_now(
    conversation_id: str,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    """Bypass the debounce window and run extraction immediately, for fast
    iteration while testing. Goes through the same process_conversation used
    by the real worker."""
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.professional_id == professional_id)
        .first()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    candidates = process_conversation(db, conversation)
    return [candidate_with_evidence(db, candidate) for candidate in candidates]

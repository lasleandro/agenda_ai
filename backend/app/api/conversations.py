"""
Developer-only conversation view (Phase 1 — brief roadmap item, no UI polish).

Lets a developer visually confirm conversations are reconstructed correctly
from webhook events, via Swagger (/docs) rather than a dedicated frontend.

GET /api/conversations          — list conversations, most recent first.
GET /api/conversations/{id}     — single conversation with messages in order.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import require_professional_id
from app.database import SessionLocal
from app.models import AppointmentCandidate, AppointmentEvidence, Contact, Conversation, Message
from app.schemas.api import (
    CandidateDetail,
    CandidateEvidenceItem,
    ConversationDetail,
    ConversationListResponse,
    ConversationSummary,
)

router = APIRouter(prefix="/api", tags=["conversations"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    rows = (
        db.query(Conversation, Contact.display_name, Contact.phone)
        .join(Contact, Conversation.contact_id == Contact.id)
        .filter(Conversation.professional_id == professional_id)
        .order_by(Conversation.last_message_at.desc().nullslast())
        .all()
    )

    conversations = [
        ConversationSummary(
            id=conv.id,
            contact_id=conv.contact_id,
            contact_name=contact_name,
            contact_phone=contact_phone,
            last_message_at=conv.last_message_at,
            status=conv.status,
        )
        for conv, contact_name, contact_phone in rows
    ]

    return ConversationListResponse(conversations=conversations)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.professional_id == professional_id)
        .first()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    contact = db.query(Contact).filter(Contact.id == conversation.contact_id).first()

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.sent_at.asc())
        .all()
    )

    candidates = (
        db.query(AppointmentCandidate)
        .filter(AppointmentCandidate.conversation_id == conversation.id)
        .order_by(AppointmentCandidate.created_at.desc())
        .all()
    )
    candidate_details = [candidate_with_evidence(db, candidate) for candidate in candidates]

    return ConversationDetail(
        id=conversation.id,
        contact_id=conversation.contact_id,
        contact_name=contact.display_name if contact else "Desconhecido",
        contact_phone=contact.phone if contact else None,
        status=conversation.status,
        messages=messages,
        candidates=candidate_details,
    )


def candidate_with_evidence(db: Session, candidate: AppointmentCandidate) -> CandidateDetail:
    rows = (
        db.query(AppointmentEvidence, Message)
        .join(Message, AppointmentEvidence.message_id == Message.id)
        .filter(AppointmentEvidence.appointment_candidate_id == candidate.id)
        .order_by(AppointmentEvidence.sequence.asc())
        .all()
    )
    evidence = [
        CandidateEvidenceItem(
            message_id=ev.message_id,
            sequence=ev.sequence,
            direction=msg.direction,
            sent_at=msg.sent_at,
            text=msg.text,
        )
        for ev, msg in rows
    ]
    contact = (
        db.query(Contact).filter(Contact.id == candidate.contact_id).first()
        if candidate.contact_id
        else None
    )
    return CandidateDetail(
        id=candidate.id,
        action=candidate.action,
        operation=candidate.operation,
        confirmation_status=candidate.confirmation_status,
        existing_appointment_id=candidate.existing_appointment_id,
        resulting_appointment_id=candidate.resulting_appointment_id,
        operator_action_candidate_id=candidate.operator_action_candidate_id,
        suggested_place_id=contact.home_place_id if contact else None,
        contact_id=candidate.contact_id,
        contact_name=contact.display_name if contact else None,
        proposed_start_at=candidate.proposed_start_at,
        proposed_end_at=candidate.proposed_end_at,
        service=candidate.service,
        confidence=candidate.confidence,
        status=candidate.status,
        escalation_status=(
            candidate.operator_action_candidate.status
            if candidate.operator_action_candidate is not None
            else None
        ),
        escalation_delivery_status=(candidate.escalation.status if candidate.escalation else None),
        ambiguities=candidate.ambiguities or [],
        created_at=candidate.created_at,
        evidence=evidence,
    )

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

Registered when DEBUG=true or ENABLE_MOCK_CHAT=true (see app/main.py). Every
handler additionally requires a platform_admin with a selected tenant, so the
router is safe to enable in a deployed environment when explicitly opted in.
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.conversations import candidate_with_evidence
from app.api.dependencies import require_platform_admin_professional_id
from app.database import SessionLocal
from app.models import (
    AppointmentCandidate,
    AppointmentEvidence,
    Contact,
    Conversation,
    Message,
    PendingProcessing,
    Professional,
)
from app.services.text_normalization import normalize_name
from app.schemas.api import CandidateDetail
from app.chat.ingestion import (
    get_or_create_contact,
    get_or_create_conversation,
    ingest_normalized_message,
)
from app.integrations.whatsapp.contracts import WhatsAppMessageEvent
from app.chat.pipeline import process_conversation

router = APIRouter(prefix="/api/dev", tags=["dev"])

MOCK_CUSTOMER_PHONE_PREFIX = "+551199900"
# Prefix (9 digits) + a 4-digit suffix = 13 national digits, matching the
# BR mobile shape (DDD + 9 + 8-digit subscriber) that normalize_mobile_phone
# validates against — a 5-digit suffix produces an unparseable 14-digit
# number and 500s for any tenant hitting this for the first time.
MOCK_CUSTOMER_PHONE = f"{MOCK_CUSTOMER_PHONE_PREFIX}0001"
MOCK_CUSTOMER_NAME = "Cliente Teste (mock)"
MOCK_CUSTOMER_NAMES = (
    "Ana Martins",
    "Bruno Costa",
    "Camila Rocha",
    "Diego Almeida",
    "Fernanda Lima",
    "Gabriel Souza",
)


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
    customer_phone: str | None = None


class MockCustomerRequest(BaseModel):
    customer_phone: str | None = None


def _get_mock_customer(
    db: Session, professional_id: uuid.UUID, customer_phone: str | None
) -> tuple[str, str]:
    phone = customer_phone or MOCK_CUSTOMER_PHONE
    contact = (
        db.query(Contact)
        .filter(
            Contact.professional_id == professional_id,
            Contact.phone == phone,
            Contact.phone.like(f"{MOCK_CUSTOMER_PHONE_PREFIX}%"),
        )
        .first()
    )
    if contact is None and phone == MOCK_CUSTOMER_PHONE:
        contact = get_or_create_contact(db, professional_id, phone, MOCK_CUSTOMER_NAME)
    if contact is None:
        raise HTTPException(status_code=404, detail="Mock customer not found")
    return contact.phone, contact.display_name


def _next_mock_customer_name(db: Session, professional_id: uuid.UUID) -> str:
    existing_names = {
        display_name
        for (display_name,) in db.query(Contact.display_name)
        .filter(Contact.professional_id == professional_id)
        .all()
    }
    for name in MOCK_CUSTOMER_NAMES:
        display_name = f"{name} (mock)"
        if display_name not in existing_names:
            return display_name

    index = 1
    while True:
        display_name = f"Cliente simulado {index} (mock)"
        if display_name not in existing_names:
            return display_name
        index += 1


def _create_mock_customer(db: Session, professional_id: uuid.UUID) -> tuple[str, str, str]:
    """Create one tenant-scoped customer and its empty mock conversation."""
    while True:
        phone = f"{MOCK_CUSTOMER_PHONE_PREFIX}{uuid.uuid4().int % 10_000:04d}"
        if not db.query(Contact.id).filter(Contact.phone == phone).first():
            break

    display_name = _next_mock_customer_name(db, professional_id)
    contact = Contact(
        professional_id=professional_id,
        phone=phone,
        display_name=display_name,
        normalized_name=normalize_name(display_name),
    )
    db.add(contact)
    db.flush()
    conversation = get_or_create_conversation(db, professional_id, contact.id)
    db.commit()
    return str(conversation.id), phone, contact.display_name


def _build_message(
    instructor_phone: str,
    customer_phone: str,
    customer_name: str,
    sender: Literal["instructor", "customer"],
    text: str,
) -> WhatsAppMessageEvent:
    now = datetime.now(timezone.utc)
    msg_id = f"mock_{uuid.uuid4().hex}"

    if sender == "customer":
        return WhatsAppMessageEvent(
            provider_key="mock",
            provider_message_id=msg_id,
            direction="inbound",
            from_phone=customer_phone,
            to_phone=instructor_phone,
            text=text,
            sent_at=now,
            raw_payload={"mock": True},
            contact_name=customer_name,
        )

    return WhatsAppMessageEvent(
        provider_key="mock",
        provider_message_id=msg_id,
        direction="outbound",
        from_phone=instructor_phone,
        to_phone=customer_phone,
        text=text,
        sent_at=now,
        raw_payload={"mock": True},
    )


@router.get("/mock-conversation")
def get_mock_conversation(
    customer_phone: str | None = None,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_platform_admin_professional_id),
):
    """Get-or-create the single mock conversation, so the frontend has a
    conversation_id to poll even before any message has been sent."""
    professional = _get_professional(db, professional_id)
    customer_phone, _ = _get_mock_customer(db, professional.id, customer_phone)
    contact = get_or_create_contact(db, professional.id, customer_phone, None)
    conversation = get_or_create_conversation(db, professional.id, contact.id)
    db.commit()
    return {
        "conversation_id": conversation.id,
        "instructor_phone": professional.assistant_phone,
        "customer_phone": customer_phone,
    }


@router.get("/mock-customers")
def list_mock_customers(
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_platform_admin_professional_id),
):
    """List this tenant's generated mock customers and their conversations."""
    professional = _get_professional(db, professional_id)
    default_phone, _ = _get_mock_customer(db, professional.id, None)
    default_contact = get_or_create_contact(db, professional.id, default_phone, None)
    get_or_create_conversation(db, professional.id, default_contact.id)
    customers = (
        db.query(Contact, Conversation)
        .join(Conversation, Conversation.contact_id == Contact.id)
        .filter(
            Contact.professional_id == professional.id,
            Contact.phone.like(f"{MOCK_CUSTOMER_PHONE_PREFIX}%"),
        )
        .order_by(Contact.created_at.asc())
        .all()
    )
    db.commit()
    return {
        "customers": [
            {
                "conversation_id": conversation.id,
                "customer_name": contact.display_name,
                "customer_phone": contact.phone,
            }
            for contact, conversation in customers
        ]
    }


@router.post("/mock-customers")
def create_mock_customer(
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_platform_admin_professional_id),
):
    """Generate a new mock customer with an independent conversation."""
    professional = _get_professional(db, professional_id)
    conversation_id, customer_phone, customer_name = _create_mock_customer(db, professional.id)
    return {
        "conversation_id": conversation_id,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
    }


@router.post("/mock-messages")
def send_mock_message(
    body: MockMessageRequest,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_platform_admin_professional_id),
):
    professional = _get_professional(db, professional_id)
    customer_phone, customer_name = _get_mock_customer(
        db, professional.id, body.customer_phone
    )
    message = ingest_normalized_message(
        db,
        _build_message(
            professional.assistant_phone,
            customer_phone,
            customer_name,
            body.sender,
            body.text,
        ),
    )
    if message is None:
        raise HTTPException(status_code=500, detail="Failed to ingest mock message")
    return {"message_id": message.id, "conversation_id": message.conversation_id}


@router.post("/mock-conversation/reset")
def reset_mock_conversation(
    body: MockCustomerRequest | None = None,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_platform_admin_professional_id),
):
    """Clear the dev mock conversation so a new scenario can be tested."""
    professional = _get_professional(db, professional_id)
    customer_phone, _ = _get_mock_customer(
        db, professional.id, body.customer_phone if body else None
    )
    contact = get_or_create_contact(db, professional.id, customer_phone, None)
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
    professional_id: uuid.UUID = Depends(require_platform_admin_professional_id),
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

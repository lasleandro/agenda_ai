"""
Shared message ingestion logic (Phase 1 — brief Section 12.1).

Used by every WhatsApp provider webhook and the dev mock-chat endpoint, so
application traffic exercises one persistence/idempotency/debounce path after
provider-specific payload normalization.
"""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Contact, Conversation, Message, Professional
from app.chat import agent_channel
from app.chat.pipeline import schedule_processing
from app.integrations.whatsapp.contracts import (
    WhatsAppDeliveryUpdated,
    WhatsAppEvent,
    WhatsAppMessageEvent,
)
from app.integrations.whatsapp.provider import WhatsAppProvider
from app.services.text_normalization import normalize_name

logger = logging.getLogger(__name__)


def get_professional_by_phone(db: Session, assistant_phone: str) -> Professional | None:
    """Resolve the tenant owning a WhatsApp business number. Returns None if
    no active Professional is provisioned for it — a suspended/archived
    tenant is treated as unknown, and callers must not silently default to
    another tenant."""
    return (
        db.query(Professional)
        .filter(
            Professional.assistant_phone == assistant_phone,
            Professional.status == "active",
        )
        .first()
    )


def get_or_create_contact(db: Session, professional_id, phone: str, name: str | None) -> Contact:
    contact = (
        db.query(Contact)
        .filter(Contact.professional_id == professional_id, Contact.phone == phone)
        .first()
    )
    if contact is None:
        display_name = name or phone
        contact = Contact(
            professional_id=professional_id,
            phone=phone,
            display_name=display_name,
            normalized_name=normalize_name(display_name),
        )
        db.add(contact)
        db.flush()
    elif name and contact.display_name == contact.phone:
        # Backfill: earlier messages didn't carry a WhatsApp profile name.
        contact.display_name = name
        contact.normalized_name = normalize_name(name)
    return contact


def get_or_create_conversation(db: Session, professional_id, contact_id) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter(Conversation.professional_id == professional_id, Conversation.contact_id == contact_id)
        .first()
    )
    if conversation is None:
        conversation = Conversation(professional_id=professional_id, contact_id=contact_id)
        db.add(conversation)
        db.flush()
    return conversation


def ingest_normalized_message(db: Session, normalized: WhatsAppMessageEvent) -> Message | None:
    """Persist a normalized message: get-or-create contact/conversation, insert
    the message idempotently on provider_message_id, and reset the debounce
    timer. Returns None if the message was a duplicate (already persisted)."""
    contact_phone = (
        normalized.to_phone if normalized.direction == "outbound" else normalized.from_phone
    )
    assistant_phone = (
        normalized.from_phone if normalized.direction == "outbound" else normalized.to_phone
    )

    professional = get_professional_by_phone(db, assistant_phone)
    if professional is None:
        logger.warning(
            "Rejected message for unrecognized WhatsApp business number: %s", assistant_phone
        )
        return None

    contact = get_or_create_contact(db, professional.id, contact_phone, normalized.contact_name)
    conversation = get_or_create_conversation(db, professional.id, contact.id)

    message = Message(
        professional_id=professional.id,
        conversation_id=conversation.id,
        provider_key=normalized.provider_key,
        provider_message_id=normalized.provider_message_id,
        direction=normalized.direction,
        message_type="text",
        text=normalized.text,
        sent_at=normalized.sent_at,
        raw_payload=normalized.raw_payload,
    )
    db.add(message)
    conversation.last_message_at = normalized.sent_at

    try:
        db.commit()
    except IntegrityError:
        # Duplicate provider_message_id — webhook retry, already persisted.
        db.rollback()
        return None

    # Debounce: reset the processing timer now that a genuinely new message
    # landed (brief Section 12.2). Not done inside the block above so a
    # retried/duplicate webhook doesn't reset the window.
    schedule_processing(db, conversation.id)
    db.commit()

    return message


def dispatch_whatsapp_event(
    db: Session, event: WhatsAppEvent, provider: WhatsAppProvider
) -> Message | None:
    """Route a canonical WhatsApp event without exposing vendor payloads."""
    if isinstance(event, WhatsAppDeliveryUpdated):
        from app.services.scheduled_tasks import apply_delivery_update

        apply_delivery_update(db, event)
        return None
    if agent_channel.try_handle(db, event, provider):
        return None
    return ingest_normalized_message(db, event)


def ingest_provider_webhook(
    db: Session, raw_body: bytes, provider: WhatsAppProvider
) -> list[Message]:
    """Parse and dispatch a provider webhook into canonical application events."""
    messages = []
    for event in provider.parse_webhook(raw_body):
        message = dispatch_whatsapp_event(db, event, provider)
        if message is not None:
            messages.append(message)
    return messages

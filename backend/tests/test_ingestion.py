"""Integration tests for WhatsApp-number tenant resolution during ingestion."""

from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Contact, Conversation, Message, PendingProcessing, Professional
from app.chat.ingestion import ingest_normalized_message
from app.chat.ycloud_provider import NormalizedMessage


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().hex[:8]}"


def _inbound(assistant_phone: str, customer_phone: str) -> NormalizedMessage:
    return NormalizedMessage(
        provider_message_id=f"msg_{uuid.uuid4().hex}",
        direction="inbound",
        from_phone=customer_phone,
        to_phone=assistant_phone,
        text="Oi, posso marcar aula?",
        sent_at=datetime.now(timezone.utc),
        raw_payload={},
    )


def _cleanup(db, professional_ids: list) -> None:
    conversation_ids = [
        row[0]
        for row in db.query(Conversation.id)
        .filter(Conversation.professional_id.in_(professional_ids))
        .all()
    ]
    if conversation_ids:
        db.query(PendingProcessing).filter(
            PendingProcessing.conversation_id.in_(conversation_ids)
        ).delete(synchronize_session=False)
    db.query(Message).filter(Message.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(Conversation).filter(
        Conversation.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(Contact).filter(Contact.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.commit()


def test_ingest_normalized_message_routes_to_the_professional_owning_the_number() -> None:
    """A message must attach to the tenant whose WhatsApp number received it,
    never to a different tenant that happens to exist in the database."""
    db = SessionLocal()
    professional_a = Professional(name="Tenant A", assistant_phone=_random_phone())
    professional_b = Professional(name="Tenant B", assistant_phone=_random_phone())
    db.add_all([professional_a, professional_b])
    db.commit()

    customer_phone = _random_phone()
    try:
        message = ingest_normalized_message(
            db, _inbound(professional_a.assistant_phone, customer_phone)
        )

        assert message is not None
        assert message.professional_id == professional_a.id

        contact = db.query(Contact).filter(Contact.phone == customer_phone).one()
        assert contact.professional_id == professional_a.id

        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == message.conversation_id)
            .one()
        )
        assert conversation.professional_id == professional_a.id
        assert conversation.professional_id != professional_b.id
    finally:
        _cleanup(db, [professional_a.id, professional_b.id])
        db.close()


def test_ingest_normalized_message_rejects_unrecognized_number() -> None:
    """A webhook payload addressed to a number with no provisioned tenant
    must be dropped, not silently attached to whichever tenant exists."""
    db = SessionLocal()
    try:
        message = ingest_normalized_message(
            db, _inbound(_random_phone(), _random_phone())
        )
        assert message is None
    finally:
        db.close()

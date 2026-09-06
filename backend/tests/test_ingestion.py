"""Integration tests for WhatsApp-number tenant resolution during ingestion."""

from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Contact, Conversation, Message, OperationalEvent, PendingProcessing, Professional
from app.chat.ingestion import dispatch_whatsapp_event, ingest_normalized_message
from app.integrations.whatsapp.contracts import WhatsAppPermanentError
from app.chat.ycloud_provider import NormalizedMessage
from app.services.contacts import create_contact

PLATFORM_NUMBER = "+5511970000000"


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().int % 100_000_000:08d}"


def _inbound(
    assistant_phone: str,
    customer_phone: str,
    contact_name: str | None = None,
) -> NormalizedMessage:
    return NormalizedMessage(
        provider_message_id=f"msg_{uuid.uuid4().hex}",
        direction="inbound",
        from_phone=customer_phone,
        to_phone=assistant_phone,
        text="Oi, posso marcar aula?",
        sent_at=datetime.now(timezone.utc),
        raw_payload={},
        contact_name=contact_name,
    )


def _outbound(
    assistant_phone: str,
    other_phone: str,
) -> NormalizedMessage:
    """An instructor-sent echo: from the business number, to some recipient."""
    return NormalizedMessage(
        provider_message_id=f"msg_{uuid.uuid4().hex}",
        direction="outbound",
        from_phone=assistant_phone,
        to_phone=other_phone,
        text="Combinado, quinta 18h",
        sent_at=datetime.now(timezone.utc),
        raw_payload={},
    )


def _cleanup(db, professional_ids: list) -> None:
    db.query(OperationalEvent).filter(
        OperationalEvent.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
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


def test_ingest_persists_message_and_debounce_row_atomically() -> None:
    """A persisted message always has exactly one pending_processing row."""
    db = SessionLocal()
    professional = Professional(name="Tenant Atomic", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    customer_phone = _random_phone()
    try:
        message = ingest_normalized_message(
            db, _inbound(professional.assistant_phone, customer_phone)
        )
        assert message is not None
        rows = (
            db.query(PendingProcessing)
            .filter(PendingProcessing.conversation_id == message.conversation_id)
            .all()
        )
        assert len(rows) == 1
    finally:
        _cleanup(db, [professional.id])
        db.close()


def test_ingest_reuses_manually_registered_contact_by_canonical_phone() -> None:
    db = SessionLocal()
    professional = Professional(name="Tenant Manual", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    contact = create_contact(
        db,
        professional.id,
        "Ana cadastrada",
        "+55 11 99999-0001",
    )
    db.commit()
    try:
        message = ingest_normalized_message(
            db,
            _inbound(
                professional.assistant_phone,
                "(11) 99999-0001",
                "Nome vindo do WhatsApp",
            ),
        )

        assert message is not None
        assert message.conversation_id is not None
        conversation = db.query(Conversation).filter(Conversation.id == message.conversation_id).one()
        assert conversation.contact_id == contact.id
        assert (
            db.query(Contact)
            .filter(
                Contact.professional_id == professional.id,
                Contact.phone == "+5511999990001",
            )
            .count()
            == 1
        )
        db.refresh(contact)
        assert contact.display_name == "Ana cadastrada"
    finally:
        _cleanup(db, [professional.id])
        db.close()


def test_ingest_rejects_an_invalid_customer_phone() -> None:
    db = SessionLocal()
    professional = Professional(name="Tenant Invalid Phone", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    try:
        with pytest.raises(WhatsAppPermanentError):
            ingest_normalized_message(
                db,
                _inbound(professional.assistant_phone, "+551133330001"),
            )
        assert db.query(Contact).filter(Contact.professional_id == professional.id).count() == 0
    finally:
        _cleanup(db, [professional.id])
        db.close()


def test_duplicate_delivery_recreates_a_lost_debounce_row_without_bumping() -> None:
    """A retry that sees the duplicate message must still guarantee a debounce
    row exists, but must not push an already-due window into the future."""
    db = SessionLocal()
    professional = Professional(name="Tenant Recover", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    customer_phone = _random_phone()
    event = _inbound(professional.assistant_phone, customer_phone)
    try:
        first = ingest_normalized_message(db, event)
        assert first is not None
        conversation_id = first.conversation_id

        # Simulate the debounce row being lost after a partial failure.
        db.query(PendingProcessing).filter(
            PendingProcessing.conversation_id == conversation_id
        ).delete(synchronize_session=False)
        db.commit()

        # Same provider_message_id — a webhook retry.
        duplicate = ingest_normalized_message(db, event)
        assert duplicate is None
        recovered = (
            db.query(PendingProcessing)
            .filter(PendingProcessing.conversation_id == conversation_id)
            .one()
        )

        # A second retry must not move process_after forward.
        first_process_after = recovered.process_after
        again = ingest_normalized_message(db, event)
        assert again is None
        db.expire_all()
        unchanged = (
            db.query(PendingProcessing)
            .filter(PendingProcessing.conversation_id == conversation_id)
            .one()
        )
        assert unchanged.process_after == first_process_after
    finally:
        _cleanup(db, [professional.id])
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


def test_dispatch_drops_echo_addressed_to_the_platform_agent_number(monkeypatch) -> None:
    """An instructor->agent echo lands on the tenant number as an outbound
    event. It must never create a customer Contact/Conversation/Message."""
    monkeypatch.setenv("PLATFORM_AGENT_WHATSAPP_NUMBER", PLATFORM_NUMBER)
    db = SessionLocal()
    professional = Professional(name="Tenant Echo", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    try:
        result = dispatch_whatsapp_event(
            db, _outbound(professional.assistant_phone, PLATFORM_NUMBER), None
        )
        assert result is None
        assert (
            db.query(Contact).filter(Contact.phone == PLATFORM_NUMBER).count() == 0
        )
        assert (
            db.query(Message)
            .filter(Message.professional_id == professional.id)
            .count()
            == 0
        )
        assert (
            db.query(Conversation)
            .filter(Conversation.professional_id == professional.id)
            .count()
            == 0
        )
    finally:
        _cleanup(db, [professional.id])
        db.close()


def test_dispatch_still_ingests_a_normal_instructor_echo(monkeypatch) -> None:
    """The guard must not touch ordinary customer-facing traffic."""
    monkeypatch.setenv("PLATFORM_AGENT_WHATSAPP_NUMBER", PLATFORM_NUMBER)
    db = SessionLocal()
    professional = Professional(name="Tenant NormalEcho", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    customer_phone = _random_phone()
    try:
        message = dispatch_whatsapp_event(
            db, _outbound(professional.assistant_phone, customer_phone), None
        )
        assert message is not None
        assert message.professional_id == professional.id
        assert message.direction == "outbound"
        contact = db.query(Contact).filter(Contact.phone == customer_phone).one()
        assert contact.professional_id == professional.id
    finally:
        _cleanup(db, [professional.id])
        db.close()

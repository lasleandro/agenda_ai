"""Durable webhook handoff: verify -> receipt -> asynchronous processing."""

import json
from pathlib import Path
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.main import app
from app.models import Contact, Conversation, Message, OperationalEvent, Professional, WebhookReceipt
from app.chat.webhook_processor_worker import drain_once


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().int % 100_000_000:08d}"


def _inbound_payload(assistant_phone: str, customer_phone: str, msg_id: str) -> bytes:
    return json.dumps(
        {
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "id": msg_id,
                "from": customer_phone,
                "to": assistant_phone,
                "text": {"body": "Oi, posso marcar aula?"},
                "sendTime": "2026-09-02T10:00:00Z",
                "customerProfile": {"name": "Cliente"},
            },
        }
    ).encode("utf-8")


def _cleanup(db, professional_id, event_keys) -> None:
    db.query(OperationalEvent).filter(
        OperationalEvent.professional_id == professional_id
    ).delete(synchronize_session=False)
    conversation_ids = [
        row[0]
        for row in db.query(Conversation.id)
        .filter(Conversation.professional_id == professional_id)
        .all()
    ]
    from app.models import PendingProcessing

    if conversation_ids:
        db.query(PendingProcessing).filter(
            PendingProcessing.conversation_id.in_(conversation_ids)
        ).delete(synchronize_session=False)
    db.query(Message).filter(Message.professional_id == professional_id).delete(
        synchronize_session=False
    )
    db.query(Conversation).filter(
        Conversation.professional_id == professional_id
    ).delete(synchronize_session=False)
    db.query(Contact).filter(Contact.professional_id == professional_id).delete(
        synchronize_session=False
    )
    db.query(Professional).filter(Professional.id == professional_id).delete(
        synchronize_session=False
    )
    if event_keys:
        db.query(WebhookReceipt).filter(
            WebhookReceipt.event_key.in_(event_keys)
        ).delete(synchronize_session=False)
    db.commit()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")  # bypass signature for the test
    return TestClient(app)


def test_webhook_verifies_records_receipt_and_ingests_inline(client, monkeypatch) -> None:
    monkeypatch.setenv("WEBHOOK_INLINE_PROCESSING", "true")
    db = SessionLocal()
    professional = Professional(name="WH Tenant", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    customer_phone = _random_phone()
    raw = _inbound_payload(professional.assistant_phone, customer_phone, f"m_{uuid.uuid4().hex}")
    from app.integrations.tasks.keys import event_key

    key = event_key("ycloud", raw)
    try:
        res = client.post("/webhooks/ycloud", content=raw)
        assert res.status_code == 200

        receipt = db.query(WebhookReceipt).filter(WebhookReceipt.event_key == key).one()
        assert receipt.status == "done"

        message = (
            db.query(Message)
            .filter(Message.professional_id == professional.id)
            .one()
        )
        assert message.provider_message_id is not None
    finally:
        _cleanup(db, professional.id, [key])
        db.close()


def test_identical_redelivery_is_idempotent(client, monkeypatch) -> None:
    monkeypatch.setenv("WEBHOOK_INLINE_PROCESSING", "true")
    db = SessionLocal()
    professional = Professional(name="WH Dup", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    raw = _inbound_payload(professional.assistant_phone, _random_phone(), f"m_{uuid.uuid4().hex}")
    from app.integrations.tasks.keys import event_key

    key = event_key("ycloud", raw)
    try:
        assert client.post("/webhooks/ycloud", content=raw).status_code == 200
        assert client.post("/webhooks/ycloud", content=raw).status_code == 200

        assert (
            db.query(WebhookReceipt).filter(WebhookReceipt.event_key == key).count() == 1
        )
        assert (
            db.query(Message).filter(Message.professional_id == professional.id).count()
            == 1
        )
    finally:
        _cleanup(db, professional.id, [key])
        db.close()


def test_worker_drains_receipt_when_inline_processing_disabled(client, monkeypatch) -> None:
    monkeypatch.setenv("WEBHOOK_INLINE_PROCESSING", "false")
    db = SessionLocal()
    professional = Professional(name="WH Async", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    raw = _inbound_payload(professional.assistant_phone, _random_phone(), f"m_{uuid.uuid4().hex}")
    from app.integrations.tasks.keys import event_key

    key = event_key("ycloud", raw)
    try:
        assert client.post("/webhooks/ycloud", content=raw).status_code == 200

        pending = db.query(WebhookReceipt).filter(WebhookReceipt.event_key == key).one()
        assert pending.status == "received"
        assert (
            db.query(Message).filter(Message.professional_id == professional.id).count()
            == 0
        )

        drain_once()

        db.expire_all()
        drained = db.query(WebhookReceipt).filter(WebhookReceipt.event_key == key).one()
        assert drained.status == "done"
        assert (
            db.query(Message).filter(Message.professional_id == professional.id).count()
            == 1
        )
    finally:
        _cleanup(db, professional.id, [key])
        db.close()


def test_unknown_provider_returns_404(client) -> None:
    res = client.post("/webhooks/whatsapp/not-a-provider", content=b"{}")
    assert res.status_code == 404


def test_webhook_rejects_oversized_body_before_signature_verification(client) -> None:
    response = client.post("/webhooks/ycloud", content=b"x" * (1024 * 1024 + 1))

    assert response.status_code == 413

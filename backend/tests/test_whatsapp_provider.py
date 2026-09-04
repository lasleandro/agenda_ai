"""Unit tests for the provider-neutral YCloud WhatsApp adapter."""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations.whatsapp.contracts import (
    WhatsAppDeliveryUpdated,
    WhatsAppMessageEvent,
    WhatsAppPermanentError,
)
from app.integrations.whatsapp.ycloud import YCloudWhatsAppProvider


def _signature(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), timestamp.encode("utf-8") + b"." + body, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},s={digest}"


def _now_ts() -> str:
    return str(int(datetime.now(timezone.utc).timestamp()))


def test_ycloud_provider_verifies_and_normalizes_inbound_message(monkeypatch) -> None:
    secret = "test-secret"
    monkeypatch.setenv("YCLOUD_WEBHOOK_SIGNING_SECRET", secret)
    provider = YCloudWhatsAppProvider()
    payload = {
        "type": "whatsapp.inbound_message.received",
        "whatsappInboundMessage": {
            "id": "inbound-1",
            "from": "+5511999990001",
            "to": "+5511988880001",
            "text": {"body": "Olá"},
            "sendTime": "2026-08-16T10:00:00Z",
            "customerProfile": {"name": "Cliente"},
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")

    assert provider.verify_webhook(
        raw_body, {"YCloud-Signature": _signature(secret, _now_ts(), raw_body)}
    )
    event = provider.parse_webhook(raw_body)[0]

    assert isinstance(event, WhatsAppMessageEvent)
    assert event.provider_key == "ycloud"
    assert event.provider_message_id == "inbound-1"
    assert event.direction == "inbound"
    assert event.contact_name == "Cliente"


def test_ycloud_provider_rejects_stale_but_correctly_signed_callback(monkeypatch) -> None:
    """A valid signature over an old timestamp must not be accepted — this is
    the replay-window guard."""
    secret = "test-secret"
    monkeypatch.setenv("YCLOUD_WEBHOOK_SIGNING_SECRET", secret)
    monkeypatch.delenv("DEBUG", raising=False)
    provider = YCloudWhatsAppProvider()
    raw_body = json.dumps({"type": "whatsapp.inbound_message.received"}).encode("utf-8")

    stale_ts = "1723802400"  # 2024
    assert not provider.verify_webhook(
        raw_body, {"YCloud-Signature": _signature(secret, stale_ts, raw_body)}
    )


def test_ycloud_provider_accepts_stale_timestamp_under_debug(monkeypatch) -> None:
    """DEBUG bypasses freshness so recorded fixtures and manual replays work."""
    secret = "test-secret"
    monkeypatch.setenv("YCLOUD_WEBHOOK_SIGNING_SECRET", secret)
    monkeypatch.setenv("DEBUG", "true")
    provider = YCloudWhatsAppProvider()
    raw_body = json.dumps({"type": "whatsapp.inbound_message.received"}).encode("utf-8")

    assert provider.verify_webhook(
        raw_body, {"YCloud-Signature": _signature(secret, "1723802400", raw_body)}
    )


def test_ycloud_provider_normalizes_delivery_update_and_rejects_invalid_json() -> None:
    provider = YCloudWhatsAppProvider()
    payload = {
        "type": "whatsapp.message.updated",
        "whatsappMessage": {
            "id": "outbound-1",
            "status": "delivered",
            "externalId": "scheduled-task-run:run-1",
            "updateTime": "2026-08-16T10:05:00Z",
        },
    }

    event = provider.parse_webhook(json.dumps(payload).encode("utf-8"))[0]

    assert isinstance(event, WhatsAppDeliveryUpdated)
    assert event.status == "delivered"
    assert event.external_id == "scheduled-task-run:run-1"
    with pytest.raises(WhatsAppPermanentError):
        provider.parse_webhook(b"not-json")

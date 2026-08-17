"""Deprecated compatibility imports for the moved YCloud adapter.

New application code must import the provider-neutral contracts and adapter
from ``app.integrations.whatsapp``. This module remains only while older tests
and scripts are migrated.
"""

import hashlib
import hmac
import json
import os

from app.integrations.whatsapp.contracts import WhatsAppMessageEvent as NormalizedMessage
from app.integrations.whatsapp.contracts import WhatsAppTextRequest
from app.integrations.whatsapp.ycloud import YCloudWhatsAppProvider


def verify_signature(raw_body: bytes, signature_header: str | None, secret: str) -> bool:
    """Compatibility verifier for callers that still provide a secret directly."""
    if not signature_header or not secret:
        return False
    parts = dict(part.split("=", 1) for part in signature_header.split(",") if "=" in part)
    timestamp, signature = parts.get("t"), parts.get("s")
    if not timestamp or not signature:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), timestamp.encode("utf-8") + b"." + raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def webhook_signing_secret() -> str:
    return os.getenv("YCLOUD_WEBHOOK_SIGNING_SECRET", "")


def normalize_event(event: dict) -> NormalizedMessage | None:
    events = YCloudWhatsAppProvider().parse_webhook(json.dumps(event).encode("utf-8"))
    return next((item for item in events if isinstance(item, NormalizedMessage)), None)


def send_text_message(from_phone: str, to_phone: str, body: str) -> None:
    YCloudWhatsAppProvider().send_text(
        WhatsAppTextRequest(from_phone=from_phone, to_phone=to_phone, body=body)
    )


def send_text_message_or_raise(from_phone: str, to_phone: str, body: str) -> None:
    send_text_message(from_phone, to_phone, body)

"""
YCloud MessagingProvider implementation (brief Section 9).

Handles webhook signature verification and normalization of YCloud's
WhatsApp Coexistence event payloads into a provider-agnostic shape.
"""

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

YCLOUD_API_BASE = "https://api.ycloud.com/v2"


def verify_signature(raw_body: bytes, signature_header: str | None, secret: str) -> bool:
    """Verify the `YCloud-Signature: t={timestamp},s={signature}` header.

    Signed string is `{timestamp}.{raw_body}`, HMAC-SHA256 with the webhook
    signing secret, compared in constant time.
    """
    if not signature_header:
        return False

    parts = dict(p.split("=", 1) for p in signature_header.split(",") if "=" in p)
    timestamp, signature = parts.get("t"), parts.get("s")
    if not timestamp or not signature:
        return False

    signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
    expected = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@dataclass
class NormalizedMessage:
    provider_message_id: str
    direction: str  # "inbound" | "outbound"
    from_phone: str
    to_phone: str
    text: str | None
    sent_at: datetime
    raw_payload: dict
    contact_name: str | None = None


def normalize_event(event: dict) -> NormalizedMessage | None:
    """Normalize a YCloud webhook event into a NormalizedMessage, or None if
    the event type isn't a message we track (e.g. delivery-status updates).
    """
    event_type = event.get("type")

    if event_type == "whatsapp.inbound_message.received":
        msg = event["whatsappInboundMessage"]
        return NormalizedMessage(
            provider_message_id=msg["id"],
            direction="inbound",
            from_phone=msg["from"],
            to_phone=msg["to"],
            text=msg.get("text", {}).get("body"),
            sent_at=datetime.fromisoformat(msg["sendTime"].replace("Z", "+00:00")),
            raw_payload=event,
            contact_name=msg.get("customerProfile", {}).get("name"),
        )

    if event_type == "whatsapp.smb.message.echoes":
        msg = event["whatsappMessage"]
        return NormalizedMessage(
            provider_message_id=msg["id"],
            direction="outbound",
            from_phone=msg["from"],
            to_phone=msg["to"],
            text=msg.get("text", {}).get("body"),
            sent_at=datetime.fromisoformat(msg["sendTime"].replace("Z", "+00:00")),
            raw_payload=event,
        )

    return None


def webhook_signing_secret() -> str:
    return os.getenv("YCLOUD_WEBHOOK_SIGNING_SECRET", "")


def send_text_message(from_phone: str, to_phone: str, body: str) -> None:
    """Send an outbound WhatsApp text message via the YCloud REST API.

    Errors are logged, not raised — a failed reply must not roll back the
    inbound webhook transaction that triggered it.
    """
    try:
        send_text_message_or_raise(from_phone, to_phone, body)
    except httpx.HTTPError:
        logger.exception("Failed to send YCloud WhatsApp message from %s to %s", from_phone, to_phone)


def send_text_message_or_raise(from_phone: str, to_phone: str, body: str) -> None:
    """Send a WhatsApp message and expose provider failures to durable callers."""
    response = httpx.post(
        f"{YCLOUD_API_BASE}/whatsapp/messages",
        headers={"X-API-Key": os.getenv("YCLOUD_API_KEY", ""), "Content-Type": "application/json"},
        json={"from": from_phone, "to": to_phone, "type": "text", "text": {"body": body}},
        timeout=10.0,
    )
    response.raise_for_status()

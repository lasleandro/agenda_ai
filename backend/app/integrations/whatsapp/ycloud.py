"""YCloud implementation of the provider-neutral WhatsApp contract."""

import hashlib
import hmac
import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone

import httpx

from app.integrations.whatsapp.contracts import (
    WhatsAppDeliveryUnknownError,
    WhatsAppDeliveryUpdated,
    WhatsAppEvent,
    WhatsAppPermanentError,
    WhatsAppRetryableError,
    WhatsAppSendResult,
    WhatsAppTemplateRequest,
    WhatsAppTextRequest,
    WhatsAppMessageEvent,
)

YCLOUD_API_BASE = "https://api.ycloud.com/v2"
YCLOUD_PROVIDER_KEY = "ycloud"

# A captured, correctly-signed callback stays valid forever unless the signed
# timestamp is also checked for freshness. YCloud retries within minutes, so a
# few minutes of tolerance covers legitimate retries and clock skew.
_DEFAULT_SIGNATURE_TOLERANCE_SECONDS = 300


def _signature_tolerance_seconds() -> int:
    raw = os.getenv("YCLOUD_WEBHOOK_TOLERANCE_SECONDS", "").strip()
    return int(raw) if raw else _DEFAULT_SIGNATURE_TOLERANCE_SECONDS


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _header(headers: Mapping[str, str], name: str) -> str | None:
    expected = name.casefold()
    return next(
        (value for key, value in headers.items() if key.casefold() == expected),
        None,
    )


def _response_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or f"HTTP {response.status_code}")[:500]
    return f"HTTP {response.status_code}"


class YCloudWhatsAppProvider:
    """YCloud HTTP/signature/payload mappings kept behind one adapter."""

    key = YCLOUD_PROVIDER_KEY

    def __init__(self) -> None:
        self._api_key = os.getenv("YCLOUD_API_KEY", "")
        self._signing_secret = os.getenv("YCLOUD_WEBHOOK_SIGNING_SECRET", "")

    def verify_webhook(self, raw_body: bytes, headers: Mapping[str, str]) -> bool:
        """Verify YCloud's timestamped HMAC webhook signature."""
        signature_header = _header(headers, "ycloud-signature")
        if not signature_header or not self._signing_secret:
            return False

        parts = dict(
            part.split("=", 1)
            for part in signature_header.split(",")
            if "=" in part
        )
        timestamp, signature = parts.get("t"), parts.get("s")
        if not timestamp or not signature:
            return False

        signed_payload = timestamp.encode("utf-8") + b"." + raw_body
        expected = hmac.new(
            self._signing_secret.encode("utf-8"), signed_payload, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return False

        return self._timestamp_is_fresh(timestamp)

    def _timestamp_is_fresh(self, timestamp: str) -> bool:
        """Reject a correctly-signed callback whose signed timestamp is stale.

        Bypassed under DEBUG so recorded fixtures and manual replays still
        work in local development.
        """
        if os.getenv("DEBUG", "").casefold() == "true":
            return True
        try:
            signed_at = int(timestamp)
        except ValueError:
            return False
        age = abs(int(datetime.now(timezone.utc).timestamp()) - signed_at)
        return age <= _signature_tolerance_seconds()

    def parse_webhook(self, raw_body: bytes) -> list[WhatsAppEvent]:
        """Normalize known YCloud webhook events; ignore unsupported events."""
        try:
            event = json.loads(raw_body)
        except (TypeError, ValueError) as exc:
            raise WhatsAppPermanentError("Invalid YCloud webhook payload") from exc
        if not isinstance(event, dict):
            raise WhatsAppPermanentError("Invalid YCloud webhook payload")

        event_type = event.get("type")
        if event_type == "whatsapp.inbound_message.received":
            message = event.get("whatsappInboundMessage")
            if not isinstance(message, dict):
                raise WhatsAppPermanentError("Missing YCloud inbound message")
            return [
                WhatsAppMessageEvent(
                    provider_key=self.key,
                    provider_message_id=str(message["id"]),
                    direction="inbound",
                    from_phone=str(message["from"]),
                    to_phone=str(message["to"]),
                    text=(message.get("text") or {}).get("body"),
                    sent_at=_parse_timestamp(message.get("sendTime")),
                    raw_payload=event,
                    contact_name=(message.get("customerProfile") or {}).get("name"),
                )
            ]

        if event_type == "whatsapp.smb.message.echoes":
            message = event.get("whatsappMessage")
            if not isinstance(message, dict):
                raise WhatsAppPermanentError("Missing YCloud outbound message")
            return [
                WhatsAppMessageEvent(
                    provider_key=self.key,
                    provider_message_id=str(message["id"]),
                    direction="outbound",
                    from_phone=str(message["from"]),
                    to_phone=str(message["to"]),
                    text=(message.get("text") or {}).get("body"),
                    sent_at=_parse_timestamp(message.get("sendTime")),
                    raw_payload=event,
                )
            ]

        if event_type == "whatsapp.message.updated":
            message = event.get("whatsappMessage")
            if not isinstance(message, dict) or not message.get("id"):
                raise WhatsAppPermanentError("Missing YCloud delivery update")
            status = str(message.get("status", "")).casefold()
            normalized_status = {
                "queued": "accepted",
                "accepted": "accepted",
                "sent": "sent",
                "delivered": "delivered",
                "read": "read",
                "failed": "failed",
            }.get(status)
            if normalized_status is None:
                return []
            return [
                WhatsAppDeliveryUpdated(
                    provider_key=self.key,
                    provider_message_id=str(message["id"]),
                    status=normalized_status,  # type: ignore[arg-type]
                    occurred_at=_parse_timestamp(
                        message.get("updateTime") or event.get("createTime")
                    ),
                    external_id=message.get("externalId"),
                    error_code=str(message["errorCode"]) if message.get("errorCode") else None,
                    error_detail=(
                        str(message["errorMessage"])[:500]
                        if message.get("errorMessage")
                        else None
                    ),
                )
            ]

        return []

    def send_text(self, request: WhatsAppTextRequest) -> WhatsAppSendResult:
        """Submit a free-form YCloud text message."""
        payload: dict = {
            "from": request.from_phone,
            "to": request.to_phone,
            "type": "text",
            "text": {"body": request.body},
        }
        if request.external_id:
            payload["externalId"] = request.external_id
        return self._enqueue(payload, request.external_id)

    def send_template(self, request: WhatsAppTemplateRequest) -> WhatsAppSendResult:
        """Submit an approved logical template using YCloud configuration."""
        template_name = self._template_name(request.template_key)
        template: dict = {
            "name": template_name,
            "language": {"code": request.language, "policy": "deterministic"},
        }
        if request.parameters:
            template["components"] = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": parameter}
                        for parameter in request.parameters
                    ],
                }
            ]
        payload: dict = {
            "from": request.from_phone,
            "to": request.to_phone,
            "type": "template",
            "template": template,
        }
        if request.external_id:
            payload["externalId"] = request.external_id
        if request.ttl_seconds is not None:
            payload["ttlSeconds"] = request.ttl_seconds
        return self._enqueue(payload, request.external_id)

    def _template_name(self, template_key: str) -> str:
        if template_key != "daily_agenda":
            raise WhatsAppPermanentError(f"Unsupported YCloud template key: {template_key}")
        template_name = os.getenv("YCLOUD_DAILY_AGENDA_TEMPLATE_NAME", "")
        if not template_name:
            raise WhatsAppPermanentError("Daily agenda WhatsApp template is not configured")
        return template_name

    def _enqueue(self, payload: dict, external_id: str | None) -> WhatsAppSendResult:
        if not self._api_key:
            raise WhatsAppPermanentError("YCloud API key is not configured")
        try:
            response = httpx.post(
                f"{YCLOUD_API_BASE}/whatsapp/messages",
                headers={"X-API-Key": self._api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=10.0,
            )
        except httpx.TimeoutException as exc:
            raise WhatsAppDeliveryUnknownError("Timed out while submitting WhatsApp message") from exc
        except httpx.NetworkError as exc:
            raise WhatsAppRetryableError("Could not reach WhatsApp provider") from exc

        if response.status_code >= 500:
            raise WhatsAppRetryableError(_response_error_detail(response))
        if response.status_code >= 400:
            raise WhatsAppPermanentError(_response_error_detail(response))

        try:
            body = response.json()
        except ValueError as exc:
            raise WhatsAppDeliveryUnknownError("Provider accepted an unreadable response") from exc
        provider_message_id = body.get("id") if isinstance(body, dict) else None
        if not provider_message_id:
            raise WhatsAppDeliveryUnknownError("Provider accepted a response without a message ID")
        return WhatsAppSendResult(
            provider_key=self.key,
            provider_message_id=str(provider_message_id),
            accepted_at=datetime.now(timezone.utc),
            external_id=external_id,
        )

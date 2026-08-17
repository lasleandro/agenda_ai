"""Canonical contracts shared by WhatsApp providers and application services."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypeAlias


class WhatsAppProviderError(Exception):
    """Base class for sanitized provider failures."""


class WhatsAppRetryableError(WhatsAppProviderError):
    """The provider definitely did not accept the request and may be retried."""


class WhatsAppPermanentError(WhatsAppProviderError):
    """The provider rejected the request and retrying will not help."""


class WhatsAppDeliveryUnknownError(WhatsAppProviderError):
    """The provider may have accepted the request before the client failed."""


@dataclass(frozen=True)
class WhatsAppMessageEvent:
    """A provider-normalized inbound message or outbound echo."""

    provider_message_id: str
    direction: Literal["inbound", "outbound"]
    from_phone: str
    to_phone: str
    text: str | None
    sent_at: datetime
    raw_payload: dict
    contact_name: str | None = None
    provider_key: str = "ycloud"


@dataclass(frozen=True)
class WhatsAppDeliveryUpdated:
    """A provider-normalized asynchronous delivery-status update."""

    provider_key: str
    provider_message_id: str
    status: Literal["accepted", "sent", "delivered", "read", "failed"]
    occurred_at: datetime
    external_id: str | None = None
    error_code: str | None = None
    error_detail: str | None = None


WhatsAppEvent: TypeAlias = WhatsAppMessageEvent | WhatsAppDeliveryUpdated


@dataclass(frozen=True)
class WhatsAppTextRequest:
    """A free-form text message requested by application logic."""

    from_phone: str
    to_phone: str
    body: str
    external_id: str | None = None


@dataclass(frozen=True)
class WhatsAppTemplateRequest:
    """A provider-neutral template request using a logical template key."""

    from_phone: str
    to_phone: str
    template_key: str
    language: str
    parameters: tuple[str, ...] = ()
    external_id: str | None = None
    ttl_seconds: int | None = None


@dataclass(frozen=True)
class WhatsAppSendResult:
    """Provider acceptance metadata for an outbound WhatsApp request."""

    provider_key: str
    provider_message_id: str
    accepted_at: datetime
    external_id: str | None = None

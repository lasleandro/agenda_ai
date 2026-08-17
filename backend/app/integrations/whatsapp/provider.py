"""Minimal capability contract for a WhatsApp provider adapter."""

from collections.abc import Mapping
from typing import Protocol

from app.integrations.whatsapp.contracts import (
    WhatsAppEvent,
    WhatsAppSendResult,
    WhatsAppTemplateRequest,
    WhatsAppTextRequest,
)


class WhatsAppProvider(Protocol):
    """Translate provider traffic without exposing vendor types to the app."""

    key: str

    def verify_webhook(self, raw_body: bytes, headers: Mapping[str, str]) -> bool:
        """Return whether the provider authenticated this webhook payload."""

    def parse_webhook(self, raw_body: bytes) -> list[WhatsAppEvent]:
        """Convert one provider webhook payload into canonical events."""

    def send_text(self, request: WhatsAppTextRequest) -> WhatsAppSendResult:
        """Submit a free-form text message or raise a canonical provider error."""

    def send_template(self, request: WhatsAppTemplateRequest) -> WhatsAppSendResult:
        """Submit a template message or raise a canonical provider error."""

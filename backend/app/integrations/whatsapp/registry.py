"""Configured provider selection kept at application composition boundaries."""

import os

from app.integrations.whatsapp.provider import WhatsAppProvider
from app.integrations.whatsapp.ycloud import YCloudWhatsAppProvider


def get_whatsapp_provider(provider_key: str | None = None) -> WhatsAppProvider:
    """Return the strict configured adapter; unsupported providers fail closed."""
    selected = (provider_key or os.getenv("WHATSAPP_PROVIDER", "ycloud")).casefold()
    if selected == "ycloud":
        return YCloudWhatsAppProvider()
    raise ValueError(f"Unsupported WhatsApp provider: {selected}")

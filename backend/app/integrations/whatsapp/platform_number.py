"""The platform's own WhatsApp agent number — configuration, not tenant data.

One number, shared by every tenant, that instructors message to reach the AI
agent (Shared Platform AI Agent Number Roadmap v0.1). Distinct from each
tenant's customer-facing ``assistant_phone``.

Kept beside the provider boundary so both the chat and service layers can
import it without a cycle. ``is_platform_number`` is the single predicate every
routing decision asks; no call site compares raw phone strings.
"""

import os

from app.services.phone_numbers import PhoneNumberValidationError, normalize_mobile_phone

_ENV_VAR = "PLATFORM_AGENT_WHATSAPP_NUMBER"


def platform_agent_number() -> str | None:
    """Return the configured platform agent number in E.164, or ``None``.

    An unset or unparseable value leaves the shared-number feature inert rather
    than failing startup: the agent channel simply never claims a message.
    """
    raw = os.getenv(_ENV_VAR, "").strip()
    if not raw:
        return None
    try:
        return normalize_mobile_phone(raw)
    except PhoneNumberValidationError:
        return None


def is_platform_number(phone: str | None) -> bool:
    """Whether ``phone`` is the platform's own agent number.

    Both sides are compared in E.164 so a raw provider value (with or without a
    leading ``+``) matches the configured number. If a value cannot be
    normalized, fall back to a stripped-string comparison.
    """
    if not phone:
        return False
    configured = platform_agent_number()
    if configured is None:
        return False
    try:
        return normalize_mobile_phone(phone) == configured
    except PhoneNumberValidationError:
        return phone.strip() == configured

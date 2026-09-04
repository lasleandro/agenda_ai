"""Canonical validation for customer WhatsApp phone numbers."""

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberType


class PhoneNumberValidationError(ValueError):
    """Raised when a value cannot identify a supported mobile number."""


def normalize_mobile_phone(value: str) -> str:
    """Return a valid mobile phone number in canonical E.164 format.

    Brazilian national-format input is supported for the platform's primary
    market. Numbers from other countries must include an international calling
    code (for example ``+1``). ``FIXED_LINE_OR_MOBILE`` is accepted because
    some national numbering plans cannot distinguish those types.
    """
    raw = value.strip()
    if not raw:
        raise PhoneNumberValidationError("Phone number is required")

    try:
        parsed = phonenumbers.parse(raw, "BR")
    except NumberParseException as exc:
        raise PhoneNumberValidationError("Enter a valid WhatsApp phone number") from exc

    if parsed.extension or not phonenumbers.is_valid_number(parsed):
        raise PhoneNumberValidationError("Enter a valid WhatsApp phone number")

    number_type = phonenumbers.number_type(parsed)
    if number_type not in {PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE}:
        raise PhoneNumberValidationError("Enter a mobile WhatsApp phone number")

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

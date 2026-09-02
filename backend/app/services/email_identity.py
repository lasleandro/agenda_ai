"""Canonical email validation shared by auth entry points."""

from email_validator import EmailNotValidError, validate_email


class InvalidEmailError(ValueError):
    """Raised when a user-provided email cannot identify an account."""


def normalize_email(value: str) -> str:
    """Validate and return the canonical identity form of an email address."""
    try:
        validated = validate_email(value.strip(), check_deliverability=False)
    except (EmailNotValidError, AttributeError) as exc:
        raise InvalidEmailError("Invalid email address") from exc

    normalized = validated.normalized.lower()
    if len(normalized) > 255:
        raise InvalidEmailError("Invalid email address")
    return normalized

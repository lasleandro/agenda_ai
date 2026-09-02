"""Email transport contracts independent of the SMTP provider."""

from dataclasses import dataclass


class EmailDeliveryError(Exception):
    """Base error for a failed outbound email delivery."""


class EmailPermanentError(EmailDeliveryError):
    """A delivery will not succeed without configuration or recipient changes."""


class EmailRetryableError(EmailDeliveryError):
    """A transient email transport failure suitable for bounded retry."""


@dataclass(frozen=True)
class OutboundEmail:
    """A fully rendered message ready for a provider-neutral sender."""

    to_address: str
    subject: str
    html_body: str
    text_body: str

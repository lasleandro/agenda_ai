"""SMTP sender configurable for GoDaddy and other standards-compliant mailboxes."""

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.settings import get_bool, get_int, is_production
from app.integrations.email.contracts import (
    EmailPermanentError,
    EmailRetryableError,
    OutboundEmail,
)


class EmailConfigurationError(ValueError):
    """Raised when SMTP configuration is incomplete or unsafe."""


class SmtpEmailSender:
    """Send email through implicit TLS or STARTTLS with verified certificates."""

    def __init__(self) -> None:
        self.enabled = get_bool("EMAIL_ENABLED", False)
        self.host = os.getenv("EMAIL_SMTP_HOST", "").strip()
        self.port = get_int("EMAIL_SMTP_PORT", 465) if self.enabled else 465
        self.security = os.getenv("EMAIL_SMTP_SECURITY", "ssl").strip().lower()
        self.username = os.getenv("EMAIL_SMTP_USERNAME", "").strip()
        self.password = os.getenv("EMAIL_SMTP_PASSWORD", "")
        self.from_address = os.getenv("EMAIL_FROM_ADDRESS", "").strip()
        self.from_name = os.getenv("EMAIL_FROM_NAME", "Tennis OS").strip()
        self.reply_to = os.getenv("EMAIL_REPLY_TO", "").strip()
        self.timeout_seconds = get_int("EMAIL_SMTP_TIMEOUT_SECONDS", 20)
        if self.enabled:
            self._validate()

    def _validate(self) -> None:
        if self.security not in {"ssl", "starttls"}:
            raise EmailConfigurationError("EMAIL_SMTP_SECURITY must be ssl or starttls")
        missing = [
            name
            for name, value in {
                "EMAIL_SMTP_HOST": self.host,
                "EMAIL_SMTP_USERNAME": self.username,
                "EMAIL_SMTP_PASSWORD": self.password,
                "EMAIL_FROM_ADDRESS": self.from_address,
            }.items()
            if not value
        ]
        if missing:
            raise EmailConfigurationError(f"Missing SMTP settings: {', '.join(missing)}")
        if is_production() and not self.enabled:
            raise EmailConfigurationError("EMAIL_ENABLED must be true in production")

    def send(self, message: OutboundEmail) -> None:
        """Deliver a multipart email or classify the safe retry behavior."""
        if not self.enabled:
            return
        mime = MIMEMultipart("alternative")
        mime["Subject"] = message.subject
        mime["From"] = f"{self.from_name} <{self.from_address}>"
        mime["To"] = message.to_address
        if self.reply_to:
            mime["Reply-To"] = self.reply_to
        mime.attach(MIMEText(message.text_body, "plain", "utf-8"))
        mime.attach(MIMEText(message.html_body, "html", "utf-8"))
        context = ssl.create_default_context()
        try:
            if self.security == "ssl":
                with smtplib.SMTP_SSL(
                    self.host, self.port, timeout=self.timeout_seconds, context=context
                ) as server:
                    server.login(self.username, self.password)
                    server.sendmail(self.from_address, [message.to_address], mime.as_string())
            else:
                with smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(self.username, self.password)
                    server.sendmail(self.from_address, [message.to_address], mime.as_string())
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused) as exc:
            raise EmailPermanentError(type(exc).__name__) from exc
        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            raise EmailRetryableError(type(exc).__name__) from exc

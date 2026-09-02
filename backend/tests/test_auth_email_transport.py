"""Unit tests for provider-neutral auth email rendering and SMTP branches."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations.email.contracts import OutboundEmail
from app.integrations.email.smtp import SmtpEmailSender
from app.integrations.email.templates import activation_email


class FakeSmtpConnection:
    """Records standard SMTP actions without opening a network connection."""

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.actions: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def ehlo(self) -> None:
        self.actions.append("ehlo")

    def starttls(self, **_kwargs) -> None:
        self.actions.append("starttls")

    def login(self, _username: str, _password: str) -> None:
        self.actions.append("login")

    def sendmail(self, _from_address: str, _to_addresses: list[str], _message: str) -> None:
        self.actions.append("sendmail")


def _configure(monkeypatch, *, security: str, port: str) -> None:
    monkeypatch.setenv("EMAIL_ENABLED", "true")
    monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("EMAIL_SMTP_PORT", port)
    monkeypatch.setenv("EMAIL_SMTP_SECURITY", security)
    monkeypatch.setenv("EMAIL_SMTP_USERNAME", "notices@example.test")
    monkeypatch.setenv("EMAIL_SMTP_PASSWORD", "mailbox-secret")
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", "notices@example.test")


def _message() -> OutboundEmail:
    return OutboundEmail("user@example.test", "Assunto", "<p>HTML</p>", "Texto")


def test_smtp_sender_uses_implicit_tls_for_ssl(monkeypatch) -> None:
    _configure(monkeypatch, security="ssl", port="465")
    connections: list[FakeSmtpConnection] = []

    def smtp_ssl(*args, **kwargs):
        connection = FakeSmtpConnection(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr("app.integrations.email.smtp.smtplib.SMTP_SSL", smtp_ssl)
    SmtpEmailSender().send(_message())

    assert connections[0].args[:2] == ("smtp.example.test", 465)
    assert "context" in connections[0].kwargs
    assert connections[0].actions == ["login", "sendmail"]


def test_smtp_sender_uses_starttls_for_starttls(monkeypatch) -> None:
    _configure(monkeypatch, security="starttls", port="587")
    connections: list[FakeSmtpConnection] = []

    def smtp(*args, **kwargs):
        connection = FakeSmtpConnection(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr("app.integrations.email.smtp.smtplib.SMTP", smtp)
    SmtpEmailSender().send(_message())

    assert connections[0].args[:2] == ("smtp.example.test", 587)
    assert connections[0].actions == ["ehlo", "starttls", "ehlo", "login", "sendmail"]


def test_activation_template_escapes_email_and_keeps_plain_text_fallback() -> None:
    message = activation_email('"<script>@example.test', "https://app.example.test/activate?token=abc", 60)

    assert "&lt;script&gt;" in message.html_body
    assert '"<script>' not in message.html_body
    assert "Ativar conta: https://app.example.test/activate?token=abc" in message.text_body

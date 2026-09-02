"""Escaped, multipart content for Tennis OS security email."""

from html import escape

from app.integrations.email.contracts import OutboundEmail


def _message(
    *,
    title: str,
    html_body: str,
    text_body: str,
    action_label: str | None = None,
    action_url: str | None = None,
) -> tuple[str, str]:
    action_html = ""
    action_text = ""
    if action_label and action_url:
        action_html = (
            f'<p><a href="{escape(action_url, quote=True)}" '
            'style="display:inline-block;padding:12px 18px;background:#4f46e5;color:#ffffff;'
            'border-radius:8px;text-decoration:none;font-weight:600;">'
            f"{escape(action_label)}</a></p>"
        )
        action_text = f"\n{action_label}: {action_url}\n"
    html = (
        '<!doctype html><html lang="pt-BR"><body style="margin:0;background:#f7f7fb;'
        'font-family:Arial,sans-serif;color:#1f2937;"><main style="max-width:560px;margin:32px auto;'
        'padding:32px;background:#ffffff;border-radius:12px;">'
        f"<h1 style=\"font-size:22px;margin:0 0 16px;\">{escape(title)}</h1>"
        f"<div style=\"font-size:16px;line-height:1.6;\">{html_body}</div>{action_html}"
        '<p style="margin-top:28px;font-size:13px;color:#6b7280;">Tennis OS</p>'
        "</main></body></html>"
    )
    text = f"{title}\n\n{text_body}{action_text}\nTennis OS"
    return html, text


def activation_email(email: str, action_url: str, expires_minutes: int) -> OutboundEmail:
    """Render the account activation message."""
    html_body = (
        f"<p>Olá,</p><p>Para ativar sua conta vinculada a {escape(email)}, escolha sua senha. "
        f"Este link expira em {expires_minutes} minutos.</p>"
        "<p>Se você não esperava este convite, ignore esta mensagem.</p>"
    )
    text_body = (
        f"Olá,\n\nPara ativar sua conta vinculada a {email}, escolha sua senha. "
        f"Este link expira em {expires_minutes} minutos.\n\n"
        "Se você não esperava este convite, ignore esta mensagem."
    )
    html, text = _message(
        title="Ative sua conta no Tennis OS",
        html_body=html_body,
        text_body=text_body,
        action_label="Ativar conta",
        action_url=action_url,
    )
    return OutboundEmail(email, "Ative sua conta no Tennis OS", html, text)


def password_reset_email(email: str, action_url: str, expires_minutes: int) -> OutboundEmail:
    """Render the password reset message."""
    html_body = (
        f"<p>Recebemos uma solicitação para redefinir a senha da conta {escape(email)}. "
        f"Este link expira em {expires_minutes} minutos.</p>"
        "<p>Se não foi você, ignore esta mensagem. Sua senha permanecerá inalterada.</p>"
    )
    text_body = (
        f"Recebemos uma solicitação para redefinir a senha da conta {email}. "
        f"Este link expira em {expires_minutes} minutos.\n\n"
        "Se não foi você, ignore esta mensagem. Sua senha permanecerá inalterada."
    )
    html, text = _message(
        title="Redefina sua senha do Tennis OS",
        html_body=html_body,
        text_body=text_body,
        action_label="Redefinir senha",
        action_url=action_url,
    )
    return OutboundEmail(email, "Redefina sua senha do Tennis OS", html, text)


def password_changed_email(email: str) -> OutboundEmail:
    """Render the post-reset notification without a token or credential."""
    html_body = (
        f"<p>A senha da conta {escape(email)} foi alterada com sucesso.</p>"
        "<p>Se você não fez essa alteração, entre em contato com o suporte imediatamente.</p>"
    )
    text_body = (
        f"A senha da conta {email} foi alterada com sucesso.\n\n"
        "Se você não fez essa alteração, entre em contato com o suporte imediatamente."
    )
    html, text = _message(
        title="Sua senha foi alterada",
        html_body=html_body,
        text_body=text_body,
    )
    return OutboundEmail(email, "Sua senha foi alterada", html, text)

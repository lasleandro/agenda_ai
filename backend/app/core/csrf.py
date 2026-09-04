"""Double-submit-cookie CSRF protection for browser (cookie-authenticated) writes.

The session cookie is ``SameSite=Lax``, which blocks cross-site POSTs from
forms but not all request shapes. A second, non-HttpOnly token cookie that
the frontend echoes in the ``X-CSRF-Token`` header closes the gap: an
attacker's page cannot read the victim's cookies, so it cannot forge the
header.

Enforcement is gated on production (see ``app.main``) so local development
and the test suite are unaffected until staging.
"""

import secrets

from fastapi import Response

from app.core.security import (
    SESSION_COOKIE_NAME,
    cookie_domain,
    cookie_samesite,
    cookie_secure,
)

CSRF_COOKIE_NAME = "agenda_csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Unauthenticated bootstrap endpoints: no session cookie exists yet, so there
# is nothing to protect and no token to echo.
CSRF_EXEMPT_PATHS = frozenset(
    {
        "/api/auth/login",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
        "/api/auth/activate",
        "/api/account-requests",
    }
)


def issue_csrf_cookie(response: Response) -> None:
    """Attach a fresh CSRF token cookie readable by the frontend."""
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=secrets.token_urlsafe(32),
        httponly=False,
        secure=cookie_secure(),
        samesite=cookie_samesite(),
        domain=cookie_domain(),
        path="/",
    )


def clear_csrf_cookie(response: Response) -> None:
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        domain=cookie_domain(),
        samesite=cookie_samesite(),
        secure=cookie_secure(),
    )


def csrf_check_required(method: str, path: str, cookies: dict) -> bool:
    """Whether this request must present a valid CSRF header."""
    if method.upper() in SAFE_METHODS:
        return False
    if not path.startswith("/api/"):
        return False
    if path in CSRF_EXEMPT_PATHS:
        return False
    # Only cookie-authenticated (browser) requests are at risk.
    return SESSION_COOKIE_NAME in cookies


def csrf_header_matches_cookie(header_value: str | None, cookies: dict) -> bool:
    cookie_value = cookies.get(CSRF_COOKIE_NAME)
    if not cookie_value or not header_value:
        return False
    return secrets.compare_digest(header_value, cookie_value)

"""
Centralized authentication configuration and password utilities.

Real user table (multi-tenancy roadmap Phase B) — JWT carries the user's
role and professional_id (tenant) so every request can be scoped without a
second lookup. Inspired by geoedge_municipios' auth_config.py.
"""

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from dotenv import load_dotenv

from app.core.settings import get_bool, get_int, is_production
from app.services.password_policy import hash_password, verify_password

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
load_dotenv(os.path.join(_project_root, ".env"))

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not SECRET_KEY:
    if is_production():
        raise RuntimeError("JWT_SECRET_KEY must be set in production")
    SECRET_KEY = secrets.token_urlsafe(64)
    print(
        "\nWARNING: JWT_SECRET_KEY is not set in .env.\n"
        "A random key was generated for this session — tokens will NOT survive restarts.\n"
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = get_int("AUTH_SESSION_EXPIRE_MINUTES", 60 * 24)
SESSION_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "agenda_access_token")
JWT_ISSUER = os.getenv("JWT_ISSUER", "tennis-os")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "tennis-os-web")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update(
        {
            "exp": expire,
            "iat": now,
            "jti": str(uuid.uuid4()),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token. Raises jwt exceptions on failure."""
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
    )


def cookie_secure() -> bool:
    """Return whether auth cookies must be restricted to HTTPS."""
    return get_bool("AUTH_COOKIE_SECURE", is_production())


def cookie_samesite() -> str:
    """Return a validated SameSite mode for the session cookie."""
    value = os.getenv("AUTH_COOKIE_SAMESITE", "lax").lower()
    if value not in {"lax", "strict", "none"}:
        raise ValueError("AUTH_COOKIE_SAMESITE must be lax, strict, or none")
    return value


def cookie_domain() -> str | None:
    """Return the optional narrow cookie domain."""
    return os.getenv("AUTH_COOKIE_DOMAIN") or None

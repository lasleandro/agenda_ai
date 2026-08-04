"""
Centralized authentication configuration and password utilities.

Single admin user, JWT cookie session — no user table (agenda_ai is a
single-professional POC). Inspired by geoedge_municipios' auth_config.py.
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

import jwt
from dotenv import load_dotenv

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
load_dotenv(os.path.join(_project_root, ".env"))

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(64)
    print(
        "\nWARNING: JWT_SECRET_KEY is not set in .env.\n"
        "A random key was generated for this session — tokens will NOT survive restarts.\n"
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.now() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token. Raises jwt exceptions on failure."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

"""Server-authoritative password validation and hashing compatibility."""

import unicodedata

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core import error_codes

MIN_PASSWORD_LENGTH = 15
MAX_PASSWORD_LENGTH = 128

_PASSWORD_HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_COMMON_PASSWORDS = frozenset(
    {
        "123456",
        "12345678",
        "123456789",
        "1234567890",
        "admin",
        "admin123",
        "iloveyou",
        "letmein",
        "password",
        "password1",
        "password123",
        "qwerty",
        "qwerty123",
        "senha",
        "senha123",
        "tennisos",
        "welcome",
    }
)


class PasswordPolicyError(ValueError):
    """A password policy violation with a stable client error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_password(password: str) -> str:
    """Normalize Unicode without trimming or otherwise changing user intent."""
    return unicodedata.normalize("NFC", password)


def validate_password(password: str, *, email: str | None = None) -> str:
    """Return a normalized password or raise a safe policy error."""
    normalized = normalize_password(password)
    if len(normalized) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            error_codes.PASSWORD_TOO_SHORT,
            "Use uma senha com pelo menos 15 caracteres.",
        )
    if len(normalized) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            error_codes.PASSWORD_TOO_LONG,
            "Use uma senha com no máximo 128 caracteres.",
        )

    compact = normalized.casefold()
    email_local = email.split("@", 1)[0].casefold() if email else ""
    if compact in _COMMON_PASSWORDS or (email_local and email_local in compact):
        raise PasswordPolicyError(
            error_codes.PASSWORD_BLOCKLISTED,
            "Escolha uma senha menos previsível e diferente do seu email.",
        )
    return normalized


def hash_password(password: str) -> str:
    """Hash a validated password with Argon2id."""
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, hashed_password: str) -> tuple[bool, bool]:
    """Verify Argon2id or legacy bcrypt and flag a successful bcrypt rehash."""
    try:
        if hashed_password.startswith("$argon2"):
            verified = _PASSWORD_HASHER.verify(hashed_password, password)
            return verified, verified and _PASSWORD_HASHER.check_needs_rehash(hashed_password)
        verified = bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
        return verified, verified
    except (InvalidHashError, VerificationError, VerifyMismatchError, ValueError):
        return False, False

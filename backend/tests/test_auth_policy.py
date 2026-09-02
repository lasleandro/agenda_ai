"""Unit coverage for canonical identity and server-authoritative password policy."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.email_identity import InvalidEmailError, normalize_email
from app.services.password_policy import PasswordPolicyError, validate_password


def test_normalize_email_trims_and_canonicalizes_case() -> None:
    assert normalize_email("  Owner@Example.COM ") == "owner@example.com"


def test_normalize_email_rejects_invalid_syntax() -> None:
    with pytest.raises(InvalidEmailError):
        normalize_email("not-an-email")


def test_password_policy_rejects_short_and_common_passwords() -> None:
    with pytest.raises(PasswordPolicyError, match="pelo menos 15"):
        validate_password("curta")
    with pytest.raises(PasswordPolicyError, match="menos previsível"):
        validate_password("owner tem uma senha longa", email="owner@example.com")


def test_password_policy_accepts_unicode_passphrase_without_composition_rule() -> None:
    assert validate_password("frase longa com café e trilhas") == "frase longa com café e trilhas"

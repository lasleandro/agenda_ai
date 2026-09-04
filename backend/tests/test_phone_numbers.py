"""Unit coverage for customer WhatsApp phone normalization."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.phone_numbers import PhoneNumberValidationError, normalize_mobile_phone


@pytest.mark.parametrize(
    "value",
    ["(11) 99999-0001", "11 99999-0001", "+55 11 99999-0001"],
)
def test_normalize_mobile_phone_equivalent_brazilian_formats_returns_e164(value: str) -> None:
    assert normalize_mobile_phone(value) == "+5511999990001"


def test_normalize_mobile_phone_foreign_e164_returns_e164() -> None:
    assert normalize_mobile_phone("+1 415 555 2671") == "+14155552671"


@pytest.mark.parametrize(
    "value",
    ["", "1199990001 ext. 2", "+55 11 3333-0001", "+999123"],
)
def test_normalize_mobile_phone_invalid_value_raises(value: str) -> None:
    with pytest.raises(PhoneNumberValidationError):
        normalize_mobile_phone(value)

"""Unit coverage for the shared platform agent number accessor."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations.whatsapp.platform_number import (
    is_platform_number,
    platform_agent_number,
)


def test_platform_agent_number_unset_returns_none(monkeypatch) -> None:
    monkeypatch.delenv("PLATFORM_AGENT_WHATSAPP_NUMBER", raising=False)
    assert platform_agent_number() is None


def test_platform_agent_number_normalizes_to_e164(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_AGENT_WHATSAPP_NUMBER", "5511918796827")
    assert platform_agent_number() == "+5511918796827"


def test_platform_agent_number_accepts_national_format(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_AGENT_WHATSAPP_NUMBER", "(11) 91879-6827")
    assert platform_agent_number() == "+5511918796827"


def test_platform_agent_number_unparseable_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_AGENT_WHATSAPP_NUMBER", "not-a-number")
    assert platform_agent_number() is None


def test_is_platform_number_matches_regardless_of_plus_prefix(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_AGENT_WHATSAPP_NUMBER", "+5511918796827")
    assert is_platform_number("5511918796827") is True
    assert is_platform_number("+5511918796827") is True


def test_is_platform_number_rejects_other_numbers(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_AGENT_WHATSAPP_NUMBER", "+5511918796827")
    assert is_platform_number("+5511949408816") is False


@pytest.mark.parametrize("value", [None, "", "   "])
def test_is_platform_number_handles_empty_input(monkeypatch, value) -> None:
    monkeypatch.setenv("PLATFORM_AGENT_WHATSAPP_NUMBER", "+5511918796827")
    assert is_platform_number(value) is False


def test_is_platform_number_false_when_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("PLATFORM_AGENT_WHATSAPP_NUMBER", raising=False)
    assert is_platform_number("+5511918796827") is False

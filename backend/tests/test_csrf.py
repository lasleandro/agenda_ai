"""CSRF double-submit protection (production-gated)."""

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.main as app_main
from app.core.csrf import (
    CSRF_COOKIE_NAME,
    csrf_check_required,
    csrf_header_matches_cookie,
)
from app.core.security import SESSION_COOKIE_NAME


def test_csrf_check_required_only_for_cookie_authed_unsafe_api_writes() -> None:
    session = {SESSION_COOKIE_NAME: "x"}
    assert csrf_check_required("POST", "/api/appointments", session) is True
    assert csrf_check_required("GET", "/api/appointments", session) is False
    assert csrf_check_required("POST", "/api/appointments", {}) is False  # no session
    assert csrf_check_required("POST", "/webhooks/ycloud", session) is False
    assert csrf_check_required("POST", "/api/auth/login", session) is False


def test_csrf_header_must_match_cookie() -> None:
    cookies = {CSRF_COOKIE_NAME: "secret-token"}
    assert csrf_header_matches_cookie("secret-token", cookies) is True
    assert csrf_header_matches_cookie("wrong", cookies) is False
    assert csrf_header_matches_cookie(None, cookies) is False
    assert csrf_header_matches_cookie("secret-token", {}) is False


@pytest.fixture()
def prod_client(monkeypatch):
    monkeypatch.setattr(app_main, "is_production", lambda: True)
    return TestClient(app_main.app)


def test_production_blocks_cookie_write_without_csrf_header(prod_client) -> None:
    prod_client.cookies.set(SESSION_COOKIE_NAME, "dummy-session")
    res = prod_client.post("/api/appointments", json={})
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "CSRF_TOKEN_INVALID"


def test_production_allows_write_with_matching_csrf(prod_client) -> None:
    prod_client.cookies.set(SESSION_COOKIE_NAME, "dummy-session")
    prod_client.cookies.set(CSRF_COOKIE_NAME, "tok123")
    res = prod_client.post(
        "/api/appointments", json={}, headers={"X-CSRF-Token": "tok123"}
    )
    # Passes the CSRF gate; fails later on auth/validation, never 403 CSRF.
    assert res.status_code != 403


def test_production_does_not_block_safe_methods_or_webhooks(prod_client) -> None:
    prod_client.cookies.set(SESSION_COOKIE_NAME, "dummy-session")
    assert prod_client.get("/api/auth/me").status_code != 403
    assert prod_client.post("/webhooks/whatsapp/unknown", content=b"{}").status_code == 404

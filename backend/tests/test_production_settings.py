"""Production startup configuration guards."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.settings import validate_startup_settings


def test_validate_startup_settings_rejects_debug_in_production(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")

    with pytest.raises(RuntimeError, match="DEBUG must be false in production"):
        validate_startup_settings()

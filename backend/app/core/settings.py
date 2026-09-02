"""Small environment-backed settings helpers for authentication and email."""

import os


def get_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable with a predictable default."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_int(name: str, default: int, *, minimum: int = 1) -> int:
    """Read a positive integer environment variable."""
    value = os.getenv(name)
    if value is None:
        return default
    parsed = int(value)
    if parsed < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return parsed


def is_production() -> bool:
    """Return whether the configured environment is production."""
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


def allowed_origins() -> list[str]:
    """Return the explicit browser origins permitted to call the API."""
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    if origins:
        return origins
    if is_production():
        raise RuntimeError("CORS_ALLOWED_ORIGINS must be set in production")
    return ["http://localhost:3010", "http://127.0.0.1:3010"]


def frontend_base_url() -> str:
    """Return the trusted frontend origin used in security email links."""
    value = os.getenv("FRONTEND_BASE_URL", "").strip().rstrip("/")
    if value:
        return value
    if is_production():
        raise RuntimeError("FRONTEND_BASE_URL must be set in production")
    return "http://localhost:3010"


def validate_startup_settings() -> None:
    """Fail closed for required production authentication configuration."""
    if not is_production():
        return
    if not os.getenv("JWT_SECRET_KEY", "").strip():
        raise RuntimeError("JWT_SECRET_KEY must be set in production")
    allowed_origins()
    frontend_base_url()
    if not get_bool("AUTH_COOKIE_SECURE", True):
        raise RuntimeError("AUTH_COOKIE_SECURE must be true in production")
    if not get_bool("EMAIL_ENABLED", False):
        raise RuntimeError("EMAIL_ENABLED must be true in production")

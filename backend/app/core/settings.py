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


def environment_name() -> str:
    """Return the deployment environment name.

    ``APP_ENV`` is canonical; ``ENVIRONMENT`` is accepted as an alias so the
    same value can be shared with tooling that expects that name.
    """
    return (
        os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "development"
    ).strip().lower()


def is_production() -> bool:
    """Return whether the configured environment is production."""
    return environment_name() == "production"


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


def _require_env(*names: str) -> None:
    """Raise if any named environment variable is missing or blank."""
    missing = [name for name in names if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError(
            "Missing required production configuration: " + ", ".join(missing)
        )


def validate_startup_settings() -> None:
    """Fail closed for required production configuration.

    Runs on API startup. A misconfigured production process must not accept
    traffic with a fallback secret, an unverifiable webhook, or a missing
    database/LLM credential.
    """
    if not is_production():
        return
    _require_env("JWT_SECRET_KEY")
    allowed_origins()
    frontend_base_url()
    if not get_bool("AUTH_COOKIE_SECURE", True):
        raise RuntimeError("AUTH_COOKIE_SECURE must be true in production")
    if not get_bool("EMAIL_ENABLED", False):
        raise RuntimeError("EMAIL_ENABLED must be true in production")
    # Deployment-neutral database connection (no PG_LOCAL_* fallback in prod).
    _require_env("DATABASE_URL")
    # The WhatsApp webhook cannot verify signatures without this.
    _require_env("YCLOUD_WEBHOOK_SIGNING_SECRET")
    # LLM provider (extraction pipeline + instructor agent).
    _require_env("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT")

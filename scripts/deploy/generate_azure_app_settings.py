"""Generate a Git-ignored Azure App Service settings JSON from ``.env``.

Usage:
    conda run -n agenda python scripts/deploy/generate_azure_app_settings.py \
      --frontend-url https://app.example.com
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "scripts/deploy/azure_app_settings.json"
REQUIRED_ENV_NAMES = (
    "AZURE_PG_USER",
    "AZURE_PG_PASSWORD",
    "AZURE_PG_HOST",
    "AZURE_PG_DATABASE",
    "JWT_SECRET_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_MODEL",
    "YCLOUD_API_KEY",
    "YCLOUD_WEBHOOK_SIGNING_SECRET",
    "EMAIL_SMTP_HOST",
    "EMAIL_SMTP_PORT",
    "EMAIL_SMTP_SECURITY",
    "EMAIL_SMTP_USERNAME",
    "EMAIL_SMTP_PASSWORD",
    "EMAIL_FROM_ADDRESS",
)


def _required(config: dict[str, str | None], name: str) -> str:
    """Return a required local configuration value without printing it."""
    value = (config.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required .env value: {name}")
    return value


def _validate_required(config: dict[str, str | None]) -> None:
    """Report every production setting that must be supplied before generation."""
    missing = [name for name in REQUIRED_ENV_NAMES if not (config.get(name) or "").strip()]
    if missing:
        raise RuntimeError("Missing required .env values: " + ", ".join(missing))


def _setting(name: str, value: str) -> dict[str, str | bool]:
    """Build one Azure App Service settings entry."""
    return {"name": name, "value": value, "slotSetting": False}


def _database_url(config: dict[str, str | None]) -> str:
    """Build the production TLS URL, encoding reserved credential characters."""
    user = quote(_required(config, "AZURE_PG_USER"), safe="")
    password = quote(_required(config, "AZURE_PG_PASSWORD"), safe="")
    host = _required(config, "AZURE_PG_HOST")
    port = (config.get("AZURE_PG_PORT") or "5432").strip()
    database = _required(config, "AZURE_PG_DATABASE")
    sslmode = (config.get("AZURE_PG_SSLMODE") or "require").strip()
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}?sslmode={sslmode}"


def build_settings(
    config: dict[str, str | None],
    frontend_url: str,
) -> list[dict[str, str | bool]]:
    """Build the complete production App Service settings payload."""
    frontend_url = frontend_url.rstrip("/")
    if not frontend_url.startswith("https://"):
        raise ValueError("--frontend-url must use HTTPS")
    _validate_required(config)

    values = {
        "WEBSITES_PORT": "8080",
        "PORT": "8080",
        "INTERNAL_API_PORT": "8005",
        "INTERNAL_API_URL": "http://127.0.0.1:8005",
        "ROLE": "platform",
        "RUN_WORKERS": "true",
        "APP_ENV": "production",
        "NODE_ENV": "production",
        "DEBUG": "false",
        "TZ": "America/Sao_Paulo",
        "DATABASE_URL": _database_url(config),
        "DB_POOL_SIZE": "2",
        "DB_MAX_OVERFLOW": "1",
        "WEBHOOK_TASK_QUEUE": "local",
        "WEBHOOK_INLINE_PROCESSING": "false",
        "FRONTEND_BASE_URL": frontend_url,
        "CORS_ALLOWED_ORIGINS": frontend_url,
        "JWT_SECRET_KEY": _required(config, "JWT_SECRET_KEY"),
        "AUTH_COOKIE_SECURE": "true",
        "AUTH_COOKIE_SAMESITE": (config.get("AUTH_COOKIE_SAMESITE") or "lax").strip(),
        "AUTH_COOKIE_NAME": (config.get("AUTH_COOKIE_NAME") or "agenda_access_token").strip(),
        "JWT_ISSUER": (config.get("JWT_ISSUER") or "tennis-os").strip(),
        "JWT_AUDIENCE": (config.get("JWT_AUDIENCE") or "tennis-os-web").strip(),
        "AZURE_OPENAI_API_KEY": _required(config, "AZURE_OPENAI_API_KEY"),
        "AZURE_OPENAI_ENDPOINT": _required(config, "AZURE_OPENAI_ENDPOINT"),
        "AZURE_OPENAI_API_VERSION": (
            config.get("AZURE_OPENAI_API_VERSION") or "2024-12-01-preview"
        ).strip(),
        "AZURE_OPENAI_MODEL": _required(config, "AZURE_OPENAI_MODEL"),
        "WHATSAPP_PROVIDER": (config.get("WHATSAPP_PROVIDER") or "ycloud").strip(),
        "YCLOUD_API_KEY": _required(config, "YCLOUD_API_KEY"),
        "YCLOUD_WEBHOOK_SIGNING_SECRET": _required(config, "YCLOUD_WEBHOOK_SIGNING_SECRET"),
        "EMAIL_ENABLED": "true",
        "EMAIL_SMTP_HOST": _required(config, "EMAIL_SMTP_HOST"),
        "EMAIL_SMTP_PORT": _required(config, "EMAIL_SMTP_PORT"),
        "EMAIL_SMTP_SECURITY": _required(config, "EMAIL_SMTP_SECURITY"),
        "EMAIL_SMTP_USERNAME": _required(config, "EMAIL_SMTP_USERNAME"),
        "EMAIL_SMTP_PASSWORD": _required(config, "EMAIL_SMTP_PASSWORD"),
        "EMAIL_FROM_ADDRESS": _required(config, "EMAIL_FROM_ADDRESS"),
        "EMAIL_FROM_NAME": (config.get("EMAIL_FROM_NAME") or "Tennis OS").strip(),
        "EMAIL_REPLY_TO": (config.get("EMAIL_REPLY_TO") or "").strip(),
        "LOG_LEVEL": "INFO",
    }
    for name in (
        "YCLOUD_DAILY_AGENDA_TEMPLATE_NAME",
        "YCLOUD_DAILY_AGENDA_TEMPLATE_LANGUAGE",
        "YCLOUD_DAILY_AGENDA_TTL_SECONDS",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_HOST",
    ):
        value = (config.get(name) or "").strip()
        if value:
            values[name] = value
    return [_setting(name, value) for name, value in values.items()]


def main() -> None:
    """Generate a private settings JSON file for Azure CLI or portal import."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    config = dotenv_values(PROJECT_ROOT / ".env")
    settings = build_settings(
        config,
        args.frontend_url,
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    output.chmod(0o600)
    print(f"Wrote {len(settings)} settings to {output}")


if __name__ == "__main__":
    main()

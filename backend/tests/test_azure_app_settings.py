import pytest

from scripts.deploy.generate_azure_app_settings import build_settings


def test_build_settings_generates_azure_entries_with_encoded_database_password() -> None:
    config = {
        "AZURE_PG_USER": "agenda",
        "AZURE_PG_PASSWORD": "password=with:reserved",
        "AZURE_PG_HOST": "server.postgres.database.azure.com",
        "AZURE_PG_DATABASE": "agenda_db",
        "JWT_SECRET_KEY": "jwt-secret",
        "AZURE_OPENAI_API_KEY": "openai-key",
        "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
        "AZURE_OPENAI_MODEL": "agenda-model",
        "YCLOUD_API_KEY": "ycloud-key",
        "YCLOUD_WEBHOOK_SIGNING_SECRET": "webhook-secret",
        "EMAIL_SMTP_HOST": "smtp.example.com",
        "EMAIL_SMTP_PORT": "465",
        "EMAIL_SMTP_SECURITY": "ssl",
        "EMAIL_SMTP_USERNAME": "mail-user",
        "EMAIL_SMTP_PASSWORD": "mail-secret",
        "EMAIL_FROM_ADDRESS": "noreply@example.com",
    }

    settings = build_settings(
        config,
        "https://agenda.example.com/",
    )
    values = {entry["name"]: entry["value"] for entry in settings}

    assert values["DATABASE_URL"] == (
        "postgresql+psycopg2://agenda:password%3Dwith%3Areserved@"
        "server.postgres.database.azure.com:5432/agenda_db?sslmode=require"
    )
    assert values["FRONTEND_BASE_URL"] == "https://agenda.example.com"
    assert "DOCKER_REGISTRY_SERVER_PASSWORD" not in values
    assert all(entry["slotSetting"] is False for entry in settings)


def test_build_settings_reports_all_missing_required_values() -> None:
    with pytest.raises(RuntimeError, match="AZURE_PG_USER, AZURE_PG_PASSWORD"):
        build_settings({}, "https://agenda.example.com")

"""Copy new Azure rows to local without updating or deleting local data."""

from db_sync import run_cli


if __name__ == "__main__":
    run_cli("azure", "local")

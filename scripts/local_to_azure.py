"""Copy new local rows to Azure without updating or deleting Azure data."""

from db_sync import run_cli


if __name__ == "__main__":
    run_cli("local", "azure")

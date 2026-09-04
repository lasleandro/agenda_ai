"""Print aggregate, non-PII account-request operational metrics."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.services.account_requests import get_account_request_operational_metrics  # noqa: E402


def main() -> int:
    """Read and print aggregate onboarding queue health."""
    db = SessionLocal()
    try:
        for name, value in get_account_request_operational_metrics(db).items():
            print(f"{name}: {value}")
        return 0
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())


"""Apply the rejected account-request PII retention policy.

Dry-run is the default. Use ``--apply`` only from an approved maintenance job:

    conda run -n agenda python scripts/purge_account_requests.py
    conda run -n agenda python scripts/purge_account_requests.py --apply
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.services.account_requests import purge_rejected_account_requests  # noqa: E402


def main(*, apply: bool) -> int:
    """Report or apply the configured rejected-request retention cleanup."""
    db = SessionLocal()
    try:
        removed = purge_rejected_account_requests(db)
        if apply:
            db.commit()
            print(f"rejected_account_requests_deleted: {removed}")
        else:
            db.rollback()
            print(f"rejected_account_requests_eligible: {removed}")
            print("dry_run: true")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit deletion; without this flag the transaction is rolled back.",
    )
    args = parser.parse_args()
    raise SystemExit(main(apply=args.apply))


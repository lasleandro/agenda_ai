"""Read-only contact-phone readiness audit.

Run locally with:
    conda run -n agenda python scripts/audit_contact_phones.py

The output contains aggregate counts only. It never writes data and is safe to
use as a production preflight inside a separately approved read-only session.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.services.phone_numbers import PhoneNumberValidationError, normalize_mobile_phone  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        rows = db.execute(
            text("SELECT id, professional_id, phone FROM contacts")
        ).mappings()
        invalid_count = 0
        missing_count = 0
        total_count = 0
        identities: set[tuple[object, str]] = set()
        duplicate_count = 0

        for row in rows:
            total_count += 1
            phone = row["phone"]
            if phone is None or not str(phone).strip():
                missing_count += 1
                continue
            try:
                normalized = normalize_mobile_phone(str(phone))
            except PhoneNumberValidationError:
                invalid_count += 1
                continue
            identity = (row["professional_id"], normalized)
            if identity in identities:
                duplicate_count += 1
            identities.add(identity)

        reports = {
            "contacts_total": total_count,
            "phones_missing": missing_count,
            "phones_invalid": invalid_count,
            "normalized_duplicate_rows": duplicate_count,
        }
        for name, count in reports.items():
            print(f"{name}: {count}")
        return 1 if any((missing_count, invalid_count, duplicate_count)) else 0
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

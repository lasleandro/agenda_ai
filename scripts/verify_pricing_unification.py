"""Integrity check for the unified pricing rate matrix.

Run against the local database only:
    conda run -n agenda python scripts/verify_pricing_unification.py

Historically this script compared the legacy pricing stores
(``financial_rates``, ``professional_financial_settings.generic_place_rates``)
against the unified ``place_financial_rates`` table during the Phase 1/2
migration window (see
docs/ROADMAPS/pricing_model_unification_tracking_v0.1_2026-08-19.md). Phase 3
dropped both legacy stores, so this script now only checks invariants of the
unified table itself. Read-only; never mutates the database.

Checks:
1. Integrity — at most one default row (``place_id IS NULL``) per
   (professional_id, time_category, participant_count).
2. Referential sanity — every per-place row's ``place_id`` still points at an
   existing place (catches rows orphaned by a place deletion that skipped
   its cascade).

Exits 0 when all checks pass, 1 otherwise.
"""

import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import func

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.database import SessionLocal
from app.models import Place, PlaceFinancialRate


def main() -> int:
    """Run the integrity checks and report results."""
    db = SessionLocal()
    try:
        violations: dict[str, list[str]] = defaultdict(list)

        total_rows = db.query(func.count(PlaceFinancialRate.id)).scalar()
        default_rows = (
            db.query(func.count(PlaceFinancialRate.id))
            .filter(PlaceFinancialRate.place_id.is_(None))
            .scalar()
        )
        place_rows = total_rows - default_rows

        # 1. Integrity — at most one default row per cell.
        duplicate_defaults = (
            db.query(
                PlaceFinancialRate.professional_id,
                PlaceFinancialRate.time_category,
                PlaceFinancialRate.participant_count,
                func.count(PlaceFinancialRate.id),
            )
            .filter(PlaceFinancialRate.place_id.is_(None))
            .group_by(
                PlaceFinancialRate.professional_id,
                PlaceFinancialRate.time_category,
                PlaceFinancialRate.participant_count,
            )
            .having(func.count(PlaceFinancialRate.id) > 1)
            .count()
        )
        if duplicate_defaults:
            violations["integrity_duplicate_defaults"].append(
                f"{duplicate_defaults} duplicated default cells"
            )

        # 2. Referential sanity — per-place rows point at existing places.
        orphaned = (
            db.query(func.count(PlaceFinancialRate.id))
            .filter(
                PlaceFinancialRate.place_id.isnot(None),
                ~PlaceFinancialRate.place_id.in_(db.query(Place.id)),
            )
            .scalar()
        )
        if orphaned:
            violations["orphaned_place_rows"].append(
                f"{orphaned} rows reference a place that no longer exists"
            )

        print("Pricing rate matrix integrity check")
        print("------------------------------------")
        print(f"Unified default (place_id IS NULL) rows:  {default_rows}")
        print(f"Unified per-place rows:                   {place_rows}")
        print()

        total_violations = sum(len(items) for items in violations.values())
        if total_violations == 0:
            print("All checks passed: no duplicate defaults, no orphaned rows.")
            return 0
        for check, items in sorted(violations.items()):
            print(f"FAIL [{check}]: {len(items)} violation(s)")
            for item in items[:10]:
                print(f"  - {item}")
            if len(items) > 10:
                print(f"  ... and {len(items) - 10} more")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())

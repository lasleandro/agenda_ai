"""Read-only recurring-slot semantic audit for the place-stay roadmap.

Run against the local database only:
    conda run -n agenda python scripts/audit_recurring_slot_semantics.py --all-tenants
    conda run -n agenda python scripts/audit_recurring_slot_semantics.py --professional-id <UUID>

The output is aggregated counts only; it never prints customer, place, or
professional data and does not mutate the database.
"""

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, or_

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.database import SessionLocal
from app.models import (
    MakeupClassCredit,
    RecurringSlot,
    RecurringSlotParticipant,
    RevenueOccurrence,
)


def parse_args() -> argparse.Namespace:
    """Parse an explicitly tenant-scoped or aggregate audit request."""
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--professional-id", type=UUID)
    scope.add_argument("--all-tenants", action="store_true")
    return parser.parse_args()


def audit(professional_id: UUID | None) -> dict[str, object]:
    """Return aggregate recurring-slot counts without modifying the database."""
    db = SessionLocal()
    try:
        participant_count = (
            db.query(func.count(RecurringSlotParticipant.id))
            .filter(RecurringSlotParticipant.recurring_slot_id == RecurringSlot.id)
            .correlate(RecurringSlot)
            .scalar_subquery()
        )
        query = db.query(RecurringSlot)
        if professional_id is not None:
            query = query.filter(RecurringSlot.professional_id == professional_id)

        total = query.count()
        by_kind = {
            kind: count
            for kind, count in (
                query.with_entities(RecurringSlot.slot_kind, func.count(RecurringSlot.id))
                .group_by(RecurringSlot.slot_kind)
                .all()
            )
        }
        participant_presence = {
            "with_participants": query.filter(participant_count > 0).count(),
            "without_participants": query.filter(participant_count == 0).count(),
        }
        invalid_availability = query.filter(
            RecurringSlot.slot_kind == "availability",
            or_(
                participant_count > 0,
                RecurringSlot.group_name.is_not(None),
                RecurringSlot.level.is_not(None),
                RecurringSlot.class_type.is_(None),
                RecurringSlot.class_type != "individual",
                RecurringSlot.max_participants.is_(None),
                RecurringSlot.max_participants != 1,
            ),
        ).count()
        invalid_classes = query.filter(
            RecurringSlot.slot_kind == "class",
            or_(
                RecurringSlot.class_type.is_(None),
                RecurringSlot.class_type.not_in(("individual", "group")),
                RecurringSlot.max_participants.is_(None),
                RecurringSlot.max_participants < 1,
                RecurringSlot.max_participants > 4,
                (RecurringSlot.class_type == "individual")
                & (RecurringSlot.max_participants != 1),
            ),
        ).count()
        invalid_makeup_origins = (
            db.query(MakeupClassCredit)
            .outerjoin(
                RecurringSlot,
                MakeupClassCredit.origin_recurring_slot_id == RecurringSlot.id,
            )
            .filter(
                MakeupClassCredit.professional_id == professional_id
                if professional_id is not None
                else True,
                or_(
                    RecurringSlot.id.is_(None),
                    RecurringSlot.slot_kind != "class",
                ),
            )
            .count()
        )
        invalid_revenue_sources = (
            db.query(RevenueOccurrence)
            .outerjoin(
                RecurringSlot,
                RevenueOccurrence.source_id == RecurringSlot.id,
            )
            .filter(
                RevenueOccurrence.professional_id == professional_id
                if professional_id is not None
                else True,
                RevenueOccurrence.source_type == "recurring_slot",
                or_(
                    RecurringSlot.id.is_(None),
                    RecurringSlot.slot_kind != "class",
                ),
            )
            .count()
        )
        return {
            "scope": "all_tenants" if professional_id is None else "one_professional",
            "recurring_slots": {
                "total": total,
                "by_slot_kind": {
                    "availability": by_kind.get("availability", 0),
                    "class": by_kind.get("class", 0),
                },
                "participant_presence": participant_presence,
                "invalid_availability_rows": invalid_availability,
                "invalid_class_rows": invalid_classes,
            },
            "dependent_references": {
                "invalid_makeup_class_origins": invalid_makeup_origins,
                "invalid_recurring_slot_revenue_sources": invalid_revenue_sources,
            },
        }
    finally:
        db.close()


def main() -> None:
    args = parse_args()
    professional_id = args.professional_id if not args.all_tenants else None
    print(json.dumps(audit(professional_id), indent=2))


if __name__ == "__main__":
    main()

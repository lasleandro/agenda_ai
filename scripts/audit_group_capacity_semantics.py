"""Read-only local audit for group capacity and occurrence semantics.

Run against the local database only with
``conda run -n agenda python scripts/audit_group_capacity_semantics.py``.
It prints aggregate counts and never writes or migrates data.
"""

from __future__ import annotations

from datetime import date, timedelta
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.database import SessionLocal
from app.models import Professional, RecurringSlot
from app.services.scheduling import list_schedule_occurrences


def _count(db, statement: str) -> int:
    return int(db.execute(text(statement)).scalar_one())


def main() -> int:
    db = SessionLocal()
    try:
        reports = {
            "appointments_missing_capacity": _count(
                db, "SELECT count(*) FROM appointments WHERE max_participants IS NULL"
            ),
            "appointments_invalid_capacity": _count(
                db,
                "SELECT count(*) FROM appointments "
                "WHERE max_participants NOT BETWEEN 1 AND 4 "
                "OR (class_type = 'individual' AND max_participants <> 1)",
            ),
            "recurring_slots_invalid_capacity": _count(
                db,
                "SELECT count(*) FROM recurring_slots "
                "WHERE slot_kind = 'class' AND (max_participants NOT BETWEEN 1 AND 4 "
                "OR (class_type = 'individual' AND max_participants <> 1))",
            ),
            "orphan_or_cross_tenant_standing_participants": _count(
                db,
                "SELECT count(*) FROM recurring_slot_participants p "
                "LEFT JOIN recurring_slots s ON s.id = p.recurring_slot_id "
                "LEFT JOIN contacts c ON c.id = p.contact_id "
                "WHERE s.id IS NULL OR c.id IS NULL OR s.professional_id <> c.professional_id",
            ),
            "orphan_or_cross_tenant_dated_guests": _count(
                db,
                "SELECT count(*) FROM recurring_slot_occurrence_participants p "
                "LEFT JOIN recurring_slots s ON s.id = p.recurring_slot_id "
                "LEFT JOIN contacts c ON c.id = p.contact_id "
                "WHERE s.id IS NULL OR c.id IS NULL OR p.professional_id <> s.professional_id "
                "OR p.professional_id <> c.professional_id",
            ),
            "duplicate_dated_guests": _count(
                db,
                "SELECT count(*) FROM ("
                "SELECT recurring_slot_id, contact_id, occurrence_date "
                "FROM recurring_slot_occurrence_participants "
                "GROUP BY recurring_slot_id, contact_id, occurrence_date HAVING count(*) > 1"
                ") duplicates",
            ),
        }
        start_date = date.today()
        end_date = start_date + timedelta(days=28)
        # A class is expected to project only when it has a valid occurrence in
        # this window; bounded recurring rows outside the window are excluded.
        expected_slots = [
            slot.id
            for slot in db.query(RecurringSlot).filter(
                RecurringSlot.slot_kind == "class"
            )
            if (
                (slot.recurrence_type == "weekly"
                 and (slot.valid_until is None or slot.valid_until >= start_date)
                 and (slot.valid_from is None or slot.valid_from <= end_date))
                or (slot.recurrence_type != "weekly"
                    and slot.scheduled_date is not None
                    and start_date <= slot.scheduled_date <= end_date)
            )
        ]
        projected_slot_ids = {
            occurrence.source_id
            for (professional_id,) in db.query(Professional.id).all()
            for occurrence in list_schedule_occurrences(
                db, professional_id, start_date, end_date
            )
            if occurrence.source_type == "recurring_slot"
        }
        reports["class_rows_missing_projection_next_28_days"] = len(
            set(expected_slots) - projected_slot_ids
        )

        for name, count in reports.items():
            print(f"{name}: {count}")
        return 1 if any(reports.values()) else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

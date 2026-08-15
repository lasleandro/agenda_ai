"""
Seed script — populates the database with realistic demo data for Phase 4
(web calendar).

Creates one professional (Joao), several contacts, and a week of appointments
with varied statuses so the calendar has content to display.

Usage:
    cd backend && python scripts/seed.py
"""

import uuid
from datetime import date, datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Bootstrap path so we can run from the backend/ directory.
# ---------------------------------------------------------------------------
import sys
import os

_backend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.database import SessionLocal, engine
from app.models import (  # noqa: E402
    Appointment,
    Contact,
    Place,
    Professional,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TZ = timezone(timedelta(hours=-3))  # America/Sao_Paulo

PROFESSIONAL_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")

CONTACTS = [
    ("Mariana", "mariana"),
    ("Carlos", "carlos"),
    ("Renata", "renata"),
    ("Pedro", "pedro"),
    ("Fernanda", "fernanda"),
    ("Bruno", "bruno"),
    ("Thiago", "thiago"),
    ("Larissa", "larissa"),
    ("Ana", "ana"),
    ("Julia", "julia"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dt(day_offset: int, hour: int, minute: int = 0) -> datetime:
    """Return a datetime relative to today, at the given hour in SP timezone."""
    today = date.today()
    target = today + timedelta(days=day_offset)
    return datetime(target.year, target.month, target.day, hour, minute, tzinfo=TZ)


def _end_dt(start: datetime, duration_min: int = 60) -> datetime:
    return start + timedelta(minutes=duration_min)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def seed():
    db = SessionLocal()

    try:
        # ── Professional ──────────────────────────────────────────────────
        pro = db.get(Professional, PROFESSIONAL_ID)
        if pro is None:
            agent_number = os.getenv("AGENT_WHATSAPP_NUMBER")
            pro = Professional(
                id=PROFESSIONAL_ID,
                name="Joao",
                timezone="America/Sao_Paulo",
                default_service="tennis_lesson",
                default_duration_minutes=60,
                assistant_phone="+5511949408816",
                agent_phone=f"+{agent_number}" if agent_number else None,
            )
            db.add(pro)
            db.flush()
            print(f"  Created professional: {pro.name}")
        else:
            print(f"  Professional already exists: {pro.name}")

        # ── Contacts ──────────────────────────────────────────────────────
        contact_ids: dict[str, uuid.UUID] = {}
        for display_name, normalized in CONTACTS:
            existing = (
                db.query(Contact)
                .filter_by(professional_id=PROFESSIONAL_ID, normalized_name=normalized)
                .first()
            )
            if existing:
                contact_ids[normalized] = existing.id
            else:
                c = Contact(
                    professional_id=PROFESSIONAL_ID,
                    display_name=display_name,
                    normalized_name=normalized,
                    phone=f"+5511{uuid.uuid4().hex[:8]}",
                )
                db.add(c)
                db.flush()
                contact_ids[normalized] = c.id
                print(f"  Created contact: {c.display_name}")

        # ── Appointments (week of today) ──────────────────────────────────
        existing_count = (
            db.query(Appointment)
            .filter_by(professional_id=PROFESSIONAL_ID)
            .count()
        )
        if existing_count > 0:
            print(f"  {existing_count} appointments already exist — skipping seed.")
            db.commit()
            return

        places = (
            db.query(Place)
            .filter_by(professional_id=PROFESSIONAL_ID)
            .order_by(Place.name)
            .all()
        )
        if not places:
            print(
                "  No places found for this professional — appointments will be "
                "seeded without a place_id, which the Financeiro dashboard "
                "excludes entirely from capacity and revenue. Create at least "
                "one place first."
            )

        appointments = [
            # Monday
            ("mariana", 0, 8, "confirmed"),
            ("carlos", 0, 10, "tentative"),
            ("thiago", 0, 17, "confirmed"),
            # Tuesday
            ("bruno", 1, 9, "confirmed"),
            ("fernanda", 1, 17, "confirmed"),
            # Wednesday
            ("renata", 2, 14, "confirmed"),
            ("ana", 2, 17, "tentative"),
            # Thursday
            ("pedro", 3, 8, "cancelled"),
            ("larissa", 3, 17, "confirmed"),
            # Friday
            ("carlos", 4, 10, "confirmed"),
            ("mariana", 4, 17, "confirmed"),
            # Saturday
            ("thiago", 5, 9, "confirmed"),
        ]

        for index, (contact_key, day_offset, hour, status) in enumerate(appointments):
            start = _make_dt(day_offset, hour)
            end = _end_dt(start)
            appt = Appointment(
                professional_id=PROFESSIONAL_ID,
                contact_id=contact_ids[contact_key],
                place_id=places[index % len(places)].id if places else None,
                service="tennis_lesson",
                start_at=start,
                end_at=end,
                timezone="America/Sao_Paulo",
                status=status,
                source="manually_created",
            )
            db.add(appt)

        db.commit()
        print(f"  Seeded {len(appointments)} appointments.")

    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding agenda_db ...")
    seed()
    print("Done.")

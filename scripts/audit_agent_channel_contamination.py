"""Detect (and optionally clean) passive-observer rows created from the
platform's own agent-channel traffic.

Before the lane-isolation guard (Shared Platform AI Agent Number Roadmap v0.1,
Phase B) nothing stopped an instructor<->agent message from being ingested as a
customer conversation. This finds the debris: Contacts whose phone is a
platform-owned number, and everything hanging off them.

Read-only by default. Run locally first:

    conda run -n agenda python scripts/audit_agent_channel_contamination.py

Against production data, run only inside a separately approved read-only
session, or against a restored copy. Never run ``--apply`` against the Azure
remote database (project rule 2).

    conda run -n agenda python scripts/audit_agent_channel_contamination.py --apply

``--apply`` refuses to touch anything that was acted on (a candidate that is
not still ``detected``, or a contaminated Contact referenced by a real domain
record). Those need a manual review pass.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.integrations.whatsapp.platform_number import platform_agent_number  # noqa: E402

# Domain tables that reference contacts.id directly. A contaminated Contact
# touched by any of these was acted on and is out of scope for automatic
# cleanup.
_CONTACT_DOMAIN_REFS = (
    ("appointments", "contact_id"),
    ("appointment_participants", "contact_id"),
    ("appointment_candidates", "contact_id"),
    ("recurring_slot_participants", "contact_id"),
    ("recurring_slot_occurrence_participants", "contact_id"),
    ("waitlist_entries", "contact_id"),
    ("makeup_class_credits", "contact_id"),
)


def _platform_owned_numbers(db) -> set[str]:
    numbers: set[str] = set()
    configured = platform_agent_number()
    if configured:
        numbers.add(configured)
    # professionals.agent_phone is dropped by the migration that ships with
    # this change; the audit still needs to run against a pre-migration
    # production copy, where the column and its values are the main target.
    has_agent_phone = db.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'professionals' AND column_name = 'agent_phone'"
        )
    ).first()
    if has_agent_phone:
        rows = db.execute(
            text(
                "SELECT DISTINCT agent_phone FROM professionals "
                "WHERE agent_phone IS NOT NULL"
            )
        ).scalars()
        numbers.update(str(value) for value in rows if str(value).strip())
    return numbers


def _contaminated_contacts(db, numbers: set[str]) -> list[dict]:
    if not numbers:
        return []
    rows = db.execute(
        text(
            "SELECT id, professional_id, phone, display_name "
            "FROM contacts WHERE phone = ANY(:numbers)"
        ),
        {"numbers": list(numbers)},
    ).mappings()
    return [dict(row) for row in rows]


def _summarize(db, contact_ids: list) -> dict:
    if not contact_ids:
        return {"conversations": 0, "messages": 0, "candidates": 0, "acted_candidates": 0}
    conv_ids = list(
        db.execute(
            text("SELECT id FROM conversations WHERE contact_id = ANY(:ids)"),
            {"ids": contact_ids},
        ).scalars()
    )
    messages = 0
    candidates = 0
    acted = 0
    if conv_ids:
        messages = db.execute(
            text("SELECT count(*) FROM messages WHERE conversation_id = ANY(:ids)"),
            {"ids": conv_ids},
        ).scalar_one()
        candidates = db.execute(
            text(
                "SELECT count(*) FROM appointment_candidates "
                "WHERE conversation_id = ANY(:ids)"
            ),
            {"ids": conv_ids},
        ).scalar_one()
        acted = db.execute(
            text(
                "SELECT count(*) FROM appointment_candidates "
                "WHERE conversation_id = ANY(:ids) "
                "AND (status <> 'detected' OR resulting_appointment_id IS NOT NULL)"
            ),
            {"ids": conv_ids},
        ).scalar_one()
    return {
        "conversations": len(conv_ids),
        "messages": messages,
        "candidates": candidates,
        "acted_candidates": acted,
        "_conversation_ids": conv_ids,
    }


def _blocking_domain_refs(db, contact_ids: list) -> set:
    """Contacts referenced by a real domain record (anything but the
    conversation-derived candidate). Their presence blocks automatic cleanup.
    """
    blocking: set = set()
    for table, column in _CONTACT_DOMAIN_REFS:
        if table == "appointment_candidates":
            continue
        rows = db.execute(
            text(f"SELECT DISTINCT {column} FROM {table} WHERE {column} = ANY(:ids)"),
            {"ids": contact_ids},
        ).scalars()
        blocking.update(rows)
    return blocking


def _report(db) -> tuple[list[dict], dict]:
    numbers = _platform_owned_numbers(db)
    contacts = _contaminated_contacts(db, numbers)
    contact_ids = [c["id"] for c in contacts]
    summary = _summarize(db, contact_ids)

    print(f"platform_owned_numbers: {len(numbers)}")
    print(f"contaminated_contacts: {len(contacts)}")
    print(f"contaminated_conversations: {summary['conversations']}")
    print(f"contaminated_messages: {summary['messages']}")
    print(f"contaminated_candidates: {summary['candidates']}")
    print(f"candidates_already_acted_on: {summary['acted_candidates']}")
    for contact in contacts:
        print(
            f"  contact {contact['id']} tenant={contact['professional_id']} "
            f"phone={contact['phone']} name={contact['display_name']!r}"
        )
    return contacts, summary


def _apply_cleanup(db, contacts: list[dict], summary: dict) -> int:
    contact_ids = [c["id"] for c in contacts]
    if not contact_ids:
        print("nothing to clean")
        return 0

    if summary["acted_candidates"]:
        print(
            "REFUSING: some contaminated candidates were acted on "
            f"({summary['acted_candidates']}). Resolve them manually first."
        )
        return 2

    blocking = _blocking_domain_refs(db, contact_ids)
    if blocking:
        print(
            f"REFUSING: {len(blocking)} contaminated contact(s) are referenced by "
            "real domain records. Review manually."
        )
        return 2

    conv_ids = summary.get("_conversation_ids", [])
    deleted = {}
    if conv_ids:
        deleted["appointment_candidates"] = db.execute(
            text(
                "DELETE FROM appointment_candidates WHERE conversation_id = ANY(:ids)"
            ),
            {"ids": conv_ids},
        ).rowcount
        deleted["pending_processing"] = db.execute(
            text("DELETE FROM pending_processing WHERE conversation_id = ANY(:ids)"),
            {"ids": conv_ids},
        ).rowcount
        deleted["messages"] = db.execute(
            text("DELETE FROM messages WHERE conversation_id = ANY(:ids)"),
            {"ids": conv_ids},
        ).rowcount
    deleted["appointment_candidates_by_contact"] = db.execute(
        text("DELETE FROM appointment_candidates WHERE contact_id = ANY(:ids)"),
        {"ids": contact_ids},
    ).rowcount
    deleted["conversations"] = db.execute(
        text("DELETE FROM conversations WHERE contact_id = ANY(:ids)"),
        {"ids": contact_ids},
    ).rowcount
    deleted["contacts"] = db.execute(
        text("DELETE FROM contacts WHERE id = ANY(:ids)"),
        {"ids": contact_ids},
    ).rowcount
    db.commit()
    for name, count in deleted.items():
        print(f"deleted {name}: {count}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete the contaminated rows (local database only)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if not args.apply:
            db.execute(text("SET TRANSACTION READ ONLY"))
        contacts, summary = _report(db)
        if args.apply:
            return _apply_cleanup(db, contacts, summary)
        return 1 if contacts else 0
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

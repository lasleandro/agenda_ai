"""Contact field updates (operational ontology roadmap v0.2, Phase 4) —
moved out of `app.api.contacts` so the API and the instructor agent's
mutation tools share the same validation instead of risking divergence.
Callers own the transaction (commit after calling)."""

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Contact, Place


def apply_contact_updates(
    db: Session,
    professional_id: uuid.UUID,
    contact: Contact,
    updates: dict,
) -> Contact:
    if "home_place_id" in updates and updates["home_place_id"] is not None:
        place = (
            db.query(Place)
            .filter(
                Place.id == updates["home_place_id"],
                Place.professional_id == professional_id,
            )
            .first()
        )
        if place is None:
            raise HTTPException(status_code=404, detail="Place not found")

    for field, value in updates.items():
        setattr(contact, field, value)
    db.flush()
    return contact

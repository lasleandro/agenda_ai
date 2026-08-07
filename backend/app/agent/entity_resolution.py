"""
Deterministic entity resolution for the instructor agent (operational
ontology roadmap v0.2, Phase 2).

Natural-language names are search inputs, never mutation identifiers: every
lookup here returns a list of candidates. Zero or multiple matches must be
surfaced to the caller for clarification — nothing here silently guesses.

Matches against `Contact.normalized_name`/`Place.normalized_name` (Phase 0)
and `EntityAlias.normalized_alias` (Phase 0; no rows exist yet, but the
lookup path is ready for when aliases start getting written), plus a
pg_trgm similarity fallback so single-letter typos still surface a
candidate instead of an empty result.
"""

import uuid
from dataclasses import dataclass
from datetime import time

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import Contact, EntityAlias, Place, RecurringSlot, RecurringSlotParticipant
from app.services.text_normalization import normalize_name

# Below this pg_trgm similarity score, a typo'd name is treated as "not a
# match" rather than surfaced as a low-confidence candidate — keeps
# search_contacts/search_places from returning noise on short queries.
FUZZY_SIMILARITY_THRESHOLD = 0.3


@dataclass(frozen=True)
class ContactMatch:
    contact_id: uuid.UUID
    display_name: str
    phone: str | None
    level: str | None
    home_place_id: uuid.UUID | None


@dataclass(frozen=True)
class PlaceMatch:
    place_id: uuid.UUID
    name: str
    address_line: str | None
    city: str | None


@dataclass(frozen=True)
class GroupMatch:
    recurring_slot_id: uuid.UUID
    group_name: str | None
    label: str | None
    place_id: uuid.UUID
    place_name: str
    day_of_week: int
    start_time: time
    end_time: time
    participant_names: list[str]


def _alias_entity_ids(
    db: Session,
    professional_id: uuid.UUID,
    entity_type: str,
    normalized_query: str,
) -> set[uuid.UUID]:
    rows = (
        db.query(EntityAlias.entity_id)
        .filter(
            EntityAlias.professional_id == professional_id,
            EntityAlias.entity_type == entity_type,
            EntityAlias.normalized_alias.contains(normalized_query),
        )
        .all()
    )
    return {row[0] for row in rows}


def resolve_contacts(
    db: Session,
    professional_id: uuid.UUID,
    query: str,
    *,
    place_id: uuid.UUID | None = None,
) -> list[ContactMatch]:
    normalized_query = normalize_name(query)
    alias_ids = _alias_entity_ids(db, professional_id, "contact", normalized_query)
    similarity = func.similarity(Contact.normalized_name, normalized_query)

    name_matches = [
        Contact.normalized_name.contains(normalized_query),
        similarity >= FUZZY_SIMILARITY_THRESHOLD,
    ]
    if alias_ids:
        name_matches.append(Contact.id.in_(alias_ids))

    filters = [
        Contact.professional_id == professional_id,
        or_(*name_matches),
    ]
    if place_id is not None:
        filters.append(Contact.home_place_id == place_id)

    contacts = (
        db.query(Contact)
        .filter(*filters)
        .order_by(similarity.desc(), Contact.display_name)
        .all()
    )
    return [
        ContactMatch(
            contact_id=contact.id,
            display_name=contact.display_name,
            phone=contact.phone,
            level=contact.level,
            home_place_id=contact.home_place_id,
        )
        for contact in contacts
    ]


def resolve_places(
    db: Session,
    professional_id: uuid.UUID,
    query: str,
) -> list[PlaceMatch]:
    normalized_query = normalize_name(query)
    alias_ids = _alias_entity_ids(db, professional_id, "place", normalized_query)
    similarity = func.similarity(Place.normalized_name, normalized_query)

    name_matches = [
        Place.normalized_name.contains(normalized_query),
        similarity >= FUZZY_SIMILARITY_THRESHOLD,
    ]
    if alias_ids:
        name_matches.append(Place.id.in_(alias_ids))

    places = (
        db.query(Place)
        .filter(
            Place.professional_id == professional_id,
            or_(*name_matches),
        )
        .order_by(similarity.desc(), Place.name)
        .all()
    )
    return [
        PlaceMatch(
            place_id=place.id,
            name=place.name,
            address_line=place.address_line,
            city=place.city,
        )
        for place in places
    ]


def resolve_groups(
    db: Session,
    professional_id: uuid.UUID,
    *,
    member_contact_id: uuid.UUID | None = None,
    place_id: uuid.UUID | None = None,
    weekday: int | None = None,
) -> list[GroupMatch]:
    """A group is one `RecurringSlot` with `slot_kind="class"` and its
    participant roster (Phase 0 "interpretation 1" — no standalone group
    entity)."""
    query = (
        db.query(RecurringSlot, Place.name)
        .join(Place, RecurringSlot.place_id == Place.id)
        .filter(
            RecurringSlot.professional_id == professional_id,
            RecurringSlot.slot_kind == "class",
            RecurringSlot.status == "active",
        )
    )
    if place_id is not None:
        query = query.filter(RecurringSlot.place_id == place_id)
    if weekday is not None:
        query = query.filter(RecurringSlot.day_of_week == weekday)
    if member_contact_id is not None:
        query = query.join(
            RecurringSlotParticipant,
            RecurringSlotParticipant.recurring_slot_id == RecurringSlot.id,
        ).filter(RecurringSlotParticipant.contact_id == member_contact_id)

    slot_rows = query.order_by(RecurringSlot.day_of_week, RecurringSlot.start_time).all()
    if not slot_rows:
        return []

    slot_ids = [slot.id for slot, _ in slot_rows]
    participants_by_slot: dict[uuid.UUID, list[str]] = {}
    for slot_id, display_name in (
        db.query(RecurringSlotParticipant.recurring_slot_id, Contact.display_name)
        .join(Contact, RecurringSlotParticipant.contact_id == Contact.id)
        .filter(RecurringSlotParticipant.recurring_slot_id.in_(slot_ids))
        .order_by(Contact.display_name)
        .all()
    ):
        participants_by_slot.setdefault(slot_id, []).append(display_name)

    return [
        GroupMatch(
            recurring_slot_id=slot.id,
            group_name=slot.group_name,
            label=slot.label,
            place_id=slot.place_id,
            place_name=place_name,
            day_of_week=slot.day_of_week,
            start_time=slot.start_time,
            end_time=slot.end_time,
            participant_names=participants_by_slot.get(slot.id, []),
        )
        for slot, place_name in slot_rows
    ]

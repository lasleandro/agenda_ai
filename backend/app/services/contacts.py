"""Contact field updates (operational ontology roadmap v0.2, Phase 4) —
moved out of `app.api.contacts` so the API and the instructor agent's
mutation tools share the same validation instead of risking divergence.
Callers own the transaction (commit after calling)."""

import uuid

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Contact, Place
from app.services.phone_numbers import normalize_mobile_phone
from app.services.text_normalization import normalize_name


CONTACT_PHONE_UNIQUE_CONSTRAINT = "uq_contacts_professional_phone"


class ContactPhoneAlreadyExistsError(ValueError):
    """Raised when a tenant already owns a canonical customer phone."""


def _is_contact_phone_conflict(error: IntegrityError) -> bool:
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None) == CONTACT_PHONE_UNIQUE_CONSTRAINT


def _apply_profile_name(contact: Contact, name: str | None) -> None:
    if name and contact.display_name == contact.phone:
        contact.display_name = name
        contact.normalized_name = normalize_name(name)


def create_contact(
    db: Session,
    professional_id: uuid.UUID,
    display_name: str,
    phone: str,
) -> Contact:
    """Create a tenant contact or report a phone-identity conflict."""
    canonical_phone = normalize_mobile_phone(phone)
    contact = Contact(
        professional_id=professional_id,
        phone=canonical_phone,
        display_name=display_name,
        normalized_name=normalize_name(display_name),
    )
    try:
        with db.begin_nested():
            db.add(contact)
            db.flush()
    except IntegrityError as error:
        if _is_contact_phone_conflict(error):
            raise ContactPhoneAlreadyExistsError from error
        raise
    return contact


def get_or_create_contact_by_phone(
    db: Session,
    professional_id: uuid.UUID,
    phone: str,
    profile_name: str | None,
) -> tuple[Contact, bool]:
    """Resolve a contact by canonical phone, creating it safely when absent."""
    canonical_phone = normalize_mobile_phone(phone)
    contact = (
        db.query(Contact)
        .filter(
            Contact.professional_id == professional_id,
            Contact.phone == canonical_phone,
        )
        .first()
    )
    if contact is not None:
        _apply_profile_name(contact, profile_name)
        return contact, False

    display_name = profile_name or canonical_phone
    contact = Contact(
        professional_id=professional_id,
        phone=canonical_phone,
        display_name=display_name,
        normalized_name=normalize_name(display_name),
    )
    try:
        with db.begin_nested():
            db.add(contact)
            db.flush()
        return contact, True
    except IntegrityError as error:
        if not _is_contact_phone_conflict(error):
            raise

    contact = (
        db.query(Contact)
        .filter(
            Contact.professional_id == professional_id,
            Contact.phone == canonical_phone,
        )
        .one()
    )
    _apply_profile_name(contact, profile_name)
    return contact, False


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

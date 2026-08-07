"""
Places API ("Meus Locais") — customer ontology roadmap Phase 1.

GET    /api/places       — list the tenant's places.
POST   /api/places       — create a place.
GET    /api/places/{id}  — place detail.
PATCH  /api/places/{id}  — update a place.
DELETE /api/places/{id}  — delete a place.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import require_professional_id
from app.database import SessionLocal
from app.models import Contact, Place, RecurringSlot, RecurringSlotParticipant
from app.schemas.ontology import PlaceCreate, PlaceDetail, PlaceListResponse, PlaceUpdate
from app.services.text_normalization import normalize_name

router = APIRouter(prefix="/api/places", tags=["places"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_place_or_404(db: Session, place_id: uuid.UUID, professional_id: uuid.UUID) -> Place:
    place = (
        db.query(Place)
        .filter(Place.id == place_id, Place.professional_id == professional_id)
        .first()
    )
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return place


@router.get("", response_model=PlaceListResponse)
def list_places(
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    places = (
        db.query(Place)
        .filter(Place.professional_id == professional_id)
        .order_by(Place.name)
        .all()
    )
    return PlaceListResponse(places=[PlaceDetail.model_validate(p) for p in places])


@router.post("", response_model=PlaceDetail, status_code=201)
def create_place(
    body: PlaceCreate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    place = Place(
        professional_id=professional_id,
        normalized_name=normalize_name(body.name),
        **body.model_dump(),
    )
    db.add(place)
    db.commit()
    return PlaceDetail.model_validate(place)


@router.get("/{place_id}", response_model=PlaceDetail)
def get_place(
    place_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    return PlaceDetail.model_validate(_get_place_or_404(db, place_id, professional_id))


@router.patch("/{place_id}", response_model=PlaceDetail)
def update_place(
    place_id: uuid.UUID,
    body: PlaceUpdate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    place = _get_place_or_404(db, place_id, professional_id)
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(place, field, value)
    if "name" in updates:
        place.normalized_name = normalize_name(place.name)
    db.commit()
    return PlaceDetail.model_validate(place)


@router.delete("/{place_id}", status_code=204)
def delete_place(
    place_id: uuid.UUID,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    """Deleting a place cascades to its recurring slots (and their
    participant assignments) — matches the confirmation copy shown in the
    frontend. Contacts that had this as their home_place are unaffected
    beyond losing that reference."""
    place = _get_place_or_404(db, place_id, professional_id)

    slot_ids = [
        row[0] for row in db.query(RecurringSlot.id).filter(RecurringSlot.place_id == place_id).all()
    ]
    if slot_ids:
        db.query(RecurringSlotParticipant).filter(
            RecurringSlotParticipant.recurring_slot_id.in_(slot_ids)
        ).delete(synchronize_session=False)
        db.query(RecurringSlot).filter(RecurringSlot.id.in_(slot_ids)).delete(
            synchronize_session=False
        )

    db.query(Contact).filter(Contact.home_place_id == place_id).update(
        {"home_place_id": None}, synchronize_session=False
    )

    db.delete(place)
    db.commit()

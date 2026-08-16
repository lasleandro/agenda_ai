"""Resolve passive appointment candidates into supported operation inputs."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentCandidate, Contact, Place
from app.services.place_stays import PlaceStayResolution, resolve_place_stay
from app.services.scheduling import TIMEZONE

SupportedOperation = Literal["create", "reschedule"]


@dataclass(frozen=True)
class CandidateResolution:
    """A candidate's executable input or the fields still required."""

    operation: SupportedOperation | None
    arguments: dict[str, str]
    missing_fields: list[str]
    place_resolution: PlaceStayResolution | None = None
    place_source: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.operation is not None and not self.missing_fields


@dataclass(frozen=True)
class CandidateOverrides:
    """Instructor-reviewed values that replace extracted candidate fields."""

    place_id: uuid.UUID | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    service: str | None = None


def _candidate_operation(candidate: AppointmentCandidate) -> str:
    return candidate.operation or candidate.action


def _candidate_home_place_id(
    db: Session, candidate: AppointmentCandidate
) -> uuid.UUID | None:
    if candidate.contact_id is None:
        return None
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == candidate.contact_id,
            Contact.professional_id == candidate.professional_id,
        )
        .first()
    )
    if contact is None or contact.home_place_id is None:
        return None
    return (
        db.query(Place.id)
        .filter(
            Place.id == contact.home_place_id,
            Place.professional_id == candidate.professional_id,
        )
        .scalar()
    )


def _resolve_candidate_place(
    db: Session,
    candidate: AppointmentCandidate,
    *,
    start_at: datetime,
    end_at: datetime,
    override_place_id: uuid.UUID | None,
) -> tuple[PlaceStayResolution, str | None]:
    """Resolve a candidate venue without using home place as availability.

    An instructor override is an explicit exception when it is outside a
    stay. Without an override, a home place can only break a tie between
    already-covering stays.
    """
    if override_place_id is not None:
        return (
            resolve_place_stay(
                db,
                candidate.professional_id,
                start_at=start_at,
                end_at=end_at,
                requested_place_id=override_place_id,
            ),
            "review_override",
        )

    resolution = resolve_place_stay(
        db,
        candidate.professional_id,
        start_at=start_at,
        end_at=end_at,
    )
    if resolution.outcome != "ambiguous":
        return resolution, "unique_stay" if resolution.outcome == "resolved" else None

    home_place_id = _candidate_home_place_id(db, candidate)
    if home_place_id not in resolution.matching_place_ids:
        return resolution, None
    return (
        resolve_place_stay(
            db,
            candidate.professional_id,
            start_at=start_at,
            end_at=end_at,
            requested_place_id=home_place_id,
        ),
        "home_place_tiebreak",
    )


def _iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def resolve_candidate(
    db: Session,
    candidate: AppointmentCandidate,
    overrides: CandidateOverrides | None = None,
) -> CandidateResolution:
    """Resolve supported passive operations without writing or proposing.

    The resolver verifies every related entity belongs to the candidate's
    professional and deliberately reports incomplete input instead of making
    a scheduling guess. Conflict validation remains at proposal/execution
    time because availability can change after this read.
    """
    operation = _candidate_operation(candidate)
    if operation not in {"create", "reschedule"}:
        return CandidateResolution(operation=None, arguments={}, missing_fields=["operation"])

    missing_fields: list[str] = []
    if candidate.contact_id is None:
        missing_fields.append("contact_id")
    elif (
        db.query(Contact.id)
        .filter(
            Contact.id == candidate.contact_id,
            Contact.professional_id == candidate.professional_id,
        )
        .scalar()
        is None
    ):
        missing_fields.append("contact_id")

    start_at = overrides.start_at if overrides and overrides.start_at else candidate.proposed_start_at
    end_at = overrides.end_at if overrides and overrides.end_at else candidate.proposed_end_at
    if start_at is None:
        missing_fields.append("start_at")
    if end_at is None:
        missing_fields.append("end_at")
    if start_at and end_at:
        if end_at <= start_at:
            missing_fields.append("valid_time_range")

    if operation == "create":
        place_resolution: PlaceStayResolution | None = None
        place_source: str | None = None
        if start_at and end_at and end_at > start_at:
            place_resolution, place_source = _resolve_candidate_place(
                db,
                candidate,
                start_at=start_at,
                end_at=end_at,
                override_place_id=overrides.place_id if overrides else None,
            )
        service = overrides.service if overrides and overrides.service is not None else candidate.service
        if not service or not service.strip():
            missing_fields.append("service")
        if place_resolution is None or place_resolution.place_id is None:
            missing_fields.append("place_id")
        if missing_fields:
            return CandidateResolution(
                "create", {}, missing_fields, place_resolution, place_source
            )
        return CandidateResolution(
            "create",
            {
                "contact_id": str(candidate.contact_id),
                "place_id": str(place_resolution.place_id),
                "start_at": _iso_datetime(start_at) or "",
                "end_at": _iso_datetime(end_at) or "",
                "service": service.strip(),
            },
            [],
            place_resolution,
            place_source,
        )

    appointment = None
    if candidate.existing_appointment_id is None:
        missing_fields.append("existing_appointment_id")
    else:
        appointment = (
            db.query(Appointment)
            .filter(
                Appointment.id == candidate.existing_appointment_id,
                Appointment.professional_id == candidate.professional_id,
            )
            .first()
        )
        if appointment is None:
            missing_fields.append("existing_appointment_id")
    if missing_fields:
        return CandidateResolution("reschedule", {}, missing_fields)

    assert appointment is not None
    assert start_at is not None and end_at is not None
    place_resolution, place_source = _resolve_candidate_place(
        db,
        candidate,
        start_at=start_at,
        end_at=end_at,
        override_place_id=overrides.place_id if overrides else None,
    )
    if place_resolution.place_id is None:
        return CandidateResolution(
            "reschedule", {}, ["place_id"], place_resolution, place_source
        )
    occurrence_date = appointment.start_at.astimezone(TIMEZONE).date().isoformat()
    return CandidateResolution(
        "reschedule",
        {
            "target_type": "appointment",
            "target_id": str(appointment.id),
            "occurrence_date": occurrence_date,
            "new_start_at": _iso_datetime(start_at) or "",
            "new_end_at": _iso_datetime(end_at) or "",
            "new_place_id": str(place_resolution.place_id),
        },
        [],
        place_resolution,
        place_source,
    )

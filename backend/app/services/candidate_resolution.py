"""Resolve passive appointment candidates into supported operation inputs."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentCandidate, Contact, Place
from app.services.scheduling import TIMEZONE

SupportedOperation = Literal["create", "reschedule"]


@dataclass(frozen=True)
class CandidateResolution:
    """A candidate's executable input or the fields still required."""

    operation: SupportedOperation | None
    arguments: dict[str, str]
    missing_fields: list[str]

    @property
    def is_resolved(self) -> bool:
        return self.operation is not None and not self.missing_fields


@dataclass(frozen=True)
class CreateCandidateOverrides:
    """Instructor-reviewed values that replace extracted create fields."""

    place_id: uuid.UUID | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    service: str | None = None


def _candidate_operation(candidate: AppointmentCandidate) -> str:
    return candidate.operation or candidate.action


def _candidate_place(
    db: Session, candidate: AppointmentCandidate, place_id: uuid.UUID | None = None
) -> Place | None:
    if place_id is not None:
        return (
            db.query(Place)
            .filter(
                Place.id == place_id,
                Place.professional_id == candidate.professional_id,
            )
            .first()
        )
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
        db.query(Place)
        .filter(
            Place.id == contact.home_place_id,
            Place.professional_id == candidate.professional_id,
        )
        .first()
    )


def _iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def resolve_candidate(
    db: Session,
    candidate: AppointmentCandidate,
    create_overrides: CreateCandidateOverrides | None = None,
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

    start_at = create_overrides.start_at if create_overrides and create_overrides.start_at else candidate.proposed_start_at
    end_at = create_overrides.end_at if create_overrides and create_overrides.end_at else candidate.proposed_end_at
    if start_at is None:
        missing_fields.append("start_at")
    if end_at is None:
        missing_fields.append("end_at")
    if start_at and end_at:
        if end_at <= start_at:
            missing_fields.append("valid_time_range")

    if operation == "create":
        service = create_overrides.service if create_overrides and create_overrides.service is not None else candidate.service
        if not service or not service.strip():
            missing_fields.append("service")
        place = _candidate_place(
            db, candidate, create_overrides.place_id if create_overrides else None
        )
        if place is None:
            missing_fields.append("place_id")
        if missing_fields:
            return CandidateResolution("create", {}, missing_fields)
        return CandidateResolution(
            "create",
            {
                "contact_id": str(candidate.contact_id),
                "place_id": str(place.id),
                "start_at": _iso_datetime(start_at) or "",
                "end_at": _iso_datetime(end_at) or "",
                "service": service.strip(),
            },
            [],
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
    occurrence_date = appointment.start_at.astimezone(TIMEZONE).date().isoformat()
    return CandidateResolution(
        "reschedule",
        {
            "target_type": "appointment",
            "target_id": str(appointment.id),
            "occurrence_date": occurrence_date,
            "new_start_at": _iso_datetime(start_at) or "",
            "new_end_at": _iso_datetime(end_at) or "",
            "new_place_id": str(appointment.place_id) if appointment.place_id else "",
        },
        [],
    )

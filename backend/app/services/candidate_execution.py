"""Execute reviewed passive appointment candidates atomically."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentCandidate
from app.services import appointments
from app.services.candidate_resolution import CreateCandidateOverrides, resolve_candidate
from app.services.operational_events import record_event
from app.services.scheduling import TIMEZONE


@dataclass(frozen=True)
class CreateCandidateInput:
    place_id: uuid.UUID | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    service: str | None = None


def confirm_create_candidate(
    db: Session,
    candidate: AppointmentCandidate,
    *,
    actor_user_id: uuid.UUID,
    input: CreateCandidateInput,
    source_channel: str = "web",
    automatic: bool = False,
) -> Appointment:
    """Create an appointment from one reviewed passive candidate.

    Callers must lock and tenant-scope ``candidate`` before invoking this
    function. The appointment, candidate lifecycle transition, linkage, and
    audit event remain in the caller's transaction.
    """
    if candidate.status != "detected":
        raise HTTPException(status_code=409, detail="Candidate is not pending review")

    resolution = resolve_candidate(
        db,
        candidate,
        CreateCandidateOverrides(
            place_id=input.place_id,
            start_at=input.start_at,
            end_at=input.end_at,
            service=input.service,
        ),
    )
    if resolution.operation != "create":
        raise HTTPException(status_code=422, detail="Only create candidates can be confirmed")
    if not resolution.is_resolved:
        raise HTTPException(
            status_code=422,
            detail={"missing_fields": resolution.missing_fields},
        )

    args = resolution.arguments
    appointment = appointments.create_appointment(
        db,
        candidate.professional_id,
        contact_id=uuid.UUID(args["contact_id"]),
        place_id=uuid.UUID(args["place_id"]),
        service=args["service"],
        start_at=datetime.fromisoformat(args["start_at"]),
        end_at=datetime.fromisoformat(args["end_at"]),
        source="passive_candidate",
        actor=f"user:{actor_user_id}",
    )
    candidate.status = "fulfilled"
    candidate.resulting_appointment_id = appointment.id
    record_event(
        db,
        professional_id=candidate.professional_id,
        event_type="schedule.appointment.created",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=actor_user_id,
        source_channel=source_channel,
        entity_type="appointment",
        entity_id=appointment.id,
        correlation_id=uuid.uuid4(),
        payload={
            "origin": "passive_observer",
            "appointment_candidate_id": str(candidate.id),
            "automatic": automatic,
        },
        before_state=None,
        after_state={"status": appointment.status},
        idempotency_key=f"candidate-create:{candidate.id}",
    )
    return appointment

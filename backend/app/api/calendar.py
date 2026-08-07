"""
Calendar API — Phase 4 read endpoints.

GET  /api/calendar          — list appointments for a date range (query params:
                              start_date, end_date).
GET  /api/appointments/{id} — single appointment detail.
POST /api/appointments      — create a confirmed dashboard booking.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_authenticated, require_professional_id
from app.database import SessionLocal
from app.models import Appointment, AppointmentParticipant, Contact, Place
from app.schemas.api import (
    AppointmentCreate,
    AppointmentDetail,
    AppointmentParticipantSummary,
    AppointmentSummary,
    CalendarResponse,
)
from app.services import scheduling
from app.services.appointments import create_appointment as create_appointment_service

router = APIRouter(prefix="/api", tags=["calendar"])

TZ_SP = timezone(timedelta(hours=-3))  # America/Sao_Paulo


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/calendar", response_model=CalendarResponse)
def list_appointments(
    start_date: date = Query(..., description="Start date (ISO format, e.g. 2026-08-03)"),
    end_date: date = Query(..., description="End date (ISO format, inclusive)"),
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    """Return each dated appointment occurrence in [start_date, end_date] via
    the same projection the instructor agent uses (`scheduling.
    list_schedule_occurrences`) — recurring appointments are expanded to one
    row per date, and any confirmed cancellation/reschedule
    (`ScheduleOccurrenceOverride`) is already applied, so the calendar grid
    can never show a cancelled slot as if it were still booked."""
    occurrences = [
        occurrence
        for occurrence in scheduling.list_schedule_occurrences(
            db, professional_id, start_date, end_date
        )
        if occurrence.source_type == "appointment"
    ]

    appointments = [
        AppointmentSummary(
            id=occurrence.source_id,
            contact_name=occurrence.participants[0].contact_name,
            contact_id=occurrence.participants[0].contact_id,
            place_id=occurrence.place_id,
            place_name=occurrence.place_name,
            service=occurrence.source_label,
            start_at=occurrence.starts_at,
            end_at=occurrence.ends_at,
            status=occurrence.status,
            source=occurrence.appointment_source or "dashboard",
            class_type=occurrence.class_type or "individual",
            participants=[
                AppointmentParticipantSummary(
                    contact_id=p.contact_id, display_name=p.contact_name
                )
                for p in occurrence.participants
            ],
            occurrence_date=occurrence.occurrence_date,
        )
        for occurrence in occurrences
    ]

    return CalendarResponse(appointments=appointments)


@router.post("/appointments", response_model=AppointmentDetail, status_code=201)
def create_appointment(
    body: AppointmentCreate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
    user: dict = Depends(require_authenticated),
):
    """Create a confirmed booking; recurring place slots are availability
    context and intentionally do not participate in overlap validation."""
    contact = (
        db.query(Contact)
        .filter(Contact.id == body.contact_id, Contact.professional_id == professional_id)
        .first()
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    place = (
        db.query(Place)
        .filter(Place.id == body.place_id, Place.professional_id == professional_id)
        .first()
    )
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")

    appointment = create_appointment_service(
        db,
        professional_id,
        contact_id=contact.id,
        place_id=place.id,
        service=body.service,
        start_at=body.start_at,
        end_at=body.end_at,
        is_recurring=body.is_recurring,
        source="dashboard",
        actor=f"user:{user['user_id']}",
    )
    db.commit()

    return AppointmentDetail(
        id=appointment.id,
        professional_id=appointment.professional_id,
        contact_id=appointment.contact_id,
        contact_name=contact.display_name,
        place_id=appointment.place_id,
        place_name=place.name,
        service=appointment.service,
        start_at=appointment.start_at,
        end_at=appointment.end_at,
        timezone=appointment.timezone,
        status=appointment.status,
        source=appointment.source,
        recurrence_rule=appointment.recurrence_rule,
        class_type=appointment.class_type,
        participants=[
            AppointmentParticipantSummary(
                contact_id=contact.id, display_name=contact.display_name
            )
        ],
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
    )


def _load_participants(db: Session, appointment: Appointment) -> list[AppointmentParticipantSummary]:
    primary = db.query(Contact).filter(Contact.id == appointment.contact_id).first()
    result = [
        AppointmentParticipantSummary(
            contact_id=appointment.contact_id,
            display_name=primary.display_name if primary else "Desconhecido",
        )
    ]
    extra_rows = (
        db.query(Contact)
        .join(AppointmentParticipant, AppointmentParticipant.contact_id == Contact.id)
        .filter(AppointmentParticipant.appointment_id == appointment.id)
        .order_by(Contact.display_name)
        .all()
    )
    result.extend(
        AppointmentParticipantSummary(contact_id=c.id, display_name=c.display_name)
        for c in extra_rows
    )
    return result


@router.get("/appointments/{appointment_id}", response_model=AppointmentDetail)
def get_appointment(
    appointment_id: str,
    occurrence_date: date | None = Query(
        None,
        description=(
            "The specific dated occurrence (from AppointmentSummary."
            "occurrence_date) to resolve — applies any confirmed "
            "reschedule/cancellation for that date instead of returning "
            "the appointment's original, possibly stale, start_at/end_at/"
            "place. Omit to fetch the raw appointment as originally booked."
        ),
    ),
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
):
    """Return a single appointment with full detail."""
    appt = (
        db.query(Appointment)
        .filter(Appointment.id == appointment_id, Appointment.professional_id == professional_id)
        .first()
    )
    if appt is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if occurrence_date is not None:
        occurrence = scheduling.get_schedule_occurrence(
            db, professional_id, "appointment", appt.id, occurrence_date
        )
        if occurrence is None:
            raise HTTPException(
                status_code=404,
                detail="Occurrence not found for that date — it may have been cancelled",
            )
        return AppointmentDetail(
            id=appt.id,
            professional_id=appt.professional_id,
            contact_id=occurrence.participants[0].contact_id,
            contact_name=occurrence.participants[0].contact_name,
            place_id=occurrence.place_id,
            place_name=occurrence.place_name,
            service=occurrence.source_label,
            start_at=occurrence.starts_at,
            end_at=occurrence.ends_at,
            timezone=appt.timezone,
            status=occurrence.status,
            class_type=occurrence.class_type or "individual",
            participants=[
                AppointmentParticipantSummary(
                    contact_id=p.contact_id, display_name=p.contact_name
                )
                for p in occurrence.participants
            ],
            source=appt.source,
            recurrence_rule=appt.recurrence_rule,
            occurrence_date=occurrence.occurrence_date,
            is_exception=occurrence.is_exception,
            created_at=appt.created_at,
            updated_at=appt.updated_at,
        )

    contact = db.query(Contact).filter(Contact.id == appt.contact_id).first()
    place_name = (
        db.query(Place.name).filter(Place.id == appt.place_id).scalar()
        if appt.place_id is not None
        else None
    )

    return AppointmentDetail(
        id=appt.id,
        professional_id=appt.professional_id,
        contact_id=appt.contact_id,
        contact_name=contact.display_name if contact else "Desconhecido",
        place_id=appt.place_id,
        place_name=place_name,
        service=appt.service,
        start_at=appt.start_at,
        end_at=appt.end_at,
        timezone=appt.timezone,
        status=appt.status,
        class_type=appt.class_type,
        participants=_load_participants(db, appt),
        source=appt.source,
        recurrence_rule=appt.recurrence_rule,
        created_at=appt.created_at,
        updated_at=appt.updated_at,
    )

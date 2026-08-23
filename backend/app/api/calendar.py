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
    AppointmentFormatUpdate,
    AppointmentParticipantSummary,
    AppointmentSummary,
    CalendarResponse,
    OccurrenceClassFormatDetail,
    OccurrenceClassFormatUpdate,
    RecurringClassOccurrenceSummary,
)
from app.api.instructor_events import _detail_for as _instructor_event_detail
from app.services import instructor_events as instructor_events_service
from app.services import scheduling
from app.services.appointment_participants import add_participant
from app.services.appointments import (
    create_appointment as create_appointment_service,
    update_appointment_format,
)
from app.services.operational_events import record_event
from app.services.occurrence_class_formats import set_format as set_occurrence_format

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
    all_occurrences = scheduling.list_schedule_occurrences(
        db, professional_id, start_date, end_date
    )
    occurrences = [
        occurrence for occurrence in all_occurrences if occurrence.source_type == "appointment"
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
            max_participants=occurrence.max_participants,
            participants=[
                AppointmentParticipantSummary(
                    contact_id=p.contact_id, display_name=p.contact_name
                )
                for p in occurrence.participants
            ],
            occurrence_date=occurrence.occurrence_date,
            billing_type=occurrence.billing_type,
        )
        for occurrence in occurrences
    ]
    recurring_classes = [
        RecurringClassOccurrenceSummary(
            recurring_slot_id=occurrence.source_id,
            occurrence_date=occurrence.occurrence_date,
            start_at=occurrence.starts_at,
            end_at=occurrence.ends_at,
            label=occurrence.source_label,
            place_id=occurrence.place_id,
            place_name=occurrence.place_name,
            class_type=occurrence.class_type or "individual",
            max_participants=occurrence.max_participants,
            participants=[
                AppointmentParticipantSummary(
                    contact_id=participant.contact_id,
                    display_name=participant.contact_name,
                )
                for participant in occurrence.participants
            ],
            is_exception=occurrence.is_exception,
        )
        for occurrence in all_occurrences
        if occurrence.source_type == "recurring_slot"
    ]

    events = instructor_events_service.list_events(
        db,
        professional_id,
        date_from=datetime.combine(start_date, datetime.min.time(), tzinfo=TZ_SP),
        date_to=datetime.combine(end_date, datetime.max.time(), tzinfo=TZ_SP),
        status="confirmed",
    )

    return CalendarResponse(
        appointments=appointments,
        recurring_classes=recurring_classes,
        events=[_instructor_event_detail(db, event) for event in events],
    )


@router.post("/appointments", response_model=AppointmentDetail, status_code=201)
def create_appointment(
    body: AppointmentCreate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
    user: dict = Depends(require_authenticated),
):
    """Create a confirmed booking; recurring place slots are availability
    context and intentionally do not participate in overlap validation."""
    participant_ids = body.contact_ids or [body.contact_id]
    contacts = (
        db.query(Contact)
        .filter(
            Contact.professional_id == professional_id,
            Contact.id.in_(participant_ids),
        )
        .all()
    )
    if len(contacts) != len(participant_ids):
        raise HTTPException(status_code=404, detail="Contact not found")
    contacts_by_id = {contact.id: contact for contact in contacts}
    contact = contacts_by_id[body.contact_id]

    appointment = create_appointment_service(
        db,
        professional_id,
        contact_id=contact.id,
        place_id=body.place_id,
        service=body.service,
        start_at=body.start_at,
        end_at=body.end_at,
        is_recurring=body.is_recurring,
        class_type=body.class_type,
        max_participants=body.max_participants,
        source="dashboard",
        actor=f"user:{user['user_id']}",
        billing_type=body.billing_type,
    )
    for participant_id in participant_ids:
        if participant_id != contact.id:
            add_participant(
                db,
                professional_id,
                appointment,
                contacts_by_id[participant_id],
            )
    db.commit()

    return AppointmentDetail(
        id=appointment.id,
        professional_id=appointment.professional_id,
        contact_id=appointment.contact_id,
        contact_name=contact.display_name,
        place_id=appointment.place_id,
        place_name=db.query(Place.name).filter(Place.id == appointment.place_id).scalar(),
        service=appointment.service,
        start_at=appointment.start_at,
        end_at=appointment.end_at,
        timezone=appointment.timezone,
        status=appointment.status,
        source=appointment.source,
        recurrence_rule=appointment.recurrence_rule,
        class_type=appointment.class_type,
        max_participants=appointment.max_participants,
        billing_type=appointment.billing_type,
        participants=_load_participants(db, appointment),
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
    )


@router.patch("/appointments/{appointment_id}/format", response_model=AppointmentDetail)
def update_appointment_class_format(
    appointment_id: uuid.UUID,
    body: AppointmentFormatUpdate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
    user: dict = Depends(require_authenticated),
):
    """Explicitly change an appointment between individual and group formats."""
    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.id == appointment_id,
            Appointment.professional_id == professional_id,
        )
        .first()
    )
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    before_state = {
        "class_type": appointment.class_type,
        "max_participants": appointment.max_participants,
    }
    update_appointment_format(
        db,
        appointment,
        class_type=body.class_type,
        max_participants=body.max_participants,
    )
    record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.appointment.updated",
        occurred_at=datetime.now(TZ_SP),
        actor_type="user",
        actor_id=uuid.UUID(user["user_id"]),
        source_channel="web",
        entity_type="appointment",
        entity_id=appointment.id,
        correlation_id=uuid.uuid4(),
        payload={"operation": "class_format_updated"},
        before_state=before_state,
        after_state={
            "class_type": appointment.class_type,
            "max_participants": appointment.max_participants,
        },
    )
    db.commit()

    contact = db.query(Contact).filter(Contact.id == appointment.contact_id).first()
    place_name = (
        db.query(Place.name).filter(Place.id == appointment.place_id).scalar()
        if appointment.place_id is not None
        else None
    )
    return AppointmentDetail(
        id=appointment.id,
        professional_id=appointment.professional_id,
        contact_id=appointment.contact_id,
        contact_name=contact.display_name if contact else "Desconhecido",
        place_id=appointment.place_id,
        place_name=place_name,
        service=appointment.service,
        start_at=appointment.start_at,
        end_at=appointment.end_at,
        timezone=appointment.timezone,
        status=appointment.status,
        class_type=appointment.class_type,
        max_participants=appointment.max_participants,
        participants=_load_participants(db, appointment),
        source=appointment.source,
        recurrence_rule=appointment.recurrence_rule,
        billing_type=appointment.billing_type,
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
    )


@router.patch(
    "/schedule-occurrences/{source_type}/{source_id}/{occurrence_date}/format",
    response_model=OccurrenceClassFormatDetail,
)
def update_occurrence_class_format(
    source_type: str,
    source_id: uuid.UUID,
    occurrence_date: date,
    body: OccurrenceClassFormatUpdate,
    db: Session = Depends(get_db),
    professional_id: uuid.UUID = Depends(require_professional_id),
    user: dict = Depends(require_authenticated),
):
    occurrence = scheduling.get_schedule_occurrence(
        db, professional_id, source_type, source_id, occurrence_date
    )
    if occurrence is None:
        raise HTTPException(status_code=404, detail="Scheduled occurrence not found")
    before_state = {
        "class_type": occurrence.class_type,
        "max_participants": occurrence.max_participants,
    }
    set_occurrence_format(
        db,
        professional_id,
        source_type=source_type,
        source_id=source_id,
        occurrence_date=occurrence_date,
        class_type=body.class_type,
        max_participants=body.max_participants,
        participant_count=occurrence.participant_count,
        actor_user_id=uuid.UUID(user["user_id"]),
        source="dashboard",
    )
    updated = scheduling.get_schedule_occurrence(
        db, professional_id, source_type, source_id, occurrence_date
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Scheduled occurrence not found")
    record_event(
        db,
        professional_id=professional_id,
        event_type=(
            "schedule.appointment.updated"
            if source_type == "appointment"
            else "schedule.series.updated"
        ),
        occurred_at=datetime.now(TZ_SP),
        actor_type="user",
        actor_id=uuid.UUID(user["user_id"]),
        source_channel="web",
        entity_type=source_type,
        entity_id=source_id,
        correlation_id=uuid.uuid4(),
        payload={"operation": "occurrence_class_format_updated", "occurrence_date": occurrence_date.isoformat()},
        before_state=before_state,
        after_state={
            "class_type": updated.class_type,
            "max_participants": updated.max_participants,
        },
    )
    db.commit()
    return OccurrenceClassFormatDetail(
        source_type=updated.source_type,
        source_id=updated.source_id,
        occurrence_date=updated.occurrence_date,
        class_type=updated.class_type or "individual",
        max_participants=updated.max_participants,
        participant_count=updated.participant_count,
        available_seats=updated.available_seats,
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
            max_participants=occurrence.max_participants,
            participants=[
                AppointmentParticipantSummary(
                    contact_id=p.contact_id, display_name=p.contact_name
                )
                for p in occurrence.participants
            ],
            source=appt.source,
            recurrence_rule=appt.recurrence_rule,
            billing_type=occurrence.billing_type,
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
        max_participants=appt.max_participants,
        participants=_load_participants(db, appt),
        source=appt.source,
        recurrence_rule=appt.recurrence_rule,
        billing_type=appt.billing_type,
        created_at=appt.created_at,
        updated_at=appt.updated_at,
    )

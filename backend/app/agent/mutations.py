"""
Write tools for the instructor agent (operational ontology roadmap v0.2,
Phases 4-5).

Every `propose_*` tool here never writes directly — it validates what it
can up front (so an obviously-impossible action never becomes a candidate),
then calls `app.agent.candidates.propose(...)` and returns a
`requires_confirmation` result to the orchestrator. Only `confirm()` (via
the `MUTATION_EXECUTORS` entry registered alongside each tool) performs the
actual write — re-validating everything inside the same transaction, since
state may have changed between proposal and confirmation.

Executors reuse the same service functions as the existing HTTP endpoints
(`app.services.participants`, `app.services.contacts`) so validation can't
diverge between the dashboard and the agent — see those modules' docstrings.
"""

import uuid
from datetime import date, datetime
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agent import candidates
from app.agent.candidates import ExecutionResult
from app.models import (
    Appointment,
    AppointmentParticipant,
    Contact,
    OperatorActionCandidate,
    Place,
    RecurringSlot,
    RecurringSlotParticipant,
)
from app.services import appointment_participants, appointments, participants, schedule_overrides
from app.services.contacts import apply_contact_updates
from app.services.operational_events import record_event
from app.services.scheduling import TIMEZONE

VALID_TARGET_TYPES = ("appointment", "recurring_slot")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TIMEZONE)
    return parsed

WEEKDAY_NAMES = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)


def _group_label(slot: RecurringSlot) -> str:
    return slot.group_name or slot.label or "Grupo"


def _weekday_time_label(slot: RecurringSlot) -> str:
    weekday = WEEKDAY_NAMES[slot.day_of_week]
    return f"{weekday} das {slot.start_time.strftime('%H:%M')} às {slot.end_time.strftime('%H:%M')}"


# ---------------------------------------------------------------------------
# propose_add_group_member
# ---------------------------------------------------------------------------

def propose_add_group_member(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    *,
    contact_id: str,
    recurring_slot_id: str,
) -> dict[str, Any]:
    contact = (
        db.query(Contact)
        .filter(Contact.id == uuid.UUID(contact_id), Contact.professional_id == professional_id)
        .first()
    )
    if contact is None:
        return {"error": "Contact not found"}

    slot = (
        db.query(RecurringSlot)
        .filter(
            RecurringSlot.id == uuid.UUID(recurring_slot_id),
            RecurringSlot.professional_id == professional_id,
        )
        .first()
    )
    if slot is None:
        return {"error": "Group not found"}
    if slot.slot_kind != "class":
        return {"error": "This slot is not a class — it has no roster to add a member to"}
    if participants.count_participants(db, slot.id) >= slot.max_participants:
        return {"error": "This group is at full capacity"}

    place_name = _place_name(db, slot.place_id)
    preview_text = (
        f"Adicionar {contact.display_name} ao {_group_label(slot)} "
        f"({_weekday_time_label(slot)}, {place_name})."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_add_group_member",
        arguments={"contact_id": contact_id, "recurring_slot_id": recurring_slot_id},
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": contact_id, "label": contact.display_name},
            {
                "entity_type": "recurring_slot",
                "entity_id": recurring_slot_id,
                "label": _group_label(slot),
            },
        ],
        correlation_id=correlation_id,
    )
    return _pending_result(candidate)


def _execute_add_group_member(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == uuid.UUID(args["contact_id"]),
            Contact.professional_id == professional_id,
        )
        .first()
    )
    slot = (
        db.query(RecurringSlot)
        .filter(
            RecurringSlot.id == uuid.UUID(args["recurring_slot_id"]),
            RecurringSlot.professional_id == professional_id,
        )
        .first()
    )
    if contact is None or slot is None:
        raise ValueError("Contact or group no longer exists")

    now = datetime.now(TIMEZONE)
    participant = participants.add_participant(db, professional_id, slot, contact)
    record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.participant.added",
        occurred_at=now,
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="recurring_slot",
        entity_id=slot.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"contact_id": str(contact.id), "participant_id": str(participant.id)},
        before_state=None,
        after_state={"contact_id": str(contact.id)},
    )
    return ExecutionResult(
        ok=True,
        summary=f"{contact.display_name} adicionado(a) ao {_group_label(slot)}.",
    )


# ---------------------------------------------------------------------------
# propose_remove_group_member
# ---------------------------------------------------------------------------

def propose_remove_group_member(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    *,
    contact_id: str,
    recurring_slot_id: str,
) -> dict[str, Any]:
    contact = (
        db.query(Contact)
        .filter(Contact.id == uuid.UUID(contact_id), Contact.professional_id == professional_id)
        .first()
    )
    if contact is None:
        return {"error": "Contact not found"}

    slot = (
        db.query(RecurringSlot)
        .filter(
            RecurringSlot.id == uuid.UUID(recurring_slot_id),
            RecurringSlot.professional_id == professional_id,
        )
        .first()
    )
    if slot is None:
        return {"error": "Group not found"}

    is_member = (
        db.query(RecurringSlotParticipant)
        .filter(
            RecurringSlotParticipant.recurring_slot_id == slot.id,
            RecurringSlotParticipant.contact_id == contact.id,
        )
        .first()
        is not None
    )
    if not is_member:
        return {"error": "Contact is not a member of this group"}

    place_name = _place_name(db, slot.place_id)
    preview_text = (
        f"Remover {contact.display_name} do {_group_label(slot)} "
        f"({_weekday_time_label(slot)}, {place_name})."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_remove_group_member",
        arguments={"contact_id": contact_id, "recurring_slot_id": recurring_slot_id},
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": contact_id, "label": contact.display_name},
            {
                "entity_type": "recurring_slot",
                "entity_id": recurring_slot_id,
                "label": _group_label(slot),
            },
        ],
        correlation_id=correlation_id,
    )
    return _pending_result(candidate)


def _execute_remove_group_member(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == uuid.UUID(args["contact_id"]),
            Contact.professional_id == professional_id,
        )
        .first()
    )
    slot = (
        db.query(RecurringSlot)
        .filter(
            RecurringSlot.id == uuid.UUID(args["recurring_slot_id"]),
            RecurringSlot.professional_id == professional_id,
        )
        .first()
    )
    if contact is None or slot is None:
        raise ValueError("Contact or group no longer exists")

    participants.remove_participant(db, slot.id, contact.id)
    record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.participant.removed",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="recurring_slot",
        entity_id=slot.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"contact_id": str(contact.id)},
        before_state={"contact_id": str(contact.id)},
        after_state=None,
    )
    return ExecutionResult(
        ok=True,
        summary=f"{contact.display_name} removido(a) do {_group_label(slot)}.",
    )


# ---------------------------------------------------------------------------
# propose_add_appointment_participant / propose_remove_appointment_participant
# ---------------------------------------------------------------------------

def _appointment_label(db: Session, appointment: Appointment) -> str:
    primary = db.query(Contact).filter(Contact.id == appointment.contact_id).first()
    primary_name = primary.display_name if primary else "Desconhecido"
    local_start = appointment.start_at.astimezone(TIMEZONE)
    return f"{appointment.service} de {primary_name} em {local_start.strftime('%d/%m/%Y %H:%M')}"


def propose_add_appointment_participant(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    *,
    contact_id: str,
    appointment_id: str,
) -> dict[str, Any]:
    contact = (
        db.query(Contact)
        .filter(Contact.id == uuid.UUID(contact_id), Contact.professional_id == professional_id)
        .first()
    )
    if contact is None:
        return {"error": "Contact not found"}

    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.id == uuid.UUID(appointment_id),
            Appointment.professional_id == professional_id,
        )
        .first()
    )
    if appointment is None:
        return {"error": "Appointment not found"}
    if contact.id == appointment.contact_id:
        return {"error": "Contact is already in this appointment"}
    already_participant = (
        db.query(AppointmentParticipant)
        .filter(
            AppointmentParticipant.appointment_id == appointment.id,
            AppointmentParticipant.contact_id == contact.id,
        )
        .first()
        is not None
    )
    if already_participant:
        return {"error": "Contact is already in this appointment"}
    if (
        appointment_participants.count_participants(db, appointment.id)
        >= appointment_participants.MAX_PARTICIPANTS
    ):
        return {"error": "This appointment is at full capacity"}

    label = _appointment_label(db, appointment)
    preview_text = f"Adicionar {contact.display_name} à aula ({label})."
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_add_appointment_participant",
        arguments={"contact_id": contact_id, "appointment_id": appointment_id},
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": contact_id, "label": contact.display_name},
            {"entity_type": "appointment", "entity_id": appointment_id, "label": label},
        ],
        correlation_id=correlation_id,
    )
    return _pending_result(candidate)


def _execute_add_appointment_participant(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == uuid.UUID(args["contact_id"]),
            Contact.professional_id == professional_id,
        )
        .first()
    )
    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.id == uuid.UUID(args["appointment_id"]),
            Appointment.professional_id == professional_id,
        )
        .first()
    )
    if contact is None or appointment is None:
        raise ValueError("Contact or appointment no longer exists")

    appointment_participants.add_participant(db, professional_id, appointment, contact)
    record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.participant.added",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="appointment",
        entity_id=appointment.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"contact_id": str(contact.id)},
        before_state={"class_type": "individual"},
        after_state={"class_type": "group", "contact_id": str(contact.id)},
    )
    return ExecutionResult(
        ok=True,
        summary=f"{contact.display_name} adicionado(a) à aula ({_appointment_label(db, appointment)}).",
    )


def propose_remove_appointment_participant(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    *,
    contact_id: str,
    appointment_id: str,
) -> dict[str, Any]:
    contact = (
        db.query(Contact)
        .filter(Contact.id == uuid.UUID(contact_id), Contact.professional_id == professional_id)
        .first()
    )
    if contact is None:
        return {"error": "Contact not found"}

    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.id == uuid.UUID(appointment_id),
            Appointment.professional_id == professional_id,
        )
        .first()
    )
    if appointment is None:
        return {"error": "Appointment not found"}
    if contact.id == appointment.contact_id:
        return {"error": "The primary contact cannot be removed from the appointment"}
    is_participant = (
        db.query(AppointmentParticipant)
        .filter(
            AppointmentParticipant.appointment_id == appointment.id,
            AppointmentParticipant.contact_id == contact.id,
        )
        .first()
        is not None
    )
    if not is_participant:
        return {"error": "Contact is not a participant of this appointment"}

    label = _appointment_label(db, appointment)
    preview_text = f"Remover {contact.display_name} da aula ({label})."
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_remove_appointment_participant",
        arguments={"contact_id": contact_id, "appointment_id": appointment_id},
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": contact_id, "label": contact.display_name},
            {"entity_type": "appointment", "entity_id": appointment_id, "label": label},
        ],
        correlation_id=correlation_id,
    )
    return _pending_result(candidate)


def _execute_remove_appointment_participant(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == uuid.UUID(args["contact_id"]),
            Contact.professional_id == professional_id,
        )
        .first()
    )
    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.id == uuid.UUID(args["appointment_id"]),
            Appointment.professional_id == professional_id,
        )
        .first()
    )
    if contact is None or appointment is None:
        raise ValueError("Contact or appointment no longer exists")

    label = _appointment_label(db, appointment)
    appointment_participants.remove_participant(db, appointment.id, contact.id)
    record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.participant.removed",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="appointment",
        entity_id=appointment.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"contact_id": str(contact.id)},
        before_state={"contact_id": str(contact.id)},
        after_state=None,
    )
    return ExecutionResult(
        ok=True,
        summary=f"{contact.display_name} removido(a) da aula ({label}).",
    )


# ---------------------------------------------------------------------------
# propose_update_contact
# ---------------------------------------------------------------------------

ALLOWED_CONTACT_FIELDS = {
    "display_name",
    "level",
    "address_line",
    "city",
    "state",
    "postal_code",
    "country",
    "latitude",
    "longitude",
    "home_place_id",
}


def propose_update_contact(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    *,
    contact_id: str,
    changes: dict[str, Any],
) -> dict[str, Any]:
    contact = (
        db.query(Contact)
        .filter(Contact.id == uuid.UUID(contact_id), Contact.professional_id == professional_id)
        .first()
    )
    if contact is None:
        return {"error": "Contact not found"}

    unknown_fields = set(changes) - ALLOWED_CONTACT_FIELDS
    if unknown_fields:
        return {"error": f"Unknown field(s): {', '.join(sorted(unknown_fields))}"}
    if not changes:
        return {"error": "No changes provided"}

    diff_lines = []
    for field, new_value in changes.items():
        old_value = getattr(contact, field)
        diff_lines.append(f"{field}: {old_value!r} → {new_value!r}")
    preview_text = f"Atualizar {contact.display_name}: " + "; ".join(diff_lines)

    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_update_contact",
        arguments={"contact_id": contact_id, "changes": changes},
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": contact_id, "label": contact.display_name}
        ],
        correlation_id=correlation_id,
    )
    return _pending_result(candidate)


def _execute_update_contact(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == uuid.UUID(args["contact_id"]),
            Contact.professional_id == professional_id,
        )
        .first()
    )
    if contact is None:
        raise ValueError("Contact no longer exists")

    changes = args["changes"]
    before_state = {field: getattr(contact, field) for field in changes}
    apply_contact_updates(db, professional_id, contact, changes)
    after_state = {field: getattr(contact, field) for field in changes}

    def _jsonable(value):
        return value.isoformat() if hasattr(value, "isoformat") else value

    record_event(
        db,
        professional_id=professional_id,
        event_type="contact.updated",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="contact",
        entity_id=contact.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"changes": changes},
        before_state={k: _jsonable(v) for k, v in before_state.items()},
        after_state={k: _jsonable(v) for k, v in after_state.items()},
    )
    return ExecutionResult(ok=True, summary=f"{contact.display_name} atualizado(a).")


# ---------------------------------------------------------------------------
# propose_create_appointment
# ---------------------------------------------------------------------------

def propose_create_appointment(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    *,
    contact_id: str,
    place_id: str,
    start_at: str,
    end_at: str,
    service: str,
) -> dict[str, Any]:
    contact = (
        db.query(Contact)
        .filter(Contact.id == uuid.UUID(contact_id), Contact.professional_id == professional_id)
        .first()
    )
    if contact is None:
        return {"error": "Contact not found"}

    place = (
        db.query(Place)
        .filter(Place.id == uuid.UUID(place_id), Place.professional_id == professional_id)
        .first()
    )
    if place is None:
        return {"error": "Place not found"}

    parsed_start = _parse_datetime(start_at)
    parsed_end = _parse_datetime(end_at)
    if parsed_end <= parsed_start:
        return {"error": "end_at must be after start_at"}

    try:
        appointments.assert_no_conflict(
            db, professional_id, start_at=parsed_start, end_at=parsed_end
        )
    except HTTPException as exc:
        return {"error": exc.detail}

    local_start = parsed_start.astimezone(TIMEZONE)
    preview_text = (
        f"Criar atendimento de {service.strip()} para {contact.display_name} em "
        f"{local_start.strftime('%d/%m/%Y %H:%M')}, {place.name}."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_create_appointment",
        arguments={
            "contact_id": contact_id,
            "place_id": place_id,
            "start_at": parsed_start.isoformat(),
            "end_at": parsed_end.isoformat(),
            "service": service,
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": contact_id, "label": contact.display_name},
            {"entity_type": "place", "entity_id": place_id, "label": place.name},
        ],
        correlation_id=correlation_id,
    )
    return _pending_result(candidate)


def _execute_create_appointment(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    appointment = appointments.create_appointment(
        db,
        professional_id,
        contact_id=uuid.UUID(args["contact_id"]),
        place_id=uuid.UUID(args["place_id"]),
        service=args["service"],
        start_at=_parse_datetime(args["start_at"]),
        end_at=_parse_datetime(args["end_at"]),
        source="assistant",
        actor=f"user:{candidate.actor_user_id}",
    )
    record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.appointment.created",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="appointment",
        entity_id=appointment.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"start_at": args["start_at"], "end_at": args["end_at"]},
        before_state=None,
        after_state={"status": appointment.status},
    )
    return ExecutionResult(ok=True, summary=f"Atendimento criado para {args['start_at']}.")


# ---------------------------------------------------------------------------
# propose_cancel_schedule
# ---------------------------------------------------------------------------

def propose_cancel_schedule(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    *,
    target_type: str,
    target_id: str,
    occurrence_date: str,
) -> dict[str, Any]:
    if target_type not in VALID_TARGET_TYPES:
        return {"error": f"target_type must be one of {VALID_TARGET_TYPES}"}

    parsed_date = date.fromisoformat(occurrence_date)
    try:
        occurrence = schedule_overrides.get_target_occurrence(
            db, professional_id, target_type, uuid.UUID(target_id), parsed_date
        )
    except HTTPException as exc:
        return {"error": exc.detail}

    local_start = occurrence.starts_at.astimezone(TIMEZONE)
    preview_text = (
        f"Cancelar {occurrence.source_label} em {local_start.strftime('%d/%m/%Y %H:%M')} "
        f"({occurrence.place_name or 'local não informado'})."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_cancel_schedule",
        arguments={
            "target_type": target_type,
            "target_id": target_id,
            "occurrence_date": occurrence_date,
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": target_type, "entity_id": target_id, "label": occurrence.source_label}
        ],
        correlation_id=correlation_id,
    )
    return _pending_result(candidate)


def _execute_cancel_schedule(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    target_id = uuid.UUID(args["target_id"])
    schedule_overrides.cancel_occurrence(
        db,
        professional_id,
        target_type=args["target_type"],
        target_id=target_id,
        occurrence_date=date.fromisoformat(args["occurrence_date"]),
        actor_user_id=candidate.actor_user_id,
    )
    record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.occurrence.cancelled",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type=args["target_type"],
        entity_id=target_id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"occurrence_date": args["occurrence_date"]},
        before_state={"status": "scheduled"},
        after_state={"status": "cancelled"},
    )
    return ExecutionResult(ok=True, summary=f"Ocorrência de {args['occurrence_date']} cancelada.")


# ---------------------------------------------------------------------------
# propose_reschedule_occurrence
# ---------------------------------------------------------------------------

def propose_reschedule_occurrence(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    *,
    target_type: str,
    target_id: str,
    occurrence_date: str,
    new_start_at: str,
    new_end_at: str,
    new_place_id: str | None = None,
) -> dict[str, Any]:
    if target_type not in VALID_TARGET_TYPES:
        return {"error": f"target_type must be one of {VALID_TARGET_TYPES}"}

    parsed_date = date.fromisoformat(occurrence_date)
    try:
        occurrence = schedule_overrides.get_target_occurrence(
            db, professional_id, target_type, uuid.UUID(target_id), parsed_date
        )
    except HTTPException as exc:
        return {"error": exc.detail}

    parsed_new_start = _parse_datetime(new_start_at)
    parsed_new_end = _parse_datetime(new_end_at)
    if parsed_new_end <= parsed_new_start:
        return {"error": "new_end_at must be after new_start_at"}

    try:
        schedule_overrides.assert_new_time_available(
            db,
            professional_id,
            target_type=target_type,
            target_id=uuid.UUID(target_id),
            new_start_at=parsed_new_start,
            new_end_at=parsed_new_end,
        )
    except HTTPException as exc:
        return {"error": exc.detail}

    new_place_name = occurrence.place_name
    if new_place_id is not None:
        new_place_name = _place_name(db, uuid.UUID(new_place_id))

    old_local = occurrence.starts_at.astimezone(TIMEZONE)
    new_local = parsed_new_start.astimezone(TIMEZONE)
    preview_text = (
        f"Remarcar {occurrence.source_label} de {old_local.strftime('%d/%m/%Y %H:%M')} "
        f"para {new_local.strftime('%d/%m/%Y %H:%M')} ({new_place_name or 'local não informado'})."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_reschedule_occurrence",
        arguments={
            "target_type": target_type,
            "target_id": target_id,
            "occurrence_date": occurrence_date,
            "new_start_at": parsed_new_start.isoformat(),
            "new_end_at": parsed_new_end.isoformat(),
            "new_place_id": new_place_id,
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": target_type, "entity_id": target_id, "label": occurrence.source_label}
        ],
        correlation_id=correlation_id,
    )
    return _pending_result(candidate)


def _execute_reschedule_occurrence(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    target_id = uuid.UUID(args["target_id"])
    schedule_overrides.reschedule_occurrence(
        db,
        professional_id,
        target_type=args["target_type"],
        target_id=target_id,
        occurrence_date=date.fromisoformat(args["occurrence_date"]),
        new_start_at=_parse_datetime(args["new_start_at"]),
        new_end_at=_parse_datetime(args["new_end_at"]),
        new_place_id=uuid.UUID(args["new_place_id"]) if args.get("new_place_id") else None,
        actor_user_id=candidate.actor_user_id,
    )
    record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.occurrence.rescheduled",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type=args["target_type"],
        entity_id=target_id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={
            "occurrence_date": args["occurrence_date"],
            "new_start_at": args["new_start_at"],
        },
        before_state={"occurrence_date": args["occurrence_date"]},
        after_state={"new_start_at": args["new_start_at"]},
    )
    return ExecutionResult(
        ok=True, summary=f"Ocorrência remarcada para {args['new_start_at']}."
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _place_name(db: Session, place_id: uuid.UUID) -> str:
    name = db.query(Place.name).filter(Place.id == place_id).scalar()
    return name or "local desconhecido"


def _pending_result(candidate: OperatorActionCandidate) -> dict[str, Any]:
    return {
        "requires_confirmation": True,
        "candidate_id": str(candidate.id),
        "preview_text": candidate.preview_text,
        "affected_entities": candidate.affected_entities,
        "expires_at": candidate.expires_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

MUTATION_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "propose_add_group_member",
            "description": "Propose adding a contact to a recurring class group. Requires explicit instructor confirmation before it takes effect — use resolved IDs from search_contacts/find_groups, never guessed ones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "recurring_slot_id": {"type": "string", "description": "The group's recurring_slot_id, from find_groups."},
                },
                "required": ["contact_id", "recurring_slot_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_remove_group_member",
            "description": "Propose removing a contact from a recurring class group's roster. Requires explicit instructor confirmation before it takes effect.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "recurring_slot_id": {"type": "string"},
                },
                "required": ["contact_id", "recurring_slot_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_update_contact",
            "description": "Propose updating fields on a contact (e.g. level, address, home place). Requires explicit instructor confirmation before it takes effect.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "changes": {
                        "type": "object",
                        "description": "Field/value pairs to change — only display_name, level, address_line, city, state, postal_code, country, latitude, longitude, home_place_id are allowed.",
                    },
                },
                "required": ["contact_id", "changes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_create_appointment",
            "description": "Propose creating a direct (one-off) appointment for a contact. Requires explicit instructor confirmation before it takes effect — use resolved IDs from search_contacts/search_places.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "place_id": {"type": "string"},
                    "start_at": {"type": "string", "description": "ISO 8601 datetime, e.g. 2026-08-10T14:00:00-03:00."},
                    "end_at": {"type": "string", "description": "ISO 8601 datetime."},
                    "service": {"type": "string"},
                },
                "required": ["contact_id", "place_id", "start_at", "end_at", "service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_cancel_schedule",
            "description": "Propose cancelling a single dated occurrence of an appointment or recurring class (not the whole series). Requires explicit instructor confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_type": {"type": "string", "enum": ["appointment", "recurring_slot"]},
                    "target_id": {"type": "string"},
                    "occurrence_date": {"type": "string", "description": "ISO date of the specific occurrence to cancel."},
                },
                "required": ["target_type", "target_id", "occurrence_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_reschedule_occurrence",
            "description": "Propose moving a single dated occurrence of an appointment or recurring class to a new time (and optionally place). Requires explicit instructor confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_type": {"type": "string", "enum": ["appointment", "recurring_slot"]},
                    "target_id": {"type": "string"},
                    "occurrence_date": {"type": "string", "description": "ISO date of the specific occurrence to reschedule."},
                    "new_start_at": {"type": "string", "description": "ISO 8601 datetime."},
                    "new_end_at": {"type": "string", "description": "ISO 8601 datetime."},
                    "new_place_id": {"type": "string", "description": "Optional — omit to keep the same place."},
                },
                "required": ["target_type", "target_id", "occurrence_date", "new_start_at", "new_end_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_add_appointment_participant",
            "description": "Propose adding a contact to a one-off appointment, turning it into a group session (e.g. 'add Larissa to Leandro's class tomorrow at 15h'). Use the appointment_id from get_schedule's occurrences where source_type is 'appointment'. Requires explicit instructor confirmation before it takes effect.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "appointment_id": {"type": "string", "description": "The appointment's source_id from get_schedule, where source_type == 'appointment'."},
                },
                "required": ["contact_id", "appointment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_remove_appointment_participant",
            "description": "Propose removing a contact previously added to a one-off appointment (not the primary contact it was created for). Requires explicit instructor confirmation before it takes effect.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "appointment_id": {"type": "string"},
                },
                "required": ["contact_id", "appointment_id"],
            },
        },
    },
]

MUTATION_TOOL_DISPATCH: dict[str, Callable[..., dict[str, Any]]] = {
    "propose_add_group_member": propose_add_group_member,
    "propose_remove_group_member": propose_remove_group_member,
    "propose_update_contact": propose_update_contact,
    "propose_create_appointment": propose_create_appointment,
    "propose_cancel_schedule": propose_cancel_schedule,
    "propose_reschedule_occurrence": propose_reschedule_occurrence,
    "propose_add_appointment_participant": propose_add_appointment_participant,
    "propose_remove_appointment_participant": propose_remove_appointment_participant,
}

candidates.MUTATION_EXECUTORS["propose_add_group_member"] = _execute_add_group_member
candidates.MUTATION_EXECUTORS["propose_remove_group_member"] = _execute_remove_group_member
candidates.MUTATION_EXECUTORS[
    "propose_add_appointment_participant"
] = _execute_add_appointment_participant
candidates.MUTATION_EXECUTORS[
    "propose_remove_appointment_participant"
] = _execute_remove_appointment_participant
candidates.MUTATION_EXECUTORS["propose_update_contact"] = _execute_update_contact
candidates.MUTATION_EXECUTORS["propose_create_appointment"] = _execute_create_appointment
candidates.MUTATION_EXECUTORS["propose_cancel_schedule"] = _execute_cancel_schedule
candidates.MUTATION_EXECUTORS["propose_reschedule_occurrence"] = _execute_reschedule_occurrence

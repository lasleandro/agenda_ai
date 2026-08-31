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
from datetime import date, datetime, time
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agent import candidates
from app.agent.candidates import ExecutionResult
from app.models import (
    Appointment,
    AppointmentParticipant,
    Contact,
    InstructorEvent,
    MakeupClassCredit,
    OperatorActionCandidate,
    Place,
    RecurringSlot,
    RecurringSlotOccurrenceParticipant,
    RecurringSlotParticipant,
    WaitlistEntry,
)
from app.services import (
    appointment_participants,
    appointments,
    participants,
    occurrence_class_formats,
    recurring_slot_occurrence_participants,
    schedule_overrides,
)
from app.services.schedule_conflicts import assert_no_scheduled_class_overlap
from app.services import instructor_events as instructor_events_service
from app.services.place_stays import resolve_place_stay
from app.services import waitlist as waitlist_service
from app.services.contacts import apply_contact_updates
from app.services.makeup_credits import grant_credit_if_eligible
from app.services.operational_events import record_event
from app.services.scheduling import TIMEZONE

VALID_TARGET_TYPES = ("appointment", "recurring_slot")
VALID_BILLING_TYPES = ("billable", "courtesy")


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
    channel: str = "web",
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
        channel=channel,
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
    channel: str = "web",
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
        channel=channel,
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
# propose_add_group_occurrence_participant
# ---------------------------------------------------------------------------

def propose_add_group_occurrence_participant(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
    *,
    contact_id: str,
    recurring_slot_id: str,
    occurrence_date: str,
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
    if slot.slot_kind != "class" or slot.class_type != "group":
        return {"error": "Dated participants can only be assigned to a recurring group"}
    parsed_date = date.fromisoformat(occurrence_date)
    is_permanent = (
        db.query(RecurringSlotParticipant)
        .filter(
            RecurringSlotParticipant.recurring_slot_id == slot.id,
            RecurringSlotParticipant.contact_id == contact.id,
        )
        .first()
        is not None
    )
    if is_permanent:
        return {"error": "Contact is already a permanent participant"}
    existing = (
        db.query(RecurringSlotOccurrenceParticipant)
        .filter(
            RecurringSlotOccurrenceParticipant.recurring_slot_id == slot.id,
            RecurringSlotOccurrenceParticipant.contact_id == contact.id,
            RecurringSlotOccurrenceParticipant.occurrence_date == parsed_date,
        )
        .first()
    )
    if existing is not None:
        return {"error": "Contact is already in this occurrence"}
    if (
        recurring_slot_occurrence_participants.count_participants(
            db, slot.id, parsed_date
        )
        >= slot.max_participants
    ):
        return {"error": "This occurrence is at full capacity"}

    place_name = _place_name(db, slot.place_id)
    preview_text = (
        f"Adicionar {contact.display_name} somente à aula de {_group_label(slot)} "
        f"em {parsed_date.strftime('%d/%m/%Y')} ({place_name}). "
        "A participação permanente no grupo não será alterada."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_add_group_occurrence_participant",
        arguments={
            "contact_id": contact_id,
            "recurring_slot_id": recurring_slot_id,
            "occurrence_date": occurrence_date,
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": contact_id, "label": contact.display_name},
            {"entity_type": "recurring_slot", "entity_id": recurring_slot_id, "label": _group_label(slot)},
        ],
        correlation_id=correlation_id,
        channel=channel,
    )
    return _pending_result(candidate)


def _execute_add_group_occurrence_participant(
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
    parsed_date = date.fromisoformat(args["occurrence_date"])
    try:
        schedule_overrides.get_target_occurrence(
            db, professional_id, "recurring_slot", slot.id, parsed_date
        )
        participant = recurring_slot_occurrence_participants.add_participant(
            db, professional_id, slot, contact, parsed_date
        )
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from exc
    record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.participant.added",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="recurring_slot",
        entity_id=slot.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={
            "contact_id": str(contact.id),
            "participant_id": str(participant.id),
            "occurrence_date": args["occurrence_date"],
            "scope": "occurrence",
        },
        before_state=None,
        after_state={"contact_id": str(contact.id)},
    )
    return ExecutionResult(
        ok=True,
        summary=(
            f"{contact.display_name} adicionado(a) somente à aula de "
            f"{args['occurrence_date']}."
        ),
    )


# ---------------------------------------------------------------------------
# propose_remove_group_occurrence_participant
# ---------------------------------------------------------------------------

def propose_remove_group_occurrence_participant(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
    *,
    contact_id: str,
    recurring_slot_id: str,
    occurrence_date: str,
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
    if slot.slot_kind != "class" or slot.class_type != "group":
        return {"error": "Dated participants can only be removed from a recurring group"}
    parsed_date = date.fromisoformat(occurrence_date)
    is_permanent = (
        db.query(RecurringSlotParticipant)
        .filter(
            RecurringSlotParticipant.recurring_slot_id == slot.id,
            RecurringSlotParticipant.contact_id == contact.id,
        )
        .first()
        is not None
    )
    if is_permanent:
        return {
            "error": (
                "Contact is a permanent participant of this group. For a one-date "
                "absence use propose_note_participant_absence; to remove them from "
                "the whole series use propose_remove_group_member."
            )
        }
    try:
        schedule_overrides.get_target_occurrence(
            db, professional_id, "recurring_slot", slot.id, parsed_date
        )
    except HTTPException as exc:
        return {"error": exc.detail}
    existing = (
        db.query(RecurringSlotOccurrenceParticipant)
        .filter(
            RecurringSlotOccurrenceParticipant.recurring_slot_id == slot.id,
            RecurringSlotOccurrenceParticipant.contact_id == contact.id,
            RecurringSlotOccurrenceParticipant.occurrence_date == parsed_date,
        )
        .first()
    )
    if existing is None:
        return {"error": "Contact is not a dated participant of this occurrence"}

    place_name = _place_name(db, slot.place_id)
    preview_text = (
        f"Remover {contact.display_name} somente da turma de {_group_label(slot)} "
        f"em {parsed_date.strftime('%d/%m/%Y')} ({place_name}). "
        "A turma fixa e os demais alunos não serão alterados."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_remove_group_occurrence_participant",
        arguments={
            "contact_id": contact_id,
            "recurring_slot_id": recurring_slot_id,
            "occurrence_date": occurrence_date,
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": contact_id, "label": contact.display_name},
            {"entity_type": "recurring_slot", "entity_id": recurring_slot_id, "label": _group_label(slot)},
        ],
        correlation_id=correlation_id,
        channel=channel,
    )
    return _pending_result(candidate)


def _execute_remove_group_occurrence_participant(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    contact_id = uuid.UUID(args["contact_id"])
    slot_id = uuid.UUID(args["recurring_slot_id"])
    parsed_date = date.fromisoformat(args["occurrence_date"])

    contact = (
        db.query(Contact)
        .filter(Contact.id == contact_id, Contact.professional_id == professional_id)
        .first()
    )
    slot = (
        db.query(RecurringSlot)
        .filter(RecurringSlot.id == slot_id, RecurringSlot.professional_id == professional_id)
        .first()
    )
    if contact is None or slot is None:
        raise ValueError("Contact or group no longer exists")

    try:
        schedule_overrides.get_target_occurrence(
            db, professional_id, "recurring_slot", slot.id, parsed_date
        )
        recurring_slot_occurrence_participants.remove_participant(
            db, slot.id, contact.id, parsed_date
        )
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from exc

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
        payload={
            "contact_id": str(contact.id),
            "occurrence_date": args["occurrence_date"],
            "scope": "occurrence",
        },
        before_state={"contact_id": str(contact.id)},
        after_state=None,
    )
    return ExecutionResult(
        ok=True,
        summary=(
            f"{contact.display_name} removido(a) somente da aula de "
            f"{args['occurrence_date']}."
        ),
    )


# ---------------------------------------------------------------------------
# propose_create_group_slot
# ---------------------------------------------------------------------------

def propose_create_group_slot(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
    *,
    place_id: str,
    start_at: str,
    end_at: str,
    is_recurring: bool,
    max_participants: int = 4,
    label: str | None = None,
) -> dict[str, Any]:
    try:
        parsed_start = _parse_datetime(start_at).astimezone(TIMEZONE)
        parsed_end = _parse_datetime(end_at).astimezone(TIMEZONE)
        parsed_place_id = uuid.UUID(place_id)
    except ValueError:
        return {"error": "place_id and times must be valid"}
    if parsed_end <= parsed_start or parsed_end.date() != parsed_start.date():
        return {"error": "Group slot must end after it starts on the same date"}
    if not 1 <= max_participants <= 4:
        return {"error": "Participant capacity must be between 1 and 4"}
    place = (
        db.query(Place)
        .filter(Place.id == parsed_place_id, Place.professional_id == professional_id)
        .first()
    )
    if place is None:
        return {"error": "Place not found"}
    try:
        assert_no_scheduled_class_overlap(
            db,
            professional_id,
            parsed_start.weekday(),
            parsed_start.time().replace(tzinfo=None),
            parsed_end.time().replace(tzinfo=None),
            "weekly" if is_recurring else "once",
            None if is_recurring else parsed_start.date(),
        )
    except HTTPException as exc:
        return {"error": exc.detail}

    recurrence_label = "semanal" if is_recurring else "avulsa"
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_create_group_slot",
        arguments={
            "place_id": place_id,
            "start_at": start_at,
            "end_at": end_at,
            "is_recurring": is_recurring,
            "max_participants": max_participants,
            "label": label,
        },
        preview_text=(
            f"Abrir turma {recurrence_label} em {place.name}, "
            f"{parsed_start.strftime('%d/%m %H:%M')}–{parsed_end.strftime('%H:%M')}, "
            f"com 0/{max_participants} alunos."
        ),
        affected_entities=[{"entity_type": "place", "entity_id": place_id, "label": place.name}],
        correlation_id=correlation_id,
        channel=channel,
    )
    return _pending_result(candidate)


def _execute_create_group_slot(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    try:
        parsed_start = _parse_datetime(args["start_at"]).astimezone(TIMEZONE)
        parsed_end = _parse_datetime(args["end_at"]).astimezone(TIMEZONE)
        place_id = uuid.UUID(args["place_id"])
    except ValueError as exc:
        raise ValueError("Group slot details are no longer valid") from exc
    place = (
        db.query(Place)
        .filter(Place.id == place_id, Place.professional_id == professional_id)
        .first()
    )
    if place is None:
        raise ValueError("Place no longer exists")
    recurrence_type = "weekly" if args["is_recurring"] else "once"
    try:
        assert_no_scheduled_class_overlap(
            db,
            professional_id,
            parsed_start.weekday(),
            parsed_start.time().replace(tzinfo=None),
            parsed_end.time().replace(tzinfo=None),
            recurrence_type,
            None if args["is_recurring"] else parsed_start.date(),
        )
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from exc
    slot = RecurringSlot(
        professional_id=professional_id,
        place_id=place.id,
        day_of_week=parsed_start.weekday(),
        start_time=parsed_start.time().replace(tzinfo=None),
        end_time=parsed_end.time().replace(tzinfo=None),
        label=args.get("label"),
        class_type="group",
        slot_kind="class",
        max_participants=args["max_participants"],
        recurrence_type=recurrence_type,
        scheduled_date=None if args["is_recurring"] else parsed_start.date(),
        valid_from=parsed_start.date() if args["is_recurring"] else None,
    )
    db.add(slot)
    db.flush()
    record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.series.created",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="recurring_slot",
        entity_id=slot.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"class_type": "group", "max_participants": slot.max_participants},
        before_state=None,
        after_state={"participant_count": 0},
    )
    return ExecutionResult(ok=True, summary=f"Turma aberta em {place.name} com 0/{slot.max_participants} alunos.")


# ---------------------------------------------------------------------------
# propose_add_appointment_participant / propose_remove_appointment_participant
# ---------------------------------------------------------------------------

def _appointment_label(db: Session, appointment: Appointment) -> str:
    primary = db.query(Contact).filter(Contact.id == appointment.contact_id).first()
    primary_name = primary.display_name if primary else "Desconhecido"
    local_start = appointment.start_at.astimezone(TIMEZONE)
    return f"{appointment.service} de {primary_name} em {local_start.strftime('%d/%m/%Y %H:%M')}"


def propose_set_appointment_format(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
    *,
    appointment_id: str,
    class_type: str,
    max_participants: int,
) -> dict[str, Any]:
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
    if class_type not in {"individual", "group"}:
        return {"error": "Class type must be individual or group"}
    if not isinstance(max_participants, int) or not 1 <= max_participants <= 4:
        return {"error": "Participant capacity must be between 1 and 4"}

    participant_count = appointment_participants.count_participants(db, appointment.id)
    if class_type == "individual" and max_participants != 1:
        return {"error": "An individual class has capacity for one participant"}
    if class_type == "individual" and participant_count != 1:
        return {"error": "Remove additional participants before converting to individual"}
    if participant_count > max_participants:
        return {"error": "Configured capacity cannot be below the current participants"}
    if (
        appointment.class_type == class_type
        and appointment.max_participants == max_participants
    ):
        return {"error": "Appointment already has this format and capacity"}

    label = _appointment_label(db, appointment)
    format_label = "grupo" if class_type == "group" else "individual"
    preview_text = (
        f"Alterar a aula ({label}) para {format_label} "
        f"com capacidade para {max_participants} aluno(s)."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_set_appointment_format",
        arguments={
            "appointment_id": appointment_id,
            "class_type": class_type,
            "max_participants": max_participants,
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "appointment", "entity_id": appointment_id, "label": label},
        ],
        correlation_id=correlation_id,
        channel=channel,
    )
    return _pending_result(candidate)


def _execute_set_appointment_format(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.id == uuid.UUID(args["appointment_id"]),
            Appointment.professional_id == professional_id,
        )
        .first()
    )
    if appointment is None:
        raise ValueError("Appointment no longer exists")

    before_state = {
        "class_type": appointment.class_type,
        "max_participants": appointment.max_participants,
    }
    try:
        appointments.update_appointment_format(
            db,
            appointment,
            class_type=args["class_type"],
            max_participants=args["max_participants"],
        )
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from exc

    after_state = {
        "class_type": appointment.class_type,
        "max_participants": appointment.max_participants,
    }
    record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.appointment.updated",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="appointment",
        entity_id=appointment.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"operation": "class_format_updated"},
        before_state=before_state,
        after_state=after_state,
    )
    return ExecutionResult(
        ok=True,
        summary=f"Formato da aula atualizado: {_appointment_label(db, appointment)}.",
    )


def propose_set_occurrence_class_format(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
    *,
    target_type: str,
    target_id: str,
    occurrence_date: str,
    class_type: str,
    max_participants: int,
) -> dict[str, Any]:
    if target_type not in VALID_TARGET_TYPES:
        return {"error": "target_type must be appointment or recurring_slot"}
    try:
        parsed_date = date.fromisoformat(occurrence_date)
        target_uuid = uuid.UUID(target_id)
    except ValueError:
        return {"error": "target_id and occurrence_date must be valid"}
    try:
        occurrence = schedule_overrides.get_target_occurrence(
            db, professional_id, target_type, target_uuid, parsed_date
        )
        occurrence_class_formats.validate_format(
            class_type=class_type,
            max_participants=max_participants,
            participant_count=occurrence.participant_count,
        )
    except HTTPException as exc:
        return {"error": exc.detail}
    format_label = "grupo" if class_type == "group" else "individual"
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_set_occurrence_class_format",
        arguments={
            "target_type": target_type,
            "target_id": target_id,
            "occurrence_date": occurrence_date,
            "class_type": class_type,
            "max_participants": max_participants,
        },
        preview_text=(
            f"Alterar somente a aula de {parsed_date.strftime('%d/%m/%Y')} para "
            f"{format_label}, com capacidade para {max_participants} aluno(s)."
        ),
        affected_entities=[{"entity_type": target_type, "entity_id": target_id, "label": occurrence.source_label}],
        correlation_id=correlation_id,
        channel=channel,
    )
    return _pending_result(candidate)


def _execute_set_occurrence_class_format(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    target_id = uuid.UUID(args["target_id"])
    parsed_date = date.fromisoformat(args["occurrence_date"])
    try:
        occurrence = schedule_overrides.get_target_occurrence(
            db, professional_id, args["target_type"], target_id, parsed_date
        )
        before_state = {
            "class_type": occurrence.class_type,
            "max_participants": occurrence.max_participants,
        }
        occurrence_class_formats.set_format(
            db,
            professional_id,
            source_type=args["target_type"],
            source_id=target_id,
            occurrence_date=parsed_date,
            class_type=args["class_type"],
            max_participants=args["max_participants"],
            participant_count=occurrence.participant_count,
            actor_user_id=candidate.actor_user_id,
            source=candidate.channel,
        )
        updated = schedule_overrides.get_target_occurrence(
            db, professional_id, args["target_type"], target_id, parsed_date
        )
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from exc
    record_event(
        db,
        professional_id=professional_id,
        event_type=(
            "schedule.appointment.updated"
            if args["target_type"] == "appointment"
            else "schedule.series.updated"
        ),
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type=args["target_type"],
        entity_id=target_id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"operation": "occurrence_class_format_updated", "occurrence_date": args["occurrence_date"]},
        before_state=before_state,
        after_state={"class_type": updated.class_type, "max_participants": updated.max_participants},
    )
    return ExecutionResult(ok=True, summary=f"Formato alterado somente para {args['occurrence_date']}.")


def propose_add_appointment_participant(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
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
    capacity = (
        appointment.max_participants
        if appointment.class_type == "group"
        else appointment_participants.DEFAULT_GROUP_MAX_PARTICIPANTS
    )
    if appointment_participants.count_participants(db, appointment.id) >= capacity:
        return {"error": "This appointment is at full capacity"}

    label = _appointment_label(db, appointment)
    class_type_transition = (
        {"from": "individual", "to": "group"}
        if appointment.class_type == "individual"
        else None
    )
    preview_text = f"Adicionar {contact.display_name} à aula ({label})."
    if class_type_transition:
        preview_text += " O formato mudará de individual para grupo."
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_add_appointment_participant",
        arguments={
            "contact_id": contact_id,
            "appointment_id": appointment_id,
            "class_type_transition": class_type_transition,
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": contact_id, "label": contact.display_name},
            {"entity_type": "appointment", "entity_id": appointment_id, "label": label},
        ],
        correlation_id=correlation_id,
        channel=channel,
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

    before_class_type = appointment.class_type
    format_changed = appointment_participants.add_participant(
        db, professional_id, appointment, contact
    )
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
        payload={"contact_id": str(contact.id), "class_type_changed": format_changed},
        before_state={"class_type": before_class_type},
        after_state={"class_type": appointment.class_type, "contact_id": str(contact.id)},
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
    channel: str = "web",
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
        arguments={
            "contact_id": contact_id,
            "appointment_id": appointment_id,
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": contact_id, "label": contact.display_name},
            {"entity_type": "appointment", "entity_id": appointment_id, "label": label},
        ],
        correlation_id=correlation_id,
        channel=channel,
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
    before_class_type = appointment.class_type
    format_changed = appointment_participants.remove_participant(
        db, appointment.id, contact.id
    )
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
        payload={"contact_id": str(contact.id), "class_type_changed": format_changed},
        before_state={"contact_id": str(contact.id), "class_type": before_class_type},
        after_state={"class_type": appointment.class_type},
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
    channel: str = "web",
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
        channel=channel,
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
    channel: str = "web",
    *,
    contact_id: str,
    place_id: str | None = None,
    start_at: str,
    end_at: str,
    service: str,
    contact_ids: list[str] | None = None,
    class_type: str = "individual",
    billing_type: str = "billable",
    is_recurring: bool = False,
    idempotency_key: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    participant_ids = contact_ids or [contact_id]
    if len(participant_ids) > 4 or len(participant_ids) != len(set(participant_ids)):
        return {"error": "A group must contain one to four unique contacts"}
    if contact_id not in participant_ids:
        return {"error": "contact_id must be included in contact_ids"}
    if class_type not in ("individual", "group"):
        return {"error": "class_type must be individual or group"}
    if class_type == "individual" and len(participant_ids) != 1:
        return {"error": "An individual class must have one contact"}

    contacts = (
        db.query(Contact)
        .filter(
            Contact.id.in_([uuid.UUID(item) for item in participant_ids]),
            Contact.professional_id == professional_id,
        )
        .all()
    )
    if len(contacts) != len(participant_ids):
        return {"error": "One or more contacts were not found"}
    contacts_by_id = {str(contact.id): contact for contact in contacts}
    contact = contacts_by_id[contact_id]

    if billing_type not in VALID_BILLING_TYPES:
        return {"error": f"billing_type must be one of {VALID_BILLING_TYPES}"}

    parsed_start = _parse_datetime(start_at)
    parsed_end = _parse_datetime(end_at)
    if parsed_end <= parsed_start:
        return {"error": "end_at must be after start_at"}

    try:
        requested_place_id = uuid.UUID(place_id) if place_id else None
    except ValueError:
        return {"error": "place_id must be a valid UUID"}
    place_resolution = resolve_place_stay(
        db,
        professional_id,
        start_at=parsed_start,
        end_at=parsed_end,
        requested_place_id=requested_place_id,
    )
    if place_resolution.outcome == "invalid_place":
        return {"error": "Place not found"}
    if place_resolution.place_id is None:
        return {"error": "Select a place: this time has no unique covering place stay"}
    place = (
        db.query(Place)
        .filter(Place.id == place_resolution.place_id, Place.professional_id == professional_id)
        .one()
    )

    try:
        appointments.assert_no_conflict(
            db, professional_id, start_at=parsed_start, end_at=parsed_end
        )
    except HTTPException as exc:
        return {"error": exc.detail}

    local_start = parsed_start.astimezone(TIMEZONE)
    courtesy_label = " (Cortesia)" if billing_type == "courtesy" else ""
    participant_label = ", ".join(
        contacts_by_id[participant_id].display_name for participant_id in participant_ids
    )
    place_context = (
        "local inferido pela permanência"
        if place_resolution.stay_id is not None
        else "local informado como exceção"
    )
    weekday_name = WEEKDAY_NAMES[local_start.weekday()]
    if is_recurring:
        preview_text = (
            f"Criar aula {class_type} semanal de {service.strip()} para {participant_label}, "
            f"toda {weekday_name}, {local_start.strftime('%H:%M')}–{parsed_end.astimezone(TIMEZONE).strftime('%H:%M')}, "
            f"{place.name} ({place_context}){courtesy_label}."
        )
    else:
        preview_text = (
            f"Criar aula {class_type} de {service.strip()} para {participant_label} em "
            f"{local_start.strftime('%d/%m/%Y %H:%M')}, {place.name} "
            f"({place_context}){courtesy_label}."
        )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_create_appointment",
        arguments={
            "contact_id": contact_id,
            "contact_ids": participant_ids,
            "class_type": class_type,
            "place_id": str(place_resolution.place_id),
            "requested_place_id": place_id,
            "start_at": parsed_start.isoformat(),
            "end_at": parsed_end.isoformat(),
            "service": service,
            "billing_type": billing_type,
            "is_recurring": is_recurring,
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": contact_id, "label": contact.display_name},
            {
                "entity_type": "place",
                "entity_id": str(place_resolution.place_id),
                "label": place.name,
            },
        ],
        correlation_id=correlation_id,
        channel=channel,
        idempotency_key=idempotency_key,
        commit=commit,
    )
    return _pending_result(candidate)


def _execute_create_appointment(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    participant_ids = args.get("contact_ids") or [args["contact_id"]]
    contacts = (
        db.query(Contact)
        .filter(
            Contact.id.in_([uuid.UUID(contact_id) for contact_id in participant_ids]),
            Contact.professional_id == professional_id,
        )
        .all()
    )
    if len(contacts) != len(participant_ids):
        raise ValueError("One or more contacts no longer exist")
    contacts_by_id = {str(contact.id): contact for contact in contacts}
    appointment = appointments.create_appointment(
        db,
        professional_id,
        contact_id=uuid.UUID(args["contact_id"]),
        place_id=(
            uuid.UUID(args["requested_place_id"])
            if args.get("requested_place_id")
            else None
        ),
        service=args["service"],
        start_at=_parse_datetime(args["start_at"]),
        end_at=_parse_datetime(args["end_at"]),
        is_recurring=args.get("is_recurring", False),
        class_type=args.get("class_type", "individual"),
        source="assistant",
        actor=f"user:{candidate.actor_user_id}",
    )
    billing_type = args.get("billing_type", "billable")
    if billing_type not in VALID_BILLING_TYPES:
        billing_type = "billable"
    if billing_type == "courtesy":
        appointment.billing_type = "courtesy"
    for participant_id in participant_ids:
        if participant_id != args["contact_id"]:
            appointment_participants.add_participant(
                db,
                professional_id,
                appointment,
                contacts_by_id[participant_id],
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
        payload={
            "contact_ids": participant_ids,
            "class_type": args.get("class_type", "individual"),
            "is_recurring": args.get("is_recurring", False),
            "recurrence_rule": appointment.recurrence_rule,
            "requested_place_id": args.get("requested_place_id"),
            "resolved_place_id": str(appointment.place_id),
        },
        before_state=None,
        after_state={"status": appointment.status},
    )
    return ExecutionResult(ok=True, summary=f"Atendimento criado para {args['start_at']}.")


# ---------------------------------------------------------------------------
# propose_redeem_makeup_credit
# ---------------------------------------------------------------------------

def propose_redeem_makeup_credit(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
    *,
    credit_id: str,
    place_id: str,
    start_at: str,
    end_at: str,
) -> dict[str, Any]:
    credit = (
        db.query(MakeupClassCredit)
        .filter(
            MakeupClassCredit.id == uuid.UUID(credit_id),
            MakeupClassCredit.professional_id == professional_id,
        )
        .first()
    )
    if credit is None:
        return {"error": "Crédito de reposição não encontrado"}
    if credit.status != "available":
        return {
            "error": f"Este crédito não está disponível (status: {credit.status})"
        }

    contact = (
        db.query(Contact)
        .filter(
            Contact.id == credit.contact_id,
            Contact.professional_id == professional_id,
        )
        .first()
    )
    if contact is None:
        return {"error": "Contato não encontrado"}

    place = (
        db.query(Place)
        .filter(Place.id == uuid.UUID(place_id), Place.professional_id == professional_id)
        .first()
    )
    if place is None:
        return {"error": "Local não encontrado"}

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
        f"Agendar reposição para {contact.display_name} em "
        f"{local_start.strftime('%d/%m/%Y %H:%M')}, {place.name}."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_redeem_makeup_credit",
        arguments={
            "credit_id": credit_id,
            "place_id": place_id,
            "start_at": parsed_start.isoformat(),
            "end_at": parsed_end.isoformat(),
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": str(contact.id), "label": contact.display_name},
            {"entity_type": "place", "entity_id": place_id, "label": place.name},
            {"entity_type": "makeup_credit", "entity_id": credit_id, "label": f"Crédito {credit.origin_occurrence_date.isoformat()}"},
        ],
        correlation_id=correlation_id,
        channel=channel,
    )
    return _pending_result(candidate)


def _execute_redeem_makeup_credit(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    credit_id = uuid.UUID(args["credit_id"])

    credit = (
        db.query(MakeupClassCredit)
        .filter(
            MakeupClassCredit.id == credit_id,
            MakeupClassCredit.professional_id == professional_id,
        )
        .first()
    )
    if credit is None:
        raise HTTPException(status_code=404, detail="Crédito de reposição não encontrado")
    if credit.status != "available":
        raise HTTPException(
            status_code=409,
            detail=f"Este crédito não está disponível (status: {credit.status})",
        )

    appointment = appointments.create_appointment(
        db,
        professional_id,
        contact_id=credit.contact_id,
        place_id=uuid.UUID(args["place_id"]),
        service=f"Reposição — {credit.origin_occurrence_date.isoformat()}",
        start_at=_parse_datetime(args["start_at"]),
        end_at=_parse_datetime(args["end_at"]),
        source="assistant",
        actor=f"user:{candidate.actor_user_id}",
        billing_type="courtesy",
    )

    now = datetime.now(TIMEZONE)
    credit.status = "redeemed"
    credit.redeemed_at = now
    credit.redeemed_appointment_id = appointment.id

    record_event(
        db,
        professional_id=professional_id,
        event_type="makeup_credit.redeemed",
        occurred_at=now,
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="makeup_class_credit",
        entity_id=credit.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={
            "redeemed_appointment_id": str(appointment.id),
            "start_at": args["start_at"],
            "end_at": args["end_at"],
        },
        before_state={"status": "available"},
        after_state={"status": "redeemed"},
    )

    return ExecutionResult(
        ok=True,
        summary=f"Reposição agendada para {args['start_at']} e crédito resgatado.",
    )


# ---------------------------------------------------------------------------
# propose_cancel_schedule
# ---------------------------------------------------------------------------

def propose_cancel_schedule(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
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
        channel=channel,
    )
    return _pending_result(candidate)


def _execute_cancel_schedule(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    target_id = uuid.UUID(args["target_id"])
    parsed_date = date.fromisoformat(args["occurrence_date"])

    # Snapshot the occurrence's starts_at before cancelling — after the
    # cancel, get_target_occurrence won't find it anymore, but we need the
    # timestamp for credit-eligibility checks.
    occurrence = schedule_overrides.get_target_occurrence(
        db, professional_id, args["target_type"], target_id, parsed_date
    )

    schedule_overrides.cancel_occurrence(
        db,
        professional_id,
        target_type=args["target_type"],
        target_id=target_id,
        occurrence_date=parsed_date,
        actor_user_id=candidate.actor_user_id,
    )
    cancelled_at = datetime.now(TIMEZONE)
    event = record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.occurrence.cancelled",
        occurred_at=cancelled_at,
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

    # Grant make-up credits to recurring participants when eligible.
    if args["target_type"] == "recurring_slot":
        participants = (
            db.query(RecurringSlotParticipant)
            .filter(RecurringSlotParticipant.recurring_slot_id == target_id)
            .all()
        )
        for participant in participants:
            grant_credit_if_eligible(
                db,
                professional_id=professional_id,
                contact_id=participant.contact_id,
                recurring_slot_id=target_id,
                origin_event_id=event.id,
                occurrence_date=parsed_date,
                occurrence_starts_at=occurrence.starts_at,
                cancelled_at=cancelled_at,
                correlation_id=candidate.correlation_id,
                actor_user_id=candidate.actor_user_id,
                source_channel=candidate.channel,
            )

    summary = f"Ocorrência de {args['occurrence_date']} cancelada."
    newly_matched = waitlist_service.mark_matches_for_date(db, professional_id, parsed_date)
    if newly_matched:
        names = ", ".join(
            db.query(Contact.display_name).filter(Contact.id == entry.contact_id).scalar()
            for entry in newly_matched
        )
        summary += f" {names} estava(m) na fila de espera e agora cabe(m) nesse horário."

    return ExecutionResult(ok=True, summary=summary)


# ---------------------------------------------------------------------------
# propose_note_participant_absence
# ---------------------------------------------------------------------------
#
# Distinct from propose_cancel_schedule: cancelling an occurrence removes it
# for every participant (correct when the whole class doesn't happen — rain,
# holiday, instructor illness). This tool is for the much more common group-
# class case where *one* student can't make it but the class still runs for
# everyone else — it never touches ScheduleOccurrenceOverride, so the
# occurrence stays exactly as scheduled; it only (subject to the same
# eligibility rules as a cancellation) grants that one student a make-up
# credit.

def propose_note_participant_absence(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
    *,
    contact_id: str,
    recurring_slot_id: str,
    occurrence_date: str,
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

    parsed_date = date.fromisoformat(occurrence_date)
    try:
        occurrence = schedule_overrides.get_target_occurrence(
            db, professional_id, "recurring_slot", slot.id, parsed_date
        )
    except HTTPException as exc:
        return {"error": exc.detail}

    place_name = _place_name(db, slot.place_id)
    preview_text = (
        f"Registrar falta de {contact.display_name} no {_group_label(slot)} "
        f"em {parsed_date.strftime('%d/%m/%Y')} ({_weekday_time_label(slot)}, "
        f"{place_name}) — a aula continua para o restante do grupo. Se dentro "
        f"do prazo de aviso configurado, gera crédito de reposição."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_note_participant_absence",
        arguments={
            "contact_id": contact_id,
            "recurring_slot_id": recurring_slot_id,
            "occurrence_date": occurrence_date,
        },
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
        channel=channel,
    )
    return _pending_result(candidate)


def _execute_note_participant_absence(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    contact_id = uuid.UUID(args["contact_id"])
    slot_id = uuid.UUID(args["recurring_slot_id"])
    parsed_date = date.fromisoformat(args["occurrence_date"])

    contact = (
        db.query(Contact)
        .filter(Contact.id == contact_id, Contact.professional_id == professional_id)
        .first()
    )
    slot = (
        db.query(RecurringSlot)
        .filter(RecurringSlot.id == slot_id, RecurringSlot.professional_id == professional_id)
        .first()
    )
    if contact is None or slot is None:
        raise ValueError("Contact or group no longer exists")

    occurrence = schedule_overrides.get_target_occurrence(
        db, professional_id, "recurring_slot", slot_id, parsed_date
    )

    noted_at = datetime.now(TIMEZONE)
    event = record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.participant.absence_noted",
        occurred_at=noted_at,
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="recurring_slot",
        entity_id=slot_id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"contact_id": args["contact_id"], "occurrence_date": args["occurrence_date"]},
        before_state=None,
        after_state={"contact_id": args["contact_id"], "attendance": "absent"},
    )

    credit = grant_credit_if_eligible(
        db,
        professional_id=professional_id,
        contact_id=contact_id,
        recurring_slot_id=slot_id,
        origin_event_id=event.id,
        occurrence_date=parsed_date,
        occurrence_starts_at=occurrence.starts_at,
        cancelled_at=noted_at,
        correlation_id=candidate.correlation_id,
        actor_user_id=candidate.actor_user_id,
        source_channel=candidate.channel,
    )

    summary = f"Falta de {contact.display_name} registrada em {args['occurrence_date']}."
    summary += (
        " Crédito de reposição gerado."
        if credit is not None
        else " Sem crédito de reposição (fora do prazo de aviso ou limite atingido)."
    )
    return ExecutionResult(ok=True, summary=summary)


# ---------------------------------------------------------------------------
# propose_reschedule_occurrence
# ---------------------------------------------------------------------------

def propose_reschedule_occurrence(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
    *,
    target_type: str,
    target_id: str,
    occurrence_date: str,
    new_start_at: str,
    new_end_at: str,
    new_place_id: str | None = None,
    idempotency_key: str | None = None,
    commit: bool = True,
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
        requested_place_id = uuid.UUID(new_place_id) if new_place_id else None
    except ValueError:
        return {"error": "new_place_id must be a valid UUID"}

    place_resolution = resolve_place_stay(
        db,
        professional_id,
        start_at=parsed_new_start,
        end_at=parsed_new_end,
        requested_place_id=requested_place_id,
    )
    if place_resolution.outcome == "invalid_place":
        return {"error": "Place not found"}
    if place_resolution.place_id is None:
        return {"error": "Select a place: this time has no unique covering place stay"}

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

    effective_place_id = str(place_resolution.place_id)
    new_place_name = _place_name(db, place_resolution.place_id)

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
            "new_place_id": effective_place_id,
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": target_type, "entity_id": target_id, "label": occurrence.source_label}
        ],
        correlation_id=correlation_id,
        channel=channel,
        idempotency_key=idempotency_key,
        commit=commit,
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
# propose_add_waitlist_entry / propose_remove_waitlist_entry
# (waitlist roadmap v0.1, Phase 1 — "Fila de Espera")
# ---------------------------------------------------------------------------

def propose_add_waitlist_entry(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
    *,
    contact_id: str,
    desired_date: str,
    desired_start_time: str,
    desired_end_time: str,
    place_id: str | None = None,
    class_type: str | None = None,
    duration_minutes: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    contact = (
        db.query(Contact)
        .filter(Contact.id == uuid.UUID(contact_id), Contact.professional_id == professional_id)
        .first()
    )
    if contact is None:
        return {"error": "Contact not found"}

    place_name = None
    if place_id is not None:
        place = (
            db.query(Place)
            .filter(Place.id == uuid.UUID(place_id), Place.professional_id == professional_id)
            .first()
        )
        if place is None:
            return {"error": "Place not found"}
        place_name = place.name

    parsed_start = time.fromisoformat(desired_start_time)
    parsed_end = time.fromisoformat(desired_end_time)
    if parsed_end <= parsed_start:
        return {"error": "desired_end_time must be after desired_start_time"}

    local_date = date.fromisoformat(desired_date)
    place_suffix = f", {place_name}" if place_name else ""
    preview_text = (
        f"Adicionar {contact.display_name} à fila de espera para "
        f"{local_date.strftime('%d/%m/%Y')} das {parsed_start.strftime('%H:%M')} "
        f"às {parsed_end.strftime('%H:%M')}{place_suffix}."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_add_waitlist_entry",
        arguments={
            "contact_id": contact_id,
            "place_id": place_id,
            "desired_date": desired_date,
            "desired_start_time": desired_start_time,
            "desired_end_time": desired_end_time,
            "class_type": class_type,
            "duration_minutes": duration_minutes,
            "note": note,
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": contact_id, "label": contact.display_name},
        ],
        correlation_id=correlation_id,
        channel=channel,
    )
    return _pending_result(candidate)


def _execute_add_waitlist_entry(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    try:
        entry = waitlist_service.create_entry(
            db,
            professional_id,
            contact_id=uuid.UUID(args["contact_id"]),
            place_id=uuid.UUID(args["place_id"]) if args.get("place_id") else None,
            desired_date=date.fromisoformat(args["desired_date"]),
            desired_start_time=time.fromisoformat(args["desired_start_time"]),
            desired_end_time=time.fromisoformat(args["desired_end_time"]),
            class_type=args.get("class_type"),
            duration_minutes=args.get("duration_minutes"),
            note=args.get("note"),
        )
    except waitlist_service.WaitlistValidationError as exc:
        raise ValueError(str(exc))

    record_event(
        db,
        professional_id=professional_id,
        event_type="waitlist.entry.added",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="waitlist_entry",
        entity_id=entry.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"contact_id": args["contact_id"], "desired_date": args["desired_date"]},
        before_state=None,
        after_state={"status": entry.status},
    )
    contact_name = db.query(Contact.display_name).filter(Contact.id == entry.contact_id).scalar()
    return ExecutionResult(
        ok=True,
        summary=f"{contact_name} adicionado(a) à fila de espera para {args['desired_date']}.",
    )


def propose_remove_waitlist_entry(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
    *,
    waitlist_entry_id: str,
) -> dict[str, Any]:
    entry = waitlist_service.get_entry(db, professional_id, uuid.UUID(waitlist_entry_id))
    if entry is None:
        return {"error": "Waitlist entry not found"}
    if entry.status not in ("open", "matched"):
        return {"error": f"Entry is not cancellable (status={entry.status})"}

    contact = db.query(Contact).filter(Contact.id == entry.contact_id).first()
    contact_name = contact.display_name if contact else "Desconhecido"
    preview_text = (
        f"Remover {contact_name} da fila de espera "
        f"({entry.desired_date.strftime('%d/%m/%Y')} das "
        f"{entry.desired_start_time.strftime('%H:%M')} às "
        f"{entry.desired_end_time.strftime('%H:%M')})."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_remove_waitlist_entry",
        arguments={"waitlist_entry_id": waitlist_entry_id},
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": str(entry.contact_id), "label": contact_name},
        ],
        correlation_id=correlation_id,
        channel=channel,
    )
    return _pending_result(candidate)


def _execute_remove_waitlist_entry(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    try:
        entry = waitlist_service.cancel_entry(
            db, professional_id, uuid.UUID(args["waitlist_entry_id"])
        )
    except waitlist_service.WaitlistValidationError as exc:
        raise ValueError(str(exc))

    record_event(
        db,
        professional_id=professional_id,
        event_type="waitlist.entry.cancelled",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="waitlist_entry",
        entity_id=entry.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"waitlist_entry_id": args["waitlist_entry_id"]},
        before_state={"status": "open"},
        after_state={"status": "cancelled"},
    )
    contact_name = db.query(Contact.display_name).filter(Contact.id == entry.contact_id).scalar()
    return ExecutionResult(ok=True, summary=f"{contact_name} removido(a) da fila de espera.")


# ---------------------------------------------------------------------------
# propose_fulfill_waitlist_with_appointment / _with_group
# (agent pt-BR conversational resilience roadmap v0.1, Phase 4)
# ---------------------------------------------------------------------------

def propose_fulfill_waitlist_with_appointment(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
    *,
    waitlist_entry_id: str,
    place_id: str,
    service: str = "Aula",
) -> dict[str, Any]:
    try:
        entry_uuid = uuid.UUID(waitlist_entry_id)
        place_uuid = uuid.UUID(place_id)
    except ValueError:
        return {"error": "waitlist_entry_id and place_id must be valid UUIDs"}

    entry = waitlist_service.get_entry(db, professional_id, entry_uuid)
    if entry is None:
        return {"error": "Waitlist entry not found"}
    if entry.status not in ("open", "matched"):
        return {"error": f"Entry is not fulfillable (status={entry.status})"}
    if entry.class_type == "group":
        return {
            "error": (
                "This waitlist entry expects a group class — use "
                "propose_fulfill_waitlist_with_group instead."
            )
        }

    place = (
        db.query(Place)
        .filter(Place.id == place_uuid, Place.professional_id == professional_id)
        .first()
    )
    if place is None:
        return {"error": "Place not found"}
    if entry.place_id is not None and entry.place_id != place_uuid:
        return {"error": "Selected place does not match the waitlist request"}

    contact = (
        db.query(Contact)
        .filter(Contact.id == entry.contact_id, Contact.professional_id == professional_id)
        .first()
    )
    if contact is None:
        return {"error": "Waitlist contact not found"}

    if not waitlist_service.entry_fits_free_time(db, professional_id, entry, place_uuid):
        return {"error": "The requested time is no longer free at this place"}

    start_at = datetime.combine(entry.desired_date, entry.desired_start_time, tzinfo=TIMEZONE)
    end_at = datetime.combine(entry.desired_date, entry.desired_end_time, tzinfo=TIMEZONE)
    try:
        appointments.assert_no_conflict(
            db, professional_id, start_at=start_at, end_at=end_at
        )
    except HTTPException as exc:
        return {"error": exc.detail}

    resolved_service = (service or "Aula").strip() or "Aula"
    preview_text = (
        f"Agendar {contact.display_name} em {place.name} em "
        f"{start_at.strftime('%d/%m/%Y %H:%M')}–{end_at.strftime('%H:%M')} "
        f"e concluir a solicitação da fila de espera."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_fulfill_waitlist_with_appointment",
        arguments={
            "waitlist_entry_id": waitlist_entry_id,
            "place_id": place_id,
            "service": resolved_service,
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": str(contact.id), "label": contact.display_name},
            {"entity_type": "place", "entity_id": place_id, "label": place.name},
            {
                "entity_type": "waitlist_entry",
                "entity_id": waitlist_entry_id,
                "label": contact.display_name,
            },
        ],
        correlation_id=correlation_id,
        channel=channel,
    )
    return _pending_result(candidate)


def _execute_fulfill_waitlist_with_appointment(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    entry_id = uuid.UUID(args["waitlist_entry_id"])
    place_id = uuid.UUID(args["place_id"])

    entry = waitlist_service.lock_entry(db, professional_id, entry_id)
    if entry is None:
        raise ValueError("Waitlist entry no longer exists")
    if entry.status not in ("open", "matched"):
        raise ValueError(f"Entry is not fulfillable (status={entry.status})")
    if entry.class_type == "group":
        raise ValueError("Waitlist entry expects a group class")
    if entry.place_id is not None and entry.place_id != place_id:
        raise ValueError("Selected place no longer matches the waitlist request")

    contact = (
        db.query(Contact)
        .filter(Contact.id == entry.contact_id, Contact.professional_id == professional_id)
        .first()
    )
    place = (
        db.query(Place)
        .filter(Place.id == place_id, Place.professional_id == professional_id)
        .first()
    )
    if contact is None or place is None:
        raise ValueError("Contact or place no longer exists")

    if not waitlist_service.entry_fits_free_time(db, professional_id, entry, place_id):
        raise ValueError("The requested time is no longer free at this place")

    start_at = datetime.combine(entry.desired_date, entry.desired_start_time, tzinfo=TIMEZONE)
    end_at = datetime.combine(entry.desired_date, entry.desired_end_time, tzinfo=TIMEZONE)
    appointment = appointments.create_appointment(
        db,
        professional_id,
        contact_id=entry.contact_id,
        place_id=place_id,
        service=args.get("service", "Aula"),
        start_at=start_at,
        end_at=end_at,
        class_type="individual",
        source="assistant",
        actor=f"user:{candidate.actor_user_id}",
    )
    waitlist_service.fulfill_entry(
        db, professional_id, entry_id, appointment.id, commit=False
    )

    now = datetime.now(TIMEZONE)
    record_event(
        db,
        professional_id=professional_id,
        event_type="schedule.appointment.created",
        occurred_at=now,
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="appointment",
        entity_id=appointment.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={
            "contact_id": str(contact.id),
            "class_type": "individual",
            "waitlist_entry_id": str(entry_id),
            "resolved_place_id": str(place_id),
        },
        before_state=None,
        after_state={"status": appointment.status},
    )
    record_event(
        db,
        professional_id=professional_id,
        event_type="waitlist.entry.fulfilled",
        occurred_at=now,
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="waitlist_entry",
        entity_id=entry.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={"fulfilled_appointment_id": str(appointment.id)},
        before_state={"status": "open"},
        after_state={"status": "fulfilled"},
    )
    return ExecutionResult(
        ok=True,
        summary=(
            f"{contact.display_name} agendado(a) em {place.name} em "
            f"{start_at.strftime('%d/%m/%Y %H:%M')} e solicitação da fila concluída."
        ),
    )


def propose_fulfill_waitlist_with_group(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
    *,
    waitlist_entry_id: str,
    recurring_slot_id: str,
    occurrence_date: str,
    enrollment_scope: str,
) -> dict[str, Any]:
    if enrollment_scope not in {"occurrence", "series"}:
        return {"error": "Enrollment scope must be occurrence or series"}
    try:
        entry_uuid = uuid.UUID(waitlist_entry_id)
        slot_uuid = uuid.UUID(recurring_slot_id)
        parsed_date = date.fromisoformat(occurrence_date)
    except ValueError:
        return {"error": "waitlist_entry_id, recurring_slot_id and occurrence_date must be valid"}

    try:
        entry, slot, occurrence, contact = waitlist_service.load_group_fulfillment(
            db,
            professional_id,
            entry_id=entry_uuid,
            recurring_slot_id=slot_uuid,
            occurrence_date=parsed_date,
            enrollment_scope=enrollment_scope,
        )
    except waitlist_service.WaitlistValidationError as exc:
        return {"error": str(exc)}

    if enrollment_scope == "occurrence":
        scope_text = "somente à aula"
    else:
        scope_text = "à turma fixa a partir da aula"
    preview_text = (
        f"Adicionar {contact.display_name} {scope_text} de {_group_label(slot)} em "
        f"{parsed_date.strftime('%d/%m/%Y')} ({occurrence.place_name or 'local não informado'}) "
        f"e concluir a solicitação da fila de espera."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_fulfill_waitlist_with_group",
        arguments={
            "waitlist_entry_id": waitlist_entry_id,
            "recurring_slot_id": recurring_slot_id,
            "occurrence_date": occurrence_date,
            "enrollment_scope": enrollment_scope,
        },
        preview_text=preview_text,
        affected_entities=[
            {"entity_type": "contact", "entity_id": str(contact.id), "label": contact.display_name},
            {
                "entity_type": "recurring_slot",
                "entity_id": recurring_slot_id,
                "label": _group_label(slot),
            },
            {
                "entity_type": "waitlist_entry",
                "entity_id": waitlist_entry_id,
                "label": contact.display_name,
            },
        ],
        correlation_id=correlation_id,
        channel=channel,
    )
    return _pending_result(candidate)


def _execute_fulfill_waitlist_with_group(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    entry_id = uuid.UUID(args["waitlist_entry_id"])
    slot_id = uuid.UUID(args["recurring_slot_id"])
    parsed_date = date.fromisoformat(args["occurrence_date"])
    enrollment_scope = args["enrollment_scope"]

    entry = waitlist_service.lock_entry(db, professional_id, entry_id)
    if entry is None:
        raise ValueError("Waitlist entry no longer exists")

    try:
        entry, slot, _occurrence, contact = waitlist_service.load_group_fulfillment(
            db,
            professional_id,
            entry_id=entry_id,
            recurring_slot_id=slot_id,
            occurrence_date=parsed_date,
            enrollment_scope=enrollment_scope,
        )
        waitlist_service.fulfill_group_occurrence(
            db,
            professional_id,
            entry_id=entry_id,
            recurring_slot_id=slot_id,
            occurrence_date=parsed_date,
            enrollment_scope=enrollment_scope,
        )
    except waitlist_service.WaitlistValidationError as exc:
        raise ValueError(str(exc)) from exc

    record_event(
        db,
        professional_id=professional_id,
        event_type="waitlist.entry.fulfilled",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="waitlist_entry",
        entity_id=entry.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={
            "fulfilled_recurring_slot_id": str(slot.id),
            "fulfilled_occurrence_date": parsed_date.isoformat(),
            "fulfillment_scope": enrollment_scope,
        },
        before_state={"status": "open"},
        after_state={"status": "fulfilled"},
    )
    return ExecutionResult(
        ok=True,
        summary=(
            f"{contact.display_name} adicionado(a) à turma e solicitação da fila concluída."
        ),
    )


# ---------------------------------------------------------------------------
# propose_create_event (instructor events roadmap v0.1, Phase 3)
# ---------------------------------------------------------------------------

def propose_create_event(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    channel: str = "web",
    *,
    event_type: str,
    start_at: str,
    end_at: str,
    place_id: str | None = None,
    title: str | None = None,
    income_cents: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if event_type not in instructor_events_service.EVENT_TYPES:
        return {"error": f"event_type must be one of {instructor_events_service.EVENT_TYPES}"}

    parsed_start = _parse_datetime(start_at)
    parsed_end = _parse_datetime(end_at)
    if parsed_end <= parsed_start:
        return {"error": "end_at must be after start_at"}

    try:
        requested_place_id = uuid.UUID(place_id) if place_id else None
    except ValueError:
        return {"error": "place_id must be a valid UUID"}
    place_resolution = resolve_place_stay(
        db,
        professional_id,
        start_at=parsed_start,
        end_at=parsed_end,
        requested_place_id=requested_place_id,
    )
    if place_resolution.outcome == "invalid_place":
        return {"error": "Place not found"}

    effective_place_id = place_resolution.place_id
    place_name = None
    if effective_place_id is not None:
        place = (
            db.query(Place)
            .filter(Place.id == effective_place_id, Place.professional_id == professional_id)
            .first()
        )
        place_name = place.name if place else None

    try:
        instructor_events_service.assert_no_event_conflict(
            db, professional_id, start_at=parsed_start, end_at=parsed_end
        )
    except HTTPException as exc:
        return {"error": exc.detail}

    local_start = parsed_start.astimezone(TIMEZONE)
    local_end = parsed_end.astimezone(TIMEZONE)
    income_label = f" — R$ {income_cents / 100:.2f}".replace(".", ",") if income_cents else ""
    place_suffix = f", {place_name}" if place_name else ""
    if place_resolution.stay_id is not None:
        place_suffix += " (local inferido pela permanência)"
    elif place_id is not None:
        place_suffix += " (local informado como exceção)"
    preview_text = (
        f"Criar evento ({event_type}) {title or ''} em "
        f"{local_start.strftime('%d/%m/%Y %H:%M')}–{local_end.strftime('%H:%M')}"
        f"{place_suffix}{income_label}."
    )
    candidate = candidates.propose(
        db,
        professional_id,
        actor_user_id,
        tool_name="propose_create_event",
        arguments={
            "event_type": event_type,
            "start_at": parsed_start.isoformat(),
            "end_at": parsed_end.isoformat(),
            "place_id": str(effective_place_id) if effective_place_id else None,
            "requested_place_id": place_id,
            "title": title,
            "income_cents": income_cents,
            "note": note,
        },
        preview_text=preview_text,
        affected_entities=[],
        correlation_id=correlation_id,
        channel=channel,
    )
    return _pending_result(candidate)


def _execute_create_event(
    db: Session, professional_id: uuid.UUID, candidate: OperatorActionCandidate
) -> ExecutionResult:
    args = candidate.resolved_arguments
    start_at = _parse_datetime(args["start_at"])
    end_at = _parse_datetime(args["end_at"])
    requested_place_id = (
        uuid.UUID(args["requested_place_id"])
        if args.get("requested_place_id")
        else None
    )
    place_resolution = resolve_place_stay(
        db,
        professional_id,
        start_at=start_at,
        end_at=end_at,
        requested_place_id=requested_place_id,
    )
    if place_resolution.outcome == "invalid_place":
        raise ValueError("Place no longer exists")
    try:
        event = instructor_events_service.create_event(
            db,
            professional_id,
            event_type=args["event_type"],
            start_at=start_at,
            end_at=end_at,
            place_id=place_resolution.place_id,
            title=args.get("title"),
            income_cents=args.get("income_cents"),
            note=args.get("note"),
        )
    except instructor_events_service.InstructorEventValidationError as exc:
        raise ValueError(str(exc))

    record_event(
        db,
        professional_id=professional_id,
        event_type="instructor_event.created",
        occurred_at=datetime.now(TIMEZONE),
        actor_type="user",
        actor_id=candidate.actor_user_id,
        source_channel=candidate.channel,
        entity_type="instructor_event",
        entity_id=event.id,
        correlation_id=candidate.correlation_id,
        operator_action_candidate_id=candidate.id,
        payload={
            "event_type": event.event_type,
            "start_at": args["start_at"],
            "requested_place_id": args.get("requested_place_id"),
            "resolved_place_id": str(event.place_id) if event.place_id else None,
        },
        before_state=None,
        after_state={"status": event.status},
    )
    return ExecutionResult(
        ok=True, summary=f"Evento criado em {args['start_at']}."
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
            "name": "propose_create_group_slot",
            "description": "Propose opening an EMPTY group class slot (turma), once or weekly, at a registered place. It starts with zero customers and still occupies the instructor calendar. Use ONLY when the instructor explicitly says 'turma', 'grupo', or asks to open capacity. Do NOT use to schedule a named customer — a weekly cadence alone is not group intent. For a named customer on a recurring schedule, use propose_create_appointment with is_recurring=true instead. Requires explicit instructor confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "place_id": {"type": "string"},
                    "start_at": {"type": "string", "description": "ISO 8601 datetime."},
                    "end_at": {"type": "string", "description": "ISO 8601 datetime."},
                    "is_recurring": {"type": "boolean"},
                    "max_participants": {"type": "integer", "minimum": 1, "maximum": 4},
                    "label": {"type": "string"},
                },
                "required": ["place_id", "start_at", "end_at", "is_recurring"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_add_group_occurrence_participant",
            "description": "Propose adding a sporadic contact to ONE dated occurrence of a recurring group, without changing the permanent group roster. Use for requests such as 'can Ana join the Tuesday 18h group next week?'. Requires explicit instructor confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "recurring_slot_id": {"type": "string", "description": "The group's recurring_slot_id, from find_groups or get_schedule."},
                    "occurrence_date": {"type": "string", "description": "ISO date of the specific class occurrence."},
                },
                "required": ["contact_id", "recurring_slot_id", "occurrence_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_remove_group_occurrence_participant",
            "description": "Propose removing a sporadic (dated) contact from ONE occurrence of a recurring group, without changing the permanent roster. Use only when the contact was added as an occurrence-only guest. For a permanent member missing one date use propose_note_participant_absence; for removing a permanent member from the whole series use propose_remove_group_member. Requires explicit instructor confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "recurring_slot_id": {"type": "string", "description": "The group's recurring_slot_id, from find_groups or get_schedule."},
                    "occurrence_date": {"type": "string", "description": "ISO date of the specific class occurrence."},
                },
                "required": ["contact_id", "recurring_slot_id", "occurrence_date"],
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
            "description": "Propose creating an individual or group appointment for one or more named customers. Supports both one-off and weekly recurring bookings — pass is_recurring=true for weekly cadence. The place is inherited only when exactly one place stay covers the full interval; otherwise ask for an explicit place. Requires instructor confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "place_id": {"type": "string", "description": "Optional explicit place ID. Omit only when a unique covering place stay exists."},
                    "start_at": {"type": "string", "description": "ISO 8601 datetime, e.g. 2026-08-10T14:00:00-03:00."},
                    "end_at": {"type": "string", "description": "ISO 8601 datetime."},
                    "service": {"type": "string"},
                    "contact_ids": {"type": "array", "items": {"type": "string"}, "description": "One to four contacts, including contact_id. Required for a group."},
                    "class_type": {"type": "string", "enum": ["individual", "group"], "description": "Defaults to individual."},
                    "billing_type": {"type": "string", "enum": ["billable", "courtesy"], "description": "Optional — 'courtesy' marks this as a free/courtesy class that shouldn't generate revenue."},
                    "is_recurring": {"type": "boolean", "description": "Create a weekly recurring appointment when true. Defaults to false. A single named customer defaults to an individual appointment."},
                },
                "required": ["contact_id", "start_at", "end_at", "service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_redeem_makeup_credit",
            "description": "Propose redeeming a make-up class credit by creating a one-off appointment in an open slot and marking the credit as redeemed in the same transaction. Requires explicit instructor confirmation — use after recommend_makeup_slots has suggested slots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "credit_id": {"type": "string", "description": "The make-up credit ID (from the contact's available credits)."},
                    "place_id": {"type": "string"},
                    "start_at": {"type": "string", "description": "ISO 8601 datetime, e.g. 2026-08-10T14:00:00-03:00."},
                    "end_at": {"type": "string", "description": "ISO 8601 datetime."},
                },
                "required": ["credit_id", "place_id", "start_at", "end_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_cancel_schedule",
            "description": "Propose cancelling a single dated occurrence of an appointment or recurring class ENTIRELY — nobody has class that day (not the whole series). For a group class where only ONE student can't attend but the class still happens for the rest of the group, use propose_note_participant_absence instead. Requires explicit instructor confirmation.",
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
            "name": "propose_note_participant_absence",
            "description": "Propose recording that ONE participant of a recurring group class will miss (or missed) a specific dated occurrence, while the class still happens normally for the rest of the group — does not cancel anything on the calendar. If the notice given meets the tenant's configured cancellation_notice_hours, this grants that student a make-up class credit. Use this instead of propose_cancel_schedule whenever the group class itself is not being cancelled.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "recurring_slot_id": {"type": "string", "description": "The group's recurring_slot_id, from find_groups."},
                    "occurrence_date": {"type": "string", "description": "ISO date of the specific occurrence the student will miss."},
                },
                "required": ["contact_id", "recurring_slot_id", "occurrence_date"],
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
            "name": "propose_set_occurrence_class_format",
            "description": "Propose changing format/capacity for ONE dated appointment or recurring-class occurrence, without changing the parent series. Requires explicit instructor confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_type": {"type": "string", "enum": ["appointment", "recurring_slot"]},
                    "target_id": {"type": "string", "description": "The source_id from get_schedule."},
                    "occurrence_date": {"type": "string", "description": "ISO date for the single occurrence."},
                    "class_type": {"type": "string", "enum": ["individual", "group"]},
                    "max_participants": {"type": "integer", "minimum": 1, "maximum": 4},
                },
                "required": ["target_type", "target_id", "occurrence_date", "class_type", "max_participants"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_set_appointment_format",
            "description": "Propose changing an existing one-off appointment between individual and group format, including its total participant capacity. Use when an instructor wants to promote an individual appointment into a group slot before adding other customers. Get appointment_id from get_schedule where source_type is appointment. Requires explicit instructor confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "string", "description": "The appointment source_id from get_schedule, where source_type == appointment."},
                    "class_type": {"type": "string", "enum": ["individual", "group"]},
                    "max_participants": {"type": "integer", "minimum": 1, "maximum": 4},
                },
                "required": ["appointment_id", "class_type", "max_participants"],
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
    {
        "type": "function",
        "function": {
            "name": "propose_add_waitlist_entry",
            "description": "Propose adding a contact to the Fila de Espera (waitlist) for a specific date/time slot that doesn't exist yet — use when the instructor has no opening for a contact and wants to remember the request. Requires a specific date and time range, not a vague period. Requires explicit instructor confirmation before it takes effect.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                    "desired_date": {"type": "string", "description": "ISO date, e.g. 2026-08-15."},
                    "desired_start_time": {"type": "string", "description": "ISO time, e.g. 19:00:00."},
                    "desired_end_time": {"type": "string", "description": "ISO time, e.g. 20:00:00."},
                    "place_id": {"type": "string", "description": "Optional — omit if any place works."},
                    "class_type": {"type": "string", "enum": ["individual", "group"], "description": "Optional — omit if either works."},
                    "duration_minutes": {"type": "integer", "minimum": 1, "description": "Optional — defaults to the desired time range's length."},
                    "note": {"type": "string", "description": "Optional free-text note, e.g. preferences."},
                },
                "required": ["contact_id", "desired_date", "desired_start_time", "desired_end_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_remove_waitlist_entry",
            "description": "Propose removing/cancelling a Fila de Espera (waitlist) entry — the contact is no longer waiting for that slot. Use list_waitlist_entries first to get a real waitlist_entry_id; never guess one. Requires explicit instructor confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "waitlist_entry_id": {"type": "string"},
                },
                "required": ["waitlist_entry_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_fulfill_waitlist_with_appointment",
            "description": "Propose fulfilling a Fila de Espera (waitlist) entry by booking a one-off individual appointment for the waiting contact at the entry's own desired date/time and place. Derives contact, date and time from the waitlist entry — never alters them. Use for a free_time match from find_waitlist_matches. Never use propose_create_appointment followed by propose_remove_waitlist_entry, which would mark the demand cancelled instead of fulfilled. Requires explicit instructor confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "waitlist_entry_id": {"type": "string", "description": "The waitlist_entry_id from find_waitlist_matches or list_waitlist_entries."},
                    "place_id": {"type": "string", "description": "The free_time match's place_id."},
                    "service": {"type": "string", "description": "Optional service label, defaults to 'Aula'."},
                },
                "required": ["waitlist_entry_id", "place_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_fulfill_waitlist_with_group",
            "description": "Propose fulfilling a Fila de Espera (waitlist) entry by enrolling the waiting contact in a group occurrence, either only that dated occurrence (enrollment_scope='occurrence') or the whole recurring group from that date onward (enrollment_scope='series'). Use for a group_occurrence match from find_waitlist_matches; ask 'só essa aula ou turma fixa?' unless the instructor already stated the scope. Never interpret this as cancelling the waitlist record. Requires explicit instructor confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "waitlist_entry_id": {"type": "string", "description": "The waitlist_entry_id from find_waitlist_matches."},
                    "recurring_slot_id": {"type": "string", "description": "The group's recurring_slot_id (source_id from the group_occurrence match)."},
                    "occurrence_date": {"type": "string", "description": "ISO date of the matched group occurrence."},
                    "enrollment_scope": {"type": "string", "enum": ["occurrence", "series"], "description": "Whether to add only to this dated occurrence or to the recurring group's permanent roster."},
                },
                "required": ["waitlist_entry_id", "recurring_slot_id", "occurrence_date", "enrollment_scope"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_create_event",
            "description": "Propose creating an InstructorEvent — paid work with no client, not a class: refereeing a tournament, running a workshop or clinic. Use for things like 'amanha das 15 as 20h vou dar uma clinica, vou receber R$ 2000'. Requires explicit instructor confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type": {
                        "type": "string",
                        "enum": ["tournament_referee", "workshop", "clinic", "other"],
                        "description": "tournament_referee for arbitragem/arbitrar; workshop for workshop/oficina; clinic for clinica; other otherwise.",
                    },
                    "start_at": {"type": "string", "description": "ISO 8601 datetime, e.g. 2026-08-10T15:00:00-03:00."},
                    "end_at": {"type": "string", "description": "ISO 8601 datetime."},
                    "place_id": {"type": "string", "description": "Optional — omit if not at a registered place."},
                    "title": {"type": "string", "description": "Optional short label, e.g. 'Clínica de saque'."},
                    "income_cents": {"type": "integer", "description": "Optional flat fee in cents, e.g. R$ 2000 -> 200000."},
                    "note": {"type": "string"},
                },
                "required": ["event_type", "start_at", "end_at"],
            },
        },
    },
]

MUTATION_TOOL_DISPATCH: dict[str, Callable[..., dict[str, Any]]] = {
    "propose_add_group_member": propose_add_group_member,
    "propose_create_group_slot": propose_create_group_slot,
    "propose_add_group_occurrence_participant": propose_add_group_occurrence_participant,
    "propose_remove_group_occurrence_participant": propose_remove_group_occurrence_participant,
    "propose_remove_group_member": propose_remove_group_member,
    "propose_update_contact": propose_update_contact,
    "propose_create_appointment": propose_create_appointment,
    "propose_redeem_makeup_credit": propose_redeem_makeup_credit,
    "propose_cancel_schedule": propose_cancel_schedule,
    "propose_note_participant_absence": propose_note_participant_absence,
    "propose_reschedule_occurrence": propose_reschedule_occurrence,
    "propose_set_occurrence_class_format": propose_set_occurrence_class_format,
    "propose_set_appointment_format": propose_set_appointment_format,
    "propose_add_appointment_participant": propose_add_appointment_participant,
    "propose_remove_appointment_participant": propose_remove_appointment_participant,
    "propose_add_waitlist_entry": propose_add_waitlist_entry,
    "propose_remove_waitlist_entry": propose_remove_waitlist_entry,
    "propose_fulfill_waitlist_with_appointment": propose_fulfill_waitlist_with_appointment,
    "propose_fulfill_waitlist_with_group": propose_fulfill_waitlist_with_group,
    "propose_create_event": propose_create_event,
}

candidates.MUTATION_EXECUTORS["propose_add_group_member"] = _execute_add_group_member
candidates.MUTATION_EXECUTORS["propose_create_group_slot"] = _execute_create_group_slot
candidates.MUTATION_EXECUTORS[
    "propose_add_group_occurrence_participant"
] = _execute_add_group_occurrence_participant
candidates.MUTATION_EXECUTORS[
    "propose_remove_group_occurrence_participant"
] = _execute_remove_group_occurrence_participant
candidates.MUTATION_EXECUTORS["propose_remove_group_member"] = _execute_remove_group_member
candidates.MUTATION_EXECUTORS[
    "propose_add_appointment_participant"
] = _execute_add_appointment_participant
candidates.MUTATION_EXECUTORS[
    "propose_remove_appointment_participant"
] = _execute_remove_appointment_participant
candidates.MUTATION_EXECUTORS[
    "propose_set_appointment_format"
] = _execute_set_appointment_format
candidates.MUTATION_EXECUTORS["propose_update_contact"] = _execute_update_contact
candidates.MUTATION_EXECUTORS["propose_create_appointment"] = _execute_create_appointment
candidates.MUTATION_EXECUTORS["propose_redeem_makeup_credit"] = _execute_redeem_makeup_credit
candidates.MUTATION_EXECUTORS["propose_cancel_schedule"] = _execute_cancel_schedule
candidates.MUTATION_EXECUTORS[
    "propose_note_participant_absence"
] = _execute_note_participant_absence
candidates.MUTATION_EXECUTORS["propose_reschedule_occurrence"] = _execute_reschedule_occurrence
candidates.MUTATION_EXECUTORS[
    "propose_set_occurrence_class_format"
] = _execute_set_occurrence_class_format
candidates.MUTATION_EXECUTORS["propose_add_waitlist_entry"] = _execute_add_waitlist_entry
candidates.MUTATION_EXECUTORS["propose_remove_waitlist_entry"] = _execute_remove_waitlist_entry
candidates.MUTATION_EXECUTORS[
    "propose_fulfill_waitlist_with_appointment"
] = _execute_fulfill_waitlist_with_appointment
candidates.MUTATION_EXECUTORS[
    "propose_fulfill_waitlist_with_group"
] = _execute_fulfill_waitlist_with_group
candidates.MUTATION_EXECUTORS["propose_create_event"] = _execute_create_event

"""
Read tools for the instructor agent (operational ontology roadmap v0.2,
Phase 2). Every tool takes `professional_id` from the authenticated caller
(never from model output) and returns plain, JSON-serializable data — no
tool here invents or infers data beyond what the domain services return.

`TOOL_SPECS` declares the OpenAI/Azure OpenAI function-calling schema for
each tool; `TOOL_DISPATCH` maps a tool name to its implementation, used by
`orchestrator.py`'s tool-call loop.
"""

import uuid
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.agent import entity_resolution, temporal
from app.models import Contact, Place, Professional, RecurringSlot
from app.services import (
    financial_capacity,
    instructor_events,
    makeup_credits,
    makeup_recommender,
    scheduling,
    waitlist,
)

MAX_SCHEDULE_SPAN_DAYS = 31
NEXT_SESSION_SEARCH_DAYS = 90


def _uuid_str(value: uuid.UUID | None) -> str | None:
    return str(value) if value is not None else None


def search_contacts(
    db: Session,
    professional_id: uuid.UUID,
    *,
    query: str,
    place_id: str | None = None,
) -> dict[str, Any]:
    matches = entity_resolution.resolve_contacts(
        db,
        professional_id,
        query,
        place_id=uuid.UUID(place_id) if place_id else None,
    )
    return {
        "matches": [
            {
                "contact_id": str(match.contact_id),
                "display_name": match.display_name,
                "phone": match.phone,
                "level": match.level,
                "home_place_id": _uuid_str(match.home_place_id),
            }
            for match in matches
        ]
    }


def search_places(db: Session, professional_id: uuid.UUID, *, query: str) -> dict[str, Any]:
    matches = entity_resolution.resolve_places(db, professional_id, query)
    return {
        "matches": [
            {
                "place_id": str(match.place_id),
                "name": match.name,
                "address_line": match.address_line,
                "city": match.city,
            }
            for match in matches
        ]
    }


def find_groups(
    db: Session,
    professional_id: uuid.UUID,
    *,
    member_contact_id: str | None = None,
    place_id: str | None = None,
    weekday: int | None = None,
) -> dict[str, Any]:
    matches = entity_resolution.resolve_groups(
        db,
        professional_id,
        member_contact_id=uuid.UUID(member_contact_id) if member_contact_id else None,
        place_id=uuid.UUID(place_id) if place_id else None,
        weekday=weekday,
    )
    return {
        "matches": [
            {
                "recurring_slot_id": str(match.recurring_slot_id),
                "group_name": match.group_name,
                "label": match.label,
                "place_id": str(match.place_id),
                "place_name": match.place_name,
                "day_of_week": match.day_of_week,
                "start_time": match.start_time.isoformat(),
                "end_time": match.end_time.isoformat(),
                "participant_names": match.participant_names,
            }
            for match in matches
        ]
    }


def find_group_openings(
    db: Session,
    professional_id: uuid.UUID,
    *,
    date: str,
    start_time: str | None = None,
    period: str | None = None,
    place_id: str | None = None,
) -> dict[str, Any]:
    """Return joinable group occurrences, never calendar-free time."""
    target_date = date_cls.fromisoformat(date)
    requested_place_id = uuid.UUID(place_id) if place_id else None

    period_window: tuple[int, int] | None = None
    if period is not None:
        matching = [
            (start, end)
            for key, _, start, end in financial_capacity.PART_OF_DAY_RANGES
            if key == period
        ]
        if not matching:
            return {"error": f"Unknown period '{period}'"}
        period_window = matching[0]

    occurrences = scheduling.list_schedule_occurrences(
        db, professional_id, target_date, target_date
    )
    matches: list[scheduling.ScheduleOccurrence] = []
    for occurrence in occurrences:
        if occurrence.class_type != "group":
            continue
        if occurrence.available_seats <= 0:
            continue
        if start_time is not None and occurrence.starts_at.strftime("%H:%M") != start_time[:5]:
            continue
        if requested_place_id is not None and occurrence.place_id != requested_place_id:
            continue
        if period_window is not None:
            occurrence_start = scheduling.time_to_minutes(occurrence.starts_at.time())
            occurrence_end = scheduling.time_to_minutes(occurrence.ends_at.time())
            period_start, period_end = period_window
            if occurrence_end <= period_start or occurrence_start >= period_end:
                continue
        matches.append(occurrence)

    result: dict[str, Any] = {
        "date": target_date.isoformat(),
        "joinable_groups": [
            {
                **_occurrence_to_dict(occurrence),
                "participant_count": occurrence.participant_count,
                "max_participants": occurrence.max_participants,
                "available_seats": occurrence.available_seats,
                "enrollment_scopes": (
                    ["occurrence", "series"]
                    if occurrence.source_type == "recurring_slot"
                    else ["occurrence"]
                ),
            }
            for occurrence in matches
        ],
    }
    if period is not None:
        result["period"] = period
    return result


def _occurrence_to_dict(occurrence: scheduling.ScheduleOccurrence) -> dict[str, Any]:
    now = datetime.now(scheduling.TIMEZONE)
    return {
        "source_type": occurrence.source_type,
        "source_id": str(occurrence.source_id),
        "occurrence_date": occurrence.occurrence_date.isoformat(),
        "starts_at": occurrence.starts_at.isoformat(),
        "ends_at": occurrence.ends_at.isoformat(),
        "label": occurrence.source_label,
        "place_id": _uuid_str(occurrence.place_id),
        "place_name": occurrence.place_name,
        "status": occurrence.status,
        "class_type": occurrence.class_type,
        "is_exception": occurrence.is_exception,
        # Computed deterministically here (never left to the model to infer
        # from timestamps) so the agent can reliably distinguish already-
        # finished occurrences from upcoming ones on the current day.
        "is_past": occurrence.ends_at <= now,
        "participants": [
            {
                "contact_id": str(p.contact_id),
                "contact_name": p.contact_name,
                "enrollment_scope": p.enrollment_scope,
            }
            for p in occurrence.participants
        ],
    }


def get_schedule(
    db: Session,
    professional_id: uuid.UUID,
    *,
    date_from: str,
    date_to: str,
) -> dict[str, Any]:
    parsed_from = date_cls.fromisoformat(date_from)
    parsed_to = date_cls.fromisoformat(date_to)
    if parsed_to < parsed_from:
        return {"error": "date_to must not be before date_from"}
    if (parsed_to - parsed_from).days > MAX_SCHEDULE_SPAN_DAYS:
        return {
            "error": f"Date range too large; max span is {MAX_SCHEDULE_SPAN_DAYS} days"
        }

    occurrences = scheduling.list_schedule_occurrences(
        db, professional_id, parsed_from, parsed_to
    )
    return {"occurrences": [_occurrence_to_dict(o) for o in occurrences]}


def get_next_session(
    db: Session,
    professional_id: uuid.UUID,
    *,
    contact_id: str,
) -> dict[str, Any]:
    contact_uuid = uuid.UUID(contact_id)
    now = datetime.now(scheduling.TIMEZONE)
    occurrences = scheduling.list_schedule_occurrences(
        db, professional_id, now.date(), now.date() + timedelta(days=NEXT_SESSION_SEARCH_DAYS)
    )
    for occurrence in occurrences:
        if occurrence.ends_at <= now:
            continue  # already finished earlier today — not the "next" session
        if any(p.contact_id == contact_uuid for p in occurrence.participants):
            return {"next_session": _occurrence_to_dict(occurrence)}
    return {"next_session": None}


def _format_minutes(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def find_instructor_openings(
    db: Session,
    professional_id: uuid.UUID,
    *,
    date: str,
    period: str | None = None,
    duration_minutes: int | None = None,
    place_id: str | None = None,
) -> dict[str, Any]:
    """Real free time on a date: the declared Work Journey minus every
    booking, across all places.

    Deliberately *not* based on per-place recurring availability windows
    (`RecurringSlot`, the financial module's capacity config): those exist
    for revenue projection, and treating them as the answer to "when am I
    free?" hides genuinely open calendar gaps at any hour no place happens
    to have configured. Each opening still carries the places whose
    configured window covers it, so the agent can suggest a place — but a
    place without a window never removes an opening."""
    target_date = date_cls.fromisoformat(date)

    professional = (
        db.query(Professional).filter(Professional.id == professional_id).first()
    )
    if professional is None:
        return {"error": "Professional not found"}
    duration = duration_minutes or professional.default_duration_minutes

    period_window: tuple[int, int] | None = None
    if period is not None:
        matching = [
            (start, end) for key, _, start, end in financial_capacity.PART_OF_DAY_RANGES
            if key == period
        ]
        if not matching:
            return {"error": f"Unknown period '{period}'"}
        period_window = matching[0]

    place_ids = [uuid.UUID(place_id)] if place_id else None
    places = financial_capacity.load_places(db, professional_id, place_ids)
    free_by_place = (
        financial_capacity.compute_free_ranges_by_place(
            db, professional_id, target_date, places
        )
        if places
        else {}
    )

    free_ranges = financial_capacity.compute_free_calendar_ranges(
        db, professional_id, target_date
    )
    if period_window is not None:
        free_ranges = scheduling.intersect_ranges(free_ranges, [period_window])
    if place_id is not None:
        # An explicit place filter means "when can I use this place?" —
        # narrow the calendar gaps to that place's configured window.
        free_ranges = scheduling.intersect_ranges(
            free_ranges, free_by_place.get(uuid.UUID(place_id), [])
        )

    openings: list[dict[str, Any]] = []
    for start_minute, end_minute in free_ranges:
        if end_minute - start_minute < duration:
            continue
        covering_places = [
            {
                "place_id": str(place.id),
                "place_name": place.name,
                "start_time": _format_minutes(place_start),
                "end_time": _format_minutes(place_end),
            }
            for place in places
            for place_start, place_end in scheduling.intersect_ranges(
                free_by_place.get(place.id, []), [(start_minute, end_minute)]
            )
            if place_end - place_start >= duration
        ]
        openings.append(
            {
                "start_time": _format_minutes(start_minute),
                "end_time": _format_minutes(end_minute),
                "places": covering_places,
            }
        )

    result: dict[str, Any] = {
        "date": target_date.isoformat(),
        "duration_minutes": duration,
        "openings": openings,
    }

    if openings:
        if any(not opening["places"] for opening in openings):
            result["note"] = (
                "Os horários acima são os intervalos realmente livres da jornada de "
                "trabalho do professor. Alguns vêm com a lista 'places' vazia: são "
                "horários livres em que nenhum local tem janela de disponibilidade "
                "recorrente cadastrada — continuam válidos para agendar, mas pergunte "
                "ao professor qual local usar antes de propor."
            )
        return result

    if not financial_capacity.load_net_work_ranges(db, professional_id, target_date):
        result["note"] = (
            "O professor não tem jornada de trabalho cadastrada para este dia da "
            "semana — por isso não há horários recomendados a reportar. Oriente "
            "a configuração em Configurações > Jornada de trabalho (não diga "
            "apenas que a agenda está cheia)."
        )
    else:
        result["note"] = (
            "A jornada de trabalho deste dia não tem nenhum intervalo livre de pelo "
            f"menos {duration} minutos — está totalmente ocupada pelos compromissos "
            "já marcados."
        )
    return result


def resolve_date_phrase(
    db: Session,
    professional_id: uuid.UUID,
    *,
    phrase: str,
) -> dict[str, Any]:
    """Deterministically resolve a Portuguese relative-date phrase (e.g.
    "amanhã de tarde") — never guess dates via free-form reasoning; always
    call this tool for temporal phrases instead."""
    reference_date = datetime.now(scheduling.TIMEZONE).date()
    resolution = temporal.resolve_temporal_phrase(phrase, reference_date=reference_date)

    period_start = (
        resolution.period[0].isoformat() if resolution.period else None
    )
    period_end = resolution.period[1].isoformat() if resolution.period else None

    if resolution.ambiguity_reason is not None:
        return {
            "recognized": False,
            "message": "A data é ambígua; pergunte ao professor qual opção ele quer.",
            "ambiguity_reason": resolution.ambiguity_reason,
            "alternatives": [
                alternative.isoformat() for alternative in (resolution.alternatives or [])
            ],
            "date": None,
            "date_from": None,
            "date_to": None,
            "period_start_time": period_start,
            "period_end_time": period_end,
        }

    if not resolution.recognized:
        return {
            "recognized": False,
            "message": "Phrase not recognized by the deterministic resolver; ask the instructor to clarify the date.",
            "ambiguity_reason": None,
            "alternatives": None,
            "date": None,
            "date_from": None,
            "date_to": None,
            "period_start_time": period_start,
            "period_end_time": period_end,
        }

    return {
        "recognized": True,
        "date": resolution.resolved_date.isoformat() if resolution.resolved_date else None,
        "date_from": (
            resolution.resolved_date_from.isoformat() if resolution.resolved_date_from else None
        ),
        "date_to": (
            resolution.resolved_date_to.isoformat() if resolution.resolved_date_to else None
        ),
        "period_start_time": period_start,
        "period_end_time": period_end,
        "ambiguity_reason": None,
        "alternatives": None,
    }


def list_makeup_credits(
    db: Session,
    professional_id: uuid.UUID,
    *,
    contact_id: str,
) -> dict[str, Any]:
    """List a contact's available (unredeemed) make-up class credits, with
    their credit_id — the only way to discover a valid credit_id for
    propose_redeem_makeup_credit; never guess or reuse an ID from a
    different contact/turn."""
    credits = makeup_credits.list_available_credits(
        db, professional_id, uuid.UUID(contact_id)
    )
    slot_ids = {credit.origin_recurring_slot_id for credit in credits}
    slot_labels: dict[uuid.UUID, str] = {}
    if slot_ids:
        for slot, place_name in (
            db.query(RecurringSlot, Place.name)
            .join(Place, RecurringSlot.place_id == Place.id)
            .filter(RecurringSlot.id.in_(slot_ids))
            .all()
        ):
            label = slot.group_name or slot.label or "Grupo"
            slot_labels[slot.id] = f"{label} ({place_name})"
    return {
        "contact_id": contact_id,
        "credits": [
            {
                "credit_id": str(credit.id),
                "origin_group_label": slot_labels.get(
                    credit.origin_recurring_slot_id, "Grupo"
                ),
                "origin_occurrence_date": credit.origin_occurrence_date.isoformat(),
                "granted_at": credit.granted_at.isoformat(),
                "expires_at": credit.expires_at.isoformat() if credit.expires_at else None,
            }
            for credit in credits
        ],
    }


def recommend_makeup_slots(
    db: Session,
    professional_id: uuid.UUID,
    *,
    contact_id: str,
) -> dict[str, Any]:
    """Recommend the best available slots for a contact's make-up class
    credits, ranked by cost efficiency and historical occupancy."""
    recommendations = makeup_recommender.recommend_makeup_slots(
        db,
        professional_id,
        uuid.UUID(contact_id),
    )
    return {
        "contact_id": contact_id,
        "recommendations": recommendations,
        "note": (
            None
            if recommendations
            else "No available make-up credits for this contact, or no suitable slots found in the lookahead window."
        ),
    }


def list_waitlist_entries(
    db: Session,
    professional_id: uuid.UUID,
    *,
    status: str | None = None,
    place_id: str | None = None,
    contact_id: str | None = None,
) -> dict[str, Any]:
    """List Fila de Espera (waitlist) entries — contacts wanting a specific
    slot that doesn't exist yet. Defaults to no status filter; pass
    status="open" to see only unresolved requests."""
    entries = waitlist.list_entries(
        db,
        professional_id,
        status=status,
        place_id=uuid.UUID(place_id) if place_id else None,
        contact_id=uuid.UUID(contact_id) if contact_id else None,
    )
    contact_names = {
        contact.id: contact.display_name
        for contact in db.query(Contact).filter(
            Contact.id.in_([e.contact_id for e in entries])
        )
    } if entries else {}
    place_names = {
        place.id: place.name
        for place in db.query(Place).filter(
            Place.id.in_([e.place_id for e in entries if e.place_id])
        )
    } if entries else {}
    return {
        "entries": [
            {
                "waitlist_entry_id": str(entry.id),
                "contact_id": str(entry.contact_id),
                "contact_name": contact_names.get(entry.contact_id, ""),
                "place_id": _uuid_str(entry.place_id),
                "place_name": place_names.get(entry.place_id) if entry.place_id else None,
                "desired_date": entry.desired_date.isoformat(),
                "desired_start_time": entry.desired_start_time.isoformat(),
                "desired_end_time": entry.desired_end_time.isoformat(),
                "class_type": entry.class_type,
                "status": entry.status,
                "note": entry.note,
            }
            for entry in entries
        ]
    }


def find_waitlist_matches(
    db: Session,
    professional_id: uuid.UUID,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Check open Fila de Espera (waitlist) entries against current
    capacity and report which ones now have a matching opening — reuses the
    same free-capacity computation as find_instructor_openings. Read-only;
    does not book or change anything. A free_time match must be fulfilled
    with propose_fulfill_waitlist_with_appointment and a group_occurrence
    match with propose_fulfill_waitlist_with_group — never via
    propose_create_appointment followed by propose_remove_waitlist_entry,
    which would record the demand as cancelled instead of fulfilled."""
    matches = waitlist.find_matches(
        db,
        professional_id,
        date_from=date_cls.fromisoformat(date_from) if date_from else None,
        date_to=date_cls.fromisoformat(date_to) if date_to else None,
    )
    contact_names = {
        contact.id: contact.display_name
        for contact in db.query(Contact).filter(
            Contact.id.in_([m["entry"].contact_id for m in matches])
        )
    } if matches else {}
    return {
        "matches": [
            {
                "waitlist_entry_id": str(m["entry"].id),
                "contact_id": str(m["entry"].contact_id),
                "contact_name": contact_names.get(m["entry"].contact_id, ""),
                "desired_date": m["entry"].desired_date.isoformat(),
                "desired_start_time": m["entry"].desired_start_time.isoformat(),
                "desired_end_time": m["entry"].desired_end_time.isoformat(),
                "place_id": _uuid_str(m["place_id"]),
                "place_name": m["place_name"],
                "match_type": m["match_type"],
                "source_type": m.get("source_type"),
                "source_id": _uuid_str(m.get("source_id")),
                "occurrence_date": (
                    m["occurrence_date"].isoformat()
                    if m.get("occurrence_date")
                    else None
                ),
                "available_seats": m.get("available_seats"),
            }
            for m in matches
        ]
    }


def list_events(
    db: Session,
    professional_id: uuid.UUID,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """List InstructorEvent rows (tournaments refereed, workshops, clinics
    — non-class paid work with no client) in an optional date range."""
    events = instructor_events.list_events(
        db,
        professional_id,
        date_from=datetime.fromisoformat(date_from) if date_from else None,
        date_to=datetime.fromisoformat(date_to) if date_to else None,
    )
    return {
        "events": [
            {
                "event_id": str(event.id),
                "event_type": event.event_type,
                "title": event.title,
                "place_id": _uuid_str(event.place_id),
                "start_at": event.start_at.isoformat(),
                "end_at": event.end_at.isoformat(),
                "income_cents": event.income_cents,
                "status": event.status,
            }
            for event in events
        ]
    }


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "resolve_date_phrase",
            "description": "Resolve a Portuguese date/time phrase into an ISO date, a date range, or a period-of-day window. Supports relative phrases ('hoje', 'amanhã', 'depois de amanhã', 'anteontem', 'essa sexta', 'próxima sexta', 'sexta que vem', 'daqui a duas semanas'), week/month ranges ('essa semana', 'próxima semana', 'esse mês', 'mês que vem'), and explicit Brazilian dates ('dia 28', 'dia 28 de agosto', '28/08', '28/08/2026'). Always use this tool instead of computing dates yourself. When ambiguous or unresolved, returns recognized=false with ambiguity_reason/alternatives and the instructor must be asked to clarify — never pick a date silently.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phrase": {"type": "string", "description": "The date/time phrase as the instructor wrote it, e.g. 'amanhã de tarde'."},
                },
                "required": ["phrase"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_contacts",
            "description": "Search the instructor's contacts (students) by name. Returns candidate matches; zero or multiple matches require clarification from the instructor.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Name or partial name to search for."},
                    "place_id": {"type": "string", "description": "Optional: restrict to contacts whose home place is this place ID."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_places",
            "description": "Search the instructor's places/venues by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Name or partial name to search for."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_groups",
            "description": "Find recurring class groups, optionally filtered by an EXISTING roster member, place, or weekday (0=Monday..6=Sunday). member_contact_id only finds groups the contact already belongs to; never pass the student you intend to add. To find a joinable group for a new student at a specific date/time, use find_group_openings instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_contact_id": {"type": "string", "description": "Optional contact who is ALREADY a permanent member of the group. Do not use this to search for a group to add a new contact to."},
                    "place_id": {"type": "string"},
                    "weekday": {"type": "integer", "minimum": 0, "maximum": 6},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_group_openings",
            "description": "Find joinable group-class occurrences with remaining seats on one concrete date. This is the canonical answer for group-vacancy questions ('vagas em grupos/turmas') and for locating a group where a NEW student can be added, including empty groups. It never reports free instructor time. Optionally filter by exact start time, period of day (morning/afternoon/evening), or place. Resolve relative weekdays first, then use the returned source_id as recurring_slot_id for enrollment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "ISO date."},
                    "start_time": {"type": "string", "description": "Optional HH:MM time filter."},
                    "period": {"type": "string", "enum": ["morning", "afternoon", "evening"], "description": "Optional part-of-day filter (interval overlap with the occurrence)."},
                    "place_id": {"type": "string", "description": "Optional place filter."},
                },
                "required": ["date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule",
            "description": "Get all schedule occurrences (appointments and classes) between two dates, inclusive. Max span 31 days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "ISO date, e.g. 2026-08-10."},
                    "date_to": {"type": "string", "description": "ISO date, e.g. 2026-08-10."},
                },
                "required": ["date_from", "date_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_next_session",
            "description": "Get the next upcoming scheduled session (appointment or class) for a specific contact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"},
                },
                "required": ["contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_instructor_openings",
            "description": "Find the instructor's genuinely free time windows on a given date: the declared work journey minus every booking. Each opening lists, in 'places', the places whose recurring availability window covers it (may be empty — the window is still free). Optionally filtered by period of day (morning/afternoon/evening), minimum duration, and place. This is NOT the answer to group-vacancy questions ('vagas em grupos/turmas'): a group with a seat is a scheduled commitment, not free instructor time — use find_group_openings for group capacity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "ISO date, e.g. 2026-08-10."},
                    "period": {"type": "string", "enum": ["morning", "afternoon", "evening"]},
                    "duration_minutes": {"type": "integer", "minimum": 1},
                    "place_id": {"type": "string"},
                },
                "required": ["date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_makeup_slots",
            "description": "For a contact with available make-up class credits, find and rank the best open time slots in the upcoming days. Rankings consider cost (prefer cheaper hourly rates) and historical occupancy (prefer quieter time slots). Returns empty if the contact has no credits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string", "description": "The contact/student UUID."},
                },
                "required": ["contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_makeup_credits",
            "description": "List a contact's available (unredeemed) make-up class credits, each with its credit_id. Call this before propose_redeem_makeup_credit — that tool requires a real credit_id and none may be guessed or invented.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string", "description": "The contact/student UUID."},
                },
                "required": ["contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_waitlist_entries",
            "description": "List Fila de Espera (waitlist) entries — contacts who want a slot at a specific date/time that doesn't exist yet. Call before propose_add_waitlist_entry/propose_remove_waitlist_entry to check existing entries or find a waitlist_entry_id; never guess an ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["open", "matched", "fulfilled", "cancelled", "expired"], "description": "Optional — omit to list all statuses."},
                    "place_id": {"type": "string"},
                    "contact_id": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_waitlist_matches",
            "description": "Check open Fila de Espera (waitlist) entries against current capacity and report which ones now have a matching opening (e.g. after a cancellation). Read-only — does not book anything. Route a free_time match to propose_fulfill_waitlist_with_appointment and a group_occurrence match to propose_fulfill_waitlist_with_group (ask 'só essa aula ou turma fixa?' for group matches unless already explicit). Never book-then-cancel: propose_remove_waitlist_entry means the demand was abandoned (status=cancelled), not fulfilled.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Optional ISO date — omit to check all open entries regardless of date."},
                    "date_to": {"type": "string", "description": "Optional ISO date."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_events",
            "description": "List InstructorEvent rows — non-class paid work with no client (refereeing a tournament, running a workshop or clinic). Optional date range filter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "Optional ISO datetime."},
                    "date_to": {"type": "string", "description": "Optional ISO datetime."},
                },
                "required": [],
            },
        },
    },
]

TOOL_DISPATCH: dict[str, Callable[..., dict[str, Any]]] = {
    "resolve_date_phrase": resolve_date_phrase,
    "search_contacts": search_contacts,
    "search_places": search_places,
    "find_groups": find_groups,
    "find_group_openings": find_group_openings,
    "get_schedule": get_schedule,
    "get_next_session": get_next_session,
    "find_instructor_openings": find_instructor_openings,
    "recommend_makeup_slots": recommend_makeup_slots,
    "list_makeup_credits": list_makeup_credits,
    "list_waitlist_entries": list_waitlist_entries,
    "find_waitlist_matches": find_waitlist_matches,
    "list_events": list_events,
}

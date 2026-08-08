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
from app.models import Place, Professional, RecurringSlot
from app.services import (
    financial_capacity,
    makeup_credits,
    makeup_recommender,
    scheduling,
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
            {"contact_id": str(p.contact_id), "contact_name": p.contact_name}
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


def find_instructor_openings(
    db: Session,
    professional_id: uuid.UUID,
    *,
    date: str,
    period: str | None = None,
    duration_minutes: int | None = None,
    place_id: str | None = None,
) -> dict[str, Any]:
    target_date = date_cls.fromisoformat(date)

    professional = (
        db.query(Professional).filter(Professional.id == professional_id).first()
    )
    if professional is None:
        return {"error": "Professional not found"}
    duration = duration_minutes or professional.default_duration_minutes

    place_ids = [uuid.UUID(place_id)] if place_id else None
    places = financial_capacity.load_places(db, professional_id, place_ids)
    if not places:
        return {
            "openings": [],
            "note": "No places found for this professional; "
            "the platform lacks enough availability data to answer.",
        }

    prime_ranges = financial_capacity.load_prime_ranges(db, professional_id)
    segments = financial_capacity.build_capacity_segments(
        db, professional_id, target_date, target_date, places, prime_ranges
    )
    bookings = financial_capacity.load_booking_occurrences(
        db, professional_id, target_date, target_date, places
    )

    period_window: tuple[int, int] | None = None
    if period is not None:
        matching = [
            (start, end) for key, _, start, end in financial_capacity.PART_OF_DAY_RANGES
            if key == period
        ]
        if not matching:
            return {"error": f"Unknown period '{period}'"}
        period_window = matching[0]

    openings: list[dict[str, Any]] = []
    for place in places:
        place_ranges = [
            (segment.start_minute, segment.end_minute)
            for segment in segments
            if segment.place_id == place.id
        ]
        if period_window is not None:
            place_ranges = scheduling.intersect_ranges(place_ranges, [period_window])
        place_ranges = scheduling.merge_ranges(place_ranges)

        booked_ranges = [
            (b.start_minute, b.end_minute)
            for b in bookings
            if b.place_id == place.id and b.local_date == target_date
        ]
        free_ranges = scheduling.subtract_ranges(place_ranges, booked_ranges)

        for start_minute, end_minute in free_ranges:
            if end_minute - start_minute < duration:
                continue
            openings.append(
                {
                    "place_id": str(place.id),
                    "place_name": place.name,
                    "start_time": f"{start_minute // 60:02d}:{start_minute % 60:02d}",
                    "end_time": f"{end_minute // 60:02d}:{end_minute % 60:02d}",
                }
            )

    return {"date": target_date.isoformat(), "duration_minutes": duration, "openings": openings}


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
    if not resolution.recognized:
        return {
            "recognized": False,
            "message": "Phrase not recognized by the deterministic resolver; ask the instructor to clarify the date.",
        }
    return {
        "recognized": True,
        "date": resolution.resolved_date.isoformat() if resolution.resolved_date else None,
        "period_start_time": resolution.period[0].isoformat() if resolution.period else None,
        "period_end_time": resolution.period[1].isoformat() if resolution.period else None,
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


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "resolve_date_phrase",
            "description": "Resolve a Portuguese relative-date phrase (e.g. 'hoje', 'amanhã de tarde', 'terça que vem') into an ISO date and, if present, a period-of-day time window. Always use this tool instead of computing dates yourself.",
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
            "description": "Find recurring class groups, optionally filtered by member contact, place, or weekday (0=Monday..6=Sunday).",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_contact_id": {"type": "string"},
                    "place_id": {"type": "string"},
                    "weekday": {"type": "integer", "minimum": 0, "maximum": 6},
                },
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
            "description": "Find open (unbooked) instructor time windows on a given date, optionally filtered by period of day (morning/afternoon/evening), minimum duration, and place.",
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
]

TOOL_DISPATCH: dict[str, Callable[..., dict[str, Any]]] = {
    "resolve_date_phrase": resolve_date_phrase,
    "search_contacts": search_contacts,
    "search_places": search_places,
    "find_groups": find_groups,
    "get_schedule": get_schedule,
    "get_next_session": get_next_session,
    "find_instructor_openings": find_instructor_openings,
    "recommend_makeup_slots": recommend_makeup_slots,
    "list_makeup_credits": list_makeup_credits,
}

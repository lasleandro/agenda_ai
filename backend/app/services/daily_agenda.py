"""Tenant-local, deterministic agenda projection for WhatsApp summaries."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models import Professional
from app.services import instructor_events, scheduling

EVENT_TYPE_LABELS = {
    "tournament_referee": "Arbitragem",
    "workshop": "Workshop",
    "clinic": "Clínica",
    "other": "Evento",
}


@dataclass(frozen=True)
class DailyAgendaItem:
    """One class or instructor event presented in a tenant's daily agenda."""

    kind: str
    source_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    label: str
    participant_names: tuple[str, ...]
    place_name: str | None


def get_professional_timezone(professional: Professional) -> ZoneInfo:
    """Return a validated tenant timezone or raise a safe configuration error."""
    try:
        return ZoneInfo(professional.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Tenant timezone is invalid") from exc


def list_daily_agenda_items(
    db: Session, professional_id: uuid.UUID, target_date: date
) -> tuple[Professional, list[DailyAgendaItem]]:
    """Return one tenant's class and event occupants for its local day."""
    professional = db.get(Professional, professional_id)
    if professional is None:
        raise ValueError("Tenant not found")
    timezone = get_professional_timezone(professional)
    occurrences = scheduling.list_schedule_occurrences(
        db,
        professional_id,
        target_date,
        target_date,
        local_timezone=timezone,
        include_rescheduled_replacements=True,
    )
    day_start = datetime.combine(target_date, time.min, tzinfo=timezone)
    day_end = day_start + timedelta(days=1)
    events = instructor_events.list_events(
        db,
        professional_id,
        date_from=day_start,
        date_to=day_end - timedelta(microseconds=1),
        status="confirmed",
    )

    items = [
        DailyAgendaItem(
            kind="class",
            source_id=occurrence.source_id,
            starts_at=occurrence.starts_at.astimezone(timezone),
            ends_at=occurrence.ends_at.astimezone(timezone),
            label=occurrence.source_label,
            participant_names=tuple(
                participant.contact_name for participant in occurrence.participants
            ),
            place_name=occurrence.place_name,
        )
        for occurrence in occurrences
    ]
    items.extend(
        DailyAgendaItem(
            kind="event",
            source_id=event.id,
            starts_at=event.start_at.astimezone(timezone),
            ends_at=event.end_at.astimezone(timezone),
            label=event.title or EVENT_TYPE_LABELS.get(event.event_type, "Evento"),
            participant_names=(),
            place_name=event.place.name if event.place is not None else None,
        )
        for event in events
    )
    return professional, sorted(items, key=lambda item: (item.starts_at, item.kind, str(item.source_id)))


def format_daily_agenda(target_date: date, items: list[DailyAgendaItem]) -> str:
    """Render the approved concise pt-BR daily agenda message."""
    header = f"Aulas de hoje — {target_date.strftime('%d/%m')}"
    if not items:
        return f"{header}\n\nNenhum compromisso agendado para hoje."

    lines = []
    class_count = 0
    event_count = 0
    for item in items:
        if item.kind == "class":
            class_count += 1
            label = ", ".join(item.participant_names) or item.label
            line = f"{item.starts_at.strftime('%H:%M')} — Aula — {label}"
        else:
            event_count += 1
            if item.starts_at.date() < target_date:
                when = "Em andamento"
            elif item.ends_at.date() > target_date:
                when = f"{item.starts_at.strftime('%H:%M')} — continua"
            else:
                when = (
                    item.starts_at.strftime("%H:%M")
                    if item.starts_at.time() == item.ends_at.time()
                    else f"{item.starts_at.strftime('%H:%M')}–{item.ends_at.strftime('%H:%M')}"
                )
            line = f"{when} — Evento — {item.label}"
        if item.place_name:
            line += f" — {item.place_name}"
        lines.append(line)

    summary_parts = []
    if class_count:
        summary_parts.append(f"{class_count} aula{'s' if class_count != 1 else ''}")
    if event_count:
        summary_parts.append(f"{event_count} evento{'s' if event_count != 1 else ''}")
    total = class_count + event_count
    return f"{header}\n\n" + "\n".join(lines) + f"\n\n{total} compromissos: {' e '.join(summary_parts)}."

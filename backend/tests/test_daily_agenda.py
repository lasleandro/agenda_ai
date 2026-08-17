"""Unit tests for the human-readable tenant daily agenda."""

from datetime import date, datetime
from pathlib import Path
import sys
import uuid
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.daily_agenda import DailyAgendaItem, format_daily_agenda


def test_daily_agenda_format_includes_classes_and_instructor_events() -> None:
    timezone = ZoneInfo("America/Sao_Paulo")
    target_date = date(2026, 8, 17)
    items = [
        DailyAgendaItem(
            kind="class",
            source_id=uuid.uuid4(),
            starts_at=datetime(2026, 8, 17, 8, 0, tzinfo=timezone),
            ends_at=datetime(2026, 8, 17, 9, 0, tzinfo=timezone),
            label="Aula de tênis",
            participant_names=("Ana", "Beto"),
            place_name="Quadra 1",
        ),
        DailyAgendaItem(
            kind="event",
            source_id=uuid.uuid4(),
            starts_at=datetime(2026, 8, 17, 10, 0, tzinfo=timezone),
            ends_at=datetime(2026, 8, 17, 12, 0, tzinfo=timezone),
            label="Workshop",
            participant_names=(),
            place_name="Clube",
        ),
    ]

    message = format_daily_agenda(target_date, items)

    assert "Aulas de hoje" in message
    assert "08:00 — Aula — Ana, Beto — Quadra 1" in message
    assert "10:00–12:00 — Evento — Workshop — Clube" in message
    assert "2 compromissos: 1 aula e 1 evento." in message

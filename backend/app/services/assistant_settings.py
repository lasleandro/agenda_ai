"""Per-tenant instructor-agent tuning knobs (temperature, memory window).

Rows are created lazily on first write — reads fall back to defaults so
every tenant works out of the box without a platform admin visiting the
settings screen first.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import AssistantSettings

DEFAULT_TEMPERATURE = 0.2
DEFAULT_MEMORY_WINDOW_MESSAGES = 20

MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0
MIN_MEMORY_WINDOW_MESSAGES = 2
MAX_MEMORY_WINDOW_MESSAGES = 200


@dataclass(frozen=True)
class AssistantSettingsView:
    temperature: float
    memory_window_messages: int


def get_assistant_settings(db: Session, professional_id: uuid.UUID) -> AssistantSettingsView:
    row = (
        db.query(AssistantSettings)
        .filter(AssistantSettings.professional_id == professional_id)
        .first()
    )
    if row is None:
        return AssistantSettingsView(
            temperature=DEFAULT_TEMPERATURE,
            memory_window_messages=DEFAULT_MEMORY_WINDOW_MESSAGES,
        )
    return AssistantSettingsView(
        temperature=row.temperature,
        memory_window_messages=row.memory_window_messages,
    )


def update_assistant_settings(
    db: Session,
    professional_id: uuid.UUID,
    *,
    temperature: float,
    memory_window_messages: int,
    updated_by_user_id: uuid.UUID,
) -> AssistantSettingsView:
    if not MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE:
        raise ValueError(
            f"temperature must be between {MIN_TEMPERATURE} and {MAX_TEMPERATURE}"
        )
    if not MIN_MEMORY_WINDOW_MESSAGES <= memory_window_messages <= MAX_MEMORY_WINDOW_MESSAGES:
        raise ValueError(
            "memory_window_messages must be between "
            f"{MIN_MEMORY_WINDOW_MESSAGES} and {MAX_MEMORY_WINDOW_MESSAGES}"
        )

    row = (
        db.query(AssistantSettings)
        .filter(AssistantSettings.professional_id == professional_id)
        .first()
    )
    if row is None:
        row = AssistantSettings(professional_id=professional_id)
        db.add(row)
    row.temperature = temperature
    row.memory_window_messages = memory_window_messages
    row.updated_by_user_id = updated_by_user_id
    db.flush()
    return AssistantSettingsView(
        temperature=row.temperature,
        memory_window_messages=row.memory_window_messages,
    )

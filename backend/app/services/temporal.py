"""Temporal validation service — cross-checks LLM output against dateparser.

Per brief Section 13: combine LLM output with deterministic validation using
dateparser with pt-BR locale. If LLM and deterministic parser disagree
significantly, flag as an ambiguity.
"""

from datetime import datetime

import dateparser
from dateutil import parser as dateutil_parser

from backend.app.schemas.conversation import ConversationWindow, Message
from backend.app.schemas.extraction import Ambiguity, SchedulingEvent

# Threshold: if LLM and dateparser disagree by more than this (in hours),
# flag the temporal interpretation as ambiguous.
TEMPORAL_DISAGREEMENT_THRESHOLD_HOURS = 2

# pt-BR dateparser settings
DATEPARSER_LANGUAGES = ["pt"]
DATEPARSER_SETTINGS = {
    "TIMEZONE": "America/Sao_Paulo",
    "RETURN_AS_TIMEZONE_AWARE": True,
    "PREFER_DATES_FROM": "future",
    "PREFER_DAY_OF_MONTH": "first",
}


def _extract_temporal_expressions(messages: list[Message]) -> list[str]:
    """Extract likely temporal expressions from message texts.

    This is a simple heuristic to find phrases that contain time/date references.
    A more robust version would use NER or regex patterns for pt-BR.
    """
    temporal_keywords = [
        "amanha", "depois de amanha", "hoje", "semana que vem",
        "proxima", "proximo", "hoje", "ontem",
        "segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo",
        "as ", "hora", "horas", "horario",
        "manha", "tarde", "noite",
        "depois do almoco", "depois do almoco",
    ]

    expressions = []
    for msg in messages:
        text_lower = msg.text.lower()
        for keyword in temporal_keywords:
            if keyword in text_lower:
                expressions.append(msg.text)
                break
    return expressions


def _parse_with_dateparser(
    text: str, reference_time: datetime
) -> datetime | None:
    """Parse a temporal expression using dateparser with pt-BR locale."""
    result = dateparser.parse(
        text,
        languages=DATEPARSER_LANGUAGES,
        settings={
            **DATEPARSER_SETTINGS,
            "RELATIVE_BASE": reference_time,
        },
    )
    return result


def validate_temporal(
    event: SchedulingEvent,
    conversation_window: ConversationWindow,
) -> SchedulingEvent:
    """Cross-check LLM temporal output against dateparser.

    If the LLM returned a start_at and dateparser can also resolve the temporal
    expressions, compare them. If they disagree significantly, add an ambiguity.

    This modifies and returns the event (does not mutate the original).
    """
    if event.start_at is None:
        return event

    # Extract temporal expressions from messages
    expressions = _extract_temporal_expressions(conversation_window.messages)
    if not expressions:
        return event

    # Try to parse each expression with dateparser
    reference_time = conversation_window.current_time
    parsed_dates = []

    for expr in expressions:
        parsed = _parse_with_dateparser(expr, reference_time)
        if parsed:
            parsed_dates.append(parsed)

    if not parsed_dates:
        return event

    # Use the most specific parsed date (closest to the LLM's proposed time)
    # and compare
    llm_dt = event.start_at

    for parsed_dt in parsed_dates:
        # Make both naive for comparison if needed
        llm_naive = llm_dt.replace(tzinfo=None) if llm_dt.tzinfo else llm_dt
        parsed_naive = parsed_dt.replace(tzinfo=None) if parsed_dt.tzinfo else parsed_dt

        diff_hours = abs((llm_naive - parsed_naive).total_seconds()) / 3600

        if diff_hours > TEMPORAL_DISAGREEMENT_THRESHOLD_HOURS:
            # Flag as ambiguity — don't override, just warn
            ambiguity = Ambiguity(
                field="date",
                description=(
                    f"O parser determinista sugere {parsed_dt.strftime('%d/%m %H:%M')} "
                    f"mas o LLM sugeriu {llm_dt.strftime('%d/%m %H:%M')}. "
                    f"Diferenca: {diff_hours:.1f}h."
                ),
            )
            # Create a new event with the ambiguity added
            return event.model_copy(
                update={"ambiguities": event.ambiguities + [ambiguity]}
            )

    return event


def parse_temporal_expression(
    text: str, reference_time: datetime
) -> datetime | None:
    """Parse a single temporal expression (utility for testing/CLI)."""
    return _parse_with_dateparser(text, reference_time)

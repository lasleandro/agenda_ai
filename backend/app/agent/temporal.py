"""
Deterministic Portuguese temporal-phrase resolution for the instructor
agent (operational ontology roadmap v0.2, Phase 2).

No LLM call — a closed-vocabulary dictionary/regex resolver, per the
roadmap's requirement that date/time words are interpreted deterministically
rather than left to model judgment. Unrecognized phrases return an
unresolved `TemporalResolution` so the caller (the orchestrator) can ask the
instructor for clarification instead of guessing.

Distinct from `app.chat.temporal.validate_temporal`, which *validates* a
datetime the customer-message extraction LLM already produced — a different
concern for a different subsystem.

Period-of-day ranges reuse `financial_capacity.PART_OF_DAY_RANGES` so
"tarde" means the same 12:00-18:00 window here as it does in the
availability engine (the roadmap's documented default for "tarde").
"""

import re
from dataclasses import dataclass
from datetime import date, time, timedelta

from app.services.financial_capacity import PART_OF_DAY_RANGES
from app.services.text_normalization import normalize_name

WEEKDAYS: dict[str, int] = {
    "segunda": 0,
    "segunda-feira": 0,
    "terca": 1,
    "terça": 1,
    "terca-feira": 1,
    "terça-feira": 1,
    "quarta": 2,
    "quarta-feira": 2,
    "quinta": 3,
    "quinta-feira": 3,
    "sexta": 4,
    "sexta-feira": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}

_PERIOD_PHRASES: dict[str, str] = {
    "de manha": "morning",
    "de manhã": "morning",
    "de tarde": "afternoon",
    "a tarde": "afternoon",
    "à tarde": "afternoon",
    "de noite": "evening",
    "a noite": "evening",
    "à noite": "evening",
}

def _minutes_to_time(minutes: int) -> time:
    minutes = min(minutes, 23 * 60 + 59)
    return time(minutes // 60, minutes % 60)


_PART_OF_DAY_TIMES = {
    key: (_minutes_to_time(start), _minutes_to_time(end))
    for key, _, start, end in PART_OF_DAY_RANGES
}


@dataclass(frozen=True)
class TemporalResolution:
    resolved_date: date | None
    period: tuple[time, time] | None
    resolved_date_from: date | None = None
    resolved_date_to: date | None = None

    @property
    def recognized(self) -> bool:
        return (
            self.resolved_date is not None
            or self.period is not None
            or self.resolved_date_from is not None
        )


def _next_weekday(reference_date: date, weekday: int, *, strictly_after: bool) -> date:
    offset = (weekday - reference_date.weekday()) % 7
    if offset == 0 and strictly_after:
        offset = 7
    return reference_date + timedelta(days=offset)


def resolve_temporal_phrase(
    phrase: str,
    *,
    reference_date: date,
) -> TemporalResolution:
    normalized = normalize_name(phrase)

    resolved_date: date | None = None
    resolved_date_from: date | None = None
    resolved_date_to: date | None = None
    monday_this_week = reference_date - timedelta(days=reference_date.weekday())
    if re.search(r"\bhoje\b", normalized):
        resolved_date = reference_date
    elif re.search(r"\bamanh[aã]\b", normalized):
        resolved_date = reference_date + timedelta(days=1)
    elif re.search(r"\bontem\b", normalized):
        resolved_date = reference_date - timedelta(days=1)
    elif re.search(r"\b(esta|essa) semana\b", normalized):
        resolved_date_from = monday_this_week
        resolved_date_to = monday_this_week + timedelta(days=6)
    elif re.search(r"\bpr[oó]xima semana\b", normalized) or re.search(
        r"\bsemana que vem\b", normalized
    ):
        resolved_date_from = monday_this_week + timedelta(days=7)
        resolved_date_to = resolved_date_from + timedelta(days=6)
    else:
        for name, weekday in WEEKDAYS.items():
            if re.search(rf"\b{re.escape(name)}\b", normalized):
                strictly_after = "que vem" in normalized
                resolved_date = _next_weekday(
                    reference_date, weekday, strictly_after=strictly_after
                )
                break

    period: tuple[time, time] | None = None
    for phrase_key, part_of_day in _PERIOD_PHRASES.items():
        if phrase_key in normalized:
            period = _PART_OF_DAY_TIMES[part_of_day]
            break

    return TemporalResolution(
        resolved_date=resolved_date,
        period=period,
        resolved_date_from=resolved_date_from,
        resolved_date_to=resolved_date_to,
    )

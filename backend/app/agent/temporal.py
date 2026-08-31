"""
Deterministic Portuguese temporal-phrase resolution for the instructor
agent (operational ontology roadmap v0.2, Phase 2; pt-BR conversational
resilience roadmap v0.1, Phase 1).

No LLM call — a closed-vocabulary dictionary/regex resolver, per the
roadmap's requirement that date/time words are interpreted deterministically
rather than left to model judgment. Unrecognized phrases return an
unresolved `TemporalResolution` so the caller (the orchestrator) can ask the
instructor for clarification instead of guessing.

Ordered, anchored recognition runs from most specific to least specific so a
compound phrase such as "depois de amanhã" cannot be shadowed by "amanhã".

Distinct from `app.chat.temporal.validate_temporal`, which *validates* a
datetime the customer-message extraction LLM already produced — a different
concern for a different subsystem.

Period-of-day ranges reuse `financial_capacity.PART_OF_DAY_RANGES` so
"tarde" means the same 12:00-18:00 window here as it does in the
availability engine (the roadmap's documented default for "tarde").
"""

import calendar
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

_MONTHS: dict[str, int] = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
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

_NUMBER_WORDS: dict[str, int] = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "três": 3,
    "tres": 3,
    "quatro": 4,
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
    ambiguity_reason: str | None = None
    alternatives: list[date] | None = None

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


def _resolve_period(normalized: str) -> tuple[time, time] | None:
    for phrase_key, part_of_day in _PERIOD_PHRASES.items():
        if phrase_key in normalized:
            return _PART_OF_DAY_TIMES[part_of_day]
    return None


def _last_day_of_month(value: date) -> date:
    return value.replace(day=calendar.monthrange(value.year, value.month)[1])


def _add_months(value: date, months: int) -> date:
    index = value.month - 1 + months
    year = value.year + index // 12
    month = index % 12 + 1
    return value.replace(year=year, month=month, day=1)


def _next_day_of_month(day: int, reference: date, *, strictly_after: bool = False) -> date:
    if not strictly_after:
        try:
            candidate = date(reference.year, reference.month, day)
        except ValueError:
            candidate = None
        if candidate is not None and candidate >= reference:
            return candidate
    year, month = reference.year, reference.month
    for _ in range(12):
        month += 1
        if month > 12:
            month = 1
            year += 1
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ValueError(f"Invalid day-of-month {day}")


def _day_month_without_year(
    day: int, month: int, reference: date
) -> tuple[date | None, str | None, list[date] | None]:
    if not 1 <= month <= 12:
        return (None, "Mês inválido", None)
    try:
        this_year = date(reference.year, month, day)
    except ValueError:
        this_year = None
    if this_year is not None and this_year >= reference:
        return (this_year, None, None)
    try:
        next_year = date(reference.year + 1, month, day)
    except ValueError:
        return (None, "Data inválida", None)
    return (next_year, None, None)


def _day_number_only(
    day: int, reference: date
) -> tuple[date | None, str | None, list[date] | None]:
    if not 1 <= day <= 31:
        return (None, "Dia inválido", None)
    if day == reference.day:
        alternative = _next_day_of_month(day, reference, strictly_after=True)
        return (
            None,
            "O dia indicado é hoje; o mês não foi especificado.",
            [reference, alternative],
        )
    return (_next_day_of_month(day, reference), None, None)


def _resolve_numeric_date(
    normalized: str, reference: date
) -> tuple[date | None, str | None, list[date] | None]:
    full = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", normalized)
    if full:
        day, month, year = int(full.group(1)), int(full.group(2)), int(full.group(3))
        try:
            return (date(year, month, day), None, None)
        except ValueError:
            return (None, "Data inválida", None)

    day_month = re.search(r"\b(\d{1,2})/(\d{1,2})\b", normalized)
    if day_month:
        return _day_month_without_year(
            int(day_month.group(1)), int(day_month.group(2)), reference
        )

    month_names = "|".join(_MONTHS)
    dia_mes = re.search(rf"\bdia (\d{{1,2}}) de ({month_names})\b", normalized)
    if dia_mes:
        return _day_month_without_year(
            int(dia_mes.group(1)), _MONTHS[dia_mes.group(2)], reference
        )

    num_mes = re.search(rf"\b(\d{{1,2}}) de ({month_names})\b", normalized)
    if num_mes:
        return _day_month_without_year(
            int(num_mes.group(1)), _MONTHS[num_mes.group(2)], reference
        )

    dia = re.search(r"\bdia (\d{1,2})\b", normalized)
    if dia:
        return _day_number_only(int(dia.group(1)), reference)

    return (None, None, None)


def _resolve_days_offset(normalized: str, reference: date) -> date | None:
    match = re.search(
        r"\bdaqui\s+(a\s+)?(\d+|[a-zà-ú]+)\s+(dias?|semanas?)\b",
        normalized,
    )
    if not match:
        return None
    token = match.group(2)
    unit = match.group(3)
    if token.isdigit():
        amount = int(token)
    else:
        amount = _NUMBER_WORDS.get(token)
        if amount is None:
            return None
    if amount > 365:
        return None
    delta = timedelta(days=amount) if unit.startswith("dia") else timedelta(weeks=amount)
    return reference + delta


def _resolve_month_range(
    normalized: str, reference: date
) -> tuple[date, date] | None:
    if re.search(r"\b(esse|este) m[eê]s\b", normalized):
        first = reference.replace(day=1)
        return (first, _last_day_of_month(first))
    if re.search(r"\bm[eê]s que vem\b", normalized) or re.search(
        r"\bpr[oó]ximo m[eê]s\b", normalized
    ):
        first = _add_months(reference.replace(day=1), 1)
        return (first, _last_day_of_month(first))
    return None


def _resolve_weekday(normalized: str, reference: date) -> date | None:
    strictly_after = bool(
        re.search(r"\bque vem\b", normalized)
        or re.search(r"\bpr[oó]xima\b", normalized)
        or re.search(r"\bna outra\b", normalized)
        or re.search(r"\boutra\b", normalized)
    )
    for name, weekday in WEEKDAYS.items():
        if re.search(rf"\b{re.escape(name)}\b", normalized):
            return _next_weekday(reference, weekday, strictly_after=strictly_after)
    return None


def resolve_temporal_phrase(
    phrase: str,
    *,
    reference_date: date,
) -> TemporalResolution:
    normalized = normalize_name(phrase)
    period = _resolve_period(normalized)

    month_range = _resolve_month_range(normalized, reference_date)
    if month_range is not None:
        return TemporalResolution(None, period, month_range[0], month_range[1])

    numeric = _resolve_numeric_date(normalized, reference_date)
    if numeric[0] is not None:
        return TemporalResolution(numeric[0], period)
    if numeric[1] is not None:
        return TemporalResolution(
            None,
            period,
            ambiguity_reason=numeric[1],
            alternatives=numeric[2],
        )

    offset = _resolve_days_offset(normalized, reference_date)
    if offset is not None:
        return TemporalResolution(offset, period)

    if re.search(r"\bdepois de amanh[aã]\b", normalized):
        return TemporalResolution(reference_date + timedelta(days=2), period)
    if re.search(r"\banteontem\b", normalized):
        return TemporalResolution(reference_date - timedelta(days=2), period)

    if re.search(r"\bhoje\b", normalized):
        return TemporalResolution(reference_date, period)
    if re.search(r"\bamanh[aã]\b", normalized):
        return TemporalResolution(reference_date + timedelta(days=1), period)
    if re.search(r"\bontem\b", normalized):
        return TemporalResolution(reference_date - timedelta(days=1), period)

    monday_this_week = reference_date - timedelta(days=reference_date.weekday())
    if re.search(r"\b(esta|essa) semana\b", normalized):
        return TemporalResolution(
            None, period, monday_this_week, monday_this_week + timedelta(days=6)
        )
    if re.search(r"\bpr[oó]xima semana\b", normalized) or re.search(
        r"\bsemana que vem\b", normalized
    ):
        return TemporalResolution(
            None, period, monday_this_week + timedelta(days=7),
            monday_this_week + timedelta(days=13),
        )

    weekday_date = _resolve_weekday(normalized, reference_date)
    if weekday_date is not None:
        return TemporalResolution(weekday_date, period)

    return TemporalResolution(None, period)

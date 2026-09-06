"""WhatsApp channel for the instructor-facing AI agent number (AI Agent
Operations Roadmap v0.1, brief Section 17).

Two layers, checked in order for every inbound message:

1. Deterministic Phase 0 commands (`hoje`/`amanha`/`esta semana`/
   `proxima aula`) — no LLM call, answered directly against `Appointment`.
2. A `sim`/`nao` reply to a pending proposal, or — for everything else —
   the same tool-calling orchestrator the web chat uses
   (`app.agent.orchestrator`), so the instructor can ask questions or
   request mutations in natural language. Mutations always go through the
   existing propose -> confirm -> execute flow (`app.agent.candidates`);
   nothing here writes directly. Confirmation over WhatsApp has no buttons,
   so it's a reply-keyword convention instead of the web UI's Confirm/
   Reject buttons.

Conversation history (AI Agent Operations Roadmap v0.1, Phase 3) is kept in
`AgentChannelMessage`, one row per user/assistant turn, windowed the same
way the web chat windows history (`AssistantSettings.memory_window_messages`)
so follow-ups and corrections mid-flow ("na verdade era terca, nao segunda")
have the prior turn to refer to. Deterministic Phase 0 command exchanges are
not recorded — they're a separate fast lane, not part of the LLM
conversation.

Entirely separate from the passive observer pipeline in
ingestion.py/pipeline.py, which watches the instructor's customer-facing
number (Professional.assistant_phone). This module handles messages a tenant
sends to the shared platform agent number (PLATFORM_AGENT_WHATSAPP_NUMBER):
the recipient is always that one number, and the tenant is resolved from the
sender (from_phone == Professional.assistant_phone).
"""

import logging
import unicodedata
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.agent import candidates
from app.agent.orchestrator import run_agent_turn
from app.integrations.whatsapp.contracts import (
    WhatsAppMessageEvent,
    WhatsAppProviderError,
    WhatsAppTextRequest,
)
from app.integrations.whatsapp.platform_number import (
    is_platform_number,
    platform_agent_number,
)
from app.integrations.whatsapp.provider import WhatsAppProvider
from app.integrations.whatsapp.registry import get_whatsapp_provider
from app.models import AppointmentCandidate, AgentChannelMessage, OperatorActionCandidate, PassiveEscalation, Professional, User
from app.services import agent_binding, daily_agenda, scheduling
from app.services.assistant_settings import get_assistant_settings

logger = logging.getLogger(__name__)


def _mask_phone(phone: str | None) -> str:
    if not phone:
        return "***"
    return f"***{phone[-4:]}" if len(phone) >= 4 else "***"

NEXT_SESSION_SEARCH_DAYS = 90
WHATSAPP_CHANNEL = "whatsapp"
HISTORY_MAX_AGE = timedelta(hours=12)

CONFIRM_WORDS = {"sim", "confirmar", "confirmo", "confirma", "ok"}
REJECT_WORDS = {"nao", "cancelar", "cancela", "cancelo"}


def normalize_command(text: str) -> str:
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return " ".join(stripped.strip().casefold().split())


def _participants_label(occurrence) -> str:
    names = [p.contact_name for p in occurrence.participants]
    return ", ".join(names) if names else occurrence.source_label


def _format_day_list(occurrences, header: str, empty_message: str) -> str:
    if not occurrences:
        return f"{header}\n\n{empty_message}"
    lines = [
        f"{occurrence.starts_at.strftime('%H:%M')} — {_participants_label(occurrence)}"
        for occurrence in occurrences
    ]
    return header + "\n\n" + "\n".join(lines)


def _handle_hoje(db: Session, professional_id: uuid.UUID) -> str:
    professional = db.get(Professional, professional_id)
    if professional is None:
        return "Nao foi possivel localizar a conta da agenda."
    today = datetime.now(daily_agenda.get_professional_timezone(professional)).date()
    _, items = daily_agenda.list_daily_agenda_items(db, professional_id, today)
    return daily_agenda.format_daily_agenda(today, items)


def _handle_amanha(db: Session, professional_id: uuid.UUID) -> str:
    tomorrow = datetime.now(scheduling.TIMEZONE).date() + timedelta(days=1)
    occurrences = scheduling.list_schedule_occurrences(db, professional_id, tomorrow, tomorrow)
    return _format_day_list(occurrences, "Aulas de amanha", "Nenhuma aula amanha.")


def _handle_esta_semana(db: Session, professional_id: uuid.UUID) -> str:
    today = datetime.now(scheduling.TIMEZONE).date()
    end_of_week = today + timedelta(days=6 - today.weekday())
    occurrences = scheduling.list_schedule_occurrences(db, professional_id, today, end_of_week)
    return _format_day_list(occurrences, "Aulas desta semana", "Nenhuma aula esta semana.")


def _handle_proxima_aula(db: Session, professional_id: uuid.UUID) -> str:
    now = datetime.now(scheduling.TIMEZONE)
    occurrences = scheduling.list_schedule_occurrences(
        db, professional_id, now.date(), now.date() + timedelta(days=NEXT_SESSION_SEARCH_DAYS)
    )
    for occurrence in occurrences:
        if occurrence.ends_at <= now:
            continue
        when = occurrence.starts_at.strftime("%d/%m as %H:%M")
        return f"Proxima aula\n\n{when} — {_participants_label(occurrence)}"
    return "Nenhuma aula futura encontrada nos proximos 90 dias."


COMMANDS = {
    "hoje": _handle_hoje,
    "amanha": _handle_amanha,
    "esta semana": _handle_esta_semana,
    "proxima aula": _handle_proxima_aula,
}


def _resolve_actor_user(db: Session, professional_id: uuid.UUID) -> User | None:
    """The WhatsApp agent number has no login session — mutations are
    attributed to the professional's own operator account. Exactly one is
    expected per tenant (multi-tenancy roadmap Phase B)."""
    return (
        db.query(User)
        .filter(User.professional_id == professional_id, User.role == "professional")
        .first()
    )


def _latest_pending_candidate(
    db: Session, professional_id: uuid.UUID
) -> OperatorActionCandidate | None:
    escalation_candidate = (
        db.query(OperatorActionCandidate)
        .join(AppointmentCandidate, AppointmentCandidate.operator_action_candidate_id == OperatorActionCandidate.id)
        .join(PassiveEscalation, PassiveEscalation.appointment_candidate_id == AppointmentCandidate.id)
        .filter(
            PassiveEscalation.professional_id == professional_id,
            PassiveEscalation.status == "sent",
            OperatorActionCandidate.status == "proposed",
        )
        .order_by(PassiveEscalation.sent_at.desc())
        .first()
    )
    if escalation_candidate is not None:
        return escalation_candidate
    return (
        db.query(OperatorActionCandidate)
        .filter(
            OperatorActionCandidate.professional_id == professional_id,
            OperatorActionCandidate.channel == WHATSAPP_CHANNEL,
            OperatorActionCandidate.status == "proposed",
        )
        .order_by(OperatorActionCandidate.created_at.desc())
        .first()
    )


def _pending_candidates_for_turn(
    db: Session, professional_id: uuid.UUID, correlation_id: uuid.UUID
) -> list[OperatorActionCandidate]:
    """A single instructor turn can produce more than one proposal — e.g.
    "cancela as duas aulas de hoje" makes the model call propose_cancel_schedule
    once per occurrence. All proposals from one run_agent_turn() call share
    its correlation_id, so that's the grouping key for "confirm everything
    this turn proposed" instead of just the most recently created row."""
    return (
        db.query(OperatorActionCandidate)
        .filter(
            OperatorActionCandidate.professional_id == professional_id,
            OperatorActionCandidate.channel == WHATSAPP_CHANNEL,
            OperatorActionCandidate.status == "proposed",
            OperatorActionCandidate.correlation_id == correlation_id,
        )
        .order_by(OperatorActionCandidate.created_at.asc())
        .all()
    )


def _load_history(db: Session, professional_id: uuid.UUID) -> list[dict[str, str]]:
    """Recent turns only. Bounded by age as well as by message count: unlike
    the web chat (whose history lives in the browser tab and dies on reload),
    this history is persisted server-side forever, so a count-only window can
    carry days-old turns into the context. Relative dates are the reason this
    matters — an assistant turn saying "amanhã, dia 9 de agosto" from last
    week makes the model answer today's "e amanhã?" for the wrong date."""
    window = get_assistant_settings(db, professional_id).memory_window_messages
    cutoff = datetime.now(scheduling.TIMEZONE) - HISTORY_MAX_AGE
    rows = (
        db.query(AgentChannelMessage)
        .filter(
            AgentChannelMessage.professional_id == professional_id,
            AgentChannelMessage.created_at >= cutoff,
        )
        .order_by(AgentChannelMessage.created_at.desc())
        .limit(window)
        .all()
    )
    return [{"role": row.role, "content": row.content} for row in reversed(rows)]


def _record_turn(db: Session, professional_id: uuid.UUID, role: str, content: str) -> None:
    db.add(AgentChannelMessage(professional_id=professional_id, role=role, content=content))
    db.commit()


def _handle_confirmation_reply(
    db: Session, professional: Professional, actor_user_id: uuid.UUID, command: str
) -> str:
    latest = _latest_pending_candidate(db, professional.id)
    if latest is None:
        return "Nao ha nenhuma acao pendente de confirmacao no momento."

    # Resolve the full group sharing this turn's correlation_id, not just
    # the most recent row — a single instructor request ("cancela as duas
    # aulas de hoje") can produce more than one pending proposal, and all of
    # them must be confirmed/rejected together or one silently never applies.
    group = _pending_candidates_for_turn(db, professional.id, latest.correlation_id)

    if command in CONFIRM_WORDS:
        summaries = []
        for candidate in group:
            try:
                result = candidates.confirm(db, professional.id, actor_user_id, candidate.id)
            except candidates.CandidateNotPendingError as exc:
                summaries.append(f"Ja nao estava mais pendente (status={exc.status}).")
                continue
            summaries.append(result.summary if result.ok else f"Falhou: {result.summary}")
        return "\n".join(summaries)

    for candidate in group:
        candidates.reject(db, professional.id, actor_user_id, candidate.id)
    return "Acao cancelada." if len(group) == 1 else f"{len(group)} acoes canceladas."


def _handle_agent_turn(
    db: Session, professional: Professional, actor_user_id: uuid.UUID, text: str
) -> str:
    messages = _load_history(db, professional.id) + [{"role": "user", "content": text}]
    response = run_agent_turn(
        db, professional.id, actor_user_id, messages, channel=WHATSAPP_CHANNEL
    )
    reply = response.reply
    if response.pending_candidate is not None:
        # response.pending_candidate only carries the first proposal's own
        # id, not its correlation_id — look the row up to get the actual
        # grouping key, then show every proposal from this turn, not just
        # the first (see _handle_confirmation_reply for why this matters).
        pending_row = (
            db.query(OperatorActionCandidate)
            .filter(OperatorActionCandidate.id == response.pending_candidate.id)
            .first()
        )
        proposals = (
            _pending_candidates_for_turn(db, professional.id, pending_row.correlation_id)
            if pending_row is not None
            else []
        )
        previews = [proposal.preview_text for proposal in proposals] or [
            response.pending_candidate.preview_text
        ]
        advisories = [
            proposal.resolved_arguments.get("journey_advisory")
            for proposal in proposals
            if proposal.resolved_arguments.get("journey_advisory")
        ]
        if not advisories and response.pending_candidate.advisory_text:
            advisories = [response.pending_candidate.advisory_text]
        advisory_body = "\n".join(advisories)
        advisory_text = f"\n\n{advisory_body}" if advisory_body else ""
        reply = (
            f"{reply}\n\n" + "\n".join(previews) + advisory_text + "\n\n"
            "Responda *sim* para confirmar ou *nao* para cancelar."
        )
    return reply


def send_text_message(from_phone: str, to_phone: str, body: str) -> None:
    """Compatibility helper for direct callers; production injects a provider."""
    get_whatsapp_provider().send_text(
        WhatsAppTextRequest(from_phone=from_phone, to_phone=to_phone, body=body)
    )


def _send_reply(
    provider: WhatsAppProvider | None,
    from_phone: str,
    to_phone: str,
    body: str,
    professional_id: uuid.UUID,
) -> None:
    try:
        if provider is None:
            send_text_message(from_phone=from_phone, to_phone=to_phone, body=body)
        else:
            provider.send_text(
                WhatsAppTextRequest(from_phone=from_phone, to_phone=to_phone, body=body)
            )
    except WhatsAppProviderError:
        logger.exception(
            "Failed to send private-agent WhatsApp reply (professional_id=%s)",
            professional_id,
        )


def try_handle(
    db: Session,
    normalized: WhatsAppMessageEvent,
    provider: WhatsAppProvider | None = None,
) -> bool:
    """If this inbound message is addressed to the shared platform agent
    number, answer it and return True. A message to that number from an
    unrecognized sender is claimed and dropped (still True) so it never
    reaches the customer-facing pipeline. Anything else returns False."""
    if normalized.direction != "inbound":
        return False

    if not is_platform_number(normalized.to_phone):
        return False
    platform_number = platform_agent_number()

    # ingestion.py imports this module at load time, so resolve its tenant
    # lookup lazily to avoid an import cycle. The sender is the resolution
    # key: get_professional_by_phone matches from_phone against an active
    # tenant's assistant_phone, so resolution *is* authorization.
    from app.chat.ingestion import get_professional_by_phone

    professional = get_professional_by_phone(db, normalized.from_phone)
    if professional is None:
        logger.warning(
            "Dropped agent-channel message from unrecognized sender %s",
            _mask_phone(normalized.from_phone),
        )
        return True

    text = normalized.text or ""
    command = normalize_command(text)
    actor_user = _resolve_actor_user(db, professional.id)

    # Second factor: normal handling is gated on a confirmed binding. Until
    # then the only message this channel acts on is the binding code the
    # instructor got in their authenticated web session; everything else from
    # an unbound tenant is claimed and silently dropped.
    if professional.agent_binding_confirmed_at is None:
        if actor_user is not None and agent_binding.confirm_from_message(
            db, professional, actor_user.id, text
        ):
            _send_reply(
                provider,
                platform_number,
                normalized.from_phone,
                "Assistente ativado neste numero. Pode me enviar comandos por aqui.",
                professional.id,
            )
        else:
            logger.warning(
                "Dropped agent-channel message for unbound tenant %s", professional.id
            )
        return True

    logger.info(
        "agent-channel turn resolved to tenant %s (sender %s)",
        professional.id,
        _mask_phone(normalized.from_phone),
    )

    if command in COMMANDS:
        reply = COMMANDS[command](db, professional.id)
    elif actor_user is None:
        reply = "Nenhum usuario operador configurado para esta conta."
    elif command in CONFIRM_WORDS or command in REJECT_WORDS:
        reply = _handle_confirmation_reply(db, professional, actor_user.id, command)
        _record_turn(db, professional.id, "user", text)
        _record_turn(db, professional.id, "assistant", reply)
    else:
        reply = _handle_agent_turn(db, professional, actor_user.id, text)
        _record_turn(db, professional.id, "user", text)
        _record_turn(db, professional.id, "assistant", reply)

    _send_reply(provider, platform_number, normalized.from_phone, reply, professional.id)
    return True

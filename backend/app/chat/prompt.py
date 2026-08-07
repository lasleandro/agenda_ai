"""Extraction prompt for the scheduling LLM.

All instructions are in pt-BR as per brief Section 9 (Localization).
The model receives a conversation window and must return a structured SchedulingEvent.
"""

from zoneinfo import ZoneInfo

EXTRACTION_SYSTEM_PROMPT = """\
Voce e um extrator estruturado de eventos de agendamento.

Sua tarefa: analisar a conversa fornecida e extrair APENAS decisoes de agendamento \
(aulas, compromissos, horarios) entre um profissional e seu cliente.

REGRAS:
1. Todas as mensagens de entrada estao em portugues do Brasil (pt-BR).
2. Infera APENAS acoes relacionadas a agendamento. Ignore assuntos nao relacionados.
3. Distinga PROPOSTAS de CONFIRMACOES. Uma proposta sem confirmacao NAO e um agendamento confirmado.
4. Resolva datas relativas usando o timestamp de cada mensagem e o fuso horario do profissional.
5. NAO invente informacoes ausentes. Se um campo nao puder ser determinado, deixe como null.
6. Extraia TODOS os eventos de agendamento distintos presentes na conversa.
   Retorne um item por evento. Quando nao houver evento, retorne somente um
   item com action="none".
7. Cite APENAS IDs de mensagens presentes na entrada como evidencia.
8. Identifique ambiguidades nao resolvidas (ex: "as 5" pode ser 5h ou 17h).
9. NAO crie eventos recorrentes a menos que a recorrencia seja EXPLICITA na conversa.
10. Prefira incerteza a um falso positivo com alta confianca.

CONVENCOES DE TEMPO pt-BR:
- "amanha" = dia seguinte ao timestamp da mensagem
- "depois de amanha" = dois dias apos o timestamp
- "semana que vem" = proxima semana
- "as 5" no contexto de aula = geralmente 17:00 (dominio esportivo)
- "horario de sempre" / "mesmo horario" = requer contexto de agendamentos anteriores
- "proxima sexta" = a proxima sexta-feira a partir do timestamp
- "hoje" = mesmo dia do timestamp
- Formato de data BR: dd/mm/aa

RESPONDA EXCLUSIVAMENTE com o schema JSON estruturado fornecido, no formato
{"events": [...]}. Nao inclua texto fora do JSON.
"""

EXTRACTION_USER_PROMPT_TEMPLATE = """\
CONVERSA:
{conversation_text}

CONTEXTO DO PROFISSIONAL:
- Fuso horario: {timezone}
- Duracao padrao da aula: {default_duration_minutes} minutos
- Servico padrao: {service}

HORARIO ATUAL: {current_time}

{upcoming_appointments_section}

Analise a conversa acima e extraia todos os eventos de agendamento distintos
(ou um unico item action="none" se nao houver).
"""


def build_conversation_text(messages: list, timezone: str) -> str:
    """Format messages into a readable conversation string for the prompt."""
    local_timezone = ZoneInfo(timezone)
    lines = []
    for msg in messages:
        direction = "Cliente" if msg.direction == "inbound" else "Profissional"
        sent_at = msg.sent_at.astimezone(local_timezone)
        lines.append(
            f"[{msg.id}] {direction} ({sent_at.strftime('%d/%m/%Y %H:%M')}): {msg.text}"
        )
    return "\n".join(lines)


def build_upcoming_appointments_section(appointments: list) -> str:
    """Format upcoming appointments for context."""
    if not appointments:
        return "AGENDAMENTOS FUTUROS DO CLIENTE: nenhum"
    lines = ["AGENDAMENTOS FUTUROS DO CLIENTE:"]
    for appt in appointments:
        lines.append(
            f"- ID: {appt.id} | {appt.start_at.strftime('%d/%m %H:%M')} - "
            f"{appt.end_at.strftime('%H:%M')} | {appt.service or 'aula'}"
        )
    return "\n".join(lines)


def build_extraction_prompt(conversation_window) -> tuple[str, str]:
    """Build the system and user prompts for a given conversation window.

    Returns:
        (system_prompt, user_prompt) tuple.
    """
    conversation_text = build_conversation_text(
        conversation_window.messages, conversation_window.professional.timezone
    )
    upcoming_section = build_upcoming_appointments_section(
        conversation_window.upcoming_appointments
    )

    user_prompt = EXTRACTION_USER_PROMPT_TEMPLATE.format(
        conversation_text=conversation_text,
        timezone=conversation_window.professional.timezone,
        default_duration_minutes=conversation_window.professional.default_duration_minutes,
        service=conversation_window.professional.service,
        current_time=conversation_window.current_time.astimezone(
            ZoneInfo(conversation_window.professional.timezone)
        ).strftime("%Y-%m-%d %H:%M %Z"),
        upcoming_appointments_section=upcoming_section,
    )

    return EXTRACTION_SYSTEM_PROMPT, user_prompt

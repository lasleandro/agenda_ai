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
3. Retorne DUAS dimensoes independentes para cada evento:
   - operation: a operacao discutida (create, reschedule, cancel, recurrence,
     waitlist_request ou none).
   - confirmation_status: instructor_confirmed quando o profissional afirma
     claramente que uma operacao especifica esta confirmada;
     customer_confirmed quando somente o cliente confirma;
     mutually_confirmed quando ambos confirmam claramente;
     unclear quando existe uma afirmacao de confirmacao cujo sentido ou
     referente nao pode ser determinado com seguranca; e not_confirmed quando
     ha proposta, pedido ou operacao sem confirmacao.
   A confirmacao explicita do profissional e suficiente: NAO exija acordo
   mutuo. "Confirmado", "fechado entao" e "ok, te espero" contam apenas
   quando se referem claramente a uma operacao e horario especificos.
   Um PEDIDO, PERGUNTA ou PROPOSTA do cliente por um horario NOVO (mesmo em
   tom decisivo, com ou sem ponto de interrogacao) NUNCA conta, sozinho,
   como confirmacao do cliente — apenas uma resposta do cliente ACEITANDO
   uma oferta do profissional conta. Veja EXEMPLOS abaixo: a classificacao
   correta depende de quem, na conversa, usou linguagem de ACEITE (nao de
   pedido), e siga os exemplos de perto para casos parecidos.
   "Deixa eu ver", "vou confirmar depois" e um "beleza" isolado (sem outra
   palavra de confirmacao) nao sao confirmacoes explicitas.

EXEMPLOS DE CONFIRMATION_STATUS (situacoes sinteticas, use como guia direto):
- Cliente pergunta/pede um horario novo ("Da pra ser amanha as 10h?",
  "Bora fechar toda sexta as 9h?") e o profissional responde com aceite
  claro ("Da sim.", "Fechado.") -> instructor_confirmed. O pedido do
  cliente NAO e aceite, mesmo que decisivo; so a resposta do profissional
  confirma.
- Profissional oferece um horario concreto ("Consigo sexta as 9h.") e o
  cliente aceita explicitamente ("Perfeito, pode ser.", "Otimo.") ->
  mutually_confirmed. A oferta do profissional ja e o compromisso dele; o
  aceite do cliente fecha o acordo dos dois lados.
- Profissional oferece um horario e o cliente nao responde, ou so faz uma
  pergunta de volta -> not_confirmed.
- Cliente decide cancelar ou pede para remarcar um compromisso que JA TEM
  ("Nao vou poder ir amanha, pode cancelar.") -> customer_confirmed, mesmo
  sem resposta do profissional — cancelar/remarcar o proprio compromisso e
  decisao unilateral do cliente, ao contrario de criar um compromisso novo
  (que consome o tempo do profissional e por isso exige a palavra dele).
- Cliente propoe um horario e o profissional responde so com um "beleza"
  isolado, sem outra palavra de confirmacao -> unclear.
- Cliente pergunta se pode manter/repetir um horario ou dia HABITUAL
  ("Mesmo horario de sempre semana que vem?", "Bora manter toda terca as
  18h?") e o profissional responde com aceite claro ("Sim.", "Fechado.")
  -> instructor_confirmed, NAO mutually_confirmed. Continuar um habito ou
  recorrencia ja existente ainda exige a palavra do profissional para
  aquela ocorrencia especifica, exatamente como um pedido de horario novo
  — o fato de ja ser um habito NAO torna o pedido do cliente, por si so,
  uma confirmacao.
4. Resolva datas relativas usando o timestamp de cada mensagem e o fuso horario do profissional.
5. NAO invente informacoes ausentes. Se um campo nao puder ser determinado, deixe como null.
6. Extraia TODOS os eventos de agendamento distintos presentes na conversa.
   Retorne um item por evento. Quando nao houver evento, retorne somente um
   item com operation="none" e confirmation_status="not_confirmed".
7. Cite APENAS IDs de mensagens presentes na entrada como evidencia.
8. Identifique ambiguidades nao resolvidas (ex: "as 5" pode ser 5h ou 17h).
9. NAO crie eventos recorrentes a menos que a recorrencia seja EXPLICITA na conversa.
10. Prefira incerteza a um falso positivo com alta confianca.
11. Use operation="waitlist_request" quando o profissional disser ao cliente que \
NAO tem horario disponivel no momento e que vai avisar quando abrir (ex: \
"no momento nao tenho horario", "te aviso quando abrir uma vaga", "essa \
semana ta lotado, mas te chamo"). Isso e diferente de operation="none": aqui \
existe uma demanda real do cliente que ainda nao foi atendida. Se o cliente \
mencionou um dia/horario especifico que gostaria (ex: "eu queria terca a \
noite"), preencha start_at/end_at com esse horario desejado. Se nenhum \
horario especifico foi mencionado, deixe start_at/end_at como null e \
registre uma ambiguidade de campo "date" ou "time" explicando que o \
profissional revisara e completara o horario desejado manualmente — ainda \
   assim retorne o evento com operation="waitlist_request", nao operation="none", \
pois a demanda em si foi detectada mesmo sem horario exato.
12. Um pedido ou proposta ISOLADA do cliente para uma aula NOVA, sem
NENHUMA resposta do profissional confirmando horario ou operacao, NAO
configura operation="create" — retorne operation="none" (ha apenas uma
pergunta em aberto, nao uma decisao de agendamento). Isso vale mesmo que o
horario mencionado seja resolvivel pelas convencoes de tempo abaixo:
resolver o horario nao equivale a confirmar a operacao. Ja uma mensagem que
se refere de forma clara e inambigua a um agendamento EXISTENTE do cliente
(listado em AGENDAMENTOS FUTUROS DO CLIENTE) para cancelar ou remarcar
configura a operacao correspondente (cancel/reschedule) mesmo sem resposta
do profissional — a intencao do cliente sobre um compromisso ja existente
e, por si so, o evento relevante. Excecao: se essa MESMA mensagem do
cliente tambem mencionar outro agendamento existente distinto (por nome de
dia, horario ou servico) que NAO deve ser alterado (ex: "mantem terca, so
cancela quinta" — dois agendamentos citados na mesma frase, um mantido e
outro cancelado), use confirmation_status="not_confirmed" em vez de
customer_confirmed para o evento de cancelamento/remarcacao, mesmo que a
frase pareca clara — mencionar mais de um agendamento na mesma mensagem
cria risco de troca entre eles, entao exija confirmacao explicita do
profissional antes de considerar confirmado.

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
(ou um unico item operation="none" se nao houver).
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

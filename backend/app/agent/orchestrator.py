"""
Instructor agent orchestrator (operational ontology roadmap v0.2, Phase 2
read tools; Phase 3 propose/confirm plumbing for write tools).

A manual tool-call loop against Azure OpenAI's native function-calling wire
format (not `instructor`'s structured-JSON mode, which is for single-shot
extraction — see `app/services/azure_openai.py`).

Read tools (`tools.TOOL_DISPATCH`) execute immediately. Write tools
(`mutations.MUTATION_TOOL_DISPATCH`, empty until Phase 4) never write
directly — they call `app.agent.candidates.propose(...)` and return a
`requires_confirmation` result. When that happens, this loop stops calling
further tools, forces one final text-only completion so the model can
phrase a natural confirmatory reply, and surfaces the candidate's
*deterministic* preview to the caller — the UI renders and executes from
that structured preview, never from the model's prose.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.agent.mutations import MUTATION_TOOL_DISPATCH, MUTATION_TOOL_SPECS
from app.agent.tools import TOOL_DISPATCH, TOOL_SPECS
from app.services.assistant_settings import get_assistant_settings
from app.services.azure_openai import get_azure_client, get_model_name
from app.services.scheduling import TIMEZONE

MAX_TOOL_ITERATIONS = 6
ALL_TOOL_SPECS = TOOL_SPECS + MUTATION_TOOL_SPECS

SYSTEM_PROMPT_TEMPLATE = """Você é o assistente interno de agenda de um professor autônomo (instrutor). \
Você responde apenas ao próprio professor, nunca a clientes.

Data e hora atuais (fuso horário do professor, {tz}): {now}.

Regras invioláveis:
- Ferramentas de leitura (search_*, find_*, get_*) executam na hora. \
Ferramentas de escrita (propose_*) NUNCA alteram nada diretamente — elas \
apenas criam uma proposta que o professor precisa confirmar explicitamente \
na interface. Nunca diga que algo foi alterado, cancelado ou criado a \
partir de uma ferramenta propose_* — apenas descreva o que será feito e \
que aguarda confirmação.
- Nunca invente nomes, horários, locais ou disponibilidade que não vieram \
de uma chamada de ferramenta. Se uma ferramenta não retornar dados \
suficientes, diga isso claramente.
- Para qualquer expressão de data relativa ("hoje", "amanhã", "terça que \
vem", "de tarde" etc.), sempre chame a ferramenta resolve_date_phrase — \
nunca calcule datas por conta própria.
- Expressões que cobrem uma semana inteira ("essa semana", "próxima \
semana", "semana que vem") fazem resolve_date_phrase retornar date_from/ \
date_to (segunda a domingo) em vez de date — nesse caso use date_from/ \
date_to diretamente em get_schedule. find_instructor_openings só aceita uma \
data por chamada; se o professor pedir horários vagos da semana toda, chame \
find_instructor_openings uma vez para cada dia do intervalo (no máximo 7 \
dias) e combine os resultados.
- Cada item retornado por get_schedule/get_next_session traz o campo \
booleano is_past (verdadeiro se o horário já terminou em relação à hora \
atual informada acima) — use esse campo em vez de calcular você mesmo. Ao \
responder sobre um dia que inclui o momento atual (tipicamente "hoje"), \
separe claramente o que já aconteceu do que ainda vai acontecer (por \
exemplo, em duas listas "já realizadas" e "próximas"), e se o professor \
perguntar apenas "quem tenho marcado hoje" sem especificar, inclua ambas \
as partes do dia deixando claro qual já passou.
- Sempre mencione o local (place_name) de cada aula ou compromisso quando \
a ferramenta retornar essa informação — não omita o local por padrão.
- Ao buscar um contato, local ou grupo por nome, se a busca retornar zero \
ou mais de um resultado, peça esclarecimento ao professor em vez de \
adivinhar.
- find_instructor_openings retorna os horários realmente livres do dia: a \
jornada de trabalho do professor menos todos os compromissos já marcados. \
Use-a quando o professor perguntar de forma aberta quando está livre. \
Quando ele já der uma data/hora específica para marcar, chame \
propose_create_appointment diretamente (ela valida jornada e conflitos de \
verdade).
- find_instructor_openings quase sempre retorna VÁRIAS janelas livres no \
mesmo dia — liste TODAS elas na resposta, nunca apenas a primeira ou a \
maior.
- Cada janela de find_instructor_openings traz uma lista "places" com os \
locais cuja disponibilidade recorrente cobre aquele horário. Essa lista pode \
vir vazia: o horário continua livre e válido para agendar — apenas nenhum \
local tem janela cadastrada nele, então pergunte ao professor qual local usar \
antes de propor. NUNCA trate "places" vazio como ausência de horário livre.
- Se find_instructor_openings retornar "openings" vazio, a resposta traz uma \
"note" explicando o motivo (sem jornada de trabalho cadastrada para aquele \
dia da semana, ou dia totalmente ocupado) — repasse esse motivo ao professor \
em vez de dizer genericamente que não há horários.
- propose_create_appointment exige um local (place_id). Se o professor não \
especificou o local e o contato não tem local padrão, pergunte qual local \
antes de propor — nunca conclua que não há disponibilidade só porque o \
local está faltando ou porque find_instructor_openings voltou vazio.
- Para adicionar um aluno a um compromisso avulso já existente (ex: "\
adiciona a Larissa na aula do Leandro amanhã 15h"), primeiro use get_schedule \
para localizar a ocorrência (source_type "appointment") e pegue seu \
source_id, depois chame propose_add_appointment_participant com esse ID — \
isso transforma o compromisso individual em um compromisso em grupo. Isso \
só vale para compromissos avulsos (appointment); para turmas recorrentes \
use propose_add_group_member com o recurring_slot_id.
- Cancelamento de aula em grupo tem duas ferramentas distintas — escolha com \
cuidado: propose_cancel_schedule cancela a ocorrência INTEIRA (ninguém tem \
aula naquele dia — chuva, feriado, instrutor doente); \
propose_note_participant_absence registra que APENAS UM aluno vai faltar, \
sem afetar a aula para o resto da turma. Quando o professor disser algo \
como "a Mariana não vai poder ir amanhã" sobre uma turma, use \
propose_note_participant_absence — NUNCA propose_cancel_schedule nesse \
caso, pois isso cancelaria a aula de todo o grupo e geraria crédito de \
reposição indevido para os demais alunos.
- Créditos de reposição são gerados automaticamente (se dentro do prazo de \
aviso configurado) quando uma falta de aluno recorrente é registrada via \
propose_note_participant_absence ou quando uma ocorrência de turma é \
cancelada via propose_cancel_schedule. Para agendar a reposição em si, \
primeiro chame list_makeup_credits para obter o credit_id real do aluno \
(nunca invente um credit_id), opcionalmente use recommend_makeup_slots para \
sugerir os melhores horários, e então chame propose_redeem_makeup_credit \
com o credit_id, local e horário escolhidos.
- Para marcar uma aula sem cobrança (aula teste, cortesia), passe \
billing_type="courtesy" em propose_create_appointment — reconheça pedidos \
como "aula teste", "cortesia", "de graça", "sem cobrar" mesmo que o \
professor não use a palavra exata "cortesia".
- Quando o professor não tiver horário disponível para um contato e quiser \
guardar esse pedido ("bota ela na fila", "avisa quando abrir horário"), \
use propose_add_waitlist_entry (Fila de Espera) — sempre com uma data e \
horário específicos informados pelo professor, nunca um pedido vago como \
"qualquer manhã"; se a data/horário não estiver clara, pergunte antes de \
propor. Para remover alguém da fila, primeiro chame list_waitlist_entries \
para obter o waitlist_entry_id real, nunca invente um. Fila de Espera é \
sobre demanda de agendamento — não confundir com o status comercial \
"Em espera" de um contato (assuntos financeiros, não de agenda).
- Quando o professor mencionar um compromisso que NÃO é uma aula com um \
cliente — arbitrar um torneio, dar um workshop ou clínica — use \
propose_create_event, nunca propose_create_appointment (que exige um \
cliente). Exemplo: "amanhã das 15 às 20h vou dar uma clínica, vou receber \
R$ 2000" → event_type="clinic", start_at/end_at conforme informado, \
income_cents=200000. Infira event_type pelo vocabulário: "arbitrar"/ \
"arbitragem"/"árbitro" → tournament_referee; "workshop"/"oficina" → \
workshop; "clínica" → clinic; caso contrário → other. income_cents e \
place_id são opcionais — só inclua o que o professor efetivamente disse, \
nunca invente um valor.
- Responda sempre em português, de forma direta e concisa."""


@dataclass
class ToolCallTrace:
    name: str
    arguments: dict[str, Any]
    result_summary: str


@dataclass
class PendingCandidate:
    id: uuid.UUID
    preview_text: str
    affected_entities: list[dict[str, Any]]
    expires_at: datetime


@dataclass
class AgentResponse:
    reply: str
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    pending_candidate: PendingCandidate | None = None


def _summarize_result(result: dict[str, Any]) -> str:
    serialized = json.dumps(result, ensure_ascii=False)
    if len(serialized) <= 200:
        return serialized
    return serialized[:200] + "…"


def _build_system_message(professional_id: uuid.UUID) -> dict[str, str]:
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M (%A)")
    return {
        "role": "system",
        "content": SYSTEM_PROMPT_TEMPLATE.format(tz=str(TIMEZONE), now=now),
    }


def _execute_tool_call(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    correlation_id: uuid.UUID,
    tool_name: str,
    arguments: dict[str, Any],
    channel: str,
) -> dict[str, Any]:
    read_implementation = TOOL_DISPATCH.get(tool_name)
    if read_implementation is not None:
        return read_implementation(db, professional_id, **arguments)

    mutation_implementation = MUTATION_TOOL_DISPATCH.get(tool_name)
    if mutation_implementation is not None:
        return mutation_implementation(
            db, professional_id, actor_user_id, correlation_id, channel=channel, **arguments
        )

    return {"error": f"Unknown tool '{tool_name}'"}


def run_agent_turn(
    db: Session,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    messages: list[dict[str, str]],
    channel: str = "web",
) -> AgentResponse:
    """Run one instructor turn: `messages` is the prior conversation
    (role/content pairs, oldest first, no system message — this function
    prepends its own) plus the latest user message."""
    client = get_azure_client()
    model = get_model_name()
    correlation_id = uuid.uuid4()
    settings = get_assistant_settings(db, professional_id)

    windowed_messages = messages[-settings.memory_window_messages :]
    conversation: list[dict[str, Any]] = [
        _build_system_message(professional_id),
        *windowed_messages,
    ]
    trace: list[ToolCallTrace] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.chat.completions.create(
            model=model,
            messages=conversation,
            tools=ALL_TOOL_SPECS,
            tool_choice="auto",
            temperature=settings.temperature,
        )
        choice = response.choices[0].message

        if not choice.tool_calls:
            return AgentResponse(reply=choice.content or "", tool_calls=trace)

        conversation.append(
            {
                "role": "assistant",
                "content": choice.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in choice.tool_calls
                ],
            }
        )

        pending_candidate: PendingCandidate | None = None
        for call in choice.tool_calls:
            tool_name = call.function.name
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}

            try:
                result = _execute_tool_call(
                    db, professional_id, actor_user_id, correlation_id, tool_name, arguments, channel
                )
            except Exception as exc:  # noqa: BLE001 — surface as a tool error, not a crash
                result = {"error": f"Tool execution failed: {exc}"}

            trace.append(
                ToolCallTrace(
                    name=tool_name,
                    arguments=arguments,
                    result_summary=_summarize_result(result),
                )
            )
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

            if result.get("requires_confirmation") and pending_candidate is None:
                pending_candidate = PendingCandidate(
                    id=uuid.UUID(result["candidate_id"]),
                    preview_text=result["preview_text"],
                    affected_entities=result["affected_entities"],
                    expires_at=datetime.fromisoformat(result["expires_at"]),
                )

        if pending_candidate is not None:
            # Don't let the model chain another tool call (e.g. a second
            # proposal) in the same turn — force a text-only closing reply.
            final = client.chat.completions.create(
                model=model,
                messages=conversation,
                tools=ALL_TOOL_SPECS,
                tool_choice="none",
                temperature=settings.temperature,
            )
            return AgentResponse(
                reply=final.choices[0].message.content or "",
                tool_calls=trace,
                pending_candidate=pending_candidate,
            )

    return AgentResponse(
        reply="Desculpe, não consegui concluir a consulta — tente reformular a pergunta.",
        tool_calls=trace,
    )

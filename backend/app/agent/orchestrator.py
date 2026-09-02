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
- Se resolve_date_phrase retornar recognized=false com ambiguity_reason/ \
alternatives, faça UMA pergunta objetiva de esclarecimento listando as \
alternativas retornadas (ex: "Você quer hoje, 28/08, ou a próxima sexta, \
04/09?"). NUNCA escolha uma data por conta própria depois de um resultado \
ambíguo ou não resolvido.
- Expressões que cobrem uma semana inteira ("essa semana", "próxima \
semana", "semana que vem") fazem resolve_date_phrase retornar date_from/ \
date_to (segunda a domingo) em vez de date — nesse caso use date_from/ \
date_to diretamente em get_schedule. Expressões de mês ("esse mês", "mês \
que vem") também retornam date_from/date_to; se o intervalo passar do limite \
de 31 dias do get_schedule, divida em chamadas menores. \
find_instructor_openings só aceita uma \
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
propose_create_appointment diretamente (ela valida conflitos reais e pode \
sinalizar uma exceção à jornada configurada antes da confirmação).
- Se o professor perguntar por uma hora específica que pode já estar ocupada \
(por exemplo, "tem algo às 18h para a Ana?"), consulte também \
find_group_openings nessa data/hora antes de concluir que não há opção. \
Uma turma com vaga não é horário livre: informe a turma e as vagas e peça o \
escopo, somente essa aula ou todas as semanas.
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
- A jornada de trabalho é uma preferência para recomendações, não um bloqueio. \
Se uma solicitação específica estiver fora da jornada ou durante uma pausa, \
propose_create_appointment ainda pode criar a confirmação quando não houver \
conflito real; destaque o aviso retornado e deixe o professor decidir.
- Quando o professor perguntar sobre vagas, lugares ou capacidade EM \
grupos/turmas (ex: "quais vagas tenho em grupos à noite?", "quais turmas têm \
vaga amanhã?", "existe grupo com lugar para Fernanda sexta?"), resolva a data \
aplicável e chame find_group_openings PRIMEIRO. NUNCA chame \
find_instructor_openings como resposta a uma pergunta de capacidade de grupo — \
uma turma com vaga é um compromisso agendado, não tempo livre do professor. \
Pergunta de vagas em grupo sem data explícita é interpretada como HOJE; se a \
data não puder ser resolvida, pergunte ao professor. Resuma cada turma com vaga \
como "<grupo>, <local>, <horário>, <alunos>/<capacidade>, <vagas restantes>". \
Se não houver turmas com vaga, diga apenas que não há turmas com vagas; não \
mencione ausência de jornada de trabalho, a menos que o professor também tenha \
perguntado sobre tempo livre.
- propose_create_appointment pode receber um local (place_id), mas o herda \
automaticamente quando exatamente uma permanência cobre todo o horário. Se \
não houver exatamente uma permanência, peça que o professor escolha o local; \
nunca use o local padrão do contato como prova de disponibilidade. Um local \
informado fora da permanência deve aparecer como exceção explícita na confirmação.

- Para promover um compromisso avulso individual a uma vaga de turma (ex: "\
transforma a aula da Maria amanhã 18h em turma para 3 alunos"), primeiro use \
get_schedule para localizar a ocorrência (source_type "appointment") e pegue \
seu source_id, depois chame propose_set_appointment_format com esse ID e a \
capacidade pedida. Isso preserva a aula e o aluno já marcado; só vale para \
compromissos avulsos (appointment).
- Para transformar apenas uma data de uma aula recorrente, use \
propose_set_occurrence_class_format com o source_type, source_id e a data \
de get_schedule. Nunca use essa ferramenta quando o pedido for para todas as \
semanas; confirme o escopo se a frase não o deixar claro.
- Para abrir uma turma vazia (ex: "abra uma turma toda terça às 18h no \
Clube"), resolva o local e use propose_create_group_slot. Confirme se ela é \
avulsa ou semanal quando isso não estiver claro; a confirmação deve deixar \
explícito que começa com 0 alunos e ocupa a agenda.
- REGRA DE PRECEDÊNCIA para formato de aula: quando o professor nomeia \
exatamente um cliente e pede para agendar esse cliente, use \
propose_create_appointment com class_type="individual". Se o texto também \
disser semanal/repetido (ex: "toda quinta", "semanal"), passe \
is_recurring=true. NUNCA abra uma turma apenas porque o pedido se repete \
semanalmente. Use propose_create_group_slot SOMENTE quando houver intenção \
explícita de "turma", "grupo", abrir capacidade ou equivalente. A intenção \
do cliente nomeado prevalece sobre o sinal de recorrência ao escolher o \
modelo de persistência; a recorrência só altera o recurrence_rule do \
compromisso. Exemplos: "Agenda Carlos amanhã às 19h" → \
propose_create_appointment(is_recurring=false, class_type=individual). \
"Agenda Carlos toda quinta às 19h" → \
propose_create_appointment(is_recurring=true, class_type=individual). \
"Abra uma turma toda quinta às 19h" → propose_create_group_slot(is_recurring=true). \
"Abra uma turma para Carlos e Ana toda quinta" → pergunte se é turma \
reorrente com roster ou compromissos individuais separados.
- Para adicionar um aluno a um compromisso avulso já existente (ex: "\
adiciona a Larissa na aula do Leandro amanhã 15h"), primeiro use get_schedule \
para localizar a ocorrência (source_type "appointment") e pegue seu \
source_id, depois chame propose_add_appointment_participant com esse ID — \
isso transforma o compromisso individual em um compromisso em grupo. Isso \
só vale para compromissos avulsos (appointment); para turmas recorrentes \
use propose_add_group_member com o recurring_slot_id.
- Quando o aluno quer participar de APENAS uma data de uma turma recorrente, \
use propose_add_group_occurrence_participant com o recurring_slot_id e a \
occurrence_date. Isso não o torna participante permanente. Só use \
propose_add_group_member quando o professor confirmar que a entrada é fixa.
- Para REMOVER um aluno, distinga o escopo pelo campo enrollment_scope de \
get_schedule e pela fala do professor: se enrollment_scope="occurrence" e o \
pedido for "tira só dessa aula", use propose_remove_group_occurrence_participant. \
Se enrollment_scope="series" e o aluno apenas faltar a uma data, use \
propose_note_participant_absence. Se enrollment_scope="series" e o professor \
disser que o aluno está saindo da turma fixa, use propose_remove_group_member. \
Se o escopo não estiver claro, pergunte "É só nesta aula ou ela vai sair da \
turma fixa?". NUNCA use propose_note_participant_absence para um convidado \
avulso (enrollment_scope="occurrence") — remover esse convidado é a operação \
correta de capacidade e presença.
- Para localizar uma turma PARA ADICIONAR um aluno novo (ex.: "adicione \
Fernanda na turma de sexta às 18h"), primeiro resolva Fernanda com \
search_contacts e a data com resolve_date_phrase; depois use \
find_group_openings com essa data e start_time. NUNCA passe o contact_id de \
Fernanda em find_groups(member_contact_id): esse filtro procura apenas \
turmas das quais ela JÁ é membro e, por isso, exclui turmas vazias. Se houver \
uma turma com vaga, mostre-a e peça o escopo (somente essa aula ou todas as \
semanas) quando ele não estiver explícito. Use source_id retornado por \
find_group_openings como recurring_slot_id na proposta escolhida.
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
- Quando o professor perguntar se algum pedido da fila já cabe (ex: "achou \
vaga pra alguém da fila?"), chame find_waitlist_matches. Um match \
match_type="free_time" deve ir para propose_fulfill_waitlist_with_appointment \
(com o place_id do match); um match match_type="group_occurrence" deve ir \
para propose_fulfill_waitlist_with_group (com o source_id e occurrence_date \
do match) — pergunte "só essa aula ou turma fixa?" antes de escolher \
enrollment_scope quando o professor não tiver deixado claro. NUNCA faça \
propose_create_appointment seguido de propose_remove_waitlist_entry para \
atender um match: isso registra a demanda como cancelled, não fulfilled. \
"Coloca ela nessa turma" sobre um match de fila NUNCA significa cancelar o \
registro da fila. Só use propose_remove_waitlist_entry quando o professor \
disser explicitamente que a pessoa desistiu (ex: "tira ela da fila, ela \
desistiu").
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
- Quando o professor disser "pode seguir", "confirme", "confirme o local" \
ou equivalente para continuar uma proposta anterior, herde SOMENTE os \
detalhes ainda não resolvidos da proposta imediatamente anterior. NUNCA \
altere o cliente já resolvido, o formato de aula (individual/turma) ou a \
semântica de recorrência já estabelecida. Se Carlos foi nomeado como cliente \
e o formato era individual semanal, "pode seguir" mantém Carlos, individual \
e semanal — não pode converter para turma vazia.
- Quando a conversa incluir um bloco de "Contexto autoritativo de ações \
recentes", trate-o como a fonte da verdade sobre o que JÁ foi executado ou \
rejeitado. Pronomes e demonstrativos ("essa turma", "essa aula", "ele/ela", \
"aquele horário") só podem usar um ID desse bloco se houver EXATAMENTE uma \
entidade compatível. Uma proposta rejeitada ou falha NÃO estabelece entidade \
agendada — diga que a entidade não foi criada e consulte novamente se o \
professor quiser uma alternativa. Antes de um write, o ID confiável é apenas \
referência; a mutação ainda revalida tenancy, existência, data, capacidade e \
conflitos.
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
    advisory_text: str | None = None


@dataclass
class AgentResponse:
    reply: str
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    pending_candidate: PendingCandidate | None = None


@dataclass(frozen=True)
class RecentActionContext:
    status: str
    tool_name: str
    summary: str
    entities: list[dict[str, str]] = field(default_factory=list)


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


def _format_recent_action_context(contexts: list[RecentActionContext]) -> str:
    lines = ["Contexto autoritativo de ações recentes (não é prosa do usuário):"]
    for context in contexts:
        entity_bits = "; ".join(
            f"{entity['entity_type']}_id={entity['entity_id']}" for entity in context.entities
        )
        parts = [f"status={context.status}", f"tool={context.tool_name}"]
        if entity_bits:
            parts.append(entity_bits)
        parts.append(f"summary=\"{context.summary}\"")
        lines.append("- " + "; ".join(parts))
    return "\n".join(lines)


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
    recent_action_context: list[RecentActionContext] | None = None,
) -> AgentResponse:
    """Run one instructor turn: `messages` is the prior conversation
    (role/content pairs, oldest first, no system message — this function
    prepends its own) plus the latest user message. `recent_action_context`
    is server-resolved, trusted confirmation outcome injected ahead of the
    untrusted user history."""
    client = get_azure_client()
    model = get_model_name()
    correlation_id = uuid.uuid4()
    settings = get_assistant_settings(db, professional_id)

    windowed_messages = messages[-settings.memory_window_messages :]
    conversation: list[dict[str, Any]] = [_build_system_message(professional_id)]
    if recent_action_context:
        conversation.append(
            {
                "role": "system",
                "content": _format_recent_action_context(recent_action_context),
            }
        )
    conversation.extend(windowed_messages)
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
                    advisory_text=result.get("advisory_text"),
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

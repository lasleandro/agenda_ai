# Active Agent pt-BR Conversational Resilience Roadmap

**Version:** 0.1  
**Date:** 2026-08-23  
**Status:** Proposed  
**Scope:** Active instructor assistant in the web panel and instructor WhatsApp channel  
**Primary goal:** Make short, informal Brazilian Portuguese instructions route to the correct existing domain operation, preserve conversational continuity after confirmation, and refuse unsupported write scopes safely.

## 1. Executive summary

The active agent already has broad coverage for agenda reads, individual and group scheduling, make-up credits, waitlist entries, contact edits, and instructor events. The underlying services are generally stronger than the conversational surface: several actions already exist in the API/service layer but cannot be reached through agent tools.

This code-first audit found five material gaps:

1. **Relative-date correctness:** `resolve_date_phrase` misreads “depois de amanhã” as tomorrow and treats “próxima sexta” as today when today is Friday. Common explicit or relative expressions such as “dia 28”, “28/08”, “daqui a duas semanas”, and “mês que vem” are unresolved.
2. **Web-chat continuity after confirmation:** the browser renders the confirmed/rejected candidate result, but sends only the assistant prose on the next turn. The model does not receive the authoritative execution status, summary, candidate preview, or affected entity identifiers.
3. **Missing dated-participant removal:** the API can remove a sporadic participant from one group occurrence, but the active agent can only remove a permanent roster member from the entire recurring group.
4. **Incorrect waitlist completion path:** group and appointment fulfillment services exist, but the active agent has no fulfillment mutation. Current read-tool guidance tells the model to book and then remove the entry, which records the demand as `cancelled` instead of `fulfilled` and loses the fulfillment link.
5. **Unsupported series-scope writes:** cancellation and rescheduling tools intentionally affect one occurrence. Informal requests such as “cancela todas as sextas” or “muda essa turma pras 19h daqui pra frente” have no valid agent tool and no explicit prompt-level refusal/clarification contract.

The recommended sequence is correctness first: fix temporal misresolution and confirmation continuity, then expose already-supported domain operations, then add safe scope handling. This roadmap does not duplicate the separate [group-vacancy information-recovery roadmap](agent_group_vacancy_information_recovery_roadmap_v0.1_2026-08-23.md) or the [recurring individual-booking correction roadmap](agent_recurring_individual_booking_correction_roadmap_v0.1_2026-08-23.md).

## 2. Success criteria

The roadmap is complete when all of the following are true:

- Informal pt-BR phrases never silently target the wrong date; unsupported or ambiguous dates produce one concise clarification question.
- A web-chat follow-up after confirming or rejecting a proposal includes the authoritative outcome in the next agent request.
- “Tira a Fernanda só dessa sexta” can remove an occurrence-only guest without changing the permanent roster.
- A matched waitlist entry can be booked into either a one-off appointment or a group occurrence/series and ends as `fulfilled`, with the correct fulfillment reference.
- The agent distinguishes `occurrence`, `series`, and `future occurrences` before proposing a destructive or structural recurring-schedule change.
- Unsupported series-wide mutations are stated clearly and never downgraded silently to one occurrence.
- Informal prompt-routing tests cover realistic instructor language, including omitted accents and brief follow-ups.
- The active-agent regression suite passes with no stale response-schema assertions.

## 3. Audit method and evidence

The assessment used the current working tree rather than assumptions from older roadmaps:

- inventoried every schema in `backend/app/agent/tools.py` and `backend/app/agent/mutations.py`;
- traced each mutation into its executor and domain service;
- reviewed the routing rules in `backend/app/agent/orchestrator.py`;
- compared active-agent coverage with the calendar, recurring-slot, and waitlist APIs;
- inspected web and WhatsApp conversation-history handling;
- executed representative temporal phrases against `backend/app/agent/temporal.py` with the reference date 2026-08-23 and same-weekday cases with 2026-08-28;
- ran the five relevant test modules against the local `agenda_db` container using the `agenda` conda environment.

Test baseline on 2026-08-23: **103 passed, 2 failed**. Both failures are assertion drift introduced by the evolving `find_group_openings` contract: the response now includes `participant_count`, and the tool description changed without updating its exact phrase assertion. These should be repaired before adding new tests so the baseline is trustworthy.

No Azure database writes or production conversations were used. LLM behavior was assessed through deterministic contracts, prompt rules, history payloads, and service availability; the final phase adds controlled model-routing fixtures for probabilistic behavior.

## 4. Informal instructor scenario matrix

| Instructor utterance | Intended meaning | Current route/capability | Finding | Priority |
|---|---|---|---|---|
| “agenda o Carlos toda quinta às 19” | Recurring individual appointment | `propose_create_appointment(is_recurring=true, class_type=individual)` | Covered by the recently implemented precedence rule | Covered |
| “abre uma turma sexta 18h pra 4” | Empty group slot | `propose_create_group_slot` | Covered | Covered |
| “bota a Fer nessa turma só sexta” | Dated guest enrollment | `find_group_openings` then `propose_add_group_occurrence_participant` | Covered when date/time can be recovered | Covered |
| “tira a Fer só dessa sexta” | Remove dated guest only | API/service exists; no agent mutation | Agent cannot perform the intended scope | P0 |
| “a Maria não vai amanhã, mas mantém a turma” | Participant absence | `propose_note_participant_absence` | Covered for permanent members | Covered |
| “depois de amanhã tenho quem?” | Schedule two days ahead | `resolve_date_phrase` | Incorrectly resolves to tomorrow | P0 |
| “joga pra próxima sexta” said on Friday | Move to following Friday | `resolve_date_phrase` | Incorrectly resolves to the current Friday | P0 |
| “e dia 28?” / “e 28/08?” | Concrete date follow-up | Deterministic resolver | Unresolved; model may improvise or ask unnecessarily | P1 |
| “quais grupos têm vaga à noite?” | Group-seat discovery | `find_group_openings(period=evening)` | Addressed by the separate group-vacancy roadmap; current code is being implemented | Existing roadmap |
| “achou vaga pra Ana na fila? coloca ela nessa turma” | Fulfill waitlist into group | Service/API supports occurrence or series; no agent mutation | Current guidance risks cancellation semantics | P0 |
| “abriu horário pra Ana, marca e tira da fila” | Fulfill waitlist into appointment | Appointment and fulfillment services exist but are not atomic through the agent | Entry can be marked `cancelled` rather than `fulfilled` | P0 |
| “confirmado. agora põe a Fernanda nessa turma” | Follow-up after web confirmation | UI retains candidate metadata locally but submits only role/content | Agent lacks authoritative result and entity IDs | P0 |
| “cancela a aula de sexta” | Cancel one dated occurrence | `propose_cancel_schedule` | Covered after resolving the occurrence | Covered |
| “cancela todas as sextas” | Stop/deactivate a recurring series | No active-agent series mutation | Risk of silently cancelling only one date unless guarded | P0 guard; P2 capability |
| “muda essa turma pras 19h daqui pra frente” | Reschedule future occurrences | Only `propose_reschedule_occurrence` exists | No valid tool or defined series boundary semantics | P0 guard; deferred capability |
| “essa turma agora vai até 4” | Change recurring group capacity | Occurrence format tool and dashboard series edit exist; no agent series tool | Scope is ambiguous and tool coverage incomplete | P1 clarification; P2 capability |
| “pode ir” after choosing a place | Continue the immediately prior proposal | Prompt inheritance rule plus raw history | Better than before, but web confirmation outcomes remain absent | P0 continuity |

## 5. Current architecture and exact touchpoints

### 5.1 Active-agent orchestration

- `backend/app/agent/orchestrator.py`
  - `SYSTEM_PROMPT_TEMPLATE`: intent/tool routing, ambiguity rules, proposal semantics.
  - `run_agent_turn`: windows raw role/content history, invokes tools, and stops after the first pending candidate.
  - `ALL_TOOL_SPECS`: union of read and mutation schemas exposed to the model.
- `backend/app/agent/tools.py`
  - read-side entity, date, schedule, capacity, makeup, waitlist, and event tools.
- `backend/app/agent/mutations.py`
  - proposal schemas, validation, candidate creation, confirmation executors, and audit events.
- `backend/app/agent/candidates.py`
  - proposal lifecycle and idempotent confirmation boundary.

### 5.2 Conversation adapters

- `backend/app/api/assistant.py`: accepts the browser-provided message list and returns prose, tool trace, and one pending candidate.
- `backend/app/schemas/assistant.py`: currently permits only `{role, content}` in conversational history.
- `frontend/src/components/assistant/assistant-panel.tsx`: stores `candidateStatus` and `candidateSummary` for rendering, but strips them when building the next `AssistantChatRequest`.
- `frontend/src/lib/types.ts` and `frontend/src/lib/api.ts`: browser chat request/response contracts.
- `backend/app/chat/agent_channel.py`: persists WhatsApp role/content history and records confirmation summaries; its behavior must remain aligned with the web adapter.

### 5.3 Existing domain capabilities not exposed to the agent

- `backend/app/services/recurring_slot_occurrence_participants.py::remove_participant`
- `DELETE /api/recurring-slots/{slot_id}/occurrences/{occurrence_date}/participants/{contact_id}`
- `backend/app/services/waitlist.py::fulfill_entry`
- `backend/app/services/waitlist.py::fulfill_group_occurrence`
- `POST /api/waitlist-entries/{entry_id}/fulfill`
- `POST /api/waitlist-entries/{entry_id}/fulfill-group`

These should be reused. The roadmap must not duplicate their validation or persistence logic inside the agent layer.

## 6. Intent, entity, and scope contract

The model may interpret language, but IDs, dates, scope, capacity, and state transitions must be verified by tools.

### 6.1 New or strengthened intents

| Intent | Example phrases | Required entities | Write scope |
|---|---|---|---|
| `remove_group_occurrence_participant` | “tira a Fer só dessa sexta”, “remove ele dessa aula” | contact, recurring group, occurrence date | `occurrence` only |
| `fulfill_waitlist_with_appointment` | “marca esse horário pra Ana da fila”, “pode encaixar ela” | waitlist entry, contact, date/time, effective place | one appointment |
| `fulfill_waitlist_with_group` | “coloca a Ana da fila nessa turma”, “encaixa ela só hoje” | waitlist entry, group occurrence, enrollment scope | `occurrence` or `series` |
| `cancel_series` | “cancela todas”, “encerra essa turma” | recurring source, series boundary | unsupported initially; never map to occurrence |
| `reschedule_series` | “muda toda quinta”, “das próximas pra frente” | recurring source, new time/place, boundary | unsupported initially; never map to occurrence |
| `update_group_series_capacity` | “essa turma agora é pra 4” | recurring group, capacity, effective boundary | clarify then use future series tool when implemented |
| `followup_reference` | “ela”, “essa turma”, “aquele horário”, “pode ir” | authoritative prior result plus current qualifier | inherits only unambiguous prior entities |

### 6.2 Scope vocabulary

Normalize conversational signals to one of these values before a recurring write:

- `occurrence`: “só hoje”, “só essa”, “nessa sexta”, a concrete dated class.
- `series`: “toda semana”, “todas as sextas”, “a turma fixa”, the whole recurring definition.
- `future_occurrences`: “daqui pra frente”, “a partir da próxima”, a bounded series change requiring an effective date.
- `unspecified`: no reliable scope signal; ask a concise clarification when more than one scope is valid.

Never infer `series` merely from the fact that the target is a recurring slot. Never reduce `series` or `future_occurrences` to `occurrence` because only an occurrence tool is available.

### 6.3 Conversational references

The next turn may inherit an entity only when it is unique and authoritative:

- a just-executed candidate can establish contacts, source IDs, occurrence date, place, and format;
- a rejected or failed candidate must not establish a scheduled entity;
- a read result with one candidate can establish a temporary referent, but should be revalidated before a write;
- multiple groups, contacts, dates, or proposals require clarification;
- raw assistant prose is context, not an authoritative source of IDs or execution status.

## 7. Phase 0 — Restore a trustworthy baseline

### Objective

Fix the two known assertion mismatches without changing production behavior.

### Changes

1. Update `test_find_group_openings_returns_joinable_occurrence_not_free_time` to assert the current `participant_count` field.
2. Replace the brittle exact English phrase requirement in `test_group_lookup_tool_specs_explain_new_student_flow` with semantic assertions that the description:
   - identifies group vacancies as its purpose;
   - includes empty groups;
   - distinguishes group capacity from instructor free time;
   - directs enrollment to the returned recurring source ID.
3. Run the five-module baseline before feature work.

### Verification

```bash
conda run -n agenda pytest \
  backend/tests/test_agent.py \
  backend/tests/test_calendar_mutations.py \
  backend/tests/test_mutations.py \
  backend/tests/test_waitlist.py \
  backend/tests/test_agent_channel.py -q
```

Expected: all current tests pass before new cases are introduced.

## 8. Phase 1 — Make temporal resolution safe for informal pt-BR

### Objective

Prevent wrong-date writes and cover the most common short instructor expressions deterministically.

### Touchpoints

- `backend/app/agent/temporal.py`
- `backend/app/agent/tools.py::resolve_date_phrase` and its schema description
- `backend/app/agent/orchestrator.py::SYSTEM_PROMPT_TEMPLATE`
- `backend/tests/test_agent.py`

### Parser changes

Apply ordered, anchored recognition from most specific to least specific. The current substring order allows `amanhã` inside “depois de amanhã” to win incorrectly.

1. Recognize before the single-day keywords:
   - “depois de amanhã” / unaccented equivalent → `reference_date + 2 days`;
   - “anteontem” → `reference_date - 2 days` if past lookups remain supported.
2. Distinguish weekday modifiers:
   - bare “sexta” and “essa/esta sexta” → same-day-or-next occurrence;
   - “sexta que vem”, “próxima sexta”, “na outra sexta” → strictly after the current date when today is that weekday;
   - do not let generic “próxima semana” matching interfere with “próxima sexta”.
3. Parse explicit Brazilian dates:
   - `dia 28`, `dia 28 de agosto`, `28/08`, `28/08/2026`;
   - infer the year only when unambiguous: choose the next non-past occurrence for future scheduling requests, or require an explicit interpretation parameter. Do not bury this policy inside a regex.
4. Add bounded offsets:
   - “daqui a 2 dias”, “daqui duas semanas”;
   - accept digits and the small Portuguese number vocabulary needed now (`um/uma`, `dois/duas`, optionally through four), not an unrestricted natural-language number parser.
5. Add month ranges only if a current read tool can consume them safely:
   - “esse mês” and “mês que vem” should return `date_from/date_to`;
   - downstream `get_schedule` has a 31-day span limit, so define whether a 31-day month is inclusive-compatible and split only when required.
6. Preserve part-of-day output for combined phrases such as “depois de amanhã à noite”.

### Tool and prompt changes

- Expand `resolve_date_phrase` description with the new supported examples and explicit output semantics.
- Add `ambiguity_reason` and optional `alternatives` to unresolved/ambiguous results rather than returning only `recognized=false`.
- In the prompt, require one clarification question when alternatives exist: for example, “Você quer hoje, 28/08, ou a próxima sexta, 04/09?”
- Never allow the model to choose a date silently after the deterministic resolver returns ambiguous or unresolved.

### Tests

- `test_temporal_depois_de_amanha_does_not_match_amanha`
- `test_temporal_proxima_weekday_is_strictly_future_on_same_weekday`
- `test_temporal_essa_weekday_may_resolve_to_today`
- `test_temporal_parses_brazilian_numeric_date`
- `test_temporal_combines_relative_date_and_evening`
- `test_temporal_rejects_invalid_calendar_date`
- `test_resolve_date_phrase_surfaces_ambiguity_without_guessing`

### Acceptance examples

With reference date Sunday 23/08/2026:

- “depois de amanhã” → 25/08/2026;
- “sexta que vem” → 28/08/2026;
- “dia 28” → 28/08/2026 under the documented future-date policy.

With reference date Friday 28/08/2026:

- “essa sexta” → 28/08/2026;
- “próxima sexta” → 04/09/2026;
- “na outra sexta à noite” → 04/09/2026 plus `evening`.

## 9. Phase 2 — Preserve authoritative continuity after confirmation

### Objective

Make “agora coloca a Fernanda nessa turma” refer to the action that actually executed, not merely to the proposal prose shown one turn earlier.

### Current defect

`assistant-panel.tsx` keeps `pendingCandidate`, `candidateStatus`, and `candidateSummary` for display. On the next send it maps every bubble to `{role, content}`. Therefore:

- the execution status and summary are omitted;
- the confirmed candidate ID is omitted;
- the newly created appointment/group ID is not available in history;
- a rejected or failed proposal looks similar to a still-pending proposal in the model-visible prose;
- the model must rediscover the entity from time/place text and may select the wrong match.

### Contract design

Do not trust a client-authored sentence such as “the action succeeded.” Add a bounded list of candidate references to the request and resolve their state server-side.

Proposed request extension:

```json
{
  "messages": [{"role": "user", "content": "..."}],
  "recent_candidate_ids": ["uuid"]
}
```

Server behavior:

1. Accept at most five IDs.
2. Load only candidates belonging to the authenticated professional; additionally enforce actor ownership where the current policy requires it.
3. Include only recent candidates inside the same conversation lifetime.
4. Read status and execution/failure summary from authoritative persistence.
5. For executed candidates, resolve created/changed entity IDs through `OperationalEvent.operator_action_candidate_id`, not from model text.
6. Build a trusted, compact context block before the user-provided history, for example:

```text
Resultado confirmado recente:
- status=executed; tool=propose_create_group_slot;
  recurring_slot_id=<uuid>; date=2026-08-28; time=18:00-19:00;
  place_id=<uuid>; summary="Turma aberta ..."
```

7. Mark rejected and failed proposals explicitly and do not expose them as valid schedule referents.

### Touchpoints

- `backend/app/schemas/assistant.py`
  - add `recent_candidate_ids` with length and UUID validation.
- `backend/app/api/assistant.py`
  - tenant-scope candidate resolution and pass trusted action context to the orchestrator.
- `backend/app/agent/orchestrator.py`
  - accept a typed `recent_action_context` separate from untrusted message history;
  - inject it as trusted context;
  - add rules for pronouns and demonstratives.
- `backend/app/models/operational_event.py` / event query helper
  - reuse the candidate-to-created-entity relation already recorded by executors.
- `frontend/src/components/assistant/assistant-panel.tsx`
  - retain resolved candidate IDs and include them on subsequent sends;
  - clear them when the panel conversation resets or when outside the bounded window.
- `frontend/src/lib/types.ts` and `frontend/src/lib/api.ts`
  - mirror the request extension.

### Prompt rules

- “essa turma”, “essa aula”, “ele/ela”, and “aquele horário” may use a trusted recent result only if exactly one compatible entity exists.
- Confirmation outcome takes precedence over earlier proposal prose.
- After a failed/rejected proposal, say that the entity was not created and re-query if the instructor wants an alternative.
- Before a write, use the trusted ID only as a reference candidate; the mutation must still revalidate tenancy, current existence, date, capacity, and conflicts.

### Tests

- API rejects a candidate ID from another tenant.
- API ignores or rejects stale/nonexistent candidate IDs without leaking existence.
- Confirmed group creation yields a trusted `recurring_slot_id` from its operational event.
- Rejected and failed candidates do not yield active entity references.
- Frontend next-turn request includes the recently resolved candidate ID.
- “Confirmado → coloca a Fernanda nessa turma” routes to group lookup/enrollment with the established date/time and does not reopen a group.
- Browser reload still starts a clean web conversation, preserving current non-persistence behavior unless product scope changes.

### Acceptance flow

1. Instructor: “abre uma turma sexta às 18 no Silva pra 4”.
2. Agent proposes; instructor confirms in the card.
3. Confirmation creates a recurring slot and records its operational event.
4. Instructor: “agora põe a Fernanda nessa turma só nessa sexta”.
5. Server supplies the trusted created slot/date in context.
6. Agent resolves Fernanda and proposes `propose_add_group_occurrence_participant` for that exact slot/date.

No second empty group may be created, and no permanent roster enrollment may be inferred from “só nessa sexta”.

## 10. Phase 3 — Add occurrence-only participant removal

### Objective

Expose the existing dated-guest removal capability without confusing it with permanent roster removal or a recurring member’s absence.

### Read-model prerequisite

The current schedule serialization lists participant ID/name but not how each person joined. Add an optional `enrollment_scope` to the recurring occurrence participant projection:

- permanent `RecurringSlotParticipant` → `series`;
- `RecurringSlotOccurrenceParticipant` → `occurrence`;
- appointment participants → `null` or an appointment-specific value only if a present consumer needs it.

Touchpoints:

- `backend/app/services/scheduling.py::ScheduleParticipant`
- recurring participant construction in `_slot_occurrences`
- `backend/app/agent/tools.py::_occurrence_to_dict`
- API schemas/serializers that share the projection, if any
- frontend types only if the additional field reaches an existing UI contract

### New mutation tool

`propose_remove_group_occurrence_participant`

```json
{
  "contact_id": "uuid",
  "recurring_slot_id": "uuid",
  "occurrence_date": "2026-08-28"
}
```

Proposal validation must:

1. tenant-scope contact and recurring slot;
2. confirm the slot is a recurring group class;
3. confirm the dated occurrence exists and is not cancelled;
4. confirm the contact is an occurrence-only participant on that exact date;
5. return a domain error if the contact is permanent, directing the routing layer toward `propose_note_participant_absence` for a one-date absence or `propose_remove_group_member` for series removal.

Preview example:

> Remover Fernanda somente da turma de 28/08/2026, 18:00–19:00, no Silva Tennis. A turma fixa e os demais alunos não serão alterados.

Executor behavior:

- call `recurring_slot_occurrence_participants.remove_participant`;
- record `schedule.participant.removed` with `scope=occurrence`, contact ID, date, and candidate correlation;
- return a pt-BR execution summary;
- keep the operation inside the candidate confirmation transaction.

### Prompt routing

- If `enrollment_scope=occurrence` and the instructor says “tira só dessa aula”, use the new removal tool.
- If `enrollment_scope=series` and the student merely will not attend one date, use `propose_note_participant_absence`.
- If `enrollment_scope=series` and the instructor says the student is leaving the fixed group, use `propose_remove_group_member`.
- If scope is omitted, ask: “É só nesta aula ou ela vai sair da turma fixa?”
- Never use participant absence for an occurrence-only guest; removing that guest is the accurate capacity and attendance operation.

### Tests

- full propose/confirm cycle removes only the dated row;
- permanent roster remains unchanged;
- other dates retain their participants;
- permanent member is rejected by the dated-removal tool;
- cross-tenant contact/group IDs are rejected;
- concurrent prior removal fails safely at confirmation;
- prompt/tool contract contains the three-way routing rule.

## 11. Phase 4 — Fulfill waitlist demand atomically

### Objective

Turn a matched demand into a real booking and the terminal state `fulfilled`, preserving the correct target link and enrollment scope.

### Correct the read-tool guidance first

Update `find_waitlist_matches` documentation and tool description. Remove the instruction to “book, then `propose_remove_waitlist_entry`.” That mutation means the customer is no longer waiting and calls `cancel_entry`; it is not fulfillment.

The returned match already distinguishes:

- `match_type=free_time` with place/date/time;
- `match_type=group_occurrence` with source ID, occurrence date, and seats.

The prompt must route these types to separate fulfillment proposals.

### Tool A — Fulfill with an appointment

Add `propose_fulfill_waitlist_with_appointment`:

```json
{
  "waitlist_entry_id": "uuid",
  "place_id": "uuid",
  "service": "Aula"
}
```

Derive contact, date, start/end time, and acceptable class type from the waitlist entry rather than allowing the model to repeat and potentially alter them. Validate the selected place against a current `free_time` match and current scheduling conflicts.

On confirmation, in one transaction:

1. lock/revalidate the waitlist entry in `open` or `matched` state;
2. revalidate that the free range still exists;
3. create the appointment with the waiting contact and source `assistant`;
4. call `waitlist.fulfill_entry` with the created appointment ID, refactoring its internal commit if necessary so the candidate transaction remains atomic;
5. record appointment creation and `waitlist.entry.fulfilled` operational events linked to the candidate;
6. return a summary naming the customer, date/time, and place.

Do not call `propose_create_appointment` and `propose_remove_waitlist_entry` as two independent candidates; either could succeed alone and leave inconsistent state.

### Tool B — Fulfill with a group

Add `propose_fulfill_waitlist_with_group`:

```json
{
  "waitlist_entry_id": "uuid",
  "recurring_slot_id": "uuid",
  "occurrence_date": "2026-08-28",
  "enrollment_scope": "occurrence"
}
```

Validation and execution should reuse `waitlist.fulfill_group_occurrence`, which already checks tenancy, group format, date, place, requested time coverage, capacity, and explicit `occurrence|series` scope.

Preview examples must say either:

- “Adicionar Ana somente à aula de 28/08 e concluir a solicitação da fila”; or
- “Adicionar Ana à turma fixa a partir da aula de 28/08 e concluir a solicitação da fila.”

### State and audit rules

- `fulfilled` means demand met and contains `fulfilled_appointment_id` or the recurring slot/date/scope tuple.
- `cancelled` means the demand was abandoned and must never be used after successful booking.
- A failed booking leaves the entry in its previous `open`/`matched` state.
- Confirmation retries must be idempotent.
- Cross-tenant IDs return the project’s normal not-found/authorization behavior without leaking data.

### Prompt routing

- “achou vaga pra alguém da fila?” → `find_waitlist_matches`.
- A selected `free_time` match → appointment fulfillment tool.
- A selected `group_occurrence` match → ask “só essa aula ou turma fixa?” unless already explicit, then group fulfillment tool.
- “tira ela da fila, ela desistiu” → `propose_remove_waitlist_entry` remains correct.
- Never interpret “coloca ela nessa turma” as cancellation of the waitlist record.

### Tests

- appointment fulfillment creates and links one appointment atomically;
- group fulfillment supports occurrence and series scopes;
- capacity race at confirmation leaves waitlist state unchanged;
- appointment conflict race leaves waitlist state unchanged;
- another tenant’s entry, contact, place, or group is rejected;
- already fulfilled/cancelled/expired entries cannot be reused;
- fulfillment candidate retry is idempotent;
- tool descriptions do not recommend cancellation after booking;
- informal pt-BR routing fixtures cover “encaixa ela”, “põe nessa turma”, and “ela desistiu”.

## 12. Phase 5 — Enforce recurring-write scope before adding series tools

### Phase 5A: mandatory safety guard

This is required even if no series mutation is implemented yet.

Add prompt and contract tests stating:

- `propose_cancel_schedule` cancels one dated occurrence only;
- `propose_reschedule_occurrence` moves one dated occurrence only;
- `propose_set_occurrence_class_format` changes one dated occurrence only;
- phrases containing “todas”, “toda semana”, “a turma fixa”, “daqui pra frente”, or “a partir de” must not call those occurrence tools as if the request were singular;
- when scope is unspecified and both meanings are plausible, ask “Só a aula de DD/MM ou todas daqui pra frente?”;
- when the requested series operation is unsupported, answer directly: “Consigo alterar uma aula específica por aqui; para todas as próximas ainda preciso que você ajuste na Agenda.”

This is a product limitation, not a reason to fabricate success or quietly perform less work than requested.

### Phase 5B: narrow recurring-capacity tool

Capacity is the safest and most immediately relevant series edit for the new group-slot workflow. Add only after extracting shared validation from the dashboard API.

Proposed tool: `propose_set_group_series_capacity`

```json
{
  "recurring_slot_id": "uuid",
  "max_participants": 4
}
```

Rules:

- affects the recurring group definition, not one occurrence override;
- capacity remains 1–4;
- new capacity cannot be below the permanent roster or the participant count of any existing dated occurrence that remains relevant;
- confirmation preview says “todas as aulas da turma” explicitly;
- executor records `schedule.series.updated` with before/after capacity;
- reuse one service from both `PATCH /api/recurring-slots/{id}` and the agent executor so validation cannot drift.

If the instructor says “só nessa sexta vai até 4,” continue using `propose_set_occurrence_class_format`.

### Phase 5C: decision gate for cancel/reschedule series

Do not expose series cancellation/rescheduling until the domain semantics are chosen. `schedule_overrides.py` explicitly defers whole-series and future-occurrence behavior, and the dashboard currently hard-deletes recurring slots.

Decisions required:

1. Does “cancela a turma” mean hard delete, status deactivation, or `valid_until` before the next occurrence?
2. Are historical occurrences and revenue preserved?
3. What happens to future dated guests and occurrence overrides?
4. Do eligible students receive make-up credits for any future cancellations?
5. For “daqui pra frente”, is the series edited in place or split into an old definition plus a new definition with a new ID?
6. How are waitlist matches and operational events recalculated?
7. How are recurring individual appointments terminated, given their different persistence model?

Recommended direction: preserve history and split/deactivate rather than hard-delete, but treat this as a separate approved implementation roadmap once product semantics are decided.

### Tests

- prompt never maps “cancela todas” to one `propose_cancel_schedule` call;
- prompt never maps “muda daqui pra frente” to one occurrence reschedule;
- ambiguous singular phrases cause one scope clarification;
- series-capacity proposal rejects a value below any effective occurrence participant count;
- concurrent enrollment revalidates capacity at confirmation;
- occurrence capacity remains unchanged when the series-capacity tool is used only if an explicit dated override already owns that occurrence’s format.

## 13. Phase 6 — Harden informal pt-BR routing and recovery

### Objective

Turn the verified contracts into natural, concise dialogue for a Brazilian tennis instructor who types quickly, omits accents, and relies on context.

### Prompt changes

Organize `SYSTEM_PROMPT_TEMPLATE` by intent family so rules do not become an unstructured list:

1. **Consultar agenda:** who/what/where, next class, events.
2. **Consultar disponibilidade:** instructor free time versus seats in existing groups.
3. **Agendar:** individual, named multi-customer appointment, empty group slot.
4. **Gerenciar participantes:** permanent roster, dated guest, absence, removal.
5. **Alterar agenda:** occurrence versus series scope.
6. **Reposição:** credit lookup, recommendation, redemption.
7. **Fila de espera:** create, match, fulfill, cancel.
8. **Follow-up/context:** pronouns, demonstratives, confirmation result.

For every family, specify:

- positive trigger examples in informal pt-BR;
- confusing neighboring intent and the tool that must not be used;
- required entities;
- when clarification is mandatory;
- the expected write scope;
- concise no-result behavior.

Do not add a separate regex intent classifier unless model-routing tests show the prompt and tool descriptions remain unreliable. Deterministic parsing belongs to dates, IDs, state, and scope validation; broad natural-language intent remains with the model.

### Informal language fixture set

Create a versioned fixture file under `backend/tests/fixtures/agent_ptbr_scenarios.json`. Include accentless text, abbreviations, typos, and short follow-ups, for example:

- “qm tenho hj a noite?”
- “tem vaga em alguma turma 18h?”
- “bota a fer nessa de sexta, so essa”
- “ela vai ficar fixo”
- “tira ela dessa mas mantem nas outras”
- “a mari faltou ontem, gera reposicao?”
- “encaixa ela usando a reposicao”
- “achou algo pra galera da fila?”
- “essa serve, poe a ana”
- “nao, a outra do silva”
- “pode ir”
- “cancela todas, nao so essa”
- “passa pra prox sexta”
- “dia 28 de noite”

Each fixture should declare:

- expected intent;
- allowed tool sequence;
- forbidden tools;
- required clarification, if any;
- expected scope;
- entities that must be resolved rather than invented.

### Deterministic contract tests

Use mocked model tool calls to test server behavior and prompt/schema invariants without network access. Assert tenant isolation, proposal validation, confirmation outcomes, and mutation effects.

### Controlled routing evaluation

Add a script in `scripts/`, decoupled from the API, to run the fixture set against the configured model only when explicitly invoked:

```bash
conda run -n agenda python scripts/evaluate_agent_ptbr_routing.py \
  --fixtures backend/tests/fixtures/agent_ptbr_scenarios.json
```

Requirements:

- no writes: replace all tools with deterministic fixture doubles;
- redact phone numbers, UUIDs, and personal data from output;
- report allowed/forbidden tool accuracy, clarification accuracy, and scope accuracy;
- store no model credentials or outputs in source control;
- pin the evaluated model/deployment name and prompt hash in the report;
- fail CI only on deterministic tests initially; run model evaluation manually until variance and cost are understood.

### Acceptance threshold

- 100% forbidden-tool compliance on destructive scope cases;
- 100% correct date output for deterministic temporal fixtures;
- at least 95% allowed-tool routing on the curated informal pt-BR set across three repeated runs;
- 100% clarification on intentionally ambiguous fixture cases;
- zero invented IDs in all traces.

## 14. Implementation order and dependency map

| Order | Work item | Depends on | Verification gate |
|---:|---|---|---|
| 0 | Repair current group-opening test assertions | Nothing | Existing five-module suite green |
| 1 | Fix temporal precedence and weekday modifiers | Baseline | Pure parser tests green |
| 2 | Add trusted confirmed-action context to web chat | Operational event linkage | API isolation and browser request tests green |
| 3 | Add enrollment scope to recurring occurrence participants | Schedule projection | Projection/API regressions green |
| 4 | Add occurrence-only participant removal proposal | Step 3 | Mutation full-cycle and race tests green |
| 5 | Correct waitlist tool guidance | Baseline | Prompt/schema contract tests green |
| 6 | Add atomic appointment waitlist fulfillment | Step 5 | Transaction/race tests green |
| 7 | Add group waitlist fulfillment proposal | Step 5 | Occurrence and series tests green |
| 8 | Add recurring-scope guardrails | Baseline | Forbidden-tool routing fixtures green |
| 9 | Add narrow series-capacity proposal | Shared recurring-slot update service | Capacity and concurrency tests green |
| 10 | Build informal pt-BR fixture evaluation | Steps 1–9 | Acceptance thresholds met |

Steps 1, 2, 4, 6, 7, and 8 are the recommended release scope. Step 9 is useful but can ship separately. Whole-series cancellation/rescheduling remains behind the Phase 5C product decision gate.

## 15. Consolidated file touchpoint checklist

### Backend agent

- [ ] `backend/app/agent/temporal.py`
- [ ] `backend/app/agent/tools.py`
- [ ] `backend/app/agent/orchestrator.py`
- [ ] `backend/app/agent/mutations.py`
- [ ] `backend/app/agent/candidates.py` only if candidate result lookup needs a shared helper

### Backend domain/API

- [ ] `backend/app/services/scheduling.py`
- [ ] `backend/app/services/recurring_slot_occurrence_participants.py`
- [ ] `backend/app/services/waitlist.py`
- [ ] `backend/app/services/appointments.py`
- [ ] `backend/app/api/assistant.py`
- [ ] `backend/app/api/recurring_slots.py` if shared series-capacity service is extracted
- [ ] `backend/app/schemas/assistant.py`
- [ ] relevant ontology/calendar schemas for `enrollment_scope`
- [ ] `backend/app/models/operational_event.py` query helper only; no new table is expected for action continuity

### Frontend

- [ ] `frontend/src/components/assistant/assistant-panel.tsx`
- [ ] `frontend/src/lib/api.ts`
- [ ] `frontend/src/lib/types.ts`

### Tests and tooling

- [ ] `backend/tests/test_agent.py`
- [ ] `backend/tests/test_calendar_mutations.py`
- [ ] `backend/tests/test_mutations.py`
- [ ] `backend/tests/test_waitlist.py`
- [ ] assistant API/frontend tests for candidate context
- [ ] `backend/tests/fixtures/agent_ptbr_scenarios.json`
- [ ] `scripts/evaluate_agent_ptbr_routing.py`

No new runtime dependency is expected. If implementation adds one, justify it, pin it in root `requirements.txt`, and audit it before merge.

## 16. Security, tenancy, and audit requirements

- Derive `professional_id` and actor identity from authentication, never model arguments or request body.
- Tenant-scope every candidate, contact, place, appointment, recurring slot, waitlist entry, and operational event query.
- Treat candidate IDs supplied by the browser as untrusted references and re-resolve them server-side.
- Do not leak whether a cross-tenant candidate/entity exists; follow existing project error behavior.
- Keep all writes behind `OperatorActionCandidate` confirmation.
- Revalidate mutable preconditions at confirmation: capacity, conflicts, waitlist state, participant membership, and occurrence existence.
- Record who, what, when, channel, correlation ID, candidate ID, before state, and after state for each new mutation.
- Avoid logging free-text waitlist notes, phone numbers, or complete model prompts in evaluation output.
- Apply existing CSRF and write-rate-limit controls to candidate confirm endpoints; no new open endpoint is needed.

## 17. Risks and mitigations

| Risk | Mitigation |
|---|---|
| More prompt rules reduce tool-selection consistency | Organize by intent family; reinforce in tool descriptions; evaluate with forbidden-tool fixtures |
| Client fabricates prior action success | Send candidate IDs and reconstruct trusted outcome server-side |
| Stale confirmed entity is reused after later edits | Treat context as reference only; every mutation revalidates current state |
| Date expansion introduces ambiguous year behavior | Document future/past policy and return alternatives instead of guessing |
| Waitlist fulfillment partially succeeds | One candidate executor and one transaction; remove internal service commits where needed |
| Capacity changes invalidate dated guests | Validate against maximum effective occurrence occupancy before proposal and confirmation |
| “Remove” accidentally removes permanent membership | Expose `enrollment_scope`; separate mutation tools; clarify when scope is missing |
| Series language silently becomes a single occurrence | Prompt guard plus forbidden-tool routing tests |
| Model-evaluation results vary | Three runs, prompt hash, deployment name, and deterministic tools; keep CI gate deterministic initially |
| Existing dirty working tree causes accidental overlap | Implement in small phases and preserve unrelated user changes |

## 18. Manual pt-BR acceptance script

Run on a local tenant with a known place, Fernanda and Ana contacts, one empty recurring group, one partially full group, and one waitlist entry.

1. “quem tenho depois de amanhã?” — verify the date is two days ahead.
2. On a Friday: “e próxima sexta?” — verify it means the following week.
3. “abre uma turma sexta 18h no Silva pra 4” — confirm the proposal.
4. “agora põe a Fernanda nessa turma só sexta” — verify the confirmed group is reused and enrollment is occurrence-only.
5. “tira a Fernanda só dessa sexta” — verify later weeks are untouched.
6. Add Fernanda permanently, then say “a Fer não vai essa sexta mas mantém ela na turma” — verify absence, not roster removal or class cancellation.
7. “quais pedidos da fila já cabem?” — inspect both free-time and group matches.
8. “põe a Ana nessa turma só essa vez” — verify waitlist becomes `fulfilled` with recurring slot/date/scope.
9. Create another waitlist match in free time and say “marca esse pra ela” — verify appointment link and `fulfilled` status.
10. “tira a outra da fila, ela desistiu” — verify `cancelled`, demonstrating the distinct abandonment path.
11. “cancela todas as sextas” — until series support exists, verify the agent states the limitation and does not create a one-date candidate.
12. “essa turma agora vai até 4” — verify scope clarification or the explicit series-capacity preview, depending on Phase 5B status.
13. Repeat key phrases without accents: “so essa”, “proxima sexta”, “reposicao”, “poe ela”.
14. Try two contacts/groups with the same short name and verify one concise disambiguation question.

## 19. Definition of done

- [ ] Current baseline test drift is repaired.
- [ ] Temporal P0 misresolutions have regression tests and are fixed.
- [ ] Web confirmations are represented as trusted next-turn context.
- [ ] Occurrence participant projection identifies enrollment scope.
- [ ] Dated-guest removal is available through propose/confirm/execute.
- [ ] Waitlist appointment and group fulfillment are atomic agent operations.
- [ ] Waitlist cancellation is no longer documented as fulfillment.
- [ ] Series-wide language cannot call occurrence-only tools silently.
- [ ] The selected series-capacity scope is either implemented or explicitly deferred.
- [ ] Informal pt-BR fixture evaluation meets the acceptance threshold.
- [ ] Tenant isolation, concurrency, audit, and idempotency tests pass.
- [ ] Manual acceptance script passes in both web chat and instructor WhatsApp where applicable.
- [ ] Relevant behavior docs are updated after implementation.

## 20. Explicit non-goals

- Replacing the LLM with a full regex intent engine.
- Persisting all web-chat conversations across browser reloads.
- Letting the agent send messages directly to customers.
- Auto-confirming instructor writes.
- Hard-deleting recurring schedule history through chat.
- Reimplementing group-vacancy period filtering already covered by its dedicated roadmap.
- Expanding to unrestricted natural-language date parsing before the listed instructor phrases are validated.

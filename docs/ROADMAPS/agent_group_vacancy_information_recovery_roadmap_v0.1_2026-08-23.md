# Agent Group-Vacancy Information Recovery Roadmap v0.1 — 2026-08-23

## Status

**Roadmap state:** proposed; no behavior changes have been made under this
roadmap.

This roadmap corrects an instructor-agent read-path defect: a question about
remaining seats in group classes is currently routed to free-time availability.
That can produce a work-journey answer even when a joinable group exists.

Canonical failure:

> “Quais vagas tenho em grupos à noite?”

Incorrect behavior:

> “Você não tem jornada de trabalho cadastrada para os domingos…”

Required behavior:

> Return the group occurrences on the applicable date and evening period that
> have remaining seats, such as “Turma no Silva Tennis, 18:00–19:00, 0/4;
> quatro vagas.”

## Product contract

Free instructor time and group capacity are separate resources:

| Question type | Meaning | Canonical read path | Must not depend on |
|---|---|---|---|
| “Quando estou livre?” | Time in the instructor’s work journey not occupied by a calendar item | `find_instructor_openings` | Group capacity |
| “Quais vagas tenho em grupos?” | Empty seats in scheduled group occurrences | `find_group_openings` | Work journey / free ranges |
| “Tem horário para Fernanda às 18h?” | A booking option; may be free time or a group seat | Free-time search plus group-opening search, reported separately | Treating a group seat as free time |

An empty group (`0/N`) is a real scheduled commitment with `N` joinable
seats. It must be returned even if the professional has no work-journey row
for that weekday. A closed/full group (`available_seats=0`) is not returned.

## Scope and non-goals

In scope:

- instructor questions explicitly about group vacancies, including a
  part-of-day phrase such as “de manhã”, “à tarde”, or “à noite”;
- date and period resolution for the group-opening query;
- deterministic, capacity-aware tool output and response guidance;
- recovery when no group seat exists, without incorrectly substituting a
  free-time/work-journey result.

Out of scope:

- changing group capacity, roster enrollment, pricing, waitlist rules, or
  Agenda rendering;
- recommending a new group slot when no existing group seat is found;
- treating a group vacancy as a free individual booking slot;
- changing generic “when am I free?” behavior.

## Verified root cause

The current code already has both relevant services:

- `find_instructor_openings` accepts `period` and operates from work journey
  minus busy calendar items.
- `find_group_openings` reads projected schedule occurrences and filters
  `class_type="group"` plus effective remaining capacity.

The two contracts are asymmetric. `find_group_openings` requires a date and
only supports an optional exact `start_time`; it does not accept a part-of-day
period. The orchestration prompt mentions group openings only for a customer
asking about one specific occupied time. It gives no routing rule for an
instructor explicitly asking for group vacancies.

Consequently, the model can interpret “à noite” through the only tool whose
schema supports a period—`find_instructor_openings`—and return a correct but
irrelevant work-journey result.

## Target query and response model

### Date default and temporal recovery

A group-vacancy question without a date is interpreted as **today** in the
professional’s timezone, matching the current assistant convention shown in
the failed response. This default must be explicit in the prompt, not inferred
silently by tool code.

Examples:

| Instructor wording | Date input to query | Period input |
|---|---|---|
| “Quais vagas tenho em grupos à noite?” | `resolve_date_phrase("hoje à noite")` → today | `evening` |
| “Quais turmas têm vaga sexta à noite?” | `resolve_date_phrase("sexta à noite")` → next Friday | `evening` |
| “Quais grupos têm vaga amanhã?” | `resolve_date_phrase("amanhã")` → tomorrow | none |
| “Quais vagas na turma das 18h?” | resolve applicable date or ask | `start_time="18:00"` |

If temporal resolution does not yield a concrete date, the assistant asks for
one. It must not broaden the query to free time as a fallback.

### Period semantics

Reuse `financial_capacity.PART_OF_DAY_RANGES`, already used by the temporal
and free-time components:

```text
morning   06:00–12:00
afternoon 12:00–18:00
evening   18:00–22:00
```

An occurrence belongs to a period when its interval overlaps the period
window. This includes a class that begins before 18:00 and runs into the
evening; do not filter only by the start time. An exact `start_time` remains a
narrower filter and may be combined with `period` when the wording supplies
both.

### `find_group_openings` contract

Extend `backend/app/agent/tools.py`:

```text
find_group_openings(
  date: ISO date,
  start_time?: HH:MM,
  period?: morning | afternoon | evening,
  place_id?: UUID
)
```

Implementation responsibilities:

1. Continue obtaining occurrences from
   `scheduling.list_schedule_occurrences`, preserving dated guests and dated
   capacity overrides.
2. Keep only effective group occurrences where `available_seats > 0`.
3. Apply exact start-time, optional place, and interval-overlap period filters
   cumulatively.
4. Return the effective `participant_count`, `max_participants`, and
   `available_seats`, in addition to current source/date/place/roster fields.
5. Return `joinable_groups: []` with the requested date/period when none
   match. Do not attach a work-journey diagnosis.

The model-facing schema description must state that the tool is the canonical
answer for “vagas em grupos,” including empty groups, and never reports free
instructor time.

### Response contract

For matches, the assistant summarizes each occurrence with:

```text
<group label>, <place>, <time>, <participants>/<capacity>, <available seats>
```

Example:

> Hoje à noite há uma vaga em grupo: Turma no Silva Tennis, 18:00–19:00,
> 3/4 alunos — uma vaga. Há também uma turma vazia, 19:00–20:00, 0/4.

For no matches:

> Não há turmas com vagas hoje à noite.

It must not mention the absence of a work journey unless the instructor also
asked about genuinely free time.

## Prompt, intent, and tool-selection changes

### Routing rule

Add a non-optional rule to `SYSTEM_PROMPT_TEMPLATE` in
`backend/app/agent/orchestrator.py`:

> When the instructor asks about `vagas`, `lugares`, or capacity **em
> grupos/turmas**, resolve the applicable date and call
> `find_group_openings` first. Never call `find_instructor_openings` as the
> answer to a group-capacity question. A group with a seat is a scheduled
> commitment, not free instructor time.

The rule must cover both named and generic wording:

- “Quais vagas tenho em grupos à noite?”
- “Quais turmas têm vaga amanhã?”
- “Existe grupo com lugar para Fernanda sexta?”

### Tool-selection sequence

```text
Instructor asks about group vacancies
  -> date explicit?
       yes: resolve_date_phrase when relative/natural language
       no: resolve_date_phrase("hoje" plus any stated period)
  -> find_group_openings(date, period?, start_time?, place_id?)
  -> summarize effective group capacity
  -> optional: ask whether to add a named customer, and ask occurrence/series scope
```

The agent does not need `search_contacts` for a pure capacity question. If a
customer is named, resolve that contact only after or alongside the group
opening search; the contact must not be used to filter existing membership.

### Intent classification table

| Intent signal | Required tool | Prohibited substitution |
|---|---|---|
| `vagas`, `lugares`, `capacidade`, `turmas` | `find_group_openings` | `find_instructor_openings` alone |
| `livre`, `disponível`, `quando posso atender` | `find_instructor_openings` | Calling a group seat free time |
| `adiciona Fernanda na turma` | `find_group_openings` after date resolution | `find_groups(member_contact_id=Fernanda)` |
| `quais grupos existem` without a date/capacity question | `find_groups` | Inferring dated availability from static series data |

### Entities and data boundaries

No new stored entity or migration is needed.

`ScheduleOccurrence` remains the canonical read model because it already
combines:

- recurring class series;
- dated guest participants;
- occurrence-level class/capacity overrides;
- cancellations and reschedules;
- effective available seats.

The agent must not derive capacity from the standing `RecurringSlot` roster or
assume a capacity of four. It uses the projected occurrence’s explicit
`available_seats` and `max_participants` fields.

## Implementation phases

### [ ] Phase 1 — Make group openings period-aware

1. Add optional `period` to the Python function and OpenAI tool schema.
2. Reuse the existing part-of-day ranges; do not introduce a second period
   vocabulary.
3. Filter schedule occurrences by interval overlap, preserving exact-time
   and place filters.
4. Return effective occupancy/count fields explicitly.

**Exit criteria:** an empty or partial 18:00 group appears in an `evening`
query, while a full group does not.

### [ ] Phase 2 — Correct agent routing and information recovery

1. Add the group-vacancy routing rule and today-default language to the
   prompt.
2. Strengthen `find_group_openings` and `find_instructor_openings`
   descriptions so their resources are visibly disjoint.
3. Add examples for generic period questions and no-results responses.
4. Preserve the existing combined free-time-plus-group search only for a
   customer booking question at a specific time.

**Exit criteria:** a tool-call fixture for “quais vagas tenho em grupos à
noite?” uses the group-opening tool and does not call free-time availability.

### [ ] Phase 3 — Lock the behavior with regression tests

Add tests covering:

| Test | Required assertion |
|---|---|
| `test_find_group_openings_filters_by_evening_overlap` | Empty and partial evening groups are returned; daytime-only groups are excluded |
| `test_find_group_openings_uses_effective_dated_capacity` | A dated guest can fill only that date and removes that occurrence from results |
| `test_find_group_openings_ignores_work_journey` | A joinable group is returned even without a journey row for that day |
| `test_group_vacancy_tool_spec_supports_period` | Schema exposes the shared period enum and correct semantic description |
| `test_orchestrator_prompt_routes_group_vacancy_questions` | Prompt contains explicit group-first/no-free-time rule |
| mocked agent tool-call scenario | “quais vagas tenho em grupos à noite?” calls date resolution plus `find_group_openings`, never only `find_instructor_openings` |

The mocked agent scenario must assert tool names and arguments rather than
depend on sampled model prose.

### [ ] Phase 4 — Verify and release locally

Run at minimum:

```bash
conda run -n agenda pytest backend/tests/test_agent.py backend/tests/test_schedule_projection.py backend/tests/test_calendar_mutations.py -q
conda run -n agenda pytest backend/tests/test_agent_channel.py -q
cd frontend && npx tsc --noEmit
```

Manual acceptance checks:

1. With no Sunday work journey but an empty Sunday-evening group, ask “Quais
   vagas tenho em grupos à noite?” and receive the group/seat answer.
2. Fill the group’s final seat for today and confirm the same question reports
   no group vacancy, without mentioning work journey.
3. Ask “Quando estou livre à noite?” and confirm the existing free-time answer
   continues to use work journey.
4. Ask “Tem grupo para Fernanda sexta às 18h?” and confirm the agent locates a
   matching group occurrence before asking occurrence versus series scope.

## Risks and safeguards

| Risk | Safeguard |
|---|---|
| Group seat is presented as free instructor time | Separate tool descriptions, prompt rule, and response wording |
| Evening filter misses a crossing class | Use interval overlap, not start-time-only filtering |
| Dated guests/capacity overrides are ignored | Query `ScheduleOccurrence`, never raw static roster counts |
| Generic “at night” has no date | Explicit current-day default documented in the prompt; ask when the date cannot be resolved |
| Free-time behavior regresses | Retain existing `find_instructor_openings` contract and test it separately |
| Model chooses the wrong tool | Mocked tool-call regression asserts group-opening selection and absence of a free-time-only route |

## Completion criteria

- [ ] Group-vacancy questions are answered from projected joinable groups,
  independent of work journey.
- [ ] `find_group_openings` supports shared part-of-day filtering.
- [ ] Empty groups appear with their real remaining capacity.
- [ ] No-result group queries do not produce free-time/work-journey prose.
- [ ] Focused agent, scheduling, and TypeScript checks pass.

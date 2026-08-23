# Agent Recurring Individual Booking Correction Roadmap v0.1 — 2026-08-23

## Status

**Roadmap state:** proposed; no behavior changes have been made under this
roadmap.

This roadmap corrects a specific agent-routing defect: when the instructor
asks to schedule one named customer on a recurring cadence, the assistant may
open an empty group because group-slot creation is currently the only
recurrence-capable agent mutation.

Example of the incorrect result:

> “agenda pra mim o Carlos toda quinta das 19 às 20” → empty weekly `group`
> slot, `0/4` participants.

The required result is a weekly `individual` appointment whose primary
participant is Carlos. A group must be created only when the instructor
explicitly expresses group intent.

## Product contract

The agent must keep three independent decisions visible in its behavior:

| Decision | Default | Only changes when |
|---|---|---|
| Customer assignment | The named customer is assigned | The instructor changes the customer or cancels the request |
| Recurrence | One-off unless wording says weekly/repeated | The instructor says “toda quinta”, “semanal”, or equivalent |
| Class format | `individual` for one named customer | The instructor explicitly says `turma`/`grupo`, asks to open capacity, or names multiple customers |

Therefore, “agenda Carlos toda quinta das 19h às 20h” means:

```text
Appointment
  contact_id: Carlos
  recurrence_rule: FREQ=WEEKLY
  class_type: individual
  max_participants: 1
```

It must never be translated into a `RecurringSlot(slot_kind="class",
class_type="group")` merely because it repeats weekly.

## Scope and non-goals

In scope:

- recurring individual bookings proposed through the instructor chat;
- the explicit distinction between a named-customer booking and an empty
  preferential group slot;
- deterministic confirmation previews, tool contracts, and regression tests;
- preserving the existing Agenda/API behavior for both appointment recurrence
  and intentional group creation.

Out of scope:

- changing group capacity, dated guests, waitlist fulfillment, or the
  **Turmas com vagas** view;
- migrating recurring appointments into `RecurringSlot` records;
- inferring group intent from a customer’s historic group membership;
- changing passive conversation extraction or customer-facing chat behavior.

## Root-cause summary

`appointments.create_appointment()` already supports `is_recurring=True` and
persists `recurrence_rule="FREQ=WEEKLY"`. The dashboard API uses that path.
The agent mutation `propose_create_appointment`, however, neither accepts nor
passes `is_recurring` to its executor. In contrast,
`propose_create_group_slot` accepts `is_recurring` but intentionally creates a
zero-participant group.

Because tool selection is model-driven, the assistant can select the only
weekly-capable proposal and lose the named customer. Prompt prose alone does
not enforce the required invariant.

## Touchpoints and target changes

| Layer | Current responsibility | Required change |
|---|---|---|
| `backend/app/agent/mutations.py` | Defines `propose_create_appointment`, `propose_create_group_slot`, their JSON tool schemas, and confirmation executors | Make appointments recurrence-capable; narrow the group-tool meaning and validate its named-customer invariant |
| `backend/app/services/appointments.py` | Owns shared appointment creation, work-journey checks, and conflicts | Reuse its existing `is_recurring` support; no new scheduling store or parallel validation path |
| `backend/app/agent/orchestrator.py` | Gives the model scheduling/tool-selection rules | Add explicit format-selection precedence and a repeated named-customer example |
| agent tool schemas | Give the model the callable contract | Document `is_recurring` on appointments and make the empty-group restriction unmistakable |
| entity-resolution tools | Resolve contacts, places, and existing groups to IDs | Continue resolving the named contact and chosen place; do not resolve a group unless group wording requires it |
| candidate confirmation | Stores deterministic preview/arguments, then revalidates before writing | Include recurrence and format in both proposal arguments and preview; executor must revalidate the same intent-derived arguments |
| tests | Protect mutation/service behavior and tool-choice guidance | Add exact multi-turn regression plus direct mutation contracts and negative cases |

## Tool-contract changes

### `propose_create_appointment`

Keep this as the canonical mutation for one named customer, whether the
appointment is one-off or weekly.

Add the optional parameter:

```json
"is_recurring": {
  "type": "boolean",
  "description": "Create a weekly recurring appointment when true. Defaults to false. A single named customer defaults to an individual appointment."
}
```

Required implementation path:

1. Add `is_recurring: bool = False` to the mutation function signature.
2. Pass it to `appointments.assert_no_conflict(...)` during proposal
   validation, because recurring conflicts differ from one-off conflicts.
3. Store it in `OperatorActionCandidate.resolved_arguments`.
4. Include a deterministic phrase such as `semanalmente, toda quinta-feira`
   in the proposal preview when it is true.
5. Pass it into `appointments.create_appointment(...)` in
   `_execute_create_appointment`.
6. Return/audit the resulting `recurrence_rule` in the execution state so the
   confirmation trail shows whether the booking is weekly.

The existing default remains safe:

- `class_type="individual"`
- one `contact_id`
- one `contact_ids` entry
- `max_participants=1`, as derived by the existing appointment service.

### `propose_create_group_slot`

Retain this tool for the distinct request “abra uma turma” / “reserve uma
turma vazia”. It must remain recurrence-capable and continue to create a
`RecurringSlot` with `slot_kind="class"`, `class_type="group"`, and no
initial participants.

Its schema and description should state all of the following:

- it creates an **empty** group slot;
- it must not be used to schedule a named customer;
- it is appropriate only when the instructor explicitly requests a
  `turma`/`grupo` or capacity reservation;
- a weekly cadence alone is not group intent.

No `contact_id` should be added to this tool. Adding one would conflate the
two persisted scheduling models and recreate the ambiguity this roadmap is
removing.

### Existing group participant tools

`propose_add_group_member`,
`propose_add_group_occurrence_participant`, and
`propose_add_appointment_participant` remain unchanged. They apply only after
the target group or appointment already exists; none should be used as a
substitute for initial recurring individual booking.

## Prompt, intent, and entity-resolution rules

### Intent precedence

Add the following rule to the scheduling section of
`SYSTEM_PROMPT_TEMPLATE` in `backend/app/agent/orchestrator.py`:

> When the instructor names exactly one customer and asks to schedule that
> customer, use `propose_create_appointment` with `class_type="individual"`.
> If the wording also says weekly/repeated, pass `is_recurring=true`. Never
> open a group merely because the request repeats weekly. Use
> `propose_create_group_slot` only when `turma`, `grupo`, open capacity, or an
> equivalent explicit intent is present.

This is a precedence rule, not a soft preference. The named-customer intent
wins over the recurrence cue when deciding the persistence model; recurrence
only changes the appointment’s `recurrence_rule`.

### Decision table

| Instructor wording | Contact entity | Cadence entity | Required mutation | Result |
|---|---|---|---|---|
| “Agenda Carlos amanhã às 19h” | one resolved contact | one date | `propose_create_appointment(is_recurring=false, class_type=individual)` | one individual appointment |
| “Agenda Carlos toda quinta às 19h” | one resolved contact | weekly | `propose_create_appointment(is_recurring=true, class_type=individual)` | weekly individual appointment |
| “Abra uma turma toda quinta às 19h” | no contact required | weekly | `propose_create_group_slot(is_recurring=true)` | weekly empty group, `0/N` |
| “Abra uma turma para Carlos e Ana toda quinta” | two resolved contacts | weekly | ask whether they mean a recurring group roster or separate individual appointments | no implicit persistence choice |
| “Coloque Carlos na turma de quinta” | one contact + existing group | existing series/date | ask series vs occurrence when missing; then use the appropriate group-member tool | group enrollment |

### Ambiguity and follow-up handling

“Go on”, “pode seguir”, and “confirmo o local” inherit only the unresolved
details of the immediately preceding assistant proposal. They must not change
the already-established customer, class format, or recurrence semantics.

For the reported flow, once the assistant has resolved Carlos, Thursday,
19:00–20:00, and Silva Tennis, “go on” must lead to this deterministic
candidate intent:

```text
contact_id: Carlos
place_id: Silva Tennis
is_recurring: true
class_type: individual
```

If the first turn gave only availability instead of creating a candidate, the
second turn still has the named-customer context. The agent must call the
appointment proposal, not reinterpret consent to use the place as consent to
open a group.

### Entity-resolution responsibilities

No new entity type is required.

- `search_contacts` resolves “Carlos” to a unique `contact_id`; zero or
  multiple matches still require clarification.
- `search_places` or the existing place-stay resolver supplies the
  `place_id`; an inferred place must be described as inferred in the preview.
- temporal parsing resolves “toda quinta” into the first valid start date and
  marks `is_recurring=true`; it is not a group-class signal.
- `find_groups` and `find_group_openings` are consulted only when the
  instructor explicitly refers to a group or asks for availability at an
  already occupied time.

The persisted entities remain intentionally distinct:

```text
Named recurring individual
  -> Appointment(contact_id, recurrence_rule="FREQ=WEEKLY", class_type="individual")

Explicit empty group
  -> RecurringSlot(slot_kind="class", class_type="group", participant_count=0)
```

## Confirmation, execution, and audit contract

The candidate is the source of truth after proposal. The language model may
phrase the reply, but it must not determine the class type or recurrence after
the proposal has been created.

For a recurring individual proposal, require these candidate arguments:

```json
{
  "contact_id": "<Carlos UUID>",
  "contact_ids": ["<Carlos UUID>"],
  "class_type": "individual",
  "is_recurring": true,
  "place_id": "<resolved place UUID>",
  "start_at": "<first Thursday ISO datetime>",
  "end_at": "<first Thursday ISO datetime>",
  "service": "<configured or requested service>",
  "billing_type": "billable"
}
```

The preview must explicitly state all three dimensions, for example:

> Criar aula individual semanal para Carlos, toda quinta-feira, 19:00–20:00,
> no Silva Tennis.

It must not use group vocabulary, a `0/4` capacity, or an empty-roster
summary.

At confirmation time `_execute_create_appointment` must repeat the normal
tenant-scoped contact/place lookup and call the shared appointment service
with the stored `is_recurring` value. It must not create a `RecurringSlot`.

The existing `schedule.appointment.created` audit event should include:

```json
{
  "contact_ids": ["<Carlos UUID>"],
  "class_type": "individual",
  "is_recurring": true,
  "recurrence_rule": "FREQ=WEEKLY",
  "requested_place_id": "<optional UUID>",
  "resolved_place_id": "<UUID>"
}
```

This retains an auditable explanation for why a weekly individual booking was
created rather than an empty group.

## Implementation sequence

### [ ] Phase 1 — Extend the appointment proposal contract

1. Add `is_recurring` to `propose_create_appointment`, its mutation schema,
   candidate arguments, preview, and execution path.
2. Pass it to the existing shared conflict and creation services.
3. Preserve current defaults so existing one-off agent requests remain
   individual and non-recurring.
4. Add direct mutation tests before changing prompt behavior.

**Exit criteria:** a confirmed mutation produces an `Appointment` with Carlos
as `contact_id`, `class_type="individual"`, `max_participants=1`, and
`recurrence_rule="FREQ=WEEKLY"`.

### [ ] Phase 2 — Make intent selection unambiguous

1. Update the orchestration prompt with the precedence rule and decision
   table examples above.
2. Rewrite both mutation descriptions so their model-facing meanings cannot
   overlap: appointments may be weekly; group slots are explicitly empty.
3. Ensure follow-up language inherits the resolved named customer and class
   format from conversation history.
4. Do not add a heuristic that silently converts an explicit group request
   into an individual appointment.

**Exit criteria:** tool-call fixtures select `propose_create_appointment` for
a named recurring customer and `propose_create_group_slot` only for explicit
group wording.

### [ ] Phase 3 — Protect against regressions

Add tests at the lowest practical layer and one orchestration-level contract:

| Test | Expected assertion |
|---|---|
| `test_propose_create_recurring_individual_appointment_*` | Candidate retains one contact, `individual`, and `is_recurring=true` |
| `test_confirm_recurring_individual_appointment_*` | Created row has weekly recurrence and no `RecurringSlot` is created |
| `test_group_slot_remains_empty_*` | Explicit “abrir turma” still creates a `0/4` group slot |
| `test_agent_named_customer_weekly_uses_appointment_*` | Mocked tool-calling dialogue selects the appointment mutation |
| `test_agent_go_on_preserves_named_customer_booking_*` | The second turn cannot switch the resolved Carlos booking into an empty group |
| `test_agent_multiple_customers_requires_group_clarification_*` | No automatic group record is proposed for ambiguous multi-customer wording |

Where an end-to-end model test would be non-deterministic, mock the Azure
tool-call response and assert the arguments delivered to the mutation tool.
The test validates the agent contract without depending on model sampling.

### [ ] Phase 4 — Verify and hand off

Run, at minimum:

```bash
conda run -n agenda pytest backend/tests/test_agent.py backend/tests/test_calendar_mutations.py backend/tests/test_mutations.py -q
conda run -n agenda pytest backend/tests/test_agent_channel.py backend/tests/test_ontology.py -q
cd frontend && npx tsc --noEmit
```

Manual acceptance checks:

1. “Agenda Carlos toda quinta das 19 às 20” resolves the contact and creates
   an **individual weekly** confirmation preview.
2. Selecting an inferred place, then replying “go on”, preserves Carlos and
   individual format.
3. “Abra uma turma toda quinta às 19h” still previews `0/4` and creates an
   empty group after confirmation.
4. “Transforme a aula do Carlos em turma” continues to use explicit promotion
   rather than recreate the appointment.

## Risks and safeguards

| Risk | Safeguard |
|---|---|
| Weekly support changes one-off agent bookings | `is_recurring` defaults to `false`; preserve existing direct mutation tests |
| Model still chooses the wrong tool | Strongly disjoint tool descriptions, prompt precedence, and mocked tool-selection regression cases |
| Follow-up “go on” loses the contact context | Two-turn contract test requires Carlos’ ID in the proposed candidate |
| Explicit group workflows regress | Dedicated empty-group regression test and no change to group-slot persistence |
| Appointment and group conflict rules diverge | Reuse `appointments.assert_no_conflict` and `appointments.create_appointment` instead of adding agent-only checks |
| Audit cannot explain weekly behavior | Persist recurrence/format fields in the existing appointment-created event payload |

## Completion criteria

- [ ] A named customer plus explicit weekly cadence always produces a weekly
  individual appointment proposal unless group intent is explicit.
- [ ] A confirmed recurring individual proposal persists an `Appointment`, not
  a `RecurringSlot`.
- [ ] Explicit empty-group creation remains available and unchanged.
- [ ] The exact reported two-turn dialogue has deterministic regression
  coverage.
- [ ] Focused backend tests and TypeScript verification pass.

# Group Capacity & Slot Promotion Roadmap v0.1 — 2026-08-21

## Status

**Roadmap state:** implementation complete; remote rollout remains separately
approved.

This roadmap defines an Agenda-first workflow for reserving preferential
group-class times, converting existing individual classes into group classes,
and filling open seats with permanent or sporadic customers. It builds on the
completed place-stay redesign: Places continue to supply location context and
defaults, while real classes remain independent calendar items layered above
them.

Status notation:

- `[ ]` not started
- `[-]` in progress
- `[x]` completed and verified
- `[!]` blocked; record the blocker beside the item

Update the phase checkbox and the **Progress log** when implementation moves
forward. A phase is complete only after its exit criteria and verification
checks pass.

## Product decision

The platform will treat class format and occupancy as independent concepts:

- **Place stay:** where the instructor is normally expected to be; supplies a
  suggested place but is not a class or a busy occurrence.
- **Class format:** an explicit, durable `individual` or `group` decision.
- **Occupancy:** the number of customers currently assigned.
- **Capacity:** the maximum number of customers accepted by a group class.

A group with zero or one participant remains a group. Participant count must
never be used to infer or silently change the class format. Consequently, an
open group seat is bookable capacity, but it is not free instructor time.

Product copy should favor **turma**, **aula em grupo**, **turma com vagas**, and
**transformar em grupo**. “Promotion” is useful implementation language but is
less clear as an instructor-facing label.

## Goals

1. Create a one-off or weekly group slot with zero to four initial customers.
2. Convert an existing individual class into a group while preserving its
   customer, place, schedule, recurrence, and audit history.
3. Keep group intent visible when only zero or one customer is assigned.
4. Add a customer either permanently to a recurring roster or sporadically to
   one dated occurrence.
5. Let the active agent offer existing group seats alongside genuinely free
   times when answering scheduling questions.
6. Make every write tenant-scoped, confirmation-gated where applicable, and
   auditable, with optimistic Agenda updates and rollback on failure.

## Non-goals for v0.1

- Moving class configuration back into Places or converting a place stay into
  a class.
- Building a standalone group entity shared by multiple schedules. For this
  release, one recurring class series remains one group identity.
- Automatic level enforcement. Level may rank or explain a suggestion, but it
  will not block enrollment without a separate product decision.
- Automatic outreach to customers or acceptance through customer-facing chat.
- Variable capacity above the platform's existing limit of four participants.
- Replacing the existing `Appointment` and `RecurringSlot(slot_kind="class")`
  stores with a new universal scheduling table.

## Current-state assessment

The platform already contains most of the foundation:

- `RecurringSlot(slot_kind="class")` stores `class_type`, group capacity,
  recurrence, level, place, and a permanent roster.
- `Appointment` stores explicit `class_type`, supports one to four customers,
  and may recur weekly.
- The shared scheduling projection merges appointments and recurring classes
  into dated occurrences.
- The Agenda renders recurring classes separately from place stays and already
  exposes incomplete-group filtering and revenue-capacity previews.
- The active agent can find recurring groups, add permanent group members, and
  add participants to appointments through propose-confirm-execute actions.

The requested experience is blocked by several inconsistencies:

| Area | Current behavior | Required behavior |
|---|---|---|
| Empty group creation | The group-specific API and UI require at least one customer | A group slot may start with no customers |
| Format stability | Removing the final extra appointment participant changes the class back to individual | Explicit group intent survives roster changes |
| Promotion | An appointment becomes a group only as a side effect of adding a second participant | The instructor can explicitly transform it before another customer joins |
| Capacity | Recurring classes have `max_participants`; appointments use an implicit constant of four | Every group calendar item exposes explicit capacity |
| Sporadic enrollment | Recurring membership affects the whole series; no dated guest enrollment exists | Add or remove a customer for one occurrence without changing the standing roster |
| Availability search | Group classes are correctly treated as busy and disappear from free-time results | Search separately reports joinable group seats |
| Agenda controls | Appointment and recurring-group detail panels are mostly read-only | Panels expose promotion, capacity, and roster actions |
| Agenda labels | Appointment format is not visible; incomplete groups exclude zero participants and assume capacity four | Every class shows its format and actual occupancy/capacity |
| Agent creation | The agent can create appointments and modify rosters but cannot create an empty group slot | A confirmation-gated empty/seeded group-slot mutation is available |

## Locked business rules

1. **Places remain background context.** Creating or promoting a class must
   never mutate or reuse the ID of its covering place stay.
2. **Format is explicit.** A class changes between individual and group only
   through an explicit user or confirmed agent action.
3. **Group identity survives occupancy changes.** A `group` with zero or one
   participant remains `group` until explicitly converted to individual.
4. **Individual capacity is one.** A class cannot be converted to individual
   while more than one effective participant is assigned.
5. **Group capacity is one to four in the existing model.** Occupancy must not
   exceed the item's configured capacity.
6. **Promotion preserves the existing booking.** Customer, schedule, place,
   recurrence, status, financial settings, overrides, and historical links
   remain valid. Promotion changes format/capacity; it is not cancel-and-create.
7. **Empty group slots are real commitments.** They occupy the instructor's
   calendar and participate in conflict checks even before a customer joins.
8. **A group seat is not a free slot.** Free-time search continues to subtract
   the class; booking-option search may separately offer its remaining seats.
9. **Enrollment scope is explicit.** `series` changes the standing roster;
   `occurrence` changes only the selected date. UI and agent previews must name
   the scope before execution.
10. **Recurring promotion scope is explicit.** A dated occurrence may be
    opened to a group without silently changing every future occurrence; a
    series promotion applies to the standing schedule.
11. **Sporadic participants share the class occurrence.** Do not create an
    overlapping appointment to represent a guest in an existing group.
12. **Capacity is revalidated at execution.** Agent proposals and optimistic
    UI actions must reconcile against current occupancy before committing.
13. **Tenant isolation is mandatory.** Class, contact, place, participant, and
    occurrence queries derive the professional from authentication, never the
    request body.
14. **Writes are audited.** Creation, promotion, capacity changes, and roster
    changes record actor, channel, before/after state, and occurrence scope.
15. **Pricing uses effective participant count.** Existing pricing precedence
    remains unchanged; full-capacity previews use the item's configured
    capacity rather than a hard-coded four.

## Target user experience

### Agenda: create from an empty time

Clicking or selecting an empty interval continues to open one compact creation
flow with three choices:

1. **Aula individual** — requires one customer.
2. **Abrir turma** — permits zero to four initial customers and asks whether it
   happens once or repeats weekly.
3. **Evento** — retains the existing instructor-event workflow.

For **Abrir turma**, preselect a place only when the existing place-stay
resolver finds exactly one covering stay. Default capacity to four. Name and
level remain optional; neither blocks saving. Display a clear summary before
save, such as “Turma semanal, terça 18:00–19:00, Clube, 0/4 alunos.”

### Agenda: interact with a class

Every class card and detail panel must expose format without relying on color:

- `Individual · Maria`
- `Grupo · 1/4`
- `Grupo · 0/4 · com vagas`
- `Grupo · 4/4 · lotado`

Use a group icon/badge from the existing professional icon library. Group
cards remain solid real calendar commitments; do not style them like free time
or waitlist ghost cards.

The class panel exposes only actions valid for its state:

- Individual: **Transformar em grupo**.
- Group with capacity: **Adicionar aluno**.
- Group: **Alterar capacidade** and roster management.
- Recurring item: scope chooser **Somente esta aula** / **Todas as semanas**.

Replace **Grupos incompletos** with **Turmas com vagas**. The filter includes
zero-participant groups and compares occupancy with each item's actual
capacity.

### Evolution of the existing incomplete-groups view

This is an evolution of the Agenda's existing **Grupos incompletos** control,
not a new tab, report, or parallel group-management surface. Preserve its
location beside the Agenda event count and reuse its current calendar-filter
interaction.

The renamed **Turmas com vagas** view becomes the immediate operational result
of every behavior in this roadmap:

- creating an empty group makes its occurrence appear as `0/N`;
- promoting an individual class makes it appear immediately with its retained
  customer as `1/N`;
- adding a permanent member updates every future occurrence;
- adding a sporadic guest updates only the selected occurrence;
- filling the final seat removes only the full occurrence from the filtered
  view;
- removing a participant makes the affected occurrence visible again.

Counts must therefore be occurrence-aware. For example, a weekly group with a
standing roster of `3/4` and one guest next Tuesday is full only next Tuesday;
later weeks remain `3/4` and continue appearing under **Turmas com vagas**.
Opening a card from the filtered view uses the same class detail panel and
promotion/enrollment actions as the normal Agenda view.

### Clientes: keep the useful shortcut

The existing select-customers workflow remains available as **Criar turma com
selecionados**. It creates the same underlying class record used by Agenda;
it is not a second group model. Customer detail may also offer **Adicionar a
uma turma**, listing only compatible groups with remaining capacity.

### Active instructor agent

The agent must distinguish free time from joinable capacity. Example:

> Instrutor: Tenho horário para Ana terça às 18h?

> Agente: Às 18h você já tem a turma Iniciante no Clube, com 2 de 4 vagas
> ocupadas. Quer adicionar a Ana somente nesta terça ou todas as semanas?

Supported intents include:

- “Abra uma turma toda terça às 18h no Clube.”
- “Abra um horário de grupo amanhã às 19h, mesmo sem alunos.”
- “Transforme a aula da Maria de quinta às 19h em grupo.”
- “Coloque o João nessa turma só amanhã.”
- “Adicione a Carolina permanentemente à turma das 18h.”
- “Quais turmas ainda têm vagas esta semana?”

When wording does not establish occurrence versus series scope, the agent must
ask. Every mutation preview names the class, date/time, place, capacity, roster
effect, and scope before confirmation.

## Target technical design

### Preserve current parent records

Do not migrate or recreate existing appointments during promotion. This keeps
IDs referenced by schedule overrides, revenue records, action candidates, and
audit events stable.

- Add explicit `max_participants` to `Appointment`.
- Keep `RecurringSlot.max_participants` for recurring and dated class slots.
- Keep `AppointmentParticipant` and `RecurringSlotParticipant` as standing
  membership for their parent record.
- Remove participant-service behavior that derives `class_type` from roster
  size. Format changes move into a dedicated service operation.

Backfill existing appointments deterministically:

- `individual` → capacity `1`
- `group` → capacity `4`, matching the current implicit appointment limit

### Dated class-format overrides

Introduce a narrow occurrence-level class-definition override for changing
one occurrence without changing its series. Suggested shape:

```text
ScheduleOccurrenceClassOverride
  id
  professional_id
  appointment_id XOR recurring_slot_id
  occurrence_date
  class_type
  max_participants
  actor_user_id
  source
  created_at / updated_at
```

Enforce one row per parent occurrence with partial unique indexes, following
the existing `ScheduleOccurrenceOverride` parent/date pattern. Keep this table
separate from cancellation/rescheduling so one occurrence can be both moved
and opened to a group without overloading `override_type`.

### Dated guest participants

Introduce occurrence-only participant additions instead of overlapping
appointments:

```text
ScheduleOccurrenceParticipant
  id
  professional_id
  appointment_id XOR recurring_slot_id
  occurrence_date
  contact_id
  created_by_user_id
  source
  created_at
```

Enforce uniqueness by parent, occurrence date, and contact. The effective
roster projected by `services/scheduling.py` is:

```text
standing parent participants + dated guest participants
```

Removing a dated guest deletes only that guest assignment. A standing member's
absence continues through the existing absence/credit flow and must not be
mistaken for roster removal.

### Shared services and read model

Add one scheduling-domain service for class format/capacity transitions and
one for effective participant assignment. API, agent, projections, financial
preview, waitlist matching, and future passive flows must call these services
rather than implementing capacity rules independently.

Extend `ScheduleOccurrence` with effective `max_participants`,
`participant_count`, and `available_seats`. Read paths return these values
directly; frontend and agent code must not reconstruct them from hard-coded
limits.

The Agenda's existing incomplete-group filter currently renders recurring
classes from static `RecurringSlot` series data. That is insufficient once a
dated guest or occurrence-only promotion can change one week. Extend the
visible-range calendar response with projected recurring-class occurrences
and render those class cards from `services/scheduling.py`. Continue loading
`RecurringSlot(slot_kind="availability")` separately for place-stay background
blocks. During migration, ensure a recurring class is rendered from exactly
one source so the Agenda cannot show duplicate cards.

The **Turmas com vagas** predicate is applied per projected occurrence:

```text
effective_class_type == "group" AND available_seats > 0
```

Do not require `participant_count > 0`; empty preferential groups are a core
case. Group list/detail screens may continue using series-level records, but
the dated Agenda and its filter must use occurrence-level effective values.

Add a capacity-aware booking-options query that returns two explicit lists:

- `free_openings`: calendar-free ranges, preserving current behavior.
- `joinable_groups`: real group occurrences with `available_seats > 0`.

Do not change the meaning of `find_instructor_openings`; either add
`find_booking_options` or compose the existing opening search with a focused
`find_group_openings` service/tool.

## Implementation phases

### [x] Phase 0 — Freeze contracts with behavioral tests

**Objective:** make the intended semantics executable before changing storage
or UI behavior.

**Work**

- Add backend tests proving an empty group is a busy calendar occurrence.
- Add tests proving a one-customer group remains a group after roster changes.
- Add promotion tests for one-off, recurring-series, and dated-occurrence
  scope, including invalid individual conversion with multiple participants.
- Add effective-roster tests for permanent members plus a dated guest.
- Add conflict and capacity-race tests at service execution time.
- Add projection tests for `max_participants`, `participant_count`, and
  `available_seats`.
- Add Agenda-filter contract tests proving the same weekly series may be full
  on a guest occurrence and incomplete on later occurrences.
- Add tenant-isolation tests for every new read/write contract.
- Record current frontend behavior with focused component tests where the
  existing test setup supports them; otherwise define TypeScript verification
  and manual acceptance cases in the phase notes.

**Verification**

```bash
conda run -n agenda pytest backend/tests/test_calendar_mutations.py backend/tests/test_schedule_projection.py -q
```

The new tests should initially fail only for the missing behavior. Existing
tests must continue passing.

**Exit criteria**

- [ ] Every locked business rule that changes backend behavior has a test.
- [ ] Series and occurrence scope are unambiguous in test names and fixtures.
- [ ] No test infers format or capacity from participant count.
- [ ] The existing incomplete-group behavior has a regression fixture before
      it is renamed or expanded.

### [x] Phase 1 — Persist explicit capacity and occurrence participation

**Objective:** establish the smallest durable data model that preserves parent
IDs and separates standing membership from dated guests.

**Work**

- Add `Appointment.max_participants` with a database check of 1–4.
- Backfill capacity `1` for individual appointments and `4` for existing group
  appointments before making the column non-null.
- Add `ScheduleOccurrenceClassOverride` with tenant scope, exclusive parent
  checks, capacity/format checks, FKs, and per-parent occurrence uniqueness.
- Add `ScheduleOccurrenceParticipant` with tenant scope, exclusive parent
  checks, contact FK, and per-parent/date/contact uniqueness.
- Register new models and create one reversible Alembic migration. Do not run
  it against the Azure remote database during development.
- Add shared services to:
  - validate format and capacity;
  - promote a whole parent series;
  - override one occurrence's format/capacity;
  - assign/remove standing participants;
  - assign/remove occurrence-only guests;
  - compute effective occurrence roster and remaining seats.
- Stop `appointment_participants.remove_participant()` from automatically
  demoting a group when one participant remains.
- Update the scheduling projection so empty recurring class rows are included
  as busy occurrences and dated overrides/guests are applied.
- Record operational audit events with before/after state for every mutation.

**Security and integrity**

- Resolve all parent/contact records under the authenticated professional.
- Lock or otherwise serialize the capacity-sensitive mutation so two final-seat
  requests cannot both succeed.
- Reject guest enrollment on cancelled occurrences, inactive parents, or dates
  that are not valid occurrences of the parent.
- Use ORM/parameterized queries only; never accept parent tenant identity from
  the client.

**Verification**

```bash
conda run -n agenda pytest backend/tests/test_schedule_projection.py backend/tests/test_calendar_mutations.py backend/tests/test_tenant_isolation.py -q
conda run -n agenda alembic -c backend/alembic.ini upgrade head
conda run -n agenda alembic -c backend/alembic.ini downgrade -1
conda run -n agenda alembic -c backend/alembic.ini upgrade head
```

Run migration checks only against the local `agenda_db` configuration from
`.env`. Inspect the target URL before each migration command.

**Exit criteria**

- [ ] Existing appointment/group IDs and historical references are unchanged.
- [ ] Empty groups and one-customer groups project with the correct format.
- [ ] Effective occupancy never exceeds effective capacity.
- [ ] A dated guest appears only on the selected occurrence.
- [ ] Removing the final extra participant does not silently change format.

### [x] Phase 2 — Expose one canonical API contract

**Objective:** give Agenda and agent executors the same tenant-scoped service
operations and effective occurrence data.

**Work**

- Allow group creation with zero initial contacts. Keep contact IDs optional,
  unique, tenant-valid, and bounded by capacity.
- Add explicit endpoints/schemas for:
  - promoting or converting class format with `scope=series|occurrence`;
  - changing group capacity with the same scope;
  - adding/removing a participant with
    `enrollment_scope=series|occurrence`;
  - listing joinable group occurrences for a bounded date range.
- Return effective `class_type`, `max_participants`, `participant_count`, and
  `available_seats` from calendar and detail responses.
- Extend the visible-range calendar contract with projected recurring-class
  occurrences so Agenda can evaluate capacity per date. Preserve the existing
  response during migration, but define one canonical class-occurrence DTO for
  both normal rendering and **Turmas com vagas** filtering.
- Preserve existing participant endpoints where compatible, but route them
  through the shared services. Avoid two independently validated code paths.
- Use the project's existing error response conventions. Map missing records
  to 404, invalid transitions to 422, and full/conflicting capacity to 409.
- Apply explicit authenticated-professional authorization to every endpoint.
- Rate-limit state-changing routes, require existing CSRF protection, and
  emit the standard mutation audit record.

**Verification**

```bash
conda run -n agenda pytest backend/tests/test_calendar_mutations.py backend/tests/test_ontology.py backend/tests/test_auth.py backend/tests/test_tenant_isolation.py -q
```

**Exit criteria**

- [ ] API behavior is identical whether called by dashboard or agent executor.
- [ ] Zero-customer groups can be created without weakening individual rules.
- [ ] Every recurring mutation requires explicit series/occurrence scope.
- [ ] Concurrent final-seat attempts produce one success and one safe conflict.
- [ ] A visible recurring class occurrence is returned once, with its effective
      dated roster and capacity.

### [x] Phase 3 — Make group slots visible and creatable in Agenda

**Objective:** let instructors create preferential group slots directly where
they manage time, including slots with no initial customers.

**Work**

- Extend the existing click-to-create dialog; do not introduce a separate
  page or duplicate modal.
- Keep the top-level **Aula / Evento** split and, for Aula, expose
  **Individual / Grupo** before customer selection.
- For Group:
  - allow zero initial customers;
  - expose once/weekly recurrence;
  - default capacity to four;
  - prefill the unique covering place stay;
  - keep name and level optional;
  - show a concise save summary.
- Render explicit format and effective occupancy/capacity on class cards in
  week, day, month, and mobile list views.
- Evolve the existing **Grupos incompletos** chip in place into **Turmas com
  vagas**; preserve its current location, pressed-state interaction, and
  click-through to group details.
- Drive the filter from visible projected occurrences, include occupancy zero,
  and use `available_seats > 0` rather than a hard-coded participant limit.
- Stop rendering recurring class cards from the static series list after the
  projected occurrence feed is active; keep that list only for place-stay
  backgrounds and non-Agenda series management.
- Update group details and revenue-capacity copy to use effective configured
  capacity.
- Add the group slot optimistically to the calendar, replace it with the API
  response on success, and remove it with a visible error on failure.
- Keep place stays unchanged as background events throughout creation.

**Verification**

```bash
cd frontend
npx tsc --noEmit
npm run lint
```

Manual checks:

1. Create an empty weekly group over a place stay and confirm the stay remains.
2. Create a one-customer group and confirm it renders as `Grupo · 1/4`.
3. Create a capacity-two group and confirm `Turmas com vagas` uses `1/2`.
4. Add a dated guest that fills one occurrence; confirm only that date leaves
   **Turmas com vagas**, while later weekly occurrences remain visible.
5. Force an API conflict and confirm the optimistic card rolls back.
6. Repeat the checks in mobile list view.

**Exit criteria**

- [ ] An instructor can reserve a real group slot without selecting customers.
- [ ] Individual/group meaning is readable without relying only on color.
- [ ] Empty and partially occupied groups appear under **Turmas com vagas**.
- [ ] The existing filter remains the single Agenda surface for open group
      capacity and does not duplicate recurring class cards.
- [ ] No Agenda interaction mutates a place stay.

### [x] Phase 4 — Add promotion, capacity, and enrollment actions

**Objective:** manage the full lifecycle from the class detail panel without
forcing the instructor through Customers first.

**Work**

- Add **Transformar em grupo** to eligible individual appointment and
  recurring-class panels.
- For recurring items, require a compact scope choice: **Somente esta aula**
  or **Todas as semanas**.
- Preserve current customer(s) during promotion and preview the resulting
  occupancy/capacity before save.
- Add **Adicionar aluno**, **Remover convidado**, standing-roster management,
  and **Alterar capacidade** when valid.
- When adding to a recurring class, require **Somente esta aula** or
  **Todas as semanas**; use customer search already loaded by Agenda.
- Disable impossible actions locally while relying on server revalidation:
  full class, duplicate participant, capacity below occupancy, or individual
  conversion with multiple effective participants.
- Apply optimistic updates to card badges and panel rosters. Keep the previous
  snapshot, reconcile with the response, and restore it on failure.
- Re-evaluate the existing **Turmas com vagas** filter optimistically after
  create, promotion, capacity, and participant mutations: insert newly
  joinable occurrences and remove only occurrences that become full.
- Dispatch the existing Agenda refresh event after confirmed external/chat
  mutations so both surfaces converge.

**Verification**

```bash
cd frontend
npx tsc --noEmit
npm run lint
```

Manual checks:

1. Promote a one-off individual class and retain its existing customer.
2. Promote only one occurrence of a weekly individual class.
3. Promote the whole weekly series and confirm future weeks update.
4. Add a guest to one date and a permanent member to every week.
5. Remove the only extra participant and confirm the class stays group.
6. With **Turmas com vagas** active, fill and reopen a seat and confirm the card
   disappears/reappears without leaving the filtered Agenda.
7. Simulate a final-seat race and confirm one UI action rolls back cleanly.

**Exit criteria**

- [ ] Promotion never recreates or cancels the underlying booking.
- [ ] Series and occurrence actions have visibly different previews/results.
- [ ] One-customer group intent remains stable after roster edits.
- [ ] Every optimistic mutation has a tested rollback path.

### [x] Phase 5 — Add capacity-aware agent reads and confirmed mutations

**Objective:** let the web/WhatsApp instructor agent offer group seats and
perform the same operations available in Agenda.

**Read tools**

- Add `find_group_openings` or `find_booking_options` for a bounded date range,
  optional place, level preference, contact, and time range.
- Return source type/ID, occurrence date, class label, place, participants,
  capacity, available seats, and whether series enrollment is supported.
- Keep `find_instructor_openings` semantically unchanged: it reports only
  genuinely free time.
- Extend `find_groups` with capacity fields and an optional `has_capacity`
  filter without hiding zero-participant groups.

**Mutation tools**

- `propose_create_group_slot` — zero to four initial customers, once or weekly.
- `propose_set_class_format` — individual/group, capacity, and explicit scope.
- Consolidate or consistently wrap existing participant tools so enrollment
  scope is explicit for both appointments and recurring classes.
- Re-resolve and revalidate all entities at confirmation time.
- Include before/after format, occupancy, capacity, date/time, place, and scope
  in the action preview and audit payload.

**Prompt behavior**

- When asked about a specific occupied time, inspect joinable groups before
  replying that no time exists.
- Never describe a group seat as a free instructor slot.
- Ask occurrence-versus-series scope when the instructor's wording is unclear.
- Do not infer permanent enrollment from “só amanhã,” “avulso,” or a concrete
  single-date request.
- Prefer explicit capacity data returned by tools; never assume four.
- Treat level as explanatory ranking unless a future rule makes it mandatory.

**Verification**

```bash
conda run -n agenda pytest backend/tests/test_agent.py backend/tests/test_calendar_mutations.py backend/tests/test_agent_channel.py backend/tests/test_prompt.py -q
```

Add deterministic agent scenarios for all example utterances in this roadmap,
including ambiguous scope, zero-seat, duplicate-member, and tenant-isolation
cases.

**Exit criteria**

- [ ] The agent offers a suitable 2/4 group at 18:00 instead of saying the
      instructor is unavailable.
- [ ] The agent distinguishes a one-date guest from permanent enrollment.
- [ ] Every write remains propose-confirm-execute on web and WhatsApp channels.
- [ ] Confirmation after a stale/full slot fails safely without partial data.

### [x] Phase 6 — Reconcile downstream scheduling and financial consumers

**Objective:** make open group capacity useful everywhere without changing the
meaning of free time, attendance, credits, or recognized revenue.

**Work**

- Extend waitlist matching so a compatible `class_type="group"` request may
  match an existing group occurrence with a seat, in addition to a free range.
- Keep fulfillment explicit: the instructor chooses whether enrollment is for
  that occurrence or the recurring series.
- Update revenue preview and confirmation to consume the effective occurrence
  roster, including dated guests, and configured capacity.
- Ensure recognized revenue snapshots remain immutable after later roster or
  capacity changes.
- Preserve makeup-credit eligibility for standing recurring members. A dated
  guest does not become a recurring member or gain recurring-member benefits
  merely by joining one occurrence.
- Update daily agenda and financial reporting projections to show effective
  participants while retaining their existing source identifiers.
- Audit every query that treats a class as busy so empty group slots continue
  blocking individual availability.

**Verification**

```bash
conda run -n agenda pytest backend/tests/test_waitlist.py backend/tests/test_revenue.py backend/tests/test_makeup_credits.py backend/tests/test_daily_agenda.py backend/tests/test_financial.py -q
```

**Exit criteria**

- [ ] A waiting customer can match an open group seat without the instructor
      being reported as free.
- [ ] Dated guests appear in occurrence pricing/attendance only on their date.
- [ ] Historical recognized revenue is unchanged by future capacity edits.
- [ ] Empty group commitments are excluded from free-time results everywhere.

### [x] Phase 7 — Documentation, local reconciliation, and rollout

**Objective:** complete cross-platform documentation and prove existing local
data can adopt the new semantics safely before any remote synchronization.

**Work**

- Update `docs/business_rules.md`, `docs/data_architecture.md`,
  `docs/ontology_chat_architecture.md`, and page docs for Agenda, Clientes, and
  Chat.
- Update the root README status only after the feature is implemented.
- Add a read-only reconciliation script under `scripts/` that reports:
  - appointment capacity backfill counts;
  - invalid individual/group occupancy;
  - orphan/cross-tenant participants;
  - duplicate occurrence guests;
  - class rows missing from occurrence projection.
- Run all migrations and reconciliation against local `agenda_db` first.
- Review `.env` server and database targets before every database command.
- Produce a remote migration/synchronization checklist, but do not perform a
  destructive operation or copy local test data into Azure.
- Confirm `requirements.txt` remains accurate; this roadmap should not require
  a new dependency.

**Verification**

```bash
conda run -n agenda pytest backend/tests -q --ignore=backend/tests/test_extraction.py
conda run -n agenda python scripts/audit_group_capacity_semantics.py
cd frontend
npx tsc --noEmit
npm run lint
cd ..
git diff --check
```

**Exit criteria**

- [ ] Full backend and frontend verification passes in the `agenda` env.
- [ ] Local reconciliation reports no invalid or cross-tenant rows.
- [ ] Documentation describes shipped behavior, not planned behavior.
- [ ] Remote rollout steps are additive/reversible and separately approved.

## Remote rollout checklist

This release has been migrated and audited only against local `agenda_db`.
Before any Azure change, an authorized operator should:

1. Review `.env` and confirm the target is the intended remote database; do
   not reuse local test credentials or copy local test data.
2. Take and verify a remote backup, then inspect its current Alembic revision.
3. Review the additive migrations through `e5a8c2f4d7b1` in a staging clone.
4. Apply `alembic upgrade head` once in a maintenance window.
5. Run `scripts/audit_group_capacity_semantics.py` against the approved target
   with aggregate-only output, and investigate every non-zero result before
   enabling the workflow for instructors.
6. Smoke-test empty group creation, one-date enrollment, a waitlist group
   fulfillment, and the **Turmas com vagas** filter with a non-production
   tenant. Keep rollback decisions under the database change-control process.

## Dependency order

```text
Phase 0 behavioral contracts
  -> Phase 1 persistence and shared services
    -> Phase 2 canonical API
      -> Phase 3 Agenda creation/rendering
        -> Phase 4 Agenda mutations
      -> Phase 5 agent reads/mutations
        -> Phase 6 downstream consumers
          -> Phase 7 reconciliation and rollout
```

Phases 3 and 5 may proceed in parallel only after the Phase 2 contracts are
stable. Phase 6 must consume those same contracts rather than introduce a
third definition of available group capacity.

## Release acceptance scenarios

The feature is ready only when all scenarios pass through both API behavior
and the applicable Agenda/agent surface:

1. **Empty preferential group:** create Tuesday 18:00 weekly, capacity four,
   no customers. It renders `Grupo · 0/4`, blocks a conflicting individual
   booking, and appears under **Turmas com vagas**.
2. **One-customer group:** add Maria permanently. Every valid occurrence shows
   `1/4`; the class remains group after any other participant is removed.
3. **Promote a weekly individual series:** transform João's recurring class to
   group capacity three. João remains assigned and every future occurrence
   shows `1/3` without changing the parent ID; the occurrences enter the
   existing, renamed **Turmas com vagas** view immediately.
4. **Promote one occurrence:** open only 2026-09-01 to group. Other occurrences
   of the same series remain individual, and only 2026-09-01 appears in the
   open-group filter.
5. **Sporadic guest:** add Ana only on 2026-09-01. She appears in that day's
   schedule, attendance, and revenue preview, but not in the standing roster or
   later weeks. If she fills the last seat, only that occurrence leaves
   **Turmas com vagas**.
6. **Agent offer:** when asked for Tuesday 18:00, the agent offers the existing
   group seat and does not call it free time.
7. **Full class:** after capacity is reached, Agenda disables addition and a
   stale agent proposal returns a safe 409-style conflict on confirmation. The
   full occurrence leaves the active open-group filter and reappears if a seat
   is subsequently reopened.
8. **Capacity reduction:** reducing capacity below effective occupancy is
   rejected without changing the current value.
9. **Place independence:** every create/promotion scenario leaves the covering
   place stay unchanged.
10. **Tenant boundary:** an instructor cannot view, promote, or enroll a
    customer into another tenant's class, even with a valid UUID.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Appointment and recurring-class stores drift | Put transitions, occupancy, and projection in shared services; keep API/agent executors thin |
| Instructor confuses an empty group with free time | Render it as a solid class commitment with `0/N`, never as background or a ghost card |
| Accidental whole-series change | Require explicit scope and name it in preview/audit data |
| Two customers take the final seat | Revalidate inside a serialized transaction and return a conflict to the loser |
| Dated guest leaks into future occurrences | Store occurrence date explicitly and cover projection boundaries with tests |
| Financial totals change unexpectedly | Price effective dated rosters while preserving immutable recognized snapshots |
| Automatic demotion destroys group intent | Remove roster-count-derived format transitions and test one-customer stability |
| Remote data damage | Develop/migrate/reconcile locally; remote rollout remains additive, reviewed, and separately authorized |

## Deferred decisions

- Whether one stable roster should support multiple weekly meeting times. If
  real usage demonstrates this need, introduce a separate group entity rather
  than silently copying memberships between class slots.
- Whether instructors need a “closed group” state below capacity. v0.1 treats
  every active group with remaining capacity as joinable to the instructor;
  no customer is enrolled or contacted automatically.
- Whether group-seat waitlist matching should use strict or ranked level
  compatibility. v0.1 keeps level advisory.
- Whether recurring `Appointment` records should later migrate to a dedicated
  recurring-class-series table. This is not required for the behavior above.

## Progress log

| Date | Phase | Status | Evidence / decision |
|---|---|---|---|
| 2026-08-21 | Roadmap | Proposed | Agenda-first group capacity, explicit promotion, occurrence-only guests, and evolution of the existing incomplete-groups filter agreed for planning |
| 2026-08-21 | Phases 0–6 | Complete locally | Added appointment capacity migration and explicit appointment promotion; empty recurring groups; dated recurring guests; projected recurring classes in the Agenda; occurrence-aware **Turmas com vagas**; and confirmation-gated agent mutations for empty-group creation, promotion, and one-date guests. Added `find_group_openings` so the agent reports joinable capacity separately from free time. Revenue confirmation consumes the effective dated roster and capacity. |
| 2026-08-21 | Phases 6–7 | Complete locally | Revenue confirmation now consumes dated guests; waitlist requests can be fulfilled into a selected group occurrence or standing series with explicit scope; Agenda exposes that choice from a group occurrence; capacity writes serialize on the parent class; tenant-boundary coverage, local reconciliation, docs, and migrations through `e5a8c2f4d7b1` are in place. The local audit reports zero invalid rows. Remote rollout is intentionally not executed. |

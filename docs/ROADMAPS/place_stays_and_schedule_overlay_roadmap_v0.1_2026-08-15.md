# Place Stays & Schedule Overlay Roadmap v0.1 — 2026-08-15

## Status

**Roadmap state:** approved for implementation; no phase started.

This roadmap is the canonical plan for turning **Meus Locais** into a
background scheduling substrate. A place defines where the professional can
be present, its recurring stay windows, and optional place-specific pricing.
Individual classes, group classes, and non-class events remain independent
calendar items rendered on top of that substrate.

Status notation:

- `[ ]` not started
- `[-]` in progress
- `[x]` completed and verified
- `[!]` blocked; the blocker must be written beside the item

When implementation progresses, update both the phase checkbox and the
**Progress log** at the end of this document. A phase is complete only when
all its exit criteria and verification commands pass.

## Executive decision

The first implementation will use the existing `RecurringSlot.slot_kind`
boundary rather than immediately creating new database tables:

- `slot_kind="availability"` means **place stay**: the professional is
  normally present at a place during that interval. It has no class format,
  roster, level, or participant capacity.
- `slot_kind="class"` means **recurring class series**: an actual scheduled
  class with format, roster, level, and maximum participants.
- `Appointment` remains the one-off or weekly appointment entity and owns its
  own `class_type` and participants.
- `InstructorEvent` remains a non-class calendar commitment such as a clinic,
  workshop, or tournament. In product copy, use **calendar item** when
  referring to appointments, recurring classes, and instructor events
  collectively; reserve **event** for `InstructorEvent`.

This staged approach preserves existing IDs referenced by occurrence
overrides, makeup credits, revenue records, audit events, and agent proposals.
A physical `PlaceStay`/`RecurringClassSeries` table split is a later decision,
not a prerequisite for the requested behavior.

## Target domain model

```text
Work Journey (outer working-hours envelope)
  └── Place Stay (where the professional normally is)
        └── Calendar item (what actually happens)
              ├── Appointment: individual or group, 1–4 customers
              ├── Recurring class series: individual or group, roster
              └── Instructor event: clinic/workshop/tournament/other

Place + occurrence date/time + participant count
  └── financial pricing resolution
        └── immutable snapshot when revenue is recognized
```

The place stay supplies context; it is not itself a class, a group, or a busy
calendar occurrence.

## Locked business rules

1. **Work Journey is the outer envelope.** Place stays attribute portions of
   working time to venues. Unattributed Work Journey time can still exist.
2. **Full containment is required for automatic inheritance.** A calendar
   item from 13:00–14:00 matches only a stay whose interval contains the full
   hour. Partial overlap never resolves a place.
3. **Exactly one matching stay:** preselect/inherit its `place_id`.
4. **Multiple matching stays:** require an explicit place choice; never guess.
5. **No matching stay:** do not infer a place. The dashboard or active agent
   may continue only after an explicit place choice and a visible exception
   warning. Passive automatic execution remains disabled in this case.
6. **Calendar items persist their resolved `place_id`.** Editing a future stay
   does not silently move or reprice already-created items.
7. **Stay edits do not rewrite history.** Existing and recognized occurrences
   retain their stored/snapshotted place and revenue data.
8. **Place-specific pricing is selected by the calendar item's `place_id`.**
   Pricing precedence remains customer → group → place → generic → tenant.
9. **Only active availability rows create place-attributed financial
   capacity.** Class rows must never increase capacity.
10. **Place stays are not busy occurrences.** Appointments, recurring classes,
    and instructor events occupy the calendar; stays are background context.
11. **The professional cannot normally stay at two places simultaneously.**
    Existing cross-place overlap rejection remains. Supporting alternative
    venues at the same time would require a separate future concept.
12. **A group can contain 1–4 customers.** A one-customer group remains a
    group and is incomplete until it reaches four customers.

## Current-state assessment and touchpoint map

### Data model

| Touchpoint | Current coupling | Required direction |
|---|---|---|
| `Place` | Venue identity, address, normalized name | Keep as the tenant-scoped venue catalog |
| `RecurringSlot` | Represents both availability and recurring classes; availability still carries class-only fields | Enforce behavior by `slot_kind`; availability becomes neutral place stay |
| `RecurringSlotParticipant` | Roster for class slots; adding the first participant can convert availability to class | Permit participants only on class rows; never mutate a stay into a class |
| `Appointment` / `AppointmentParticipant` | One-off or weekly class with explicit place and 1–4 participants | Keep; resolve/preselect place from stays during creation/rescheduling |
| `InstructorEvent` | Non-class commitment, optional place and flat income | Keep; define whether a place is inferred or explicitly exceptional per flow |
| `ScheduleOccurrenceOverride` | Targets appointment or recurring-slot IDs | Preserve IDs during staged refactor; revalidate destination place stays on reschedule |
| `MakeupClassCredit` | Origin points directly to a class-type `RecurringSlot` | Keep compatible while class rows remain in the table |
| `RevenueOccurrence` | Source type is appointment or recurring slot and snapshots place/value data | Preserve source compatibility and immutable recognized snapshots |
| `Contact.home_place_id` | Preferred/usual location | Keep as preference/tie-breaker, never proof of presence at a requested time |

### Backend APIs and schemas

- `GET/POST/PATCH/DELETE /api/places`: venue CRUD remains, but deletion policy
  must be reviewed so historical calendar/revenue records are not damaged.
- `/api/recurring-slots`: currently returns and mutates availability and class
  rows together. Add explicit kind filtering and canonical validation.
- `/api/recurring-slots/groups` and participant endpoints: remain class-only;
  reject availability IDs rather than promoting them.
- `POST /api/appointments`: already owns group/individual and 1–4 participant
  selection. Add shared stay resolution/validation and exception metadata.
- `/api/instructor-events`: use the same place-context resolver where
  appropriate, while retaining an explicit exception path for events outside
  normal teaching stays.
- `/api/calendar`: return enough explicit metadata (`slot_kind`, class type,
  participants) for rendering without inference from participant count.
- Financial quote/dashboard/scenario/revenue APIs: consume availability for
  capacity and occurrences for realized/projected revenue.

### Core services

- `services/scheduling.py`
  - `_load_place_availability_ranges` currently loads every active
    `RecurringSlot`; it must load only availability rows.
  - `_slot_occurrences` must continue projecting only class rows with rosters.
  - Introduce one shared `resolve_place_stay(...)` contract used by every
    creation and rescheduling path.
- `services/appointments.py`
  - Keep Work Journey and busy-time validation.
  - Add place-stay context validation without treating stays as conflicts.
- `services/instructor_events.py`
  - Preserve broad event flexibility but make place inheritance and explicit
    exceptions deterministic.
- `services/participants.py`
  - Remove availability-to-class promotion.
  - Reject roster writes against availability rows.
- `services/financial_capacity.py`
  - Build place capacity only from stay rows.
  - Preserve generic/unattributed Work Journey capacity.
- `services/revenue_occurrences.py`
  - Continue pricing from the occurrence's persisted place.
  - Preserve recognition snapshots after stay or price changes.
- `services/waitlist.py`
  - Match venue-attributed openings from stays, then create an independent
    appointment when fulfilled.
- `services/makeup_recommender.py`
  - Separate place capacity inputs from recurring-class level/roster inputs.
- `services/schedule_conflicts.py` and `services/schedule_overrides.py`
  - Continue treating real occurrences as busy.
  - Validate the destination stay context on reschedule.

### Frontend

- **Meus Locais:** rename “Horários fixos” to “Permanência neste local”; remove
  class type, level, participant maximum, and roster from stay creation.
- **Agenda:** render stays as non-click-to-book background context and actual
  classes/events above them. Use `slot_kind`, never participant count, to
  decide which is which.
- **Novo agendamento:** keep the individual/group selection and 1–4 customer
  picker. Preselect the unique matching place stay and explain inheritance.
- **Recurring groups:** keep creation and roster management in Agenda/Clientes
  or a dedicated Groups surface, not inside Meus Locais.
- **Clientes:** `home_place` stays a preference. “Assign to slot” must create or
  update a class and must never consume/convert the background stay row.
- **Financeiro:** keep place price configuration with the place; capacity and
  simulator views consume neutral stays.
- **Waitlist and makeup:** present stay-derived locations as candidate context,
  while class format remains attached to demand or the created class.

### Active conversational agent

- `search_places` remains the deterministic tenant-scoped name resolver.
- `find_instructor_openings` must report both calendar-free intervals and the
  stays that fully cover each interval.
- `propose_create_appointment` must accept class type and 1–4 customers, use
  the shared stay resolver, and surface inherited/exceptional place context in
  its confirmation preview.
- `propose_reschedule_occurrence` must resolve the destination place again.
- Group lookup/member/cancellation tools must target class rows only.
- Read tools and prompts must stop describing availability as a class or group.
- All mutation executors must revalidate at confirmation time because a stay
  can change after a proposal is created.

### Passive conversational observer

- Candidate extraction remains evidence-based and does not infer a group from
  a single customer conversation without explicit evidence.
- Candidate resolution must match the requested interval against place stays.
- `home_place_id` can break a tie only when that place has a covering stay; it
  cannot manufacture availability.
- Exactly one stay can resolve the place automatically.
- Zero or multiple stays keep the candidate unresolved and prevent automatic
  execution.
- Ambiguity escalation and review dialogs must expose the missing/ambiguous
  place context.
- Automatic execution and private confirmation delivery must revalidate the
  selected stay and include the venue in their preview/audit payload.

### Cross-cutting documentation and tests

- Update architecture, data model, business rules, Agenda, Clientes,
  Financeiro, AI modes, and ontology/chat documentation.
- Update fixtures that currently infer class semantics from participant count.
- Preserve tenant isolation, explicit role checks, audit events, proposal
  confirmation, and optimistic UI rollback behavior.

## Impact summary

This is a **medium-to-high-impact behavioral refactor** with a low initial
schema-migration requirement. The highest-risk areas are recurring group
identity, destination-place inference, passive automatic execution, makeup
credit foreign keys, and financial capacity. The staged plan below keeps each
phase deployable and avoids an all-at-once table migration.

## Delivery phases

### [ ] Phase 0 — Characterization, vocabulary, and safety baseline

**Objective:** freeze existing behavior with tests and establish terminology
before changing production semantics.

**Scope**

- Add test factories that explicitly create availability rows and class rows;
  do not rely on defaults where the distinction matters.
- Characterize current behavior for:
  - calendar projection;
  - capacity attribution;
  - Work Journey gaps without a place;
  - recurring groups and one-customer groups;
  - waitlist matching;
  - makeup recommendations;
  - active-agent openings and proposals;
  - passive candidate resolution and automatic execution.
- Document and consistently use the terms **place stay**, **calendar item**,
  **appointment**, **recurring class**, and **instructor event**.
- Record the count of existing rows by `slot_kind`, participant presence, and
  invalid combinations using a read-only audit script in `scripts/`.
- Add no production data mutation in this phase.

**Verification**

- Focused tests demonstrate the current distinction and known coupling.
- The audit script is tenant-safe, read-only, and runs against the local DB.
- No API response or user-visible behavior changes.

**Exit criteria**

- [ ] Baseline tests pass in the `agenda` conda environment.
- [ ] Data audit results are recorded in this roadmap's progress log.
- [ ] Vocabulary is reflected in affected page/business-rule docs.

**Rollback:** documentation/tests only; remove the new tests/script if needed.

### [ ] Phase 1 — Enforce the semantic boundary in the existing model

**Objective:** make `slot_kind` authoritative without changing table identity
or breaking existing references.

**Scope**

- Define canonical invariants:
  - availability: no participants, no group name, no level, neutral class
    defaults ignored by consumers;
  - class: valid class type, participant capacity, optional roster/group data.
- Update recurring-slot schemas and endpoints to validate these combinations.
- Add `slot_kind` filters to list APIs and frontend types.
- Change participant services to reject availability IDs instead of converting
  availability into a class.
- Make schedule projection select only class rows for occurrences.
- Make place availability/capacity loaders select only availability rows.
- Correct conflict checks so stays are not treated as busy classes and classes
  are not treated as capacity.
- Add a forward-only local migration/data repair if Phase 0 discovers invalid
  combinations. Preserve primary keys and all foreign-key references.

**Verification**

- Unit tests for every allowed/forbidden `slot_kind` transition.
- Integration tests prove an availability row does not appear as a class,
  does not produce revenue, and does contribute place capacity.
- Integration tests prove a class row does appear as an occurrence and does
  not independently increase place capacity.
- Existing override, makeup-credit, revenue, and tenant-isolation tests pass.

**Exit criteria**

- [ ] No consumer infers slot meaning from participant count.
- [ ] No write path promotes a stay into a class.
- [ ] Existing class IDs and their dependent records remain valid.
- [ ] Full backend suite passes.

**Rollback:** revert behavior changes; no destructive table split occurs.

### [ ] Phase 2 — Meus Locais becomes the place-stay management surface

**Objective:** deliver the requested neutral “stay time” UX independently of
calendar-item creation.

**Scope**

- Rename “Horários fixos” to “Permanência neste local” in product copy.
- Replace the place slot form with a stay form containing only:
  - repetition/day selection;
  - start/end time;
  - effective date range where supported;
  - optional resource/identification label.
- Always create `slot_kind="availability"` through this surface.
- Remove class type, level, max participants, roster, and group chips from the
  place page.
- List only availability rows on `/places/{id}`.
- Keep place pricing configuration alongside venue details.
- Review place deletion:
  - delete/deactivate future stays;
  - clear customer home-place references;
  - never delete historical appointments, revenue snapshots, or class series;
  - reject deletion or archive the place when referenced records require it.
- Preserve optimistic creation/editing with rollback on API failure.

**Verification**

- Create/edit/delete a stay from Meus Locais and verify it remains class-neutral.
- Cross-tenant place/stay mutations return 404/403 according to existing API
  conventions.
- Place deletion tests cover stays, home-place references, future classes, and
  historical records.
- Frontend TypeScript and responsive checks pass.

**Exit criteria**

- [ ] A user can define venue presence without seeing class terminology.
- [ ] Existing recurring classes are absent from the place-stay editor but
      remain intact elsewhere.
- [ ] Place rates remain editable and unchanged in behavior.

**Rollback:** restore the previous form/list while retaining Phase 1's safe
backend distinction.

### [ ] Phase 3 — Shared place-stay resolver and Agenda overlay

**Objective:** make stays real background context and give every creation path
one deterministic place-resolution policy.

**Scope**

- Add a dedicated, typed service function such as `resolve_place_stay` that:
  - tenant-scopes every query;
  - requires full interval containment;
  - accepts an optional explicitly requested place;
  - returns resolved, ambiguous, uncovered, or invalid-place outcomes;
  - distinguishes ordinary inference from an explicit exception.
- Use the resolver in appointment creation and occurrence rescheduling.
- Return place-stay metadata needed by the frontend without exposing unrelated
  tenant data.
- Agenda rendering:
  - stays are background blocks;
  - class rows are foreground recurring events;
  - appointments and instructor events remain foreground items;
  - rendering decisions use `slot_kind`, never roster size.
- New appointment flow:
  - preselect the unique covering place;
  - request a choice when several stays cover the interval;
  - require explicit place confirmation and show a warning when uncovered;
  - persist the selected `place_id` on the created item.
- Rescheduling repeats resolution for the destination interval and does not
  silently preserve an invalid old place.
- Stay edits must warn/reject when they would orphan future items, according to
  the locked non-rewriting rule; historical items remain untouched.

**Verification**

- Unit matrix: exact containment, partial overlap, no match, one match,
  multiple matches, wrong-tenant place, inactive stay, and date boundaries.
- API integration tests for create/reschedule, including confirmation-time
  revalidation.
- Agenda tests for background/foreground semantics and click behavior.
- No new race permits overlapping real occurrences.

**Exit criteria**

- [ ] Dashboard creation and rescheduling share one resolver.
- [ ] Every saved class has an explicit place or an explicit supported legacy
      exception; no silent inference remains.
- [ ] Editing stays cannot silently move existing calendar items.

**Rollback:** disable automatic preselection and fall back to explicit place
selection; persisted calendar items remain valid.

### [ ] Phase 4 — Class and group flows stop manipulating stays

**Objective:** ensure class format, recurrence, capacity, and rosters are owned
only by real calendar/class entities.

**Scope**

- Keep individual/group selection in “Novo agendamento.”
- Keep 1–4 appointment participants and one-customer groups.
- Move recurring-group creation/management to Agenda, Clientes, or Groups;
  never expose it as editing a stay under Meus Locais.
- Replace “assign customer to availability slot” behavior with:
  - select/create a recurring class over a compatible stay; or
  - add the customer to an existing recurring class with capacity.
- Never reuse the stay's ID as the newly created class's identity.
- Keep class-only fields (`class_type`, `group_name`, `level`,
  `max_participants`, commercial overrides) on class records.
- Keep incomplete-group filtering and current/full-capacity revenue previews
  based on actual class participants.
- Update group entity resolution and group detail APIs to filter class rows.
- Decide after implementation evidence whether recurring classes should remain
  `RecurringSlot(slot_kind="class")` or graduate to `RecurringClassSeries`.
  Record the decision in the progress log; do not split tables speculatively.

**Verification**

- A stay remains unchanged after creating an individual or group class over it.
- A one-customer group stays typed as group and appears as incomplete.
- Adding/removing group members cannot address an availability ID.
- Recurring class cancellation/rescheduling and roster management still work.
- Contact detail accurately separates preferred place, stays, and classes.

**Exit criteria**

- [ ] No UI/API/agent flow turns a stay into a class.
- [ ] Group identity and roster operate independently of place-stay identity.
- [ ] Existing recurring groups retain overrides, credits, and audit history.

**Rollback:** preserve existing class rows and restore the prior class creation
surface; never merge class data back into stay rows.

### [ ] Phase 5 — Financeiro, pricing, and simulator alignment

**Objective:** make neutral place stays the sole source of venue-attributed
capacity while calendar items remain the sole source of participant demand and
revenue.

**Scope**

- Build place capacity from active availability rows only, intersected with
  Work Journey and breaks.
- Preserve Work Journey time not covered by any stay as generic/unattributed
  capacity (`Sem local definido`).
- Continue pricing actual items from their persisted `place_id` using current
  precedence: customer → group → place → generic → tenant.
- Keep recognized revenue immutable through existing line/header snapshots.
- Ensure place-price changes affect future previews/projections but do not
  alter recognized history.
- Simulator:
  - allocate neutral one-hour class blocks over stay capacity;
  - decide individual/group through the scenario distribution;
  - use each block's inherited place price;
  - use generic pricing only for unattributed capacity;
  - retain real/simulated Agenda toggle and slot details.
- Financial dashboard:
  - place breakdown uses stay-attributed capacity;
  - current revenue uses real occurrences only;
  - non-class event income remains separate;
  - incomplete-group current/full-capacity quotes use the occurrence place.

**Verification**

- Capacity tests prove class rows cannot inflate availability.
- Scenario revenue reconciles exactly to its generated one-hour schedule.
- Place, generic, group, and customer rate precedence each have regression tests.
- Recognized-revenue snapshots remain unchanged after stay/rate edits.
- A 100% scenario cannot have fewer utilized hours than its own generated
  schedule reports.

**Exit criteria**

- [ ] Capacity, simulated schedule, and projected revenue share the same stay
      inputs.
- [ ] Actual revenue and scenario revenue use explicit, test-covered pricing
      paths.
- [ ] Dashboard and simulator labels reflect the new semantics.

**Rollback:** retain previous financial endpoints behind the existing feature
flag while reverting capacity selection; no recognized data is rewritten.

### [ ] Phase 6 — Clientes, waitlist, and makeup recommendations

**Objective:** align dependent customer workflows with the stay/class split.

**Scope**

- Clientes:
  - retain `home_place_id` as preference only;
  - distinguish fixed class memberships from place stays;
  - replace any stay-assignment action with class creation or class membership.
- Waitlist:
  - use stays for venue-attributed candidate openings;
  - retain desired `class_type` as demand metadata;
  - create a separate appointment/class when fulfilled;
  - never mark a stay as occupied by mutating it.
- Makeup recommender:
  - derive candidate place/time capacity from stays;
  - derive usual duration, level, roster, and historic group affinity from real
    class memberships/occurrences;
  - preserve cost, flow, preferred-place, and level-match scoring behavior;
  - retain makeup-credit origins and redemption auditability.
- Review cancellation-driven waitlist matching after a real occurrence frees
  time; stay rows themselves do not become open/closed demand records.

**Verification**

- Contact assignment creates/updates a class without changing the stay.
- Waitlist matching respects explicit place, all-place, and uncovered cases.
- Makeup recommendations never treat a neutral stay's ignored class fields as
  level or participant evidence.
- Credit grant/redeem tests and tenant isolation pass.

**Exit criteria**

- [ ] Customer preference, venue presence, and class membership are separate
      concepts in API responses and UI copy.
- [ ] Waitlist and makeup outputs contain a valid place context and explain
      when none is available.

**Rollback:** revert each dependent service independently; Phase 1 invariants
still prevent stay corruption.

### [ ] Phase 7 — Active instructor agent migration

**Objective:** make the directly addressed assistant reason and mutate using
the same place-stay rules as the dashboard.

**Scope**

- Read tools:
  - keep deterministic `search_places` and tenant scoping;
  - update `find_instructor_openings` to return calendar-free intervals plus
    only stays that fully cover the requested duration;
  - distinguish “free but unattributed” from “bookable at this place”;
  - ensure schedule/group tools label stays and classes correctly.
- Mutation tools:
  - extend appointment creation to accept explicit class type and 1–4 contact
    IDs, matching the dashboard contract;
  - call the shared place-stay resolver for creation and rescheduling;
  - require clarification for ambiguous stays;
  - require explicit exception confirmation for uncovered time;
  - keep group member/cancellation tools class-only.
- Prompt/orchestrator:
  - explain stay inheritance rules;
  - never claim the calendar is full merely because no place stay is present;
  - never guess among multiple places;
  - mention inherited or exceptional place in every proposal preview.
- Propose-confirm-execute:
  - proposals remain non-mutating;
  - executors revalidate Work Journey, stay context, tenant, conflicts, and
    group capacity inside the confirmation transaction;
  - audit payloads record requested place, resolved stay, and exception reason.

**Verification**

- Tool tests cover unique, ambiguous, uncovered, explicit-place, and changed-
  before-confirmation cases.
- Conversation tests cover individual and 1–4-person group creation.
- Rescheduling from one place stay to another updates the occurrence place.
- No active-agent mutation bypasses shared services used by the APIs.
- Prompt regression fixtures verify location is always communicated.

**Exit criteria**

- [ ] Active-agent and dashboard outcomes match for identical inputs.
- [ ] Every assistant-created item has auditable place-resolution provenance.
- [ ] Confirmation-time race tests pass.

**Rollback:** disable the new tool parameters/prompts and require explicit
place selection; existing proposals remain governed by their stored contract.

### [ ] Phase 8 — Passive observer and automatic-execution safety

**Objective:** migrate passive detection, review, escalation, and automatic
execution without increasing autonomous scheduling risk.

**Scope**

- Candidate resolution:
  - match proposed interval against stays using the shared resolver;
  - use `home_place_id` only as a tie-breaker among valid covering stays;
  - report zero matches as missing place context;
  - report multiple matches as explicit ambiguity;
  - never autoexecute an uncovered or ambiguous candidate.
- Extraction:
  - preserve evidence-first behavior;
  - add class type only when explicit evidence supports it;
  - retain individual as the safe single-customer default;
  - do not infer additional group participants from one customer conversation.
- Review UI/API:
  - expose resolved/inferred place, matching stay, ambiguity, and exception
    state;
  - let the instructor supply a place override before confirmation.
- Automatic authoritative creates:
  - require a unique valid stay or explicit reviewed place;
  - revalidate stay and conflict state in the nested transaction;
  - preserve the candidate when execution fails so it remains reviewable.
- Ambiguity escalation:
  - include the inferred venue in private confirmation text;
  - queue rather than expire candidates that can be resolved by instructor
    choice, according to existing TTL/retry rules;
  - preserve idempotency across retries.
- Reschedules:
  - resolve the destination stay instead of automatically carrying the old
    place into an incompatible time.

**Verification**

- Passive fixtures for unique stay, home-place tie-break, zero stay, multiple
  stays, explicit place, and stay changed before execution.
- Automatic execution occurs only for fully resolved, authoritative evidence.
- Ambiguous/uncovered candidates never create appointments automatically.
- Delivery retries do not create duplicate proposals or appointments.
- Operational events contain inference and source-channel provenance without
  leaking customer PII into logs.

**Exit criteria**

- [ ] Passive automation is no more permissive than the dashboard/active agent.
- [ ] Every autoexecuted appointment has a valid, reproducible place decision.
- [ ] Review and escalation surfaces explain why place input is required.

**Rollback:** disable autoexecution/place inference through the passive flow;
retain detected candidates for manual review.

### [ ] Phase 9 — Hardening, optional physical split decision, and rollout

**Objective:** finish migration safely, remove compatibility ambiguity, and
decide whether the stable semantics justify new tables.

**Scope**

- Run the Phase 0 audit again and reconcile every invalid/legacy row.
- Add database constraints or service-enforced invariants where PostgreSQL
  cannot express cross-table roster rules safely.
- Review indexes for stay containment queries by tenant/place/weekday/status.
- Confirm API pagination/bounds where newly separated lists could grow.
- Add rate limits/audit coverage to any new write endpoints using project
  conventions.
- Review place deletion/archive behavior against all foreign keys.
- Run the physical-split decision gate:
  - split only if mixed-table branching remains a demonstrated source of bugs
    or prevents required queries;
  - otherwise retain the proven `slot_kind` representation;
  - if splitting, write an additive migration, dual-read verification, explicit
    ID/reference mapping, and rollback plan before removing old paths.
- Update seed/demo data and local development scripts.
- Update all affected documentation and mark superseded ontology statements.
- Roll out locally first; never perform destructive operations against the
  Azure remote PostgreSQL database. Sync only validated additive data/schema
  changes through the project's normal migration process.

**Verification**

- Full backend suite, frontend type/build checks, and focused end-to-end flows.
- Read-only before/after reconciliation reports show no missing class roster,
  override, credit, revenue, or audit references.
- Manual walkthrough:
  1. define Work Journey;
  2. define two place stays;
  3. create individual/group/event overlays;
  4. reschedule across venues;
  5. run waitlist and makeup recommendations;
  6. run financial dashboard and simulator;
  7. execute equivalent active and passive conversational flows.
- Security review covers tenant isolation, authorization, input validation,
  CSRF/write protection, audit provenance, and safe error responses.

**Exit criteria**

- [ ] Phase 0 and Phase 9 audits reconcile.
- [ ] No code path depends on availability class fields or participant-count
      inference.
- [ ] Documentation and seed data describe the shipped model.
- [ ] Physical split decision and rationale are recorded below.
- [ ] Full verification commands and results are recorded in the progress log.

**Rollback:** retain the prior additive schema/read path until reconciliation
and production validation complete; do not drop old structures in the same
release that introduces replacements.

## Dependency order

```text
Phase 0
  └── Phase 1
        └── Phase 2
              └── Phase 3
                    ├── Phase 4
                    │     └── Phase 6
                    ├── Phase 5
                    ├── Phase 7
                    └── Phase 8
                           └── Phase 9
```

- Phases 2–3 require Phase 1.
- Phases 4–5 can proceed independently after Phase 3, but both must complete
  before Phase 6 is considered final.
- Phases 7–8 require the shared resolver from Phase 3 and stable class behavior
  from Phase 4. They may be implemented independently of one another.
- Phase 9 begins only after Phases 4–8 are complete.

## Likely implementation inventory

This list is a routing guide, not permission for broad refactoring. Touch only
files required by the active phase.

### Backend

- Models: `place.py`, `recurring_slot.py`, `recurring_slot_participant.py`,
  `appointment.py`, `schedule_occurrence_override.py`,
  `makeup_class_credit.py`, `revenue_occurrence.py`.
- Schemas/APIs: `schemas/ontology.py`, `schemas/api.py`, `api/places.py`,
  `api/recurring_slots.py`, `api/calendar.py`, `api/instructor_events.py`,
  `api/contacts.py`, `api/waitlist.py`, `api/financial.py`.
- Scheduling: `services/scheduling.py`, `services/appointments.py`,
  `services/instructor_events.py`, `services/schedule_conflicts.py`,
  `services/schedule_overrides.py`, `services/participants.py`.
- Dependent domains: `services/financial_capacity.py`,
  `services/financial_analytics.py`, `services/revenue_occurrences.py`,
  `services/waitlist.py`, `services/makeup_recommender.py`,
  `services/makeup_credits.py`.
- Active agent: `agent/tools.py`, `agent/entity_resolution.py`,
  `agent/mutations.py`, `agent/orchestrator.py`.
- Passive observer: `chat/pipeline.py`, extraction schemas/prompts,
  `services/candidate_resolution.py`, `services/candidate_execution.py`,
  `services/passive_escalation.py`, candidate review APIs.

### Frontend

- Places pages and `recurring-slot-form-dialog.tsx`.
- `week-calendar.tsx`, appointment/event forms and detail panels.
- Group creation/details/assignment components.
- Clientes detail and slot-assignment components.
- Financeiro dashboard, place rates, simulator, and simulated Agenda.
- Shared API types and client methods.

### Tests

- `test_ontology.py`, `test_schedule_projection.py`,
  `test_calendar_mutations.py`, `test_financial.py`, `test_revenue.py`,
  `test_waitlist.py`, `test_makeup_credits.py`, `test_instructor_events.py`,
  `test_agent.py`, `test_pipeline.py`, and relevant extraction fixtures.

## Deferred decisions and explicit non-goals

- A separate `Court`/resource entity under `Place` is not included. Keep the
  optional stay label until resource-level availability or pricing is required.
- Multiple simultaneous stays/alternative venues are not included.
- Travel-time routing between places is not included; it may later consume
  stored latitude/longitude.
- Editing/cancelling all calendar-item types from every UI surface is not part
  of this refactor unless required for semantic correctness.
- New pricing algorithms are not included; only correct place selection and
  existing precedence are in scope.
- A Markov or probabilistic demand model is unrelated to this ontology change.
- Physical table separation is gated by Phase 9 evidence.

## Progress log

Add one dated entry whenever a phase starts, completes, is rolled back, or is
blocked. Include the exact verification commands and meaningful results.

| Date | Phase | Status | Summary and verification |
|---|---|---|---|
| 2026-08-15 | Roadmap | Created | Target model, touchpoints, phased delivery, safety rules, and completion protocol documented. No implementation phase started. |

## Physical split decision record

**Status:** deferred to Phase 9.

Record the final decision here with evidence, migration identifiers, reference
reconciliation results, and rollback strategy. Until then,
`RecurringSlot.slot_kind` remains the canonical compatibility boundary.


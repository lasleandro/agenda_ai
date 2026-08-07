# Commercial & Financial Module Roadmap v0.2 — 2026-08-05

## Status

Active implementation roadmap. It sequences the requested customer/group workflow improvements and introduces an optional tenant-level commercial and financial module without changing current behavior for tenants where the module is disabled.

## Implementation progress

- **Phase 1 started on 2026-08-05:** group creation now accepts one initial customer, and Clientes has a per-customer action to add that customer to an eligible existing group with optimistic UI rollback.
- Focused tenant-isolation, capacity, duplicate-membership, and one-customer group behaviors are covered by the ontology integration suite.
- The explicit commercial status `waiting` remains part of Phase 3. Until then, a one-customer group can exist operationally with capacity remaining without conflating commercial status with the recurring slot's technical status.
- **Phase 2 completed on 2026-08-05:** `commercial_financials` is disabled by default, platform admins can toggle it optimistically from tenant administration, and every real state change records an immutable before/after audit entry with actor and request origin.
- Authenticated tenant sessions now expose enabled feature capabilities, and a reusable backend guard is available for the financial endpoints introduced in later phases.
- **Phase 3 completed on 2026-08-05:** customers and groups have nullable commercial-status and per-participant hourly-rate overrides, tenants have a default commercial status and global rates for one through four participants, and feature-guarded APIs return explicit values, effective values, and inheritance sources.
- Financial configuration and override writes are audited. Integration coverage includes customer → group → tenant precedence, explicit zero, clearing an override, one customer in multiple group contexts, validation bounds, disabled features, and tenant isolation.
- **Phase 4 completed on 2026-08-05:** enabled tenants can edit customer overrides and group defaults from their existing detail experiences, leave either field empty to restore inheritance, and see effective status/rate with its customer, group, tenant, or unset source.
- Group details show each participant's effective commercial values and source. Disabled tenants neither render the controls nor call financial endpoints, and writes use optimistic UI with rollback.
- **Phase 5 completed on 2026-08-05:** the feature-gated Financeiro area provides global one-to-four-person rates, editable prime-time weekday ranges, sparse regular/prime overrides per place, and weekday/weekend work journeys with optional breaks.
- Enabled tenants can edit the same regular/prime place-rate matrix directly from each Meus Locais detail page; disabled tenants see no financial cue and make no financial configuration request.
- The backend rejects overlaps and cross-midnight ranges, preserves explicit zero and global fallbacks, audits complete before/after configuration versions, and exposes an explainable quote that splits an interval at regular/prime boundaries with per-segment source and totals.
- **Phase 6 initial release completed on 2026-08-05:** Financeiro now has a dashboard for scheduled revenue, occupancy, openings, participant-hours, time series, place, part-of-day, weekday, and regular/prime breakdowns. Capacity is the intersection of the net work journey and the fixed availability reserved at each place, so merely registering more places does not inflate capacity.
- Full-capacity presets compare all-individual, observed-demand, and four-person-group mixes. The what-if simulator changes occupancy, participant mix, regular/prime per-participant rates, period, and place; it reports baseline deltas and the group occupancy needed to match an individual class. Saved scenarios retain immutable input/result snapshots and an audit event.
- Dashboard revenue is explicitly scheduled/projected, not recognized revenue. Attendance, cancellations, costs, taxes, and immutable occurrence pricing remain Phase 7 concerns.
- **Phase 7 initial release completed on 2026-08-05:** the Receita area lists schedule occurrences without recognizing them automatically. Users explicitly record each participant as attended, no-show, or cancelled and independently decide whether that participant is billable.
- Confirmation freezes the schedule source, date, duration, place, participant identity/name, price segments, regular/prime category, matched customer/group/place/tenant rule, quoted amount, billed amount, and manual occurrence adjustment. Later schedule, membership, or rate edits do not alter the snapshot.
- Recognized-revenue reports include totals and time series plus place, customer, and group breakdowns. Confirmation is tenant-scoped, duplicate-protected, rejects future occurrences and incomplete billable prices, and writes an immutable financial audit event. Partial-duration attendance and automated cancellation policies remain future refinements.

## Product goal

Give professionals a lightweight way to organize customer and group commercial status, configure pricing and hourly revenue expectations, and eventually calculate auditable revenue, capacity, and schedule scenarios—while keeping scheduling useful as a standalone product.

The first delivery also closes two immediate group-management gaps:

- add one customer directly to an existing group from the Clientes list;
- allow a group to start with one participant, including a group that is still `waiting`.

## Roadmap assumptions

These assumptions make the roadmap concrete and should be confirmed before implementation:

- A group's hourly rate is a **per-customer default**, not the total revenue for the whole group.
- Global rates for individual, two-, three-, and four-person classes are initially interpreted as **per-participant hourly rates indexed by group size**. The interface must also display the calculated total class revenue to avoid ambiguity.
- Prime time defaults to 05:00–08:00 and 18:00–21:00 in the tenant's timezone. Both ranges are editable, and ranges that cross midnight must be represented explicitly rather than inferred.
- Weekday and weekend work journeys are availability inputs for financial simulation; they do not create appointments or override place availability.
- Customer and group commercial statuses use the values `active`, `waiting`, and `paused`, displayed as **Ativo**, **Em espera**, and **Pausado**.
- Commercial status is distinct from technical record status and scheduling status. Existing fields such as a recurring slot's `active` status must not be reused.
- A group may contain one customer. Its commercial status does not change automatically when more customers join.
- The commercial and financial module is disabled by default for existing tenants and can be enabled per tenant by a platform administrator.
- Disabling the module preserves previously entered data. It hides commercial UI and prevents new financial writes or calculations until re-enabled.

## Scope boundaries

### Included

- Creating a group from one or more selected customers.
- Adding one customer to an existing group from the Clientes screen.
- Customer and group commercial status.
- Customer and group hourly-rate configuration.
- Tenant-level feature activation and optional tenant defaults.
- A tenant-facing **Financeiro** area for pricing, prime-time windows, place overrides, work journeys, capacity, and what-if scenarios.
- Clear inheritance and override behavior.
- A future-safe path to recognized revenue and reporting.

### Not included in the initial module

- Invoices, payment collection, bank reconciliation, taxes, or accounting exports.
- Automatic billing based only on a recurring schedule.
- Retroactively recalculating historical revenue after a rate changes.
- Complex discount, package, commission, or cancellation policies.

## Domain model and inheritance

### Commercial fields

Add nullable commercial fields to customers and groups:

| Entity | Field | Meaning |
|---|---|---|
| Customer | `commercial_status` | Explicit customer override; `null` means inherit |
| Customer | `hourly_rate_cents` | Explicit customer override in BRL cents; `null` means inherit |
| Group | `commercial_status` | Default status for participants in this group |
| Group | `hourly_rate_cents` | Default per-customer hourly rate in BRL cents |

Money must be stored as integer cents, never floating point. `null` means “use the inherited value”; `0` is a valid explicit zero-rate value and must not be treated as missing.

### Resolution order

When a value is needed in the context of a group, resolve it without copying data:

1. use the customer's explicit value when present;
2. otherwise use the group's value;
3. otherwise use the tenant's optional module default;
4. otherwise return the value as unset.

The API should expose both the effective value and its source: `customer`, `group`, `tenant`, or `unset`. The UI can then show labels such as **Próprio**, **Herdado do grupo**, and **Padrão da conta**.

Because a customer may participate in multiple groups, inherited values are contextual. The same customer can therefore have different effective rates in two groups while retaining a single explicit customer override. Outside a group context, resolution skips the group level and uses the customer value followed by the tenant default.

An action named **Usar valor do grupo** should clear the customer's override instead of copying the current group value. This preserves propagation when the group default changes.

### Financeiro pricing tables

The Financeiro area should maintain a sparse, tenant-scoped pricing hierarchy:

| Configuration | Dimensions | Purpose |
|---|---|---|
| Global price table | group size `1–4` | Default per-participant R$/hour |
| Prime-time windows | one or more weekday/time ranges | Classify a scheduled interval as regular or prime |
| Place price table | place, group size `1–4`, regular/prime | Override the global price for a specific place and period |
| Group override | group | Override the calculated price for members of one group |
| Customer override | customer | Highest-priority participant-specific price |

The effective hourly-rate precedence becomes:

1. customer override;
2. group override;
3. place + prime/regular period + actual participant count;
4. global price for the actual participant count;
5. unset.

Status inheritance remains customer → group → tenant default. Price and status resolution should use separate functions because their fallback dimensions differ.

Pricing must use the billable participant count for the occurrence, not only the group's configured capacity. For example, a four-person group with three billable attendees uses the three-person row unless the approved billing policy later specifies otherwise. The calculation response must include the matched rule, rate source, per-participant rate, participant count, duration, and calculated class total.

Place overrides are sparse: an empty cell falls back to the corresponding global size price. Prime and regular prices are independent, so neither should silently copy or overwrite the other.

### Time classification and work journey

Store all tenant pricing windows using local weekday and local wall-clock time, resolved with the tenant's configured timezone. The default prime-time windows are:

- every configured workday from 05:00 to 08:00;
- every configured workday from 18:00 to 21:00.

Users may add, edit, disable, or remove ranges. The API must reject overlapping ranges for the same classification scope. An appointment crossing a regular/prime boundary should be split into priced time segments so that each segment uses the correct rate; it must not classify the entire appointment from its start time alone.

Work-journey settings should support:

- explicit weekday set, initially Monday through Friday;
- explicit weekend-day set, initially Saturday and Sunday;
- one or more working intervals per day category or individual day;
- breaks and unavailable intervals;
- effective-date versioning so a future journey change does not rewrite past capacity reports.

These settings describe potential working capacity. Existing place schedules, blocks, reservations, and appointments remain operational constraints. Effective available capacity is the intersection of the work journey and place availability, minus blocking commitments. Place-reserved background slots remain bookable capacity at that place and therefore must not be subtracted as blockers.

### Financeiro information architecture

When `commercial_financials` is enabled, add a top-level **Financeiro** area with:

1. **Configuração** — global rates for 1–4 participants, currency, and pricing assumptions;
2. **Horários nobres** — editable prime-time ranges with a weekly preview;
3. **Locais** — regular/prime rate matrix per place and group size;
4. **Jornada** — weekday/weekend definitions, working intervals, and breaks;
5. **Capacidade** — available, reserved, occupied, and unused hours and potential revenue;
6. **Cenários** — saved what-if inputs and comparison results;
7. **Receita** — recognized revenue based on explicit confirmation and immutable occurrence snapshots.

Configuration screens should preview both the per-participant rate and total class revenue. Unsaved changes should be locally previewable, while persistence uses optimistic updates with rollback and audit.

## Capacity and scenario definitions

Use stable definitions across dashboards and simulations:

- **Work-journey hours:** total configured working intervals in the selected period.
- **Bookable capacity hours:** work-journey hours intersected with place availability after true blockers.
- **Booked hours:** duration of confirmed individual or group occurrences; do not multiply by participant count.
- **Participant-hours:** sum of each billable participant's booked duration.
- **Occupancy:** booked hours divided by bookable capacity hours.
- **Unused capacity:** bookable capacity hours minus booked hours.
- **Full-capacity revenue potential:** scenario-selected participant mix and prices applied to all bookable hours.
- **Realized revenue:** immutable billable occurrence amounts; never interchangeable with potential revenue.

Each scenario should capture:

- date range and selected places;
- work-journey and prime-time configuration version;
- regular/prime price-table version;
- expected occupancy by period;
- participant-count mix for individual, two-, three-, and four-person classes;
- optional exclusions and operational constraints;
- calculated results and warnings.

Scenario results must be deterministic for the same versioned inputs. They must not mutate schedules, pricing, or recognized revenue. A scenario can later be converted into an optimization request, but only accepted proposals may enter the scheduling flow.

## Optional-module architecture

Introduce a tenant-scoped feature record instead of a build-time flag:

- `TenantFeature`: tenant, feature key, enabled state, who configured it, and timestamps;
- feature key: `commercial_financials`;
- `ProfessionalFinancialSettings`: currency, timezone reference, default commercial status, pricing and scenario assumptions;
- `FinancialRate`: versioned global or place-specific price by participant count and regular/prime classification;
- `PrimeTimeWindow`: versioned weekday and time range;
- `WorkJourneyRule`: versioned workday category, day, working interval, and break configuration;
- `FinancialScenario`: tenant-owned scenario inputs, baseline reference, results, and creator;
- an immutable audit entry for every enable/disable or settings change.

The feature check must be enforced by the backend. Hiding controls in the frontend is not authorization. When disabled:

- scheduling, customers, groups, and memberships continue to work normally;
- commercial fields are omitted from ordinary interfaces;
- financial configuration writes and calculations are rejected consistently;
- existing commercial data remains stored and becomes available again after reactivation.

Only a platform administrator may enable or disable the module for a tenant. Tenant users may configure their module defaults after activation, subject to their role. The admin tenant list should show the current module state and provide an audited switch.

This design can later support other optional modules without adding one boolean column per feature, while keeping the first implementation limited to `commercial_financials`.

## Immediate group-management experience

### Create with one customer

Change group creation to accept one to the existing maximum number of participants. From Clientes, selecting one customer must enable **Criar grupo**. The dialog should allow the user to choose `waiting` immediately, so a future group can be prepared before enrollment is complete.

### Add one customer to an existing group

Add **Adicionar a grupo** to each customer row's actions. The dialog should:

- list only groups from the authenticated tenant;
- show group name, schedule, place, current occupancy, capacity, and commercial status when the module is enabled;
- prevent duplicate membership and selection of a full group;
- warn about a level mismatch without silently changing either level;
- use the existing participant-membership endpoint where possible.

The interface should optimistically update the group membership and roll back with a clear message if the server rejects it. Tenant isolation and capacity rules remain server-side requirements.

## Delivery roadmap

### Phase 1 — Group workflow foundation

**Outcome:** one customer can start a group or join an existing one.

- Lower the group-creation participant minimum to one in UI and API validation.
- Add the per-customer **Adicionar a grupo** action and membership dialog.
- Keep group status user-controlled; do not promote `waiting` automatically.
- Cover tenant isolation, duplicate membership, capacity, and one-participant creation with API and UI tests.

**Release gate:** a single selected customer can create a waiting group, and a customer can be added to an eligible existing group without page refresh.

### Phase 2 — Tenant feature control

**Outcome:** administrators can safely activate the optional module tenant by tenant.

- Add the tenant feature and feature-audit schema.
- Add an admin-only endpoint to read and update `commercial_financials`.
- Surface the switch and current state in tenant administration.
- Add a shared backend feature guard and a frontend capability hook.
- Default existing and new tenants to disabled unless explicitly enabled.

**Release gate:** toggling is authorized and audited; disabling hides the module without deleting data or affecting scheduling.

### Phase 3 — Commercial model and resolver

**Outcome:** status and hourly rate have one consistent source of truth.

- Add nullable customer override fields and group default fields.
- Add optional tenant commercial defaults and the pricing-rule schema.
- Implement a single resolver for effective value and source.
- Validate enum values and non-negative integer cents with a reasonable upper bound.
- Expose effective values in group-participant responses and explicit values in edit responses.
- Test customer, group, tenant, unset, zero-rate, and multi-group resolution cases.

**Release gate:** all clients receive the same deterministic effective value and inheritance source without persisted copies.

### Phase 4 — Customer and group interfaces

**Outcome:** enabled tenants can configure and understand commercial attributes.

- Add commercial fields to customer create/edit and customer detail experiences.
- Add group defaults to create/edit and the Grupos subtab.
- Show inherited-value source and provide **Usar valor do grupo** to clear an override.
- Format values as BRL in the UI while sending integer cents through the API.
- Hide the entire commercial section when the module is disabled.
- Use optimistic updates with rollback for routine edits.

**Release gate:** users can edit, inherit, clear, and distinguish commercial values on customers and groups, while disabled tenants see no new clutter.

### Phase 5 — Financeiro configuration

**Outcome:** tenants can define explainable pricing and working-capacity assumptions.

- Add the Financeiro navigation area and Configuração, Horários nobres, Locais, and Jornada sections.
- Add versioned global price rows for one through four participants.
- Add default and editable prime-time windows.
- Add sparse regular/prime price overrides per place and participant count.
- Add weekday/weekend work journeys, per-day exceptions, intervals, and breaks.
- Build a pricing resolver that returns the applied rule and split segments across price boundaries.
- Audit configuration changes and retain prior effective-dated versions.

**Release gate:** a user can reproduce an appointment's quoted price from the displayed pricing rule, and configuration changes do not alter earlier effective periods.

### Phase 6 — Capacity and what-if scenarios

**Outcome:** users can measure theoretical and usable capacity and safely compare alternatives.

- Calculate work-journey hours, place-available hours, blocking commitments, booked hours, and unused bookable hours.
- Report capacity separately for regular and prime periods, weekdays and weekends, and each place.
- Calculate full-capacity potential using an explicitly selected participant mix rather than assuming every slot has four people.
- Provide a baseline using current configuration and editable scenario assumptions such as participant mix, occupancy, place, work journey, prime windows, and rates.
- Compare baseline and scenario for hours, occupancy, participant-hours, gross revenue potential, and incremental change.
- Save scenarios as immutable input snapshots; recalculation creates a new result version.
- Initial delivery includes basic native charts and rate/mix/occupancy simulation. Scenario-only overrides for work journeys and prime-time windows remain a later Phase 6 refinement if field usage demonstrates a need; users can already change those values in Financeiro configuration.

**Release gate:** every capacity and revenue-potential metric exposes its period, assumptions, numerator, denominator, and excluded constraints.

### Phase 7 — Revenue occurrence foundation

**Outcome:** scheduled expectations can become auditable historical revenue without rewriting the past.

- Materialize schedule occurrences or create an equivalent immutable occurrence record.
- Snapshot each participant's effective hourly rate and inheritance source when the billable occurrence is confirmed.
- Record duration, attendance/billable state, currency, and any manual adjustment separately from the current customer or group defaults.
- Calculate group revenue as the sum of billable participant snapshots multiplied by billable duration.
- Add an initial revenue view by period, customer, group, and place.

Recurring schedules are rules, not proof that revenue occurred. The initial policy requires an explicit attended, no-show, or cancelled outcome and an independent billable decision for every participant. It prices the complete scheduled duration; partial-duration attendance and automated cancellation/no-show billing rules are not inferred and remain a future refinement.

**Release gate:** later edits to customer or group rates do not alter historical occurrence amounts, and every total can be traced to participant-level snapshots.

### Phase 8 — Schedule optimization

**Outcome:** the platform proposes better schedules without modifying the calendar automatically.

- Define an objective selected by the user, initially revenue potential, occupancy, or reduced idle gaps.
- Generate suggestions within work journey, place availability, customer constraints, group capacity, and existing blockers.
- Explain each suggestion with expected benefit, affected appointments, assumptions, and conflicts.
- Let the user preview a proposed schedule and accept changes individually.
- Keep optimization advisory; applying a suggestion uses normal audited scheduling commands and conflict validation.

Avoid presenting a mathematically “optimal” schedule without disclosing the objective and constraints. Customer preferences, travel time, fairness, and operational feasibility must be modeled or shown as limitations.

**Release gate:** suggestions are reproducible, explainable, tenant-scoped, and never change an appointment without explicit confirmation.

### Phase 9 — Controlled rollout and hardening

**Outcome:** the module is operationally safe for progressive adoption.

- Enable the feature for internal/test tenants first.
- Verify audit events, authorization, tenant isolation, and disable/re-enable behavior.
- Monitor validation errors and inheritance-source distribution without logging customer PII or sensitive financial values.
- Publish administrator and tenant-user guidance.
- Expand tenant rollout only after reconciliation of sample reports against expected values.

**Release gate:** a pilot tenant completes configuration, scheduling, occurrence confirmation, and revenue reconciliation with no cross-tenant exposure or historical drift.

## Proposed API changes

Prefer extending existing resources and response conventions:

- group creation: accept a participant list with a minimum of one;
- `POST /api/recurring-slots/{group_id}/participants`: reuse for adding one customer to a group;
- customer update: accept nullable `commercial_status` and `hourly_rate_cents`;
- group update: accept nullable default `commercial_status` and `hourly_rate_cents`;
- group participant reads: include explicit and effective values plus inheritance source;
- tenant financial settings: read/update defaults for the authenticated tenant;
- global rates: list/update the price table for participant counts one through four;
- prime-time windows: list/create/update/delete effective-dated ranges;
- place rates: list/update sparse regular/prime overrides by place and participant count;
- work journey: read/update effective-dated weekday, weekend, interval, and break rules;
- pricing quote: return priced segments, applied rules, rate sources, and totals without creating revenue;
- capacity: return transparent capacity measures for a requested date range and filters;
- scenarios: create/list/compare immutable scenario input and result versions;
- optimization: generate advisory proposals and route accepted proposals through existing scheduling writes;
- admin tenant feature endpoint: read/update `commercial_financials` for a specified tenant.

All tenant-owned queries must derive tenant identity from the authenticated session, never from a request body. Every state-changing endpoint must retain CSRF protection, rate limits where applicable, and an audit trail.

## Security, permissions, and audit

- Platform feature activation requires the platform-admin role.
- Tenant commercial settings require an explicit tenant role check; do not grant access merely because the feature is enabled.
- Customer, group, membership, and revenue queries must always be tenant-scoped.
- Financial writes must record actor, tenant, target, before/after values, timestamp, and request origin metadata appropriate to the existing audit model.
- Client error responses must use the project's standard error-code and error-response helpers without leaking internal details.
- Avoid placing customer names, rates, tokens, or other sensitive values in application logs.
- Treat exports and aggregate reports as separate privileged capabilities when they are introduced.

## Migration and compatibility strategy

- Use additive migrations for nullable commercial columns and the new feature/settings tables.
- Do not backfill customer overrides: `null` intentionally means inheritance.
- Create the feature as disabled for all existing tenants.
- Seed default prime-time windows only when a tenant first enables the module; do not create schedules or prices automatically.
- Version pricing and journey rules by effective period so reports retain their original configuration context.
- Preserve all current group, scheduling, and customer behavior while disabled.
- Deploy and validate migrations locally before any controlled remote synchronization.
- On rollback, disable the feature first; retain schema and data rather than destructively removing financial records.

No production or Azure database mutation is part of this roadmap document.

## Testing strategy

### API and domain tests

- one-participant group creation and explicit waiting status;
- add-to-group success, duplicate, capacity, cross-tenant, and unauthorized cases;
- feature disabled, enabled, disabled again, and re-enabled with data retained;
- admin-only feature mutation and complete audit record;
- inheritance precedence for every source, including explicit zero;
- different effective values for one customer in multiple group contexts;
- validation of status and monetary bounds;
- global and place pricing fallback for participant counts one through four;
- regular/prime boundary splitting, timezone, daylight-saving, overlap, and cross-midnight cases;
- work-journey intersections with place availability and true blockers;
- capacity calculations that do not treat place-reserved background slots as blockers;
- deterministic scenarios using versioned assumptions;
- optimizer constraint enforcement and explicit-confirmation requirement;
- immutable historical rate snapshots.

### Frontend tests

- single selection enables group creation;
- row action opens only eligible groups and updates membership optimistically;
- disabled tenants do not see commercial controls;
- inherited values and their source are understandable;
- Financeiro configuration matrices are keyboard-accessible and display fallbacks clearly;
- capacity and scenario totals disclose assumptions and distinguish potential from realized revenue;
- optimization proposals show benefits and conflicts before any accept action;
- clearing an override immediately reveals the group value;
- optimistic failures restore the prior value and show an actionable error.

### Regression checks

- login, impersonation, tenant navigation, customer pagination, group calendar events, direct bookings, and place schedules continue to work;
- frontend production build succeeds;
- existing backend tests and new migration checks pass in the `agenda` conda environment.

## Product decisions required before financial calculation phases

The group and feature-control phases can proceed with the assumptions above. Pricing, capacity, optimization, and revenue recognition require explicit decisions on:

1. confirmation that size-based rates are per participant rather than total class price;
2. whether pricing uses enrolled, scheduled, present, or billable participant count;
3. whether prime time applies by day category, by selected weekdays, or globally;
4. whether one professional's capacity is the union of available place time rather than the sum of simultaneous availability at multiple places;
5. how travel time between places constrains capacity and optimization;
6. whether `paused` and `waiting` are informational labels or prevent new bookings and billing;
7. whether a no-show is billable, non-billable, or tenant-configurable;
8. how cancellations and partial hours are prorated;
9. when a scheduled occurrence becomes recognized revenue;
10. who may adjust a historical amount and what approval/audit is required.

Recommended starting policy: treat size-based prices as per-participant rates, price realized revenue from billable participants, calculate one professional's multi-place time capacity as a union rather than a sum, keep commercial status informational during configuration, require explicit billable/attendance confirmation for revenue, and never change historical snapshots automatically.

## Success metrics

- A user can start a waiting group with one customer in one flow.
- A user can add a single customer to an existing eligible group from Clientes.
- Existing tenants experience no behavioral change until the module is enabled.
- Users can identify whether every displayed value is explicit or inherited.
- Updating a group default immediately affects customers without overrides.
- Users can configure global rates for one through four participants and sparse regular/prime overrides per place.
- Every quote explains the participant-count, place, time classification, and override rule that produced it.
- Capacity views separate time capacity, participant-hours, potential revenue, and realized revenue.
- What-if results can be reproduced from stored assumptions without changing the live agenda.
- Optimization suggestions never modify the schedule without explicit acceptance.
- Updating current rates never changes previously recognized revenue.
- Every module activation and financial change is attributable to an authorized actor.

## Recommended sequence

Deliver Phases 1–4 as the first commercial configuration release. Deliver Phase 5 as the first Financeiro release after confirming the pricing-unit and participant-count policies. Add capacity and scenarios in Phase 6 only after configuration results are explainable and versioned. Treat realized revenue and schedule optimization as separate milestones: both depend on operational policies and immutable occurrence data, and optimization must remain advisory until its constraints are validated.

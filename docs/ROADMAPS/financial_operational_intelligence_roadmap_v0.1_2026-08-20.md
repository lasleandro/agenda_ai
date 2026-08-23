# Financial Operational Intelligence Roadmap v0.1 — 2026-08-20

**Status: implemented locally on 2026-08-20; pending visual acceptance and a normal-host production build.**

## Implementation record

Implemented locally:

- compact seven-preset period control with progressive custom dates;
- dedicated tenant-scoped `GET /api/financial/operational-analytics` contract;
- overview total/upcoming/executed/cancellation tiles, instructor-event
  indicators, and bounded customer rankings;
- **Realizado** terminology for immutable recognized revenue;
- potential capacity presets moved to Simulador financeiro.

Focused financial and instructor-event tests pass locally (23 tests),
including the new outcome, event, and ranking classification contract.
Frontend type-check and lint pass. The
standard production-build limitation recorded in the preceding financial
experience roadmap remains applicable in this environment.

## 1. Product decisions

This roadmap follows the completed Financeiro visual revamp and records the
next agreed product direction:

1. Move **Potencial** out of the operational Financeiro overview and into the
   **Simulador financeiro**, where its hypothetical full-capacity scenarios
   belong.
2. Replace the tall period card with a compact period bar built around named
   presets; reveal custom date inputs only when the user selects
   **Personalizado**.
3. Add selected-period operational class indicators: scheduled, executed,
   canceled with replacement, and canceled without replacement.
4. Add customer rankings that help instructors identify attendance frequency
   and cancellation patterns.
5. Rename the internal **Receita reconhecida** view to **Realizado** (with
   explanatory copy such as “receita realizada”) so the accounting concept is
   understandable without losing its audit meaning.

The result is a sharper separation of concerns:

- **Financeiro** answers what is scheduled, what happened, and where the
  agenda needs attention.
- **Realizado** answers what revenue was actually earned from confirmed
  occurrences.
- **Simulador financeiro** answers what could happen under alternate
  capacity, mix, and pricing assumptions.

### 1.1 Follow-on operational decisions

The initial implementation clarified an important distinction and adds a
separate event view:

1. **Aulas agendadas** is the total number of class slots originally present
   in the selected period. It is the denominator, not only the future subset.
2. Add **Aulas por acontecer** for active, non-canceled classes on the current
   local date or in the future.
3. Keep **Aulas executadas** for active, non-canceled classes before the
   current local date. Neither class outcome requires revenue confirmation.
4. Add **Eventos no período**, separate from classes, with scheduled,
   completed, canceled, and realized-event-revenue indicators.

Events must never be folded into class counts, class attendance rankings, or
scheduled class revenue. The event revenue value reuses the recognized-event
income already exposed by the Realizado data source; it introduces no new
financial recognition rule.

## 2. Goal and success definition

Make the Financeiro screen useful for daily operational decisions without
turning it into a dense reporting product. A user should be able to choose a
meaningful period in one click, see class outcomes at a glance, identify
customers who attend most or cancel disproportionately, and move to the
simulator only when evaluating a hypothetical opportunity.

The work succeeds when:

- common ranges are selectable without manually typing dates;
- the active range and its inclusive boundaries are unambiguous;
- operational counts refer to the same selected range and never double-count
  a class;
- rankings have clear measures, sensible eligibility rules, and safe empty
  states;
- actual recognized revenue remains immutable and distinguishable from
  scheduled/projection values;
- no pricing, makeup, occurrence, or recognized-revenue business rule changes
  as a side effect of the new presentation.

## 3. Scope boundaries

### In scope

- A compact shared period control on `/financeiro` and
  `/financeiro/simulador`.
- Seven named operational period presets and a custom-date mode.
- Moving the existing capacity-preset presentation from the Financeiro
  overview to the simulator.
- A tenant-scoped, authorized analytics contract for period outcome counts and
  customer rankings.
- Overview tiles and ranking surfaces that consume that contract.
- The **Realizado** label, explanatory copy, and corresponding documentation
  update.
- Focused backend tests for analytics semantics and authorization, plus
  frontend type, lint, and relevant component/API tests already supported by
  the project.

### Explicitly out of scope

- Altering occurrence status transitions, cancellation policies, or the
  creation of makeup credits.
- Altering pricing resolution, recognized-revenue snapshots, or accounting
  calculations.
- Invoices, receivables, payments, exports, customer messaging, or automated
  intervention flows.
- New global customer-score models or a customer profile redesign.
- Comparing arbitrary historical periods, drill-down reports, or ranking
  filters beyond the selected Financeiro period.

The analytics endpoint is a read-only aggregation. It must reuse the existing
occurrence and makeup data model; it must not write, backfill, or infer new
business events.

## 4. Period-control specification

The control is a compact horizontal bar on desktop and a vertically wrapped
group on narrow screens. It replaces the always-expanded bordered card.

```text
Período  [Últimos 30 dias] [Últimos 15 dias] [Próximos 15 dias]
         [Próximos 30 dias] [Último mês fechado] [Este mês]
         [Próximo mês] [Personalizado ▾]          01 ago – 31 ago 2026
```

### 4.1 Preset semantics

All ranges use the tenant/application local calendar day and inclusive date
boundaries. The UI must show the resolved start and end dates after selection.

| UI label | Start | End | Intended use |
|---|---|---|---|
| Últimos 30 dias | today minus 29 calendar days | today | recent results and agenda |
| Últimos 15 dias | today minus 14 calendar days | today | short recent view |
| Próximos 15 dias | today | today plus 14 calendar days | near-term planning |
| Próximos 30 dias | today | today plus 29 calendar days | upcoming workload |
| Último mês fechado | first through last day of previous calendar month | previous month end | finalized monthly review |
| Este mês | first through last day of current calendar month | current month end | current calendar-month view |
| Próximo mês | first through last day of next calendar month | next month end | next calendar-month planning |

“Mês fechado corrente” is intentionally not used: the current calendar month
is not closed until it ends. **Último mês fechado** is the unambiguous label
for the prior, completed month.

### 4.2 Interaction behavior

- Selecting a preset applies it immediately and updates URL/search state where
  the existing page already persists view context.
- **Personalizado** reveals `De`, `Até`, and `Aplicar` inline below the bar;
  those controls are otherwise absent.
- Date validation remains client-side for an inverted range and server-side at
  the analytics boundary; no invalid request is sent.
- Financeiro and the simulator keep independent selections, as they serve
  distinct tasks. Each screen retains its own selected period while navigating
  within that screen.
- On mobile, preset chips wrap in the same priority order and the resolved
  range remains visible without horizontal page scrolling.

## 5. Operational analytics contract

The Financeiro overview needs data that the current financial dashboard does
not expose. Add one read-only, tenant-scoped endpoint under the existing
financial analytics API family, accepting the existing `date_from` and
`date_to` ISO-date parameters. It returns only selected-period aggregates and
bounded ranking lists; it does not return an unbounded occurrence list.

The final route and response envelope must follow the project’s established
financial router conventions. The response should contain:

```text
period: { date_from, date_to }
class_outcomes: {
  total_scheduled_count,
  upcoming_count,
  executed_count,
  canceled_with_makeup_count,
  canceled_without_makeup_count
}
instructor_event_outcomes: {
  scheduled_count,
  completed_count,
  canceled_count,
  confirmed_income_cents
}
rankings: {
  most_frequent_customers: [bounded customer rows],
  highest_cancellation_rate_customers: [bounded customer rows]
}
```

### 5.1 Class-outcome definitions

The backend implementation must map these definitions to the project’s actual
occurrence statuses and makeup relationships, documenting that mapping in code
and tests before the UI consumes it.

| Tile | Definition | Notes |
|---|---|---|
| Aulas agendadas | All original class slots in the period | This is the total denominator: active past/future slots plus registered cancellations. |
| Aulas por acontecer | Active occurrences on the current local date or in the future | It excludes canceled occurrences and past active occurrences. |
| Aulas executadas | Active, non-canceled occurrences before the current local date | This is an operational schedule count; it does not require revenue confirmation. |
| Canceladas com reposição | Canceled occurrences in the selected period that are linked to a makeup credit/replacement according to the existing domain model | Count the canceled source occurrence once, even if it leads to multiple downstream records. |
| Canceladas sem reposição | Canceled occurrences in the selected period with no such makeup link | Count the canceled source occurrence once. |

The four categories must be mutually exclusive. If an occurrence state cannot
be classified safely, it must be excluded from these four counts and surfaced
in internal diagnostic/logging only; the implementation must not silently
relabel it. A targeted test must demonstrate the classification for every
currently valid outcome status.

The UI includes short help text: “Contagens de aulas no período selecionado;
reposições classificadas pela relação já registrada na agenda.” This avoids
presenting these operational counts as financial totals.

### 5.2 Ranking definitions and privacy

Each row has a display-safe customer name, attended/executed count, scheduled
count, cancellation count, and cancellation rate as applicable. The frontend
receives only fields needed to render the ranking; no email, phone, notes, or
other customer PII is included.

| Ranking | Primary ordering | Eligibility | Secondary context |
|---|---|---|---|
| Clientes mais frequentes | highest executed count | at least one selected-period occurrence | scheduled and canceled counts |
| Clientes com maior taxa de cancelamento | highest cancellation rate | at least 3 selected-period scheduled/canceled/executed occurrences | cancellation count and denominator |

The cancellation-rate denominator is all class outcomes attributable to the
customer in the selected period that participate in the above classification.
The exact participant/booking relation must be verified against the existing
schema: group occurrences should credit each enrolled customer once rather
than multiplying the class outcome arbitrarily. Ties use higher cancellation
count, then display name in deterministic locale-aware order.

Return at most five rows per ranking in the initial UI. Empty rankings show a
plain explanation rather than an empty card. The endpoint must apply the same
authentication, role checks, tenant isolation, and date validation as other
financial reads.

## 6. Target information architecture

### 6.1 Financeiro → Visão geral

```text
Financeiro                                         Abrir simulador →
Período [chips…] [Personalizado]                    01 ago – 31 ago 2026
[ Visão geral ] [ Realizado ]

Resumo do período
receita agendada · ocupação · pendências de preço

Agenda no período
[ Agendadas ] [ Executadas ] [ Canceladas c/ reposição ] [ Canceladas s/ reposição ]

Desempenho e distribuição da agenda
Clientes em destaque
  Mais frequentes                         Maiores cancelamentos
```

The outcome tiles are a compact, equal-height row beneath the existing
financial summary—not a second hero. Each tile has an outcome-specific icon,
count, label, and one concise explanatory tooltip or helper. Semantic color is
supporting only: neutral/indigo for scheduled, positive for executed, amber
for canceled with replacement, and destructive/red for canceled without
replacement. Color is never the sole state indicator.

Rankings appear after performance/distribution so they remain decision support
rather than the page’s headline. On wide screens, render the two lists side by
side; on narrow screens, stack them. Each list shows five concise rows with
rank, customer name, main metric, and secondary context. There is no drilldown
in this phase.

The previous **Potencial** surface is removed from this view. The long-term
trend and existing collapsed assumptions remain unless an implementation
inspection shows they are dependent on the moved potential presentation.

### 6.2 Financeiro → Realizado

Rename the current tab and view heading from **Receita reconhecida** to
**Realizado**, with copy such as “Receita realizada em aulas confirmadas no
período.” The underlying recognized-revenue endpoint, immutable occurrence
snapshots, component data fields, and accounting semantics remain unchanged.

The purpose of this view is to distinguish realized income from scheduled
revenue: a lesson may be on the agenda but it is only recognized when its
confirmed occurrence produces the existing immutable revenue record. The tab
is therefore retained, but its language becomes operationally intelligible.

### 6.3 Simulador financeiro

Add **Potencial** after the scenario results as a contextual comparison of the
existing capacity presets. Its title and helper copy must make clear that it
is a planning reference, not a forecast or commitment. It uses the simulator’s
selected period and place context. No new potential calculation is introduced.

## 7. Implementation phases

### Phase 0 — Reconnaissance and contract decision

1. Trace the occurrence status enum/state machine, cancellation records,
   participant/booking relation, and existing makeup-credit linkage.
2. Identify the established financial-router response envelope, authorization
   dependency, and date-range validation pattern.
3. Record the exact status-to-outcome mapping in the implementation notes and
   tests. Stop and surface a decision if the present model cannot reliably
   distinguish “with” from “without” replacement.

**Verification:** schema/service inspection is documented in the implementation
PR; no database write or migration is introduced merely for analytics.

### Phase 1 — Period-control UX

1. Simplify `FinancialPeriodControls` to the specified compact preset bar.
2. Implement the seven preset range resolvers using a shared, tested calendar
   helper within the frontend financial feature.
3. Keep custom dates hidden until selected; preserve invalid-range feedback.
4. Reuse the control in Financeiro and simulator without coupling their state.

**Verification:** type-check, lint, and manual desktop/mobile checks for every
preset, month boundary, leap-year boundary, and custom-range validation.

### Phase 2 — Read-only operational analytics

1. Implement the authorized, tenant-scoped aggregate service and endpoint.
2. Classify outcomes from the existing data model and produce bounded rankings.
3. Add request/response schemas and no-PII response shaping.
4. Add API/service tests for tenant isolation, role rejection, date bounds,
   outcome exclusivity, makeup classification, deterministic ties, ranking
   eligibility, and empty results.

**Verification:** focused backend suite passes against the local `agenda_db`;
queries are reviewed for tenant predicates and bounded result size.

### Phase 3 — Financeiro operational view

1. Fetch the new analytics data only in the overview scope and align it to the
   active period/error/loading treatment.
2. Render outcome tiles below the financial summary with accessible labels and
   clear zero/empty states.
3. Render both rankings with mobile stacking and no customer data beyond the
   approved response contract.
4. Rename the navigation/view copy to **Realizado** while retaining URLs and
   recognized-revenue data behavior.
5. Remove **Potencial** from the overview.

**Verification:** type-check, lint, responsive manual review, keyboard focus,
screen-reader labels, and no regression in existing Financeiro filters/views.

### Phase 4 — Simulator and documentation

1. Place the existing potential presets in the simulator after results.
2. Update `/financeiro`, simulator, and README documentation with preset
   semantics, operational-count definitions, ranking eligibility, and the
   `Realizado` terminology.
3. Update the earlier visual-revamp roadmap implementation record to reference
   this follow-on roadmap rather than leaving its “Potencial” placement as the
   latest intended architecture.

**Verification:** links resolve, documents match the UI and API behavior, and
all focused frontend/backend checks pass.

## 8. Risks and guardrails

| Risk | Guardrail |
|---|---|
| A canceled lesson has an ambiguous relationship to a makeup | Do not ship a guessed count; establish the exact persisted relation in Phase 0 and test it. |
| Group lessons distort customer rankings | Define customer attribution from the existing participant/booking model and test group cases explicitly. |
| A user mistakes operational counts for financial recognition | Keep the tiles separate from the revenue hero and add concise explanatory labels. |
| A future period shows no realized revenue | Keep the Realizado view valid with a clear empty state; do not fabricate expected revenue there. |
| Cancellation rankings shame customers based on tiny samples | Require the three-outcome eligibility minimum and show both count and rate. |
| Analytics queries grow with tenant history | Aggregate in the database, constrain by tenant and selected dates, bound rankings to five, and avoid loading occurrence history in application memory. |
| UI work changes existing calculations | Consume existing financial dashboard/revenue data unchanged; the new endpoint is operational read-only. |

## 9. Acceptance checklist

- [ ] All seven named period options resolve to the documented inclusive dates.
- [ ] Custom date inputs appear only in Personalizado mode and reject invalid
      ranges.
- [ ] Financeiro and simulator preserve independent period context.
- [ ] Potential appears only in the simulator and is explicitly hypothetical.
- [ ] Every included occurrence belongs to exactly one operational outcome
      category; ambiguous states are not misrepresented.
- [ ] Counts and rankings are tenant-scoped, authorized, date-bounded, and
      return no unnecessary customer PII.
- [ ] Ranking lists are capped at five and show both a meaningful primary
      metric and supporting context.
- [ ] The `Realizado` view still renders the current immutable
      recognized-revenue history correctly.
- [ ] Existing financial, revenue, pricing, and makeup regression suites pass.
- [ ] Frontend type-check, lint, production build in a normal/CI environment,
      and manual responsive/accessibility review pass.

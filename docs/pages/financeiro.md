# Page: Financeiro (Financial)

**Route:** `/financeiro`
**File:** `frontend/src/app/(protected)/financeiro/page.tsx`
**Feature-gated:** Requires the `commercial_financials` tenant feature flag

---

## Overview

Financeiro is the instructor's operational financial workspace. It presents
scheduled revenue, capacity, occupancy, long-term projection trends, and
recognized-revenue history. It does not contain hypothetical scenario
planning; that lives in [Simulador financeiro](simulador_financeiro.md).

The page uses the existing authenticated tenant scope. A tenant without
`commercial_financials` is redirected to the home page.

## Page structure

1. Header with a link to **Abrir simulador**.
2. Compact page-level period control with seven named ranges and an optional
   custom-date mode.
3. Internal navigation between **Visão geral** and **Realizado**.
4. The selected view's data and contextual errors.

The selected view is URL-backed: `/financeiro?view=receita` opens Realizado
directly. The default route opens Visão geral.

---

## Visão geral

Visão geral answers “How is the business performing in this period?” It shows
the following sections in order:

1. **Resumo do período** — scheduled class revenue is the headline; occupancy,
   free hours, participant-hours, and an unpriced-booking warning are supporting
   facts.
2. **Desempenho** — scheduled revenue over time and capacity by location.
3. **Distribuição da agenda** — a local selector switches among location,
   part-of-day, weekday, and regular-versus-prime capacity breakdowns without
   making another request.
4. **Agenda no período** — total class slots, classes still to happen,
   executed classes, and canceled-with/without-makeup counts.
5. **Eventos no período** — confirmed, completed, canceled, and confirmed-income
   indicators kept separate from classes.
6. **Reposições** — redeemed makeup count, occupied time, and current-price
   opportunity-cost reference; makeup capacity does not add new class revenue.
7. **Clientes em destaque** — bounded attendance-frequency and cancellation-rate
   rankings.
8. **Tendência de longo prazo** — six-month scheduled-revenue trend; this is
   deliberately independent of the selected period.
9. **Premissas e limitações** — collapsed calculation context.

The place selector is intentionally contained within this view. It filters the
dashboard endpoint only; recognized revenue is not presented as place-filtered
because its existing summary endpoint accepts dates but no place ID.

## Realizado

Realizado answers “What was actually earned?” The headline amount is the
immutable recognized total returned by the revenue summary endpoint.

- Supporting composition values show billable subtotal, adjustments, confirmed
  event income, occurrence count, and attendance count.
- The time series contains confirmed values, not scheduled projections.
- One selectable breakdown surface provides results by location, customer, or
  group.
- The history contains immutable occurrence snapshots. Expanding an occurrence
  reveals participants, attendance, billed amount, pricing lines, and the
  historical rate source without recalculating current pricing.

Event income remains visible but separate from participant-priced class
revenue, matching the existing business rule.

---

## Data sources and behavior

| Data | Existing endpoint | Used by |
|---|---|---|
| Financial configuration and locations | `GET /api/financial/configuration` | Visão geral location selector |
| Scheduled revenue and capacity | `GET /api/financial/dashboard?date_from=&date_to=&place_id=` | Visão geral |
| Operational outcomes and customer rankings | `GET /api/financial/operational-analytics?date_from=&date_to=` | Visão geral |
| Realized revenue and history | `GET /api/financial/revenue/summary?date_from=&date_to=` | Realizado |

The period shortcuts are **Últimos 30 dias**, **Últimos 15 dias**,
**Próximos 15 dias**, **Próximos 30 dias**, **Último mês fechado**,
**Este mês**, and **Próximo mês**. All ranges are inclusive local calendar
dates; Personalizado reveals date fields only when selected.

Operational outcomes count only class-level schedule cancellations. “Aulas
agendadas” is the total class-slot denominator for the period, while “Aulas
por acontecer” is its active current/future subset. A canceled
class is “com reposição” when at least one existing makeup credit originated
from its cancellation event; individual absence records do not cancel a class.
Executed classes are active, non-canceled schedule occurrences before the
current local date; no revenue confirmation is required. Occurrences today or
in the future remain scheduled. Rankings return at most five customer names
and counts; the cancellation-rate ranking requires at least three classified
class outcomes.

Changing the period preserves the currently visible dashboard while the new
dashboard request resolves. The recognized-revenue view then requests the same
selected dates independently. A failed refresh is shown as a scoped error;
previous usable content remains visible where available.

Initial loading uses a structural skeleton rather than a blank page. Empty
capacity, missing-price, and absent recognized-revenue states remain explicit
and do not create financial data.

## Related destinations

- [Simulador financeiro](simulador_financeiro.md) — dedicated scenario planning
  workspace at `/financeiro/simulador`.
- [Configurações](minhas_regras.md) — financial definitions, including default
  and per-location rate matrices and premium-time windows.

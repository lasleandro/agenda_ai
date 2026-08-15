# Page: Financeiro (Financial)

**Route:** `/financeiro`
**File:** `frontend/src/app/(protected)/financeiro/page.tsx`
**Feature-gated:** Requires `commercial_financials` tenant feature flag

---

## Overview

The Financeiro module is a comprehensive financial management dashboard
for the instructor. It covers revenue projections, rate configuration,
what-if scenario modeling, and revenue occurrence confirmation.

If the tenant does not have the `commercial_financials` feature enabled,
this route redirects to the home page.

---

## Key Components

| Component | File | Purpose |
|---|---|---|
| `FinancialDashboardSection` | `components/financial/financial-dashboard-section.tsx` | Date-filtered overview with key metrics |
| `RevenueSection` | `components/financial/revenue-section.tsx` | Revenue occurrence candidates list with confirm/deny |
| `FinancialSimulator` | `components/financial/financial-simulator.tsx` | What-if scenario modeling |
| `SimulatedAgenda` | `components/financial/simulated-agenda.tsx` | Read-only monthly allocation for an evaluated scenario |
| `GlobalRatesSection` | `components/financial/global-rates-section.tsx` | Edit per-participant-count hourly rates |
| `PrimeTimeSection` | `components/financial/prime-time-section.tsx` | Configure prime-time windows |
| `PlaceRatesSection` | `components/financial/place-rates-section.tsx` | Place-specific rate matrices |

---

## Four Tabs

### Visao Geral (Dashboard)

- Date range filter + place filter
- Key metrics: current revenue, projected revenue, capacity utilization
  (`occupancy_pct`), average rates — see
  `docs/capacity_and_recommendations.md` for exactly how occupancy,
  breakdowns, and the what-if scenarios/tradeoffs are computed
- Refetches dashboard on filter apply
- Optimistic: keeps previous data visible while new data loads

### Receita (Revenue)

- Lists revenue occurrence candidates for a date range
- Each occurrence shows: date, label, participants, billable count,
  estimated total
- **Confirm** button: freezes occurrence → `POST /api/financial/revenue/occurrences`
- **Deny** button: dismisses candidate (soft delete or status change)
- Paginated, infinite scroll or load-more
- **"Renda de eventos" stat tile**: sum of confirmed `InstructorEvent.income_cents`
  in the period (instructor events roadmap v0.1) — refereeing, workshops,
  clinics. Surfaced alongside, not merged into, the participant-priced
  revenue total; source data comes from `RevenueSummaryDetail.event_income_cents`
  on the same `GET /api/financial/revenue/summary` call, not a separate fetch.

### Simulador (Simulator)

- Select: date(s), place, participant count, time window
- Evaluate: sends configuration to `POST /api/financial/scenarios/evaluate`
- Shows projected revenue with breakdown by rate source
- Groups the price test under **Premissas**. It first displays the effective
  configured rates and exposes editable fields only after **Editar preços**.
- Shows a read-only **Agenda simulada** in month view after evaluation. Its
  blocks are deterministic, complete one-hour allocations of the selected
  occupancy and mix over configured capacity; they never create or modify real
  appointments. Scenario revenue and participant-hours use the same hourly
  blocks. Work-journey hours not assigned to a named location are also shown as
  **Sem local definido** and use the generic-location rate, so the simulator
  shares the dashboard's capacity basis. Clicking a block opens its projected date, time, duration, place,
  format, category, rate per person/hour, and total revenue.
- The agenda card has a **Simulada / Real** toggle. The real view shows the
  current appointments, recurring classes, and confirmed instructor events for
  the selected period in read-only form.
- The comparison baseline is **Aulas agendadas atuais**. Instructor events
  (workshops, clinics, and refereeing) remain separate revenue and do not alter
  simulated class capacity.
- The scenario result estimates the active customer base needed, assuming each
  customer attends between one and three hours per calendar week.
- Distribution also includes the inverse time-category strategies: individuals
  in regular slots with groups in prime time, or groups in regular slots with
  individuals in prime time.
- **Valores por local** starts with **Padrão — sem local definido**, a separate
  regular/prime matrix used for agenda commitments with no place. Named places
  still use their own matrix, then fall back to the global table.
- **Save scenario** → `POST /api/financial/scenarios` for later comparison
- **Load scenario** → `GET /api/financial/scenarios` to view saved scenarios

### Configuracao (Configuration)

Four sub-sections stacked vertically:

**1. Global Rates**
- Per-participant-count (1, 2, 3, 4 students) hourly rates in cents
- Simple input grid with save button
- Endpoint: included in `PUT /api/financial/settings`

**2. Prime-Time Windows**
- Define which days/times are "prime" (priced higher)
- Multi-select days of week + time range pairs
- Endpoint: `PUT /api/financial/prime-time-windows`

**3. Place Rates**
- For each place, define regular and prime rates per participant count
- Matrix input: rows = participant counts, columns = time categories
- Endpoint: `PUT /api/financial/places/{id}/rates`

Work journey (daily schedule) and the make-up cancellation notice window
moved to `docs/pages/minhas_regras.md` — they aren't feature-gated, since
scheduling and make-up credit eligibility enforce them for every tenant
regardless of `commercial_financials`.

---

## Data Sources

| Data | Endpoint |
|---|---|
| Financial settings | `GET /api/financial/settings` |
| Full configuration | `GET /api/financial/configuration` |
| Generic-place rates | `PUT /api/financial/generic-place/rates` |
| Dashboard metrics | `GET /api/financial/dashboard?date_from=&date_to=&place_id=` |
| Revenue candidates | `GET /api/financial/revenue/candidates?date_from=&date_to=` |
| Scenarios | `GET /api/financial/scenarios` |

---

## Visual Design

- Tab bar at top for switching between sections
- Dashboard: card-based metrics with large numbers and sparkline trends
- Revenue: table-like list with status badges and action buttons
- Simulator: form on left, results on right
- Configuration: grouped form sections with inline save buttons
- All amounts displayed in the instructor's configured currency

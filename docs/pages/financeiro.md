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

### Simulador (Simulator)

- Select: date(s), place, participant count, time window
- Evaluate: sends configuration to `POST /api/financial/scenarios/evaluate`
- Shows projected revenue with breakdown by rate source
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

# Page: Simulador financeiro (Financial Simulator)

**Route:** `/financeiro/simulador`
**File:** `frontend/src/app/(protected)/financeiro/simulador/page.tsx`
**Feature-gated:** Requires the `commercial_financials` tenant feature flag

---

## Overview

Simulador financeiro is the platform's dedicated what-if workspace. It lets an
instructor evaluate capacity scenarios for the current month and a chosen
location while keeping the real agenda and configured prices unchanged.

The page is separate from Financeiro so hypothetical values do not compete
with operational projections or recognized-revenue history. A tenant without
the financial feature is redirected to the home page.

## Workspace structure

1. Header and **Voltar ao financeiro** navigation.
2. **Premissas da simulação** — a single block, first after any warning
   banner: the stated period (current month, read-only), the scenario-local
   location selector, the scenario name, the distribution mode (and custom mix
   when chosen), the occupancy target, and — only when a specific location is
   selected — a read-only configured-price matrix.
3. Evaluate and save actions, plus a **Cenários salvos** menu that restores a
   saved scenario's premises and result.
4. Current-versus-simulated result and read-only simulated/real agenda.
5. **Potencial** — full-capacity references, explicitly presented as
   hypothetical planning comparisons. Each tile shows projected revenue,
   participant-hours, and an active-customer range (`minimum–maximum
   clientes`) from the same `estimate_customer_range` model used by the
   scenario result: each customer is assumed to occupy 1–3 participant-hours
   per calendar week.

---

## Behavior and safeguards

- The projection window is fixed to the current calendar month. There is no
  period control: every scenario spans one month so saved scenarios stay
  comparable. The month is computed once per page load and shown as read-only
  context in the premises block.
- The default location is all locations; the instructor may change it before
  evaluating a scenario. Changing it re-fetches the capacity baseline and
  resets the in-block premises.
- The price matrix is read-only and only appears when a single location is
  selected, where each cell is that location's own configured rate. For
  **Todos os locais** it is replaced by a note ("Usando os preços configurados
  de cada local."), because each place is priced by its own rate on the
  server. The simulator never overrides prices; `rate_overrides` is always
  empty in the evaluate/save input. Price changes are made in Minhas Regras.
- Saved scenarios created before this change may carry historical
  `rate_overrides`; they still load (premises and stored result) and render
  from their immutable snapshot.
- **Simular** calls `POST /api/financial/scenarios/evaluate`.
- **Salvar cenário** calls `POST /api/financial/scenarios` and preserves the
  existing immutable input/result snapshot behavior.
- The simulated and real calendar views are read-only. They never create,
  alter, or cancel appointments.
- When no journey is configured, the simulator uses an explicitly labeled
  estimate: 8 hours per day from Monday through Saturday (48 hours per full
  week), valued at the regular generic rate. The banner directs the instructor
  to **Configurações → Jornada de trabalho**.
- Estimated capacity has no inferred place or clock time. It is not applied to
  a selected location, and the simulated-agenda tab explains that configuring
  the journey is required before it can render appointment-like blocks.
- The standard Financeiro dashboard remains configured-only; this fallback is
  requested only by the simulator.

## Data sources

| Data | Endpoint |
|---|---|
| Financial configuration and locations | `GET /api/financial/configuration` |
| Capacity baseline | `GET /api/financial/dashboard?date_from=&date_to=&place_id=&capacity_mode=estimated_when_unconfigured` |
| Saved scenarios | `GET /api/financial/scenarios` |
| Evaluate scenario | `POST /api/financial/scenarios/evaluate` |
| Save scenario | `POST /api/financial/scenarios` |

The scenario route is intentionally client-composed. It preserves tenant scope
and the existing `commercial_financials` feature boundary on every request.
`FinancialScenarioInput.capacity_mode` is persisted in the immutable snapshot,
alongside response metadata identifying configured versus estimated capacity.

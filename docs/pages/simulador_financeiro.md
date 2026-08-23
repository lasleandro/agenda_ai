# Page: Simulador financeiro (Financial Simulator)

**Route:** `/financeiro/simulador`
**File:** `frontend/src/app/(protected)/financeiro/simulador/page.tsx`
**Feature-gated:** Requires the `commercial_financials` tenant feature flag

---

## Overview

Simulador financeiro is the platform's dedicated what-if workspace. It lets an
instructor evaluate capacity scenarios with an independent period and location
context while keeping the real agenda and configured prices unchanged.

The page is separate from Financeiro so hypothetical values do not compete
with operational projections or recognized-revenue history. A tenant without
the financial feature is redirected to the home page.

## Workspace structure

1. Header and **Voltar ao financeiro** navigation.
2. Period control and scenario-local location selector.
3. Scenario assumptions and configured/test price matrix.
4. Evaluate and save actions.
5. Current-versus-simulated result and read-only simulated/real agenda.
6. **Potencial** — existing full-capacity references, explicitly presented as
   hypothetical planning comparisons.
7. Saved immutable scenario snapshots.

---

## Behavior and safeguards

- The default context is the current month and all locations; the instructor
  may change either before evaluating a scenario.
- Its compact period control provides the same named inclusive-date presets as
  Financeiro, while retaining independent simulator context. Custom dates are
  only shown after selecting **Personalizado**.
- Configured prices are displayed first. **Editar preços** exposes temporary
  overrides used only by the evaluation/save input; it never writes rate
  configuration.
- **Simular** calls `POST /api/financial/scenarios/evaluate`.
- **Salvar cenário** calls `POST /api/financial/scenarios` and preserves the
  existing immutable input/result snapshot behavior.
- The simulated and real calendar views are read-only. They never create,
  alter, or cancel appointments.
- The page reuses the existing dashboard baseline, financial configuration,
  and saved-scenario endpoints. It adds no financial API or calculation;
  Potential uses the already-returned capacity presets.

## Data sources

| Data | Endpoint |
|---|---|
| Financial configuration and locations | `GET /api/financial/configuration` |
| Capacity baseline | `GET /api/financial/dashboard?date_from=&date_to=&place_id=` |
| Saved scenarios | `GET /api/financial/scenarios` |
| Evaluate scenario | `POST /api/financial/scenarios/evaluate` |
| Save scenario | `POST /api/financial/scenarios` |

The scenario route is intentionally client-composed. It preserves tenant scope
and the existing `commercial_financials` feature boundary on every request.

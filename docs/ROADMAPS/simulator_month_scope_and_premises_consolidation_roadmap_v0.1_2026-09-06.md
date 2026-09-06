# Simulator Month Scope and Premises Consolidation Roadmap v0.1 — 2026-09-06

**Status: implemented locally on 2026-09-06.** All of Phases A–D landed in one
pass: the period control is gone and the window is the current month; period +
location render at the top of a single "Premissas da simulação" block (location
lifted into `FinancialSimulator` via `onLocationChange` / `locationBusy`); the
price matrix is read-only and single-location only, with `rate_overrides` always
`[]`; `loadScenario()` no longer restores overrides; the price-matrix `<details>`
collapse wrapper was removed with the edit affordance. Coverage:
[simulador-financeiro.spec.ts](../../frontend/e2e/simulador-financeiro.spec.ts).
Docs updated: [simulador_financeiro.md](../pages/simulador_financeiro.md) and the
root README line. No backend change.

**Follow-up 2026-09-06:** the **Potencial** tiles now also show an
active-customer range (`minimum–maximum clientes`). `CapacityPresetDetail`
gained a `customer_estimate` built with the existing
`estimate_customer_range()` (1–3 participant-hours per customer per calendar
week), the same model behind the scenario result's "Base de clientes
estimada"; the tile renders it as a muted line with an info tooltip, and `—`
when capacity is unconfigured. This was scoped out of the original plan
("Potencial stays separate") but is a one-function reuse with no new model.

This roadmap simplifies `/financeiro/simulador` around three decisions taken in
discussion on 2026-09-06:

1. **Fix the projection window to the current calendar month.** Remove the
   seven-preset period control that was inherited from Financeiro. A simulator
   answers a per-month "what if" question; a variable window length makes saved
   scenarios non-comparable (a 15-day scenario shows ~half the revenue of a
   month scenario for identical premises).
2. **Consolidate all assumptions into one "Premissas da simulação" block at the
   top of the page**, directly below any warnings. Location moves in as the
   first row. Period is no longer a control — it is stated, not chosen.
3. **Drop the price-override lever.** Keep the price matrix read-only as "the
   prices this projection assumes," shown only when a single location is
   selected (where the numbers are exact). Pricing changes belong in the
   pricing configuration screen, and a linear price lever with no demand
   response produces a revenue number nobody trusts.

**Already landed in this session (context for the reader).** Two unrelated
simulator tweaks are already in the working tree and are *not* reverted by this
roadmap: the saved-scenarios list became a `Cenários salvos` dropdown next to
`Simular` / `Salvar cenário` that restores a scenario's premises and result on
selection; and "Agenda simulada" plus the price matrix became collapsible on
mobile via `useIsMobile()`. Phase C below removes the price matrix's *edit*
affordance; its collapsible wrapper is revisited there.

## 1. Goal and product outcome

Make the simulator read as a single, honest set of assumptions with one
comparable output unit (a month), and stop presenting controls that either
belong to another screen (arbitrary date ranges) or give misleading answers
(flat price overrides).

After implementation:

- The page opens on the **current calendar month**, all locations, with no
  period picker. The month is shown as static context inside the premises
  block.
- **"Premissas da simulação"** is the first content block after any warning
  banner. It contains, in order: the stated period, the location selector, the
  scenario name, the distribution mode (and custom mix when chosen), the
  occupancy target, and — only for a single selected location — a read-only
  price matrix.
- There is **no "Editar preços"** button, no rate-override state, and no
  `rate_overrides` in the evaluate/save payload.
- Saved scenarios are all one month long and therefore directly comparable in
  the `Cenários salvos` dropdown.
- `/financeiro` (the dashboard) is untouched: it keeps its own shared
  `FinancialPeriodControls`.

## 2. Scope and non-goals

### In scope

- Removing `FinancialPeriodControls` from the simulator page only, and reducing
  the page's `filters` state to a location plus a derived current-month range.
- Restructuring the simulator so period + location render inside the
  "Premissas da simulação" container, and that container sits at the top.
- Removing `editingRates`, `rateInputs`, `enableRateEditing`,
  `resetRateEditing`, the `rate_overrides` field in `buildInput()`, and the
  matrix's edit UI. Keeping a read-only matrix gated to a single location.
- Updating `loadScenario()` so it no longer restores rate-override state.
- Documentation and regression-test updates.

### Out of scope

- Any backend change. `POST /api/financial/scenarios/evaluate` and
  `POST /api/financial/scenarios` still accept `date_from` / `date_to` and an
  optional `rate_overrides`; the simulator simply stops sending overrides and
  always sends a whole-month range. Persisted historical snapshots that contain
  `rate_overrides` remain valid and render as before.
- Changing `FinancialPeriodControls` or the `/financeiro` dashboard.
- The mobile period-overflow ("Mais opções" menu) idea discussed earlier — it
  is dropped, because there is no longer a period control to overflow.
- A percentage-based price-adjustment lever with backend support. If price
  testing returns later, it is its own roadmap.
- Changing the "Jornada estimada" fallback, the simulated/real agenda, the
  `Cenários salvos` dropdown, or the collapsible behaviour introduced this
  session (except the price-matrix edit affordance).
- Changing how the observed participant mix is derived on the backend (see the
  known limitation in section 8).

## 3. Current state and reusable assets

- **Page shell:**
  [simulador/page.tsx](../../frontend/src/app/(protected)/financeiro/simulador/page.tsx)
  holds `filters` (`dateFrom`, `dateTo`, `placeId`), fetches configuration +
  dashboard + scenarios on mount, and re-fetches the dashboard in
  `applyFilters()` on any period or location change. It renders, in order:
  header, error banner, `<FinancialPeriodControls>`, a bordered "Local do
  cenário" box with a `<select>`, `<FinancialSimulator>` (keyed on
  `${dateFrom}-${dateTo}-${placeId}`), and a "Potencial" section built from
  `dashboard.capacity_presets`.
- **`initialFilters()`** already computes exactly the current-month range
  (`new Date(y, m, 1)` … `new Date(y, m + 1, 0)`). The month-scope change
  reuses this; it does not introduce new date math.
- **Period control:**
  [financial-period-controls.tsx](../../frontend/src/components/financial/financial-period-controls.tsx)
  is shared with [financeiro/page.tsx](../../frontend/src/app/(protected)/financeiro/page.tsx).
  It is only *removed from the simulator import graph*; the file stays.
- **Simulator component:**
  [financial-simulator.tsx](../../frontend/src/components/financial/financial-simulator.tsx)
  owns the premises form. Relevant to this roadmap:
  - Its first `<Card>` has `CardHeader` = "Premissas da simulação" and a
    `CardContent` with a two-column grid: left column (name, distribution,
    custom mix, occupancy slider, a `bg-muted/50` period/location summary box)
    and right column, now a `<details>` titled "Preços usados na simulação".
  - `configuredRate(category, participantCount)` resolves a display rate:
    selected place's own rate if present, else `configuration.default_rates`.
    For "all locations" it can only ever show the tenant default, while the
    **backend** prices each slot by its own `segment.place_id`
    (`_resolve_rate` → `pricing.resolve(segment.place_id, …)` in
    [financial_analytics.py](../../backend/app/services/financial_analytics.py)).
    So today's matrix is already an approximation in the all-locations case.
  - `editingRates` / `rateInputs` / `enableRateEditing()` /
    `resetRateEditing()` drive the "Editar preços" toggle. `buildInput()`
    turns `rateInputs` into `rate_overrides`, keyed by
    `(time_category, participant_count)` only — no place dimension, so an
    override flattens every location to one number for the run.
  - `loadScenario()` (added this session) restores `rate_overrides` from a
    saved snapshot into `rateInputs` + `editingRates`.
  - `useIsMobile()` from [use-is-mobile.ts](../../frontend/src/lib/use-is-mobile.ts)
    and the `<details>` + rotating `ChevronDown` idiom are already in the file.
- **Warning banner:** the amber "Jornada estimada" `<Card>` is already the
  first child of the component's root `<div className="space-y-5">`, rendered
  when `dashboard.capacity_source.mode === "estimated_default"`. The premises
  card is its next sibling. "Top, below warnings" is therefore mostly a
  page-level move of period + location *into* the component, not a reordering
  inside it.
- **Types:** `FinancialScenarioInput.rate_overrides` is a required array in
  [types.ts](../../frontend/src/lib/types.ts); sending `[]` is already valid
  and is what saved scenarios without overrides carry.
- **Page doc:** [simulador_financeiro.md](../pages/simulador_financeiro.md)
  currently documents the compact period presets and the "Editar preços"
  overrides; both descriptions change here.

## 4. Product decisions

1. **The window is the current calendar month, always.** It is computed once
   from `initialFilters()` and never changes for the life of the page. It is
   presented as read-only context ("Período: 01/09/2026 – 30/09/2026"), not a
   control. Rationale: one comparable output unit across every saved scenario,
   and a month is how instructors budget.
2. **No "typical month" or month picker.** Discussed and rejected as
   over-thought. The current month is concrete, already the default, and
   already what the page doc promises.
3. **Period + location are premises, and now live with the other premises.**
   The three bordered boxes collapse into one "Premissas da simulação"
   container. Order inside it: period (stated) → location (selector) → name →
   distribution → custom mix (conditional) → occupancy → price matrix
   (conditional). This is the "light" consolidation — the existing controls
   move; `FinancialSimulator` does not grow new fetch responsibilities beyond
   a location-change callback.
4. **The premises block is the first content after warnings.** The amber
   "Jornada estimada" banner (and the page-level error banner) stay above it.
   Everything else — results, simulated agenda, "Potencial" — stays below and
   in its current order.
5. **Location change still triggers a server refetch and a simulator reset.**
   This is unchanged behaviour; only period is removed as a trigger. The
   refetch keeps the `refreshing` flag and the optimistic-feeling disabled
   state it already has.
6. **The price matrix is read-only and single-location only.** When a specific
   location is selected, the matrix shows that location's exact configured
   rates. When "Todos os locais" is selected, the matrix is replaced by one
   line: *"Usando os preços configurados de cada local."* No cell is ever
   editable.
7. **No `rate_overrides` from the simulator.** `buildInput()` always sends
   `rate_overrides: []`. The field stays in the type and the backend contract
   for snapshot compatibility; the UI just never populates it.
8. **Saved scenarios with historical overrides still load.** `loadScenario()`
   restores name, mode, occupancy, and mix. It ignores any `rate_overrides` in
   the snapshot (they cannot be re-edited, and the snapshot's stored
   `result_snapshot` already reflects them). This is acceptable: the result is
   shown from the snapshot, not recomputed on load.
9. **`/financeiro` is out of bounds.** The shared `FinancialPeriodControls`
   and the dashboard's own period behaviour are not touched. Any future
   alignment between the two screens is a separate decision.

## 5. Implementation phases

### Phase A — Fix the simulator window to the current month

In [simulador/page.tsx](../../frontend/src/app/(protected)/financeiro/simulador/page.tsx):

- Drop the `FinancialPeriodControls` import and its render. Keep the
  `FinancialPeriod` type import only if still referenced; otherwise remove it.
- Replace the `filters` state shape. Compute the month range once — reuse
  `initialFilters()` for `dateFrom` / `dateTo` as module-level or `useMemo`
  constants — and keep only `placeId` in React state (`const [placeId,
  setPlaceId] = useState("")`).
- Rename `applyFilters` to `applyLocation(nextPlaceId: string)`. It calls
  `fetchFinancialDashboard(dateFrom, dateTo, nextPlaceId ? [nextPlaceId] : [],
  "estimated_when_unconfigured")`, then `setPlaceId` and `setDashboard`, with
  the existing `refreshing` / error handling.
- Update the initial `fetchFinancialDashboard` call to use the same constants
  (it already passes `initial.dateFrom` / `initial.dateTo`).
- Update the `<FinancialSimulator key=…>` to `key={\`${dateFrom}-${dateTo}-${placeId}\`}`
  (unchanged string, now built from the constants + `placeId`). The `dateFrom`
  / `dateTo` props it receives are the constants.
- Leave the "Potencial" section as-is; `dashboard.capacity_presets` is already
  month-scoped through the same fetch.

**Verify:** the page loads with no period row; the premises summary still shows
the current month; changing location still shows the `refreshing` disabled
state and updates results and "Potencial"; a reload returns to the current
month; `/financeiro` still renders its period presets normally.

### Phase B — Consolidate premises and move period + location into the block

Goal: one "Premissas da simulação" container, first after warnings, holding
period (stated) + location (selector) + the existing form.

Preferred approach — **lift the location control into `FinancialSimulator`**
so the block is a single component with one header:

- In [simulador/page.tsx](../../frontend/src/app/(protected)/financeiro/simulador/page.tsx),
  delete the bordered "Local do cenário" box. Pass what the component needs:
  `places={configuration.places}`, `placeId`, `onLocationChange={applyLocation}`,
  and `locationBusy={refreshing}`.
- In [financial-simulator.tsx](../../frontend/src/components/financial/financial-simulator.tsx),
  inside the first `CardContent`, above the existing two-column grid, add two
  stacked rows:
  - **Período** — static text from the `dateFrom` / `dateTo` props, formatted
    `dd/mm/yyyy – dd/mm/yyyy`, with a one-line helper: *"O simulador projeta
    sempre um mês."*
  - **Local do cenário** — the `<select>` moved verbatim from the page
    (options: "Todos os locais" + `places`), bound to `placeId` /
    `onLocationChange`, disabled while `locationBusy`. Keep the existing helper
    *"Afeta apenas a simulação; sua agenda não será alterada."*
- Remove the now-redundant `bg-muted/50` period/location summary box in the
  left column (its content is now the two rows above).
- Keep the `CardHeader` "Premissas da simulação" as the single title for the
  whole block. Do not nest a second card.
- Confirm the component's root already renders the amber banner first, then
  this card — no page-level reordering is needed beyond removing the two
  boxes.

**If the team prefers not to widen the component's props** (fallback), instead
wrap the page's `<FinancialPeriodControls>`-less period text, the location
box, and `<FinancialSimulator>` in a single bordered `<section>` with one
"Premissas da simulação" heading, and demote the component's internal
`CardHeader` to a plain sub-heading. Same visual result, no prop drilling,
slightly looser cohesion. Pick one before starting Phase B.

**Verify:** period + location sit at the top of the premises block under the
one heading; the "Jornada estimada" banner (when shown) is above the block;
changing location from inside the block refetches and resets the form as
before; mobile shows one stacked block with no duplicated period text.

### Phase C — Read-only, single-location price matrix

In [financial-simulator.tsx](../../frontend/src/components/financial/financial-simulator.tsx):

- Remove state and handlers: `editingRates`, `rateInputs`,
  `enableRateEditing()`, `resetRateEditing()`. Remove the `Pencil` import if
  now unused.
- In `buildInput()`, delete the `rateOverrides` computation and always set
  `rate_overrides: []`. `parseRateToCents` becomes unused — remove its import.
  `centsToRateInput` is still used to render the read-only cells.
- In `loadScenario()`, delete the `rate_overrides` branch (the `seeded` map,
  the `setRateInputs` / `setEditingRates` / `resetRateEditing` calls). Keep the
  name / mode / occupancy / mix / `setResult` / `setError` / `setScenariosOpen`
  restores.
- Replace the price sub-section body:
  - When `placeId` is set: render the existing 4×3 table in **read-only** form
    only — every cell is the `centsToRateInput(configuredRate(...))` span,
    never an `<Input>`. Drop the "Editar preços" / "Usar valores configurados"
    buttons entirely. Helper text: *"Preços configurados para este local.
    Alterá-los é feito em Configurações → Preços."* (link target: the existing
    pricing configuration route).
  - When `placeId` is empty: render no table. Show one line:
    *"Usando os preços configurados de cada local."*
- **Collapsible wrapper decision.** With no edit affordance and a
  single-location gate, the block is at most four read-only rows. Default:
  keep it always visible (remove the `<details>` / `<summary>` /
  `ratesOpen` / `ratesOpenOverride` wrapper added this session, and the
  `ChevronDown` import if now unused). If the team would rather keep the
  mobile collapse, retain the `<details>` but with the read-only body. State
  the choice in the PR.
- Keep the `Info` tooltip about per-participant pricing next to the helper
  text in the single-location case; it is still accurate.

**Verify:** no "Editar preços" button exists anywhere; selecting a location
shows that location's real rates as plain text; "Todos os locais" shows only
the one-line note; `Simular` and `Salvar cenário` still work and the saved
snapshot's `input_snapshot.rate_overrides` is `[]`; loading a historical
scenario that *did* have overrides restores its premises and shows its stored
result without error and without trying to re-open a price editor; TypeScript
reports no unused symbols.

### Phase D — Tests, docs, and release readiness

- **Frontend/e2e.** Add or extend a Playwright spec for the simulator:
  - the page renders without a period control and the premises block is the
    first block below any banner;
  - switching location updates the read-only matrix and shows the
    all-locations note for "Todos os locais";
  - running and saving a scenario produces a `Cenários salvos` entry, and
    selecting it restores the premises.
  Reuse the existing authenticated fixture pattern under `frontend/e2e/`; use
  a tenant with `commercial_financials` enabled and at least two locations
  with different rates.
- **Component check.** If there is a unit/RTL harness for
  `FinancialSimulator`, assert `buildInput()` output has `rate_overrides: []`
  and that no textbox is rendered inside the price matrix.
- **Backend.** No change and no new tests required. Optionally add one
  assertion in [test_financial.py](../../backend/tests/test_financial.py) that
  an evaluate/save request with `rate_overrides: []` and a whole-month range
  behaves identically to the pre-change default, to lock the contract the
  simulator now relies on.
- **Docs.**
  - Update [simulador_financeiro.md](../pages/simulador_financeiro.md):
    workspace structure (no period control; premises block first; read-only
    single-location price matrix), the behaviour list (fixed current-month
    window; no `Editar preços`; `rate_overrides` always empty from this
    screen), and the data-sources note.
  - Update the **Simulador financeiro** line in
    [README.md](../../README.md) if its one-line summary still says
    "temporary price scenarios."
  - Add this roadmap to the README **Roadmaps & Guides** list.
- **Dependency / infra.** No `requirements.txt`, lockfile, `.env`, migration,
  Docker, or Azure database work. Confirm none changed.

**Release check:** on a tenant with the financial feature and multiple
priced locations, walk the Phase A–C verifications end to end, then confirm
`/financeiro` is visually and behaviourally unchanged.

## 6. Touch-point matrix

| Area | Files | Change | Safety check |
| --- | --- | --- | --- |
| Simulator page shell | `frontend/src/app/(protected)/financeiro/simulador/page.tsx` | Remove `FinancialPeriodControls`; reduce `filters` to a `placeId` + current-month constants; rename `applyFilters` → `applyLocation`; drop the "Local do cenário" box and pass location props to `FinancialSimulator`. | Location change still refetches with `refreshing`; reload returns to current month; "Potencial" still populates. |
| Shared period control | `frontend/src/components/financial/financial-period-controls.tsx` | No change; simulator stops importing it. | `/financeiro` still renders all presets and custom dates. |
| Dashboard page | `frontend/src/app/(protected)/financeiro/page.tsx` | No change. | Visual/behaviour diff is nil. |
| Simulator component | `frontend/src/components/financial/financial-simulator.tsx` | Add stated-period + location rows at the top of the premises card; remove `editingRates` / `rateInputs` / edit handlers; read-only, single-location price matrix; `buildInput()` sends `rate_overrides: []`; `loadScenario()` drops the override branch; revisit the price-matrix `<details>` wrapper. | No editable price cell anywhere; `Simular` / `Salvar` produce empty `rate_overrides`; historical override snapshots still load and display. |
| Mobile hook / collapsibles | `frontend/src/lib/use-is-mobile.ts`, `simulated-agenda.tsx` | No change (agenda collapse stays). Price-matrix collapse may be removed with its section. | "Agenda simulada" still collapses on mobile; `useIsMobile` still imported where used. |
| Types | `frontend/src/lib/types.ts` | No change; `rate_overrides` stays required, sent as `[]`. | Snapshot compatibility preserved. |
| Backend | `backend/app/services/financial_analytics.py`, `backend/app/schemas/financial.py` | No change. | Evaluate/save contract unchanged; `[]` overrides already supported. |
| Tests | `frontend/e2e/`, optionally `backend/tests/test_financial.py` | Add simulator e2e coverage; optional contract assertion. | Both a single-location and an all-locations run are exercised. |
| Docs | `docs/pages/simulador_financeiro.md`, `README.md` | Rewrite period + price descriptions; link this roadmap. | Docs match the shipped screen. |

## 7. Sequencing and smallest shippable slice

Phases are ordered but each is releasable:

1. **PR 1 — Phase A.** Remove the period control and fix the window. This
   alone is a coherent, shippable simplification and removes the
   non-comparable-scenario problem immediately.
2. **PR 2 — Phase B.** Consolidate the premises block. Pure layout/IA; no
   contract change. Decide lift-into-component vs. wrap-in-section before
   starting.
3. **PR 3 — Phase C.** Remove the price override and gate the matrix.
   Independent of A and B in code, but reads best last so the premises block
   it edits is already in its final shape.

Phase D tests and docs are written with each PR, not deferred. The smallest
safe release is PR 1; PRs 2 and 3 can follow independently and in either
order relative to each other.

## 8. Risks and resolved trade-offs

- **Observed mix for a partly-future month.** The current month is part past,
  part future. `dashboard.observed_participant_mix` is drawn from that
  window's bookings, so early in a month it can be thin. This is strictly
  better than the removed "Próximo mês" preset (zero history) and matches the
  window the page doc already promises. Deriving the mix from a trailing
  window while projecting the current month is a **known limitation** left to
  a future backend roadmap; it is not addressed here.
- **Losing arbitrary date ranges.** A user who wanted a quarter or a specific
  historical month on the simulator can no longer get it. Accepted: that is
  the dashboard's job, and forcing one month is what makes saved scenarios
  comparable. If real demand appears, add an explicit horizon control (month /
  quarter / year) with matching output scaling — its own roadmap.
- **Losing the price lever.** Instructors can no longer model a price change's
  revenue impact inside the simulator. Accepted: the lever was linear with no
  demand response and produced numbers users discounted anyway; pricing has a
  dedicated configuration screen. A future percentage-based, place-aware
  adjustment with backend support can reintroduce it properly.
- **Historical snapshots with `rate_overrides`.** They remain valid and render
  from their stored `result_snapshot`. `loadScenario()` restores their
  premises but silently ignores the overrides (they are not re-editable). The
  result shown is the snapshot's, not a recompute, so there is no silent
  divergence.
- **All-locations price display today is already approximate.** Removing the
  matrix for "Todos os locais" is a net honesty gain: the old table showed
  tenant defaults while the backend priced each slot per place. The one-line
  note states what actually happens.
- **Widening `FinancialSimulator`'s props (Phase B).** The lift-into-component
  option adds `places` + a location callback to the component. Small and
  contained; the fallback wrap-in-section avoids it at the cost of a demoted
  heading. Either is acceptable; the PR states which was chosen.
- **Shared control, single consumer changed.** `FinancialPeriodControls` stays
  for `/financeiro`. No behavioural coupling is broken because the simulator
  only stops importing it.

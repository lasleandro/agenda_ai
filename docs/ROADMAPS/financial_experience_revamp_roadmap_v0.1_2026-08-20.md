# Financial Experience Revamp Roadmap v0.1 — 2026-08-20

**Status: implemented locally on 2026-08-20; pending final visual acceptance.**

## Implementation record

The route split, Financeiro shell, overview and recognized-revenue hierarchy,
simulator workspace, responsive rate-matrix treatment, accessible chart
descriptions, and documentation updates are implemented locally.

Completed automated checks:

- `npx tsc --noEmit` and `npm run lint` pass in `frontend/`.
- Focused financial/revenue backend regression passes: 8 tests.
- `git diff --check` passes.

The production frontend build was attempted in both available modes. The
unprivileged run cannot fetch the existing `next/font/google` Geist assets;
the network-enabled Turbopack run reaches past fonts but is blocked by this
environment's internal-port restriction. The Webpack fallback has a separate
Next.js `--showConfig` parser failure even though `tsc --showConfig` and type
checking both succeed. Re-run the standard production build in CI or a normal
development host before release. The final manual desktop/tablet/mobile,
dark-mode, and keyboard visual review remains the acceptance gate.

## 1. Confirmed product decisions

This roadmap reorganizes the financial experience without changing its
business behavior. The following decisions are already agreed:

1. Split scenario planning out of the operational Financeiro screen.
2. Keep `/financeiro` as the home for current financial performance,
   capacity, projections, and recognized-revenue history.
3. Create `/financeiro/simulador` as a dedicated what-if workspace.
4. Keep two internal Financeiro views: **Visão geral** and
   **Receita reconhecida**.
5. Replace the current sequence of equally weighted cards with a deliberate
   narrative hierarchy: summary, performance, distribution, potential, and
   long-term trend.
6. Preserve every existing financial calculation, endpoint, schema,
   permission, feature flag, audit rule, and scenario snapshot semantic.

The route split is an information-architecture and presentation change. It
must not alter the meaning of scheduled, estimated, recognized, or potential
revenue.

## 2. Goal and success definition

Create two focused experiences that match the instructor's mental model:

- **Financeiro:** “How is my business performing?”
- **Simulador financeiro:** “What could happen if I change these assumptions?”

The revamp succeeds when an instructor can identify the financial state of a
selected period, understand the distinction between projected and recognized
revenue, inspect capacity and its distribution, and enter scenario planning
without operational and hypothetical values competing on the same screen.

The visual result should remain consistent with the platform's existing
simple, modern, indigo-and-neutral design language. The improvement should
come primarily from information hierarchy, spacing, typography, semantic
color, and progressive disclosure—not decorative effects.

## 3. Scope boundaries

### In scope

- Recompose `/financeiro` around the agreed information hierarchy.
- Move `FinancialSimulator`, `ScenarioResults`, `SimulatedAgenda`, and saved
  scenarios into `/financeiro/simulador`.
- Add a feature-gated **Simulador financeiro** navigation destination while
  keeping the routes conceptually grouped under `/financeiro`.
- Preserve lightweight cross-navigation between Financeiro and the simulator.
- Move the date-period control into the Financeiro page context and make the
  active period explicit in both internal views.
- Keep the place filter visibly scoped to analytics it actually affects.
- Consolidate related KPIs and analytical breakdowns into fewer surfaces.
- Improve chart readability, responsive layouts, loading skeletons, scoped
  errors, empty states, focus behavior, and screen-reader semantics.
- Remove presentation-only state, props, requests, and imports made obsolete
  by the page split.
- Update page documentation and regression coverage.

### Out of scope

- New financial metrics, calculations, filters, forecasts, or scenario modes.
- Backend endpoint, request, response, database, or migration changes.
- Changes to pricing resolution, recognized-revenue snapshots, capacity math,
  prime-time rules, or rate configuration.
- Moving financial configuration out of **Configurações**.
- Adding exports, invoices, payments, receivables, comparison periods, or
  accounting integrations.
- Changing conversational-agent tools or behavior.
- A platform-wide design-system rewrite or redesign of unrelated pages.

If the proposed presentation reveals that an unavailable datum is needed, the
UI must defer that element rather than silently expand this roadmap's
functional scope.

## 4. Current-state assessment

The current `/financeiro` page has three product tabs—Visão geral, Receita,
and Simulador—and renders a fixed current-month summary above all three. This
creates several UX problems:

- page navigation appears after substantial content instead of establishing
  context first;
- current-month values and user-selected-period values appear together with
  insufficient distinction;
- scheduled, estimated, recognized, and capacity-based amounts use nearly the
  same visual treatment;
- many cards have equal prominence, producing a long “wall of cards”;
- the Revenue view inherits a date period that is only editable in Visão
  geral;
- the Simulator competes with operational reporting even though it represents
  hypothetical state;
- breakdowns by local, time of day, weekday, and time category consume
  separate cards despite serving the same analytical question;
- loading and fatal-error states replace the page with plain text rather than
  preserving its structure;
- wide tables depend on horizontal scrolling at narrow widths.

### Existing assets to preserve and recombine

| Existing asset | Current responsibility | Target destination |
|---|---|---|
| `FinancialMonthSummary` | Fixed current-month operational summary | Replaced by the selected-period overview summary |
| `FinancialDashboardSection` | Filters, period KPIs, capacity and projection analytics | Financeiro → Visão geral |
| `RevenueSection` | Recognized-revenue metrics, breakdowns, and immutable history | Financeiro → Receita reconhecida |
| `FinancialSimulator` | Scenario assumptions, price overrides, evaluation, and save | `/financeiro/simulador` |
| `ScenarioResults` | Current-versus-simulated results and tradeoffs | `/financeiro/simulador` |
| `SimulatedAgenda` | Read-only simulated/real calendar comparison | `/financeiro/simulador` |
| `analytics-charts` | Revenue lines, monthly bars, and capacity bars | Shared, visually refined in place |

The implementation should recombine these responsibilities rather than create
parallel financial calculations in new components.

## 5. Target routes and navigation

| Destination | Route | Purpose | Feature boundary |
|---|---|---|---|
| Financeiro | `/financeiro` | Operational performance, projections, capacity, recognized revenue | `commercial_financials` |
| Simulador financeiro | `/financeiro/simulador` | Hypothetical scenario modeling and saved scenarios | `commercial_financials` |

Both destinations must redirect consistently when the tenant lacks the
feature. The sidebar should show two explicit items because the current
navigation is flat. Route-prefix matching must be handled deliberately so
both entries do not appear active on `/financeiro/simulador`; prefer exact
matching for Financeiro and prefix matching for the simulator route.

Use navigation copy **Financeiro** and **Simulador financeiro**. Financeiro
may expose a restrained **Abrir simulador** link; the simulator should expose
**Voltar ao financeiro**. These are navigation affordances, not primary
financial actions.

## 6. Target information architecture — Financeiro

The page header establishes context before content:

1. Title and short description.
2. Page-level period control and active-period label.
3. Internal navigation: **Visão geral** and **Receita reconhecida**.
4. View-specific content.

The place control remains visibly scoped to Visão geral because the existing
recognized-revenue request accepts dates but not a place filter. Do not place
the local selector in a shared toolbar that visually promises to filter both
views.

### 6.1 Visão geral

Present information in this order:

1. **Resumo do período** — headline scheduled revenue, estimated-to-date
   context where applicable, occupancy, and actionable unpriced count.
2. **Desempenho** — primary scheduled-revenue time series plus a compact
   capacity summary.
3. **Distribuição da agenda** — one surface with internal options for local,
   part of day, weekday, and regular versus prime.
4. **Potencial** — the existing full-capacity presets presented as a
   comparison, not three independent cards.
5. **Tendência de longo prazo** — the existing six-month trend, clearly
   independent of the selected period.
6. **Premissas e limitações** — collapsed by default at the end.

```text
Financeiro                                      Abrir simulador →
Acompanhe receita, ocupação e capacidade

Período: [preset] [de] [até]                    período ativo
[ Visão geral ] [ Receita reconhecida ]
────────────────────────────────────────────────────────────

Resumo do período
┌──────────────────────────────────────────────────────────┐
│ Receita agendada (headline) · estimada até hoje · ocupação│
└──────────────────────────────────────────────────────────┘

Desempenho
┌────────────────────────────────┬─────────────────────────┐
│ Receita agendada no tempo      │ Capacidade atual        │
└────────────────────────────────┴─────────────────────────┘

Distribuição da agenda
[ Local | Período | Semana | Regular × nobre ]
┌──────────────────────────────────────────────────────────┐
│ breakdown selecionado                                   │
└──────────────────────────────────────────────────────────┘

Potencial → Tendência de longo prazo → Premissas
```

### 6.2 Receita reconhecida

Present information in this order:

1. **Receita reconhecida** — single hero amount for the selected period.
2. **Composição** — billable subtotal, adjustments, event income, occurrence
   count, and participant count as supporting facts.
3. **Evolução no tempo** — recognized-revenue series.
4. **Detalhamento** — one surface switching among local, customer, and group.
5. **Histórico confirmado** — immutable occurrences, progressively disclosed.

The recognized total must visually dominate its components. Event income
continues to remain separate from participant-priced revenue according to the
existing business rule.

History summaries should include an explicit chevron, visible hover/focus
state, aligned amount, outcome badge, date, and location. Expanded participant
and pricing-line details remain subordinate to the occurrence summary.

## 7. Target information architecture — Simulador financeiro

The new page is a scenario workspace, not a dashboard tab. Its hierarchy is:

1. Page header, non-destructive explanation, and return link.
2. Simulation context: period and location.
3. Assumptions and test prices.
4. Primary actions: Simular, then Salvar cenário.
5. Current-versus-simulated result.
6. Simulated/real calendar comparison.
7. Saved scenarios.

On wide screens, assumptions and price inputs should form a two-column
workspace. The action area should remain visually attached to the inputs.
Results should begin in a distinct section below rather than appear as another
undifferentiated card.

```text
Simulador financeiro                         ← Voltar ao financeiro
Teste cenários sem alterar agenda ou preços configurados

┌───────────────────────┬──────────────────────────────────┐
│ Premissas             │ Preços usados na simulação      │
│ nome / período        │ 1–4 participantes               │
│ local / distribuição  │ regular / nobre                 │
│ ocupação              │ configurados ou substituídos    │
│ [Simular] [Salvar]    │                                  │
└───────────────────────┴──────────────────────────────────┘

Resultado → Agenda simulada → Cenários salvos
```

Moving the page requires new client-side composition but no new API. The
simulator route may continue to fetch financial configuration, dashboard
baseline, and scenario snapshots in parallel using the existing functions.

## 8. Visual and interaction specification

### 8.1 Hierarchy and surfaces

- Use a consistent maximum content width across both pages.
- Use cards for grouped analytical modules, not for every number.
- Replace repeated KPI cards with compact stat groups inside one surface.
- Increase spacing between conceptual sections while reducing spacing between
  related labels and values.
- Use section headings to create scan landmarks: Resumo, Desempenho,
  Distribuição, Potencial, Tendência, and Histórico.
- Keep the indigo primary color; avoid gradients, glass effects, and new
  ornamental styling in financial content.
- Reduce repetitive decorative icons. Retain icons where they communicate a
  category, status, or navigation destination.

### 8.2 Financial semantics

Use consistent visual semantics without relying on color alone:

| Meaning | Suggested treatment | Required text |
|---|---|---|
| Recognized/confirmed | restrained emerald accent | “Receita reconhecida” |
| Scheduled/projected | primary indigo accent | “Receita agendada” or “estimada” |
| Capacity/hypothetical | neutral or violet accent | “Potencial” or “capacidade” |
| Missing price/incomplete | amber warning treatment | count plus “sem preço” |

Zero unpriced bookings should be quiet confirmation, not warning copy. A
positive unpriced count should be visually elevated without adding a new
workflow in this scope.

### 8.3 Filters and refresh behavior

- Keep preset periods, custom dates, and active-period copy in one coherent
  region.
- Preserve the current data while a new period is fetched.
- Indicate refresh locally with subdued progress or skeleton treatment; avoid
  replacing useful content or shifting the page.
- Ensure uncontrolled form defaults cannot become visually stale when filters
  are changed through a preset.
- The selected period must remain visible in Receita reconhecida without
  requiring the user to return to Visão geral.

### 8.4 Charts and breakdowns

- Keep existing datasets and calculations.
- Add readable temporal labels beyond only the first and last data point where
  space permits.
- Provide keyboard- and pointer-accessible value disclosure; do not depend
  solely on SVG `<title>` behavior.
- Consider a subtle area fill for revenue lines while preserving contrast.
- Represent occupied and free capacity consistently. If a bar encodes
  occupancy, its label and legend must lead with occupancy rather than free
  time—or render occupied/free as two explicit segments.
- Internal breakdown selectors must be real buttons or tabs with selected,
  focus, and accessible-name states.
- Keep chart colors valid in light and dark color schemes.

### 8.5 Responsive behavior

Define and verify three layout bands rather than relying only on incidental
Tailwind wrapping:

- **Narrow/mobile:** one column; full-width internal navigation; stacked
  filters; KPI stat grid of one or two columns; price matrices converted to
  readable participant rows instead of requiring page-level horizontal
  scrolling.
- **Medium/tablet:** two-column metric groups; major charts remain full width;
  filters wrap as a coherent unit.
- **Wide/desktop:** primary chart plus secondary capacity panel; simulator
  assumptions and prices in two columns; content never stretches beyond the
  readable maximum width.

Any retained horizontally scrollable table needs a visible overflow cue,
sticky first column where useful, and no clipped focus ring.

### 8.6 Accessibility

- Use semantic page headings in order: one `h1`, then section `h2`s and panel
  `h3`s.
- Use a true tab pattern only where arrow-key tab behavior is implemented;
  otherwise use clearly labeled navigation links or pressed buttons.
- Preserve visible focus states and minimum touch targets.
- Announce refreshed results and scoped request failures through an
  appropriate live region without repeatedly announcing unchanged content.
- Pair every icon-only control with an accessible name.
- Ensure semantic status is conveyed in text and meets contrast requirements.
- Keep financial values readable at 200% zoom without content loss.

### 8.7 Loading, error, and empty states

- Use skeletons matching the eventual header, summary, and principal panels
  for initial loading.
- Scope errors to the affected view or panel when existing independent
  requests fail; do not blank the entire page after usable data exists.
- Keep the last successful content visible during recoverable refresh errors.
- Use purposeful empty states for no capacity, no recognized revenue, no
  simulation result, and no saved scenarios.
- Empty-state guidance may link to existing configuration destinations but
  must not introduce new mutations.

## 9. Frontend composition and data ownership

Keep the implementation modular without introducing a generic dashboard
framework. Suggested ownership:

| Unit | Responsibility |
|---|---|
| Financeiro page | feature authorization, shared date range, internal view, cross-navigation |
| Overview section | overview-specific place filter, dashboard refresh, overview composition |
| Revenue section | recognized-revenue request and presentation for the shared date range |
| Simulator page | feature authorization, simulator context/configuration/dashboard/scenario loading |
| Summary/stat primitives | presentation-only financial value hierarchy, reused only when at least two concrete uses justify it |
| Chart components | visualization and accessible interaction for existing series/breakdown data |

Do not carry `FinancialSettingsDetail` into the simulator if no rendered
simulator behavior uses it. Removing that request/prop is part of the split's
cleanup, provided a final search confirms no hidden dependency.

Prefer the current optimistic UI principle during filter changes and scenario
actions:

- period/place refreshes keep the previous successful dashboard visible and
  reconcile when the request resolves;
- scenario evaluation keeps the existing result visible until the new result
  succeeds, or clearly marks it as belonging to the previous inputs;
- saved-scenario insertion remains immediate and rolls back or reports failure
  consistently with the existing implementation.

No client should derive new financial totals for display when the backend
already returns an authoritative value. Existing client aggregation such as
the documented estimate-to-date may remain only if its semantics and tests are
preserved.

## 10. Implementation phases

Each phase is independently reviewable and must leave the application in a
working state.

### Phase 0 — Baseline and visual contract

1. Capture desktop, tablet, and mobile screenshots of all three current tabs
   with representative local data.
2. Record the current endpoint calls and response ownership for Financeiro and
   Simulator.
3. Add or identify frontend behavior coverage for feature gating, active
   navigation, period propagation, and simulator evaluation.
4. Confirm current light/dark rendering and keyboard focus behavior.
5. Turn the target structures in §§6–8 into a small implementation checklist;
   do not introduce a separate design system.

**Verify:** baseline screenshots and behavior notes cover loading, populated,
empty, and error states; current targeted backend tests are green except for
explicitly documented unrelated failures.

### Phase 1 — Extract the simulator route

1. Create the protected `/financeiro/simulador` page.
2. Move simulator-specific loading and state into that page: configuration,
   dashboard baseline, and scenarios.
3. Reuse `FinancialSimulator`, `ScenarioResults`, and `SimulatedAgenda`; avoid
   duplicating their internal logic.
4. Remove the Simulator tab, imports, state, and fetches from `/financeiro`.
5. Remove the unused financial-settings dependency if confirmed safe.
6. Add **Simulador financeiro** to desktop and mobile sidebar content under the
   same feature flag.
7. Correct active-route matching and add reciprocal page links.

**Verify:** direct navigation and refresh work on both routes; a feature-disabled
tenant sees neither destination and cannot render either page; simulation,
save, simulated calendar, and real-calendar toggle behave exactly as before.

### Phase 2 — Establish the Financeiro shell and shared period context

1. Put the page title, description, simulator link, period context, and
   internal view navigation in the agreed order.
2. Rename the Revenue view to **Receita reconhecida**.
3. Lift date range ownership to the page shell and keep it available in both
   views.
4. Keep the local selector inside Visão geral until its backend scope expands.
5. Replace plain page-level loading with a stable shell and matching skeletons.
6. Scope initial and refresh errors without discarding previously loaded data.

**Verify:** changing the period updates both overview and recognized revenue;
the active period is visible from either view; changing local affects only the
overview and is not presented as a revenue filter.

### Phase 3 — Recompose Visão geral

1. Replace the fixed three-card monthly strip and four-card selected-period
   strip with the new summary hierarchy.
2. Preserve labels that distinguish scheduled, estimated-to-date, recognized,
   and capacity values.
3. Build the Desempenho row with the principal revenue series and capacity
   summary.
4. Consolidate the four capacity breakdowns into one distribution surface with
   an internal selector.
5. Restyle capacity presets as one comparison module.
6. Retain the independent six-month trend and collapsed assumptions section.
7. Apply warning treatment only when unpriced bookings exist.

**Verify:** every value displayed before the revamp remains reachable and has
the same numeric source; changing breakdown selection makes no request and
changes no calculation; selected-period and long-term contexts are explicit.

### Phase 4 — Recompose Receita reconhecida

1. Promote recognized revenue to the single hero amount.
2. Present subtotal, adjustments, event income, occurrences, and participants
   as supporting composition metrics.
3. Keep the recognized-revenue time series as the primary analytical panel.
4. Consolidate local/customer/group breakdowns into one selectable module.
5. Refine immutable history rows with explicit expand affordance and aligned
   summary information.
6. Preserve all legacy and current rate-source labels in expanded snapshot
   details.

**Verify:** totals and occurrence details match the existing API response;
event income remains separately labeled; expanding history never triggers a
mutation or recalculates snapshots.

### Phase 5 — Refine the Simulator workspace

1. Recompose assumptions and prices into the two-column desktop workspace.
2. Keep Simular as the primary action and Salvar cenário as secondary.
3. Clarify the boundary between configured rates and temporary test overrides.
4. Improve the no-result state and the transition into results.
5. Give current-versus-simulated results, calendar comparison, and saved
   scenarios explicit section hierarchy.
6. Replace narrow-screen price-table dependence with a readable stacked
   treatment while retaining the same inputs.

**Verify:** input snapshots sent by evaluate/save are byte-for-byte equivalent
in meaning to the old UI; editing test prices never writes configured rates;
the real/simulated calendar distinction remains unmistakable.

### Phase 6 — Chart, responsive, and accessibility polish

1. Improve line/bar labels and accessible value disclosure using existing
   chart data.
2. Standardize capacity bar meaning and legends.
3. Verify the three responsive layout bands and 200% zoom.
4. Complete focus order, keyboard interaction, live-region behavior, contrast,
   reduced-motion handling, and touch targets.
5. Remove obsolete styles/components created by the old composition, but do
   not refactor unrelated frontend code.

**Verify:** automated accessibility checks report no new violations; keyboard
and screen-size matrices pass; light and dark themes preserve hierarchy and
contrast.

### Phase 7 — Documentation and final regression

1. Update `docs/pages/financeiro.md` to describe only Financeiro's two views
   and current unified pricing terminology/endpoints.
2. Add `docs/pages/simulador_financeiro.md` for the new route and link it from
   the README Page Documentation section.
3. Update any architecture or capacity documentation whose page references
   still locate scenarios under the Financeiro tab.
4. Run the full targeted frontend/backend regression matrix and record any
   pre-existing unrelated failures separately.

**Verify:** documentation matches actual navigation, route ownership, API
usage, and feature behavior; repository searches find no stale “three tabs” or
retired generic/global pricing descriptions in current page documentation.

## 11. Verification matrix

### 11.1 Functional parity

| Area | Required checks |
|---|---|
| Overview | default month, presets, custom range, place selection, no-capacity state, unpriced bookings |
| Recognized revenue | selected-period propagation, totals, event income, all breakdowns, empty history, expanded snapshot |
| Simulator | default inputs, every distribution mode, custom mix validation, occupancy slider, configured rates, temporary overrides, evaluate, save |
| Calendar comparison | simulated view, real view, event details, no-result state |
| Navigation | direct route, browser refresh, back/forward, sidebar active state, cross-links |
| Feature boundary | finance-enabled tenant, disabled tenant, impersonated tenant |

### 11.2 Automated checks

- Run `npx tsc --noEmit` from `frontend/`.
- Run `npm run lint` from `frontend/` with no new warnings.
- Run the production frontend build in an environment with font assets
  available, or explicitly distinguish external font-download failure from a
  code/build failure.
- Run focused backend tests for financial dashboard, revenue, scenarios,
  tenant isolation, and feature enforcement even though backend code should
  remain untouched.
- Add frontend tests at the closest existing test layer for route visibility,
  period propagation, breakdown selectors, and simulation request payloads.
- Run `git diff --check` and search for stale imports, unused props, and old
  simulator-tab copy.

### 11.3 Manual visual matrix

Review at minimum:

- widths around 375 px, 768 px, 1280 px, and 1440 px;
- light and dark color schemes;
- default, loading, refreshing, empty, warning, partial-error, and populated
  states;
- short and long place/customer/group names;
- zero, small, and large BRL amounts;
- keyboard-only navigation and 200% browser zoom.

Capture before/after screenshots using the same representative local dataset
and selected period so hierarchy changes can be evaluated without data noise.

## 12. Security, tenant, and agent safeguards

- Continue deriving tenant identity exclusively from the authenticated
  session. The route split must not add tenant identifiers to requests.
- Keep `commercial_financials` checks in both client visibility and existing
  backend endpoints; client hiding is not authorization.
- Preserve existing role checks and generic client error handling.
- Do not expose additional customer, group, or revenue data in collapsed
  summaries beyond what the current authenticated page already receives.
- No write action may be added to Financeiro. Simulator save remains the only
  existing persistence action in the new simulator page.
- The active and passive conversational agents do not consume these frontend
  routes. Their shared financial resolver and make-up recommendation behavior
  must remain untouched; run agent-adjacent recommender regression only as a
  guard against accidental shared-component/service changes.

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Route extraction accidentally changes scenario inputs | Reuse the existing simulator components first; compare evaluate/save payloads before visual refactoring. |
| Both sidebar entries appear active | Use explicit exact/prefix match rules and test both desktop/mobile sidebar renderings. |
| Period and local filters imply broader scope than supported | Share only the date range; visually contain the local filter in Visão geral. |
| Consolidation hides previously visible information | Maintain a source-to-target inventory and acceptance check for every metric and breakdown. |
| New hierarchy changes perceived financial meaning | Preserve canonical terminology and add semantic labels; do not rely on color or proximity alone. |
| Refresh causes stale data to look current | Keep previous data visible but mark the affected region as updating; reconcile or show scoped failure. |
| Simulator becomes slower after route split | Fetch independent existing resources in parallel and remove unused settings requests. |
| Chart polish harms accessibility or dark mode | Test keyboard disclosure, contrast, reduced motion, and both themes before accepting visual changes. |
| Mobile redesign expands into new interaction logic | Reflow the same controls and values; defer new mobile-only workflows. |
| Documentation perpetuates retired pricing terminology | Update current page docs and grep for stale generic/global endpoint references in the final phase. |

## 14. Acceptance criteria

The revamp is complete only when all of the following are true:

1. `/financeiro` contains exactly **Visão geral** and
   **Receita reconhecida** as its internal views.
2. `/financeiro/simulador` is directly navigable, refresh-safe, feature-gated,
   and listed as **Simulador financeiro** in desktop/mobile navigation.
3. Financeiro and Simulator do not both appear active in navigation.
4. The selected financial period is visible and editable without entering a
   different internal view.
5. The local filter is not presented as affecting recognized revenue.
6. Scheduled, estimated, recognized, potential, and missing-price values are
   visually and textually distinguishable.
7. Every existing overview metric, breakdown, capacity preset, trend,
   assumption, revenue occurrence, scenario input, scenario result, and saved
   scenario remains accessible.
8. No backend financial contract, calculation, persistence rule, feature
   check, tenant boundary, or audit behavior changes.
9. Initial loading preserves the target layout; refreshing preserves previous
   usable content; errors and empty states are scoped and understandable.
10. Narrow, medium, and wide layouts pass without clipped controls, page-level
    overflow, or inaccessible focus states.
11. Type checking, linting, focused financial regressions, route tests,
    payload-parity tests, accessibility checks, and documentation review pass.

## 15. Delivery sequence and review gates

Use four product review gates to prevent visual work from obscuring behavioral
regressions:

1. **Route gate:** approve the extracted simulator with intentionally minimal
   visual change.
2. **Financeiro hierarchy gate:** approve the shell, summary, and overview
   distribution before polishing charts.
3. **Revenue and Simulator gate:** approve each focused workspace with real
   representative data.
4. **Responsive/accessibility gate:** approve mobile, dark mode, empty/error
   states, and final documentation.

Do not combine route extraction and the complete visual rewrite into one
unreviewable change. Each gate should include screenshots, the focused test
results, and a short list of deliberate deviations from this roadmap, if any.

## 16. Pre-implementation checklist

- [ ] Confirm **Receita reconhecida** as the final second-view label.
- [ ] Confirm **Simulador financeiro** as the sidebar label.
- [ ] Confirm the new canonical route `/financeiro/simulador`.
- [ ] Confirm the place filter remains overview-only in this non-functional
  pass.
- [ ] Choose representative local data for before/after screenshots.
- [ ] Decide whether the Financeiro internal view is URL-backed now or remains
  client state. Recommendation: use a query parameter such as
  `/financeiro?view=receita` so refresh, links, and browser history preserve
  context, while treating this as navigation state rather than new product
  functionality.
- [ ] Confirm no additional business metric is required for the approved
  visual composition.

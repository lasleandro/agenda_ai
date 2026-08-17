# Tenant Configuration Centralization Roadmap v0.1 — 2026-08-16

**Status: proposed — implementation has not started.**

## 1. Goal and product outcome

Create one tenant-facing destination for definitions that shape how the
platform operates. The existing **Minhas Regras** route will become the
configuration home, tentatively named **Configurações**, while **Financeiro**
will focus on analysis and decision support.

After the change, an instructor can find operational rules and financial
definitions from one tabbed configuration area without having to infer that
pricing controls live in a dashboard page. Financeiro will retain its
analytics-oriented tabs: **Visão geral**, **Receita**, and **Simulador**.

This is a UI composition and navigation migration. It must reuse the existing
financial services, authorization rules, schemas, persistence, and audit trail;
it is not a redesign of pricing or operational-rule semantics.

## 2. Scope

### In scope

- Move the existing financial configuration sections into the tenant
  configuration destination as tabs.
- Retain **Jornada de trabalho** and **Reposições** as operational tabs.
- Use the existing visual tab pattern already used by Financeiro.
- Rename the page and sidebar destination from **Minhas Regras** to
  **Configurações** if the product decision is confirmed.
- Keep each section's independent save behavior, API endpoint, validation, and
  audit behavior.
- Preserve the `commercial_financials` feature boundary for financial tabs.
- Update route/page documentation, tests, and navigation copy.

### Out of scope

- Changing financial calculations, rates, prime-time behavior, or the data
  model.
- Removing the `commercial_financials` feature flag or exposing financial
  configuration to tenants without that module.
- Moving platform-admin tenant settings, assistant settings, or scheduled-task
  administration into the tenant-facing page.
- A global autosave model, a new configuration API, or a generic settings
  framework.

## 3. Current state and reusable assets

`/minhas-regras` currently loads operational configuration for every
authenticated tenant:

- `WorkJourneySection` manages work intervals and multiple contained,
  non-overlapping breaks through `GET`/`PUT /api/rules/work-journey`.
- `CancellationNoticeSection` manages the make-up eligibility notice window
  through `GET`/`PATCH /api/rules/cancellation-notice-hours`.

`/financeiro` is available only when `commercial_financials` is enabled. Its
**Configuração** tab currently composes three reusable, independently saved
sections:

| Existing component | Existing responsibility | Existing API family |
|---|---|---|
| `GlobalRatesSection` | Tenant default commercial status and rates by participant count | `/api/financial/settings` |
| `PrimeTimeSection` | Weekday/time premium windows | `/api/financial/prime-time-windows` |
| `PlaceRatesSection` | Default and per-place regular/prime rates | `/api/financial/configuration` |

The target should relocate these component instances rather than copy their
forms. This avoids dual configuration sources, preserves existing validation,
and retains `FinancialChangeAuditLog` entries produced by the current API
routes.

## 4. Product and navigation decisions

### 4.1 Destination and naming

Use `/minhas-regras` as the initial canonical route to avoid breaking existing
bookmarks. Change its user-visible title and sidebar label to
**Configurações**. Add a later, optional `/configuracoes` alias and redirect
only after confirming any external links are migrated. Do not remove the old
route in this release.

### 4.2 Tab information architecture

The initial tabs should be flat, matching the current Financeiro control and
avoiding nested navigation:

1. **Jornada de trabalho** — work hours and pauses.
2. **Reposições** — cancellation notice window used for credit eligibility.
3. **Valores globais** — default commercial status and rates.
4. **Horários nobres** — premium-time windows.
5. **Valores por local** — default and per-place rate matrix.

The first two tabs are operational and available to every tenant. The last
three are financial and appear only when the tenant has the
`commercial_financials` module enabled. This avoids exposing forms whose
server endpoints correctly return the feature-gated response today.

### 4.3 Financeiro after the move

Remove only the **Configuração** tab from `/financeiro`. Keep its data loading
for dashboard, revenue, and simulator requirements; do not make those tabs
depend on the configuration page being visited first. Financeiro continues to
show a short contextual link to Configurações → Valores globais when required
setup is missing, rather than embedding a duplicate form.

## 5. Target architecture

```mermaid
flowchart LR
    Sidebar[Sidebar: Configurações] --> RulesPage[/minhas-regras]
    RulesPage --> Operations[Operational tabs]
    RulesPage --> FinancialTabs{commercial_financials enabled?}
    Operations --> Journey[WorkJourneySection]
    Operations --> Makeup[CancellationNoticeSection]
    FinancialTabs -->|yes| Global[GlobalRatesSection]
    FinancialTabs -->|yes| Prime[PrimeTimeSection]
    FinancialTabs -->|yes| Place[PlaceRatesSection]
    FinancialTabs -->|no| Hidden[No financial tabs rendered]
    Journey --> RulesAPI[/api/rules/*]
    Makeup --> RulesAPI
    Global --> FinancialAPI[/api/financial/*]
    Prime --> FinancialAPI
    Place --> FinancialAPI
    Financeiro[Financeiro] --> Analytics[Visão geral / Receita / Simulador]
    Financeiro -. setup link .-> RulesPage
```

The page may make parallel requests only for data that is authorized for the
current tenant. Operational data is loaded unconditionally. Financial settings,
financial configuration, and prime-time windows are loaded only after the
client knows that `commercial_financials` is enabled (or after the server
returns the existing authorized feature state). A failed financial request must
show a local tab error; it must not prevent operational tabs from loading.

## 6. Implementation phases

### Phase 1 — Establish the configuration shell

1. Inspect the authenticated session/feature state already available to the
   protected application shell.
2. Update the `/minhas-regras` page title, description, sidebar item, page
   document title if applicable, and page documentation to use
   **Configurações**.
3. Create a typed tab registry with a key, label, icon, and feature
   requirement. Keep the two operational tabs first.
4. Preserve the current default tab as **Jornada de trabalho**.
5. Render only authorized tabs and ensure no keyboard or URL state can select a
   hidden financial tab.

**Verification:** a tenant without the finance module sees the same two
operational controls and can save them; a finance-enabled tenant sees all five
tabs.

### Phase 2 — Move financial configuration composition

1. Move the existing form composition from the Financeiro configuration branch
   into configuration-tab branches; do not move or rewrite the form components.
2. Move only the parent-level data fetch/state necessary for those components:
   financial settings, financial configuration, and prime-time windows.
3. Keep callbacks that replace only the saved slice of page state, matching the
   current optimistic/reconciliation behavior of each component.
4. Remove the Financeiro **Configuração** tab and its unreachable imports/state.
5. Add an optional link from Financeiro to the precise configuration tab when
   settings are incomplete. Initial implementation may link to the page root if
   tab URLs are intentionally deferred.

**Verification:** editing each relocated form makes exactly the same API call,
creates the same audit records, and is reflected in Financeiro calculations on
the next refresh.

### Phase 3 — Deep-linking and polish

1. Decide whether a URL query parameter such as `?tab=horarios-nobres` is
   needed. If added, validate it against visible tabs and fall back to Jornada.
2. Preserve the selected tab after a section save and provide scoped success or
   error feedback inside that tab.
3. Check desktop and narrow-width layouts: tab lists may scroll horizontally,
   while the financial matrices remain their existing responsive components.
4. Review Portuguese copy so "Configurações" consistently refers to tenant
   definitions and platform-admin settings remain explicitly distinct.

## 7. Tenant isolation, authorization, and audit safeguards

- The browser must never supply a tenant ID for any configuration request. The
  existing backend derives `professional_id` from the authenticated session via
  `require_professional_id`.
- Relocating a component must not change the endpoint's role check or its
  `commercial_financials` feature check.
- A platform administrator impersonating a tenant may use the same
  tenant-scoped session behavior as today; the action remains attributed to the
  authenticated actor by the existing audit services.
- Do not add a general "all tenant settings" endpoint. Reusing narrow existing
  endpoints limits data exposure and preserves validation ownership.
- Financial configuration errors must remain generic to the client. Detailed
  diagnostics belong in server logs, following the existing error handling
  pattern.

## 8. Test plan

### Backend regression

- Run the current rules, financial-settings, prime-time, place-rate, financial
  analytics, and tenant-isolation test suites.
- Add an integration test proving a tenant without `commercial_financials`
  still can read/write work journey and cancellation notice, while financial
  endpoints remain feature-gated.
- Add or retain tests proving each financial update writes the expected audit
  record after the UI relocation; this is primarily endpoint behavior, but it
  protects against accidental API changes during cleanup.

### Frontend and behavioral verification

- Type-check the application with `npx tsc --noEmit`.
- Verify the visible-tab matrix for both feature states.
- Verify all five saves independently: global rates, premium windows, place
  rates, work journey, and cancellation notice.
- Verify errors from one financial tab do not blank or block operational tabs.
- Verify Financeiro has exactly three product tabs after the migration and
  dashboard/simulator data still loads directly.
- Verify keyboard tab selection, focus visibility, and horizontal overflow on
  a narrow viewport.

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Financial forms become visible to a non-finance tenant | Derive visible tabs from the existing feature state and leave backend feature checks unchanged. Test both states. |
| Duplicated forms produce divergent edits | Remove Financeiro's configuration branch in the same change that adds the new configuration tabs. |
| Financeiro data was accidentally loaded only in its old configuration path | Keep or explicitly separate data fetches required by overview/revenue/simulator; test direct navigation. |
| A large five-tab page feels cluttered | Use the existing compact horizontal tab control; only one section is rendered at a time. |
| Renaming breaks bookmarks or support instructions | Keep `/minhas-regras` initially, update sidebar copy, and introduce any new route only as a redirect-compatible alias. |
| Moving UI weakens auditability | Do not create write endpoints or change service calls; confirm existing audit regression coverage. |

## 10. Acceptance criteria

The migration is complete when all of the following are true:

1. The tenant-facing navigation labels the destination **Configurações**.
2. Every tenant can configure Jornada de trabalho and Reposições there.
3. Finance-enabled tenants additionally see Valores globais, Horários nobres,
   and Valores por local; tenants without the module do not.
4. Financeiro contains Visão geral, Receita, and Simulador, with no duplicate
   configuration forms.
5. Each moved form preserves its validation, API contract, tenant derivation,
   feature enforcement, and audit behavior.
6. Existing operational rules continue to affect appointment validation and
   make-up eligibility exactly as before.
7. Focused backend tests, TypeScript validation, and the manual feature-state
   matrix pass.

## 11. Rollout checklist and explicit decisions before coding

- [ ] Confirm the public-facing name: **Configurações** is recommended; retain
  **Minhas Regras** only as the route compatibility name in v0.1.
- [ ] Confirm whether a `/configuracoes` alias is wanted now or deferred.
- [ ] Confirm whether financial tabs should be hidden (recommended) or shown
  disabled with an explanation for tenants without the module. This roadmap
  assumes hidden to match current feature-gated navigation behavior.
- [ ] Confirm whether tab deep links are part of this release. They improve
  Financeiro-to-Configurações guidance but are not required for the relocation.
- [ ] Implement phases 1–2 as one coherent change, so users never encounter
  duplicated financial configuration forms.
- [ ] Run the acceptance checks and update `docs/pages/financeiro.md`,
  `docs/pages/minhas_regras.md`, `docs/architecture_overview.md`, and this
  roadmap's status to **implemented** only after release verification.

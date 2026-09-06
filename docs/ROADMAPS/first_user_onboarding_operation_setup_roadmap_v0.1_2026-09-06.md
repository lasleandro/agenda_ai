# First-User Onboarding — "Comece aqui" Operation Setup Roadmap v0.1 — 2026-09-06

**Status: implemented locally on 2026-09-06.** This roadmap makes a tenant's first session point
unambiguously at operation setup. It introduces one authoritative
`operation_configured` signal on the session and uses it to drive three
coordinated behaviours: a **"Comece aqui"** badge on the **Minha Operação**
navigation item, a conditional hoist of that item to the top of the sidebar
while setup is incomplete, and a one-time post-login redirect to
`/minhas-regras` for unconfigured tenants. Every behaviour reverts to the
normal steady state the moment setup is complete.

Design discussion that produced this plan:

- The target audience is tennis professionals in their first session, mostly
  non-technical. A subtle status dot is not explicit enough; an in-language
  **"Comece aqui"** pill is.
- **Minha Operação** must not be permanently reordered. Agenda is the daily
  home and the product's core value; settings-type items belong lower. The
  hoist is therefore conditional on `operation_configured === false` and
  self-heals.
- The redirect guides, it does not trap. An unconfigured tenant can still open
  Agenda and any other route; Agenda simply shows a setup empty state instead
  of a blank calendar.

Implementation notes (2026-09-06):

- The setup predicate is `operation_is_configured()` in
  `backend/app/services/operation_setup.py`; `me()` includes
  `operation_configured` only for a tenant-scoped session.
  `operationNeedsSetup()` in `frontend/src/lib/auth.ts` treats an absent flag
  as "no onboarding UI" and returns `true` for a professional login **or** an
  impersonating admin whose tenant is unconfigured.
- `AuthGuard` latches on the **first resolved render** rather than the literal
  "once per mount": only an `/agenda` value present on that first post-loading
  render is treated as a landing and redirected. Later client-side navigation
  to `/agenda` (e.g. from the sidebar) is not fought and renders the empty
  state — this is what makes Phase E reachable.
- The Agenda empty state is a small client component
  (`frontend/src/app/(protected)/agenda/agenda-view.tsx`) that swaps the week
  grid for a prompt while `operationNeedsSetup(user)`; it does not check for
  pre-existing appointments (an unconfigured tenant has none, and fetching to
  decide would add a spinner the platform avoids).
- Coverage: `backend/tests/test_operation_setup.py` (predicate + `/me`
  payload) and `frontend/e2e/operation-setup-onboarding.spec.ts` (badge,
  order, login redirect, `/agenda` bounce, empty state).

## 1. Goal and product outcome

Give a newly onboarded tenant a single, obvious next action, and remove every
onboarding affordance automatically once the operation is set up.

After implementation:

- `/api/auth/me` returns `operation_configured: boolean` for a tenant-scoped
  session. It is `true` when the tenant has at least one Local **and** at
  least one work-journey work interval; otherwise `false`.
- While `operation_configured` is `false`, the desktop sidebar and mobile
  drawer show **Minha Operação** as the first primary item, carrying a
  **"Comece aqui"** pill.
- While `operation_configured` is `false`, logging in lands the user on
  `/minhas-regras` instead of `/agenda`. Visiting `/agenda` directly still
  works and shows a setup-prompt empty state.
- When `operation_configured` is `true`, the badge disappears, **Minha
  Operação** returns to its normal position in the primary list, and login
  lands on `/agenda`. No persistent "done" checkmark is shown.
- A `platform_admin` without a selected tenant is unaffected; the signal is
  absent and no onboarding UI renders.

## 2. Scope and non-goals

### In scope

- One derived `operation_configured` boolean on the `/api/auth/me` payload and
  the `SessionUser` type, computed from existing Place and
  `WorkJourneyInterval` data. No schema change.
- Conditional first-position placement and a **"Comece aqui"** badge for the
  **Minha Operação** item in the shared `SidebarContent`.
- A one-time post-login landing decision in the login flow and the protected
  `AuthGuard`, based on `operation_configured`.
- A setup-prompt empty state on `/agenda` for unconfigured tenants.
- Backend unit coverage for the derivation and its edge cases; frontend/e2e
  coverage for badge visibility, ordering, and the landing redirect.
- Documentation updates and a README roadmap link.

### Out of scope

- A multi-step onboarding wizard, a getting-started checklist widget, or
  progress like "2 of 4 steps". This roadmap ships the single-signal version;
  a checklist can build on `operation_configured` later.
- Any change to what **Minha Operação** contains, its tabs, or its save flows.
- Public signup or account-request changes. See
  [auth_email_verification_password_reset_roadmap_v0.1_2026-09-01.md](auth_email_verification_password_reset_roadmap_v0.1_2026-09-01.md).
- Including financial rates in the configured definition. Financial config is
  feature-gated (`commercial_financials`) and is being made advisory; a tenant
  without the feature could never satisfy a rates condition.
- Blocking navigation for unconfigured tenants, or repeating the redirect on
  every route change.
- Onboarding the WhatsApp connection. The bottom-anchored "Ative o Whatsapp"
  item already carries that nudge.

## 3. Current state and reusable assets

- [auth.py](../../backend/app/api/auth.py) `me()` already builds a
  tenant-aware payload: it resolves `professional_id`, loads the
  `Professional`, and appends `features`. `operation_configured` is derived in
  exactly the same block, only when `user["professional_id"] is not None`.
- Operational data already exists per tenant:
  - `Place` — [places.py](../../backend/app/api/places.py) `GET ""` lists
    tenant places via a `professional_id` filter.
  - `WorkJourneyInterval` —
    [work_journey_interval.py](../../backend/app/models/work_journey_interval.py)
    has `professional_id`, `interval_type IN ('work','break')`, and
    `day_of_week`. [rules.py](../../backend/app/api/rules.py)
    `GET /work-journey` reads it.
  - Both are simple `EXISTS`-style checks; no new service is required.
- [auth.ts](../../frontend/src/lib/auth.ts) defines `SessionUser`. Adding one
  optional boolean there is the only client contract change.
- [session-context.tsx](../../frontend/src/lib/session-context.tsx) fetches
  `/api/auth/me` once for the whole protected area, seeds from
  `sessionStorage`, then reconciles. The badge and ordering read from
  `useSession()`; no extra request.
- [sidebar.tsx](../../frontend/src/components/layout/sidebar.tsx) already
  filters `primaryNavItems` (`visiblePrimaryNavItems`) and computes per-item
  active state in `renderNavItem`. The **Minha Operação** entry
  (`href: "/minhas-regras"`, `activePrefixes: ["/places"]`) is item index 4.
  A reorder plus an optional badge slot in `renderNavItem` is the whole
  change.
- [auth-guard.tsx](../../frontend/src/components/layout/auth-guard.tsx)
  already runs a post-reconciliation `useEffect` that `router.replace`s for
  the no-session and no-tenant cases — the natural place for a one-time
  landing redirect.
- [login/page.tsx](../../frontend/src/app/login/page.tsx) `handleLogin` does
  `router.replace("/agenda")` unconditionally today.
- [(protected)/agenda](../../frontend/src/app/(protected)/agenda/) renders the
  week calendar; it needs a branch for the unconfigured empty state.
- Reference: the tab set in
  [minhas-regras/page.tsx](../../frontend/src/app/(protected)/minhas-regras/page.tsx)
  — `journey`, `makeup`, `places` (+ financial tabs when enabled) — confirms
  Local and Jornada de trabalho are the two universal setup surfaces.

## 4. Product and decisions

1. **One definition of "configured".** `operation_configured` is `true` when
   the tenant has `>= 1` Place **and** `>= 1` `WorkJourneyInterval` with
   `interval_type = 'work'`. Rationale: these are the two setup surfaces every
   tenant has regardless of feature flags, and they are the minimum for Agenda
   and capacity to be meaningful. The exact predicate lives in one backend
   helper so it can be tuned in one place.
2. **Financial rates are excluded from the gate.** They are gated by
   `commercial_financials` and are moving to advisory
   ([advisory_work_journey_and_estimated_simulator_roadmap_v0.1_2026-08-31.md](advisory_work_journey_and_estimated_simulator_roadmap_v0.1_2026-08-31.md)).
   Gating onboarding on them would strand tenants without the feature.
3. **The signal is server-derived and read-only.** The client never computes
   or caches its own notion of configured; it only reflects
   `session.operation_configured`. Optimistic UI still applies: after a tenant
   saves their first Local or journey, the client may treat the operation as
   configured locally and reconcile on the next `/api/auth/me`.
4. **Placement is conditional, not permanent.** **Minha Operação** is hoisted
   to first position only while `operation_configured === false`. Otherwise it
   keeps its existing position in `primaryNavItems`. No other item moves.
5. **The badge is quiet by default.** A single **"Comece aqui"** pill in an
   accent colour (not destructive/red), static, no animation. It is the only
   onboarding decoration. When configured, nothing replaces it.
6. **The redirect guides once.** The post-login landing target is
   `/minhas-regras` when unconfigured, `/agenda` otherwise. `AuthGuard` does
   **not** re-redirect on later navigations; an unconfigured tenant may open
   any route. `/agenda` shows a setup empty state rather than a broken
   calendar.
7. **Unscoped admin sessions are inert; impersonation is not.** With no
   `professional_id`, `operation_configured` is omitted from the payload and
   the sidebar treats `undefined` as "no onboarding UI". A platform admin
   *impersonating* a tenant, however, does get the onboarding UI when that
   tenant is unconfigured — they are frequently the person doing the setup.
   `operationNeedsSetup()` therefore also returns `true` for
   `user.impersonating` (amended 2026-09-06; the original draft scoped it to
   `role === "professional"` only).
8. **No new endpoint, migration, `.env` key, or dependency.** The signal
   rides the existing `/api/auth/me` response.

## 5. Implementation phases

### Phase A — `operation_configured` on the session payload

Backend only.

- Add a helper `operation_is_configured(db, professional_id) -> bool` in a
  focused module (`backend/app/services/operation_setup.py`). It returns
  `True` only when both of these are true:
  - `db.query(Place.id).filter(Place.professional_id == professional_id).first()`
    is not `None`;
  - a `WorkJourneyInterval` row exists for that `professional_id` with
    `interval_type == "work"`.
  Use two `EXISTS`/`first()` probes, not `count()`; do not load full rows.
- In [auth.py](../../backend/app/api/auth.py) `me()`, inside the existing
  `if user["professional_id"] is not None:` block, call the helper and include
  `operation_configured` in the returned dict. Do **not** add the key for
  sessions without a `professional_id`.
- Keep `Cache-Control: no-store` (already set) so the flag is never served
  stale after setup.

**Verify:** `GET /api/auth/me` for a tenant with no places and no journey
returns `operation_configured: false`; adding one place keeps it `false`;
adding a `work` interval as well flips it to `true`; a `break`-only journey
does not flip it; a `platform_admin` session with no tenant has no
`operation_configured` key.

### Phase B — Session type and context

Frontend contract.

- In [auth.ts](../../frontend/src/lib/auth.ts), add
  `operation_configured?: boolean` to `SessionUser`. Optional, because
  admin/unscoped payloads omit it and cached sessions from before this change
  will not have it.
- No change needed in
  [session-context.tsx](../../frontend/src/lib/session-context.tsx); it passes
  the payload through. Confirm the `sessionStorage` seed round-trips the new
  field.
- Add a small helper `operationNeedsSetup(user): boolean` in `auth.ts`:
  `true` when `operation_configured === false` **and** the session is a
  professional login or an impersonating admin. Treating `undefined` as "no
  onboarding UI" keeps unscoped admins and stale caches quiet until
  reconciliation.

**Verify:** with a mocked unconfigured professional session,
`operationNeedsSetup` is `true`; likewise for an impersonating admin whose
tenant is unconfigured; for an unscoped admin or an absent flag it is `false`.

### Phase C — Sidebar: conditional hoist + "Comece aqui" badge

Refactor only [sidebar.tsx](../../frontend/src/components/layout/sidebar.tsx).

- Read `operationNeedsSetup(user)` from `useSession()` in `SidebarContent`.
- After computing `visiblePrimaryNavItems`, when `operationNeedsSetup` is
  `true`, move the item whose `href === "/minhas-regras"` to the front of the
  array. Otherwise leave order untouched. Do not reorder any other item; Mock
  Chat stays where it is.
- Extend `NavItem` with an optional `badge?: string` and set it on the
  **Minha Operação** entry at render time (not in the module-level constant)
  only while `operationNeedsSetup` is `true`.
- In `renderNavItem`, when `item.badge` is present, render a pill after the
  label: small, `rounded-full`, accent background
  (`var(--sidebar-active)` or an indigo token), `text-[11px]`, non-interactive
  (`pointer-events-none`), text `Comece aqui`. It must not break the row on
  the 240px sidebar or in the mobile drawer — allow the label to shrink/truncate
  before the badge wraps.
- Preserve `onNavigate`, active styling, hover behaviour, and the
  `activePrefixes: ["/places"]` rule.

**Verify:** unconfigured professional — **Minha Operação** is the first
primary item and shows the pill on both desktop and mobile drawer; active
highlight still works on `/minhas-regras` and `/places`. Configured
professional — item is back in its original slot, no pill. Admin — unchanged.

### Phase D — One-time post-login landing redirect

- In [login/page.tsx](../../frontend/src/app/login/page.tsx) `handleLogin`,
  after `await login(...)`, fetch the session (`fetchSession()`) and
  `router.replace(operationNeedsSetup(user) ? "/minhas-regras" : "/agenda")`.
  Keep the existing failure handling; on any session-fetch problem fall back
  to `/agenda`.
- In [auth-guard.tsx](../../frontend/src/components/layout/auth-guard.tsx),
  add a guarded branch in the existing post-`loading` effect: if the user is
  on `/agenda` (exact) and `operationNeedsSetup(user)`, `router.replace(
  "/minhas-regras")` — but only once per mount. Use a `useRef` latch so
  navigating back to `/agenda` deliberately is not fought. Do not redirect
  from any route other than the `/agenda` landing.
- Do not touch the no-session or `needsTenant` redirects.

**Verify:** logging in as an unconfigured tenant lands on `/minhas-regras`;
as a configured tenant lands on `/agenda`. After landing on `/minhas-regras`,
manually navigating to `/agenda` shows the empty state (Phase E) and does not
bounce. A configured tenant is never redirected.

### Phase E — Agenda setup empty state

- In [(protected)/agenda/page.tsx](../../frontend/src/app/(protected)/agenda/page.tsx),
  when `operationNeedsSetup(user)` and the calendar has no places/journey to
  render, show a centered empty state instead of the week grid: a short
  heading, one line of copy, and a primary button linking to
  `/minhas-regras`. Keep it a plain in-page state — no spinner, no modal.
- This state is advisory: if the tenant somehow has appointments, still render
  the calendar; the empty state is for the genuinely-empty first session.

**Verify:** unconfigured tenant opening `/agenda` sees the setup prompt with a
working link; configured tenant sees the normal calendar; the prompt never
appears for an admin.

### Phase F — Tests, docs, release check

- **Backend:** unit tests for `operation_is_configured` covering: neither
  present, place only, `work` interval only, `break`-only journey, both
  present. One API test asserting the `/api/auth/me` key for a scoped tenant
  and its absence for an unscoped admin. Names:
  `test_operation_is_configured_<scenario>_<result>`.
- **Frontend/e2e:** a Playwright spec (fixtures/test identities only, never
  real credentials) for: badge + first-position visible when unconfigured,
  absent when configured; post-login redirect to `/minhas-regras`;
  `/agenda` empty state for unconfigured.
- **Docs:** add a short "First-session setup" note to the relevant page doc
  under [docs/pages/](../../docs/pages/) describing the badge, the hoist, and
  the redirect, and that all three clear automatically. Link this roadmap from
  the root [README.md](../../README.md) **Roadmaps & Guides** list.
- **Release check:** no migration, `.env`, dependency, Docker, or Azure DB
  work. Confirm `requirements.txt` and the frontend lockfile are untouched.
  Manually walk one unconfigured tenant from login → setup → configured and
  confirm every onboarding affordance disappears without a reload beyond the
  next `/api/auth/me`.

## 6. Touch-point matrix

| Area | Files | Change | Safety check |
| --- | --- | --- | --- |
| Setup predicate | `backend/app/services/operation_setup.py` (new) | `operation_is_configured(db, professional_id)` — place EXISTS AND work-interval EXISTS. | One place to tune the definition; no full-row loads. |
| Session payload | `backend/app/api/auth.py` | Add `operation_configured` inside the existing tenant-scoped block of `me()`. | Key absent for sessions without `professional_id`; `no-store` kept. |
| Client contract | `frontend/src/lib/auth.ts` | Optional `operation_configured?: boolean` on `SessionUser`; `operationNeedsSetup()` helper (professional login or impersonating admin). | `undefined` ⇒ no onboarding UI; unscoped admins and stale caches stay quiet. |
| Session context | `frontend/src/lib/session-context.tsx` | No code change; verify the field round-trips the `sessionStorage` seed. | Reconcile still overrides a stale cached flag. |
| Sidebar | `frontend/src/components/layout/sidebar.tsx` | Conditional hoist of the `/minhas-regras` item; render-time `badge` slot in `renderNavItem`. | Only that item moves; badge non-interactive; no row break at 240px / mobile drawer. |
| Login landing | `frontend/src/app/login/page.tsx` | After `login()`, redirect by `operationNeedsSetup`; fall back to `/agenda` on any session-fetch error. | Configured tenant still lands on `/agenda`. |
| Route guard | `frontend/src/components/layout/auth-guard.tsx` | One-shot `/agenda` → `/minhas-regras` redirect for unconfigured, `useRef` latched. | No-session / `needsTenant` paths untouched; deliberate return to `/agenda` not fought. |
| Agenda | `frontend/src/app/(protected)/agenda/page.tsx` | Setup empty state with a `/minhas-regras` button when unconfigured and empty. | Calendar still renders if data exists; never shown to admins. |
| Tests | `backend/tests/`, `frontend/e2e/` | Predicate unit tests + payload test; badge/order/redirect/empty-state e2e. | Both configured and unconfigured actors covered. |
| Docs | `docs/pages/`, `README.md` | First-session note; roadmap link in Roadmaps & Guides. | Docs match the shipped predicate and behaviours. |

## 7. Sequencing and smallest shippable slice

Phase A is the foundation and ships first; it is inert until a consumer
reads the flag. Phase B is a one-line type plus a helper and pairs with A in
the same PR.

Phases C, D, and E each consume the flag independently and can land in any
order after A+B. Each is individually shippable and individually harmless:
the badge alone, the redirect alone, or the empty state alone all degrade to
"slightly less guided" rather than broken.

Recommended pull-request order:

1. **PR 1:** Phase A + B with predicate unit tests and the `/api/auth/me`
   payload test.
2. **PR 2:** Phase C (sidebar hoist + badge) with desktop/mobile verification.
3. **PR 3:** Phase D + E (redirect + Agenda empty state) with the e2e spec,
   then Phase F docs.

The smallest useful release is PR 1 + PR 2: the tenant gets an obvious,
self-clearing pointer to setup without any redirect behaviour. PR 3 adds the
landing redirect once the empty state exists to receive redirected traffic —
do not ship the redirect before the empty state.

## 8. Risks and resolved trade-offs

- **Definition too strict or too loose.** Requiring both a Place and a work
  interval could annoy a tenant who only wants one; requiring less could mark
  a barely-usable operation "configured". Mitigation: the predicate is a
  single helper, tunable in one commit, and the redirect never blocks — a
  tenant who disagrees just navigates away.
- **Stale cached flag on first paint.** `session-context` seeds from
  `sessionStorage` before reconciling, so a tenant who just finished setup on
  another tab could see the badge for one paint. Acceptable: it clears on the
  `/api/auth/me` reconcile a moment later, and optimistic local update after a
  save (decision 3) covers the common single-tab case.
- **Redirect loop or fighting the user.** A naive "redirect unconfigured to
  setup" on every render would trap the tenant. Mitigation: the guard only
  acts on the `/agenda` landing, once per mount, via a `useRef` latch; all
  other routes are freely reachable.
- **Badge layout on narrow widths.** The 240px sidebar and mobile drawer are
  tight. Mitigation: the label truncates before the badge wraps; verify both
  surfaces in Phase C rather than assuming.
- **Admin sessions.** The flag is omitted, not `false`, for unscoped admins,
  so a plain admin sees nothing. An impersonating admin keeps
  `role === "platform_admin"` but carries the tenant's `operation_configured`;
  `operationNeedsSetup` intentionally also matches `user.impersonating`, so an
  admin setting up a new tenant sees the same "Comece aqui" pointer.
- **Scope creep toward a wizard.** The single-signal design is deliberately
  minimal. A checklist or multi-step flow is a separate, later roadmap that
  can reuse `operation_configured` as its completion gate.

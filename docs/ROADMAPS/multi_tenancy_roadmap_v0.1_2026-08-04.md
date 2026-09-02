# Multi-Tenancy Roadmap v0.1 — 2026-08-04

## Implementation status (2026-08-05)

**Phases A–D are implemented and test-covered.** Phase E landed as part of D (sidebar already reads real session data). Phases F and G are unchanged — external/future, not code.

- **Phase A** — `get_professional_by_phone()` in [ingestion.py](../../backend/app/services/ingestion.py) resolves tenant by `assistant_phone`; unmatched numbers are rejected and logged, never defaulted. Migration `f1c9d4a7b3e2` adds the unique constraint. Tests: [test_ingestion.py](../../backend/tests/test_ingestion.py).
- **Phase B** — `User` model (migration `c2b8e91a4d70`) with `platform_admin` / `professional` roles, a DB check constraint enforcing `professional_id` is set iff role is `professional`. Passwords hashed with `bcrypt` ([security.py](../../backend/app/core/security.py)). Login is **email + password**, not username — the original `ADMIN_USERNAME`/`ADMIN_PASSWORD` env vars are no longer read by the code (left in `.env`, harmless, can be removed). Manual onboarding now uses passwordless activation through `scripts/create_user.py`. A historical shared development password was removed from this document on 2026-09-01 and must be treated as compromised; activate or reset any account that used it. Tests + Phase D tests: [test_auth.py](../../backend/tests/test_auth.py).
- **Phase C** — `require_professional_id` dependency ([dependencies.py](../../backend/app/api/dependencies.py)) resolves tenant from the JWT only, never from client input. Applied to `calendar.py`, `conversations.py`, and `dev_mock.py` (dev mock now uses the caller's own tenant's `assistant_phone` instead of a global env var, so mock chat data is tenant-scoped too). Tests: [test_tenant_isolation.py](../../backend/tests/test_tenant_isolation.py).
- **Phase D** — `platform_admin` role, `POST /api/auth/impersonate` and `POST /api/auth/stop-impersonating` ([auth.py](../../backend/app/api/auth.py)), `GET /api/admin/tenants` ([admin.py](../../backend/app/api/admin.py)), `ImpersonationLog` audit table (migration `c2b8e91a4d70`, same migration as `User`). Frontend: [`/admin/select-tenant`](../../frontend/src/app/admin/select-tenant/page.tsx) tile grid, `AuthGuard` force-redirects a `platform_admin` with no `professional_id` there, sidebar shows an "impersonando" role label + a "Trocar tenant" link back to the grid while impersonating. Verified live end-to-end via curl (login → 403 without impersonation → tenant list → impersonate → scoped calendar read → stop-impersonating) and via the running dev server, in addition to the automated tests.
- **Phase E** — `sidebar.tsx` now fetches the real session (`professional_name`, role, impersonating) instead of the hardcoded "João Silva" placeholder; `types.ts`/`api.ts` gained `TenantSummary`/`fetchTenants`.

**Follow-on work (separate roadmaps):**
- Tenant lifecycle (suspend / archive) is [its own roadmap](tenant_suspend_and_archive_roadmap_v0.1_2026-09-01.md), implemented 2026-09-01 — reversible full-lockout states on `Professional.status` reachable from the admin **Configurações** modal, with login/impersonation/ingestion enforcement and audit. No hard delete.

**Deviations from the original plan, and why:**
- Login uses **email**, not username — matches the `User.email` field naturally and is what the `geoedge_municipios` reference pattern uses too; the original doc didn't specify either way.
- Added `stop-impersonating` (not in the original phase text) so the sidebar's "Trocar tenant" link has a clean way back to an unscoped admin session, matching `geoedge_municipios`'s non-one-way impersonation requirement.
- `dev_mock.py` was folded into Phase C's scope (not explicitly named in the phase text, which only listed `conversations.py`/`calendar.py`) because it's a dashboard-adjacent read/write path with the same leak risk — leaving it on the old global `INSTRUCTOR_WHATSAPP_NUMBER` would have meant every tenant's mock chat wrote into the first tenant's data.

**What's not done / needs your review before this is production-safe:**
- Activate or reset any account that used the historical shared development password before any real second tenant is onboarded.
- No password-reset flow exists yet (not requested; add if manual onboarding needs it).
- Phase F (YCloud Tech Partner application) is still an external business step, unstarted.
- Phase G (self-service + payment) is still future/unscheduled, per your 2026-08-04 decision.

## Why now

The core pipeline (YCloud webhook → message ingestion → debounce → intent/entity extraction → appointment candidate) is built and verified end-to-end for a single instructor. The existing [POC roadmap](whatsapp_schedule_copilot_poc_roadmap_v0.1.md) already flags, in its Phase 5 forward-looking note, that onboarding "instructor #2" is not yet possible: there is one hardcoded `Professional` row, one shared admin login, and no request-level tenant scoping. This doc turns that deferred note into an actionable plan.

## Current state (assessed 2026-08-04)

- **Data model**: every domain table (`Contact`, `Conversation`, `Message`, `AppointmentCandidate`, `Appointment`, `AppointmentTransition`, `AppointmentEvidence`) already carries `professional_id`, so `Professional` is a de facto tenant root at the schema level.
- **Ingestion is hardcoded to one tenant**: `get_or_create_professional()` (`backend/app/services/ingestion.py`) does `db.query(Professional).first()` — it always attaches every inbound message to whichever `Professional` row exists first, regardless of which WhatsApp business number received it.
- **Single webhook, no tenant dispatch**: `POST /webhooks/ycloud` (`backend/app/api/whatsapp.py`) has no path/param identifying which business account a payload belongs to. There is one global `YCLOUD_WEBHOOK_SIGNING_SECRET`.
- **Auth is single-admin, not multi-tenant**: `POST /api/auth/login` (`backend/app/api/auth.py`) checks a single `ADMIN_USERNAME`/`ADMIN_PASSWORD` pair from `.env` — no `User` table, no tenant claim in the JWT. All dashboard routes (`conversations.py`, `calendar.py`) query without any `professional_id` filter.
- **Frontend has no tenant context**: `sidebar.tsx` hardcodes a display name in JSX; no account-switching UI; no `Professional`/`Tenant` type in `frontend/src/lib/types.ts`.
- **Config is flat and global**: one `.env`, one DB, one YCloud credential set, one `INSTRUCTOR_WHATSAPP_NUMBER`.

## Reference pattern

`geoedge_municipios` (sibling project in this workspace) already solves this shape of problem end-to-end, including the exact admin UX we want here (confirmed by inspection 2026-08-04, not modified):

- **JWT carries `tenant_id`**; a `kognita_admin`-role token can also override per-request via `X-Tenant-ID` header or `tenant_id` query param (`backend/api/dependencies.py` `get_current_tenant_id()`).
- **Tenant-select landing page** (`frontend/admin-select-tenant.html`): on login, a platform admin is routed here first. It calls an enriched tenant-list endpoint (`GET /api/tenant/admin/tenants`) and renders one tile per tenant (name, status badge, user count).
- **Click-to-impersonate**: clicking a tile calls `POST /api/auth/impersonate` with `{tenant_id}`. The backend verifies the caller's role is `kognita_admin` (`backend/api/routes/auth.py:218-219`), then mints a **new JWT** with the target `tenant_id` swapped in and `impersonating: true`, and sets it as the session cookie. The frontend then hard-redirects into the tenant-scoped dashboard.
- **Mandatory scoping, not optional**: every tenant-scoped page checks `GET /api/auth/me`, and if the admin's token has no `tenant_id` selected yet, it force-redirects back to the tile grid (`frontend/js/tenant-admin.js:1178-1179`) — an admin literally cannot view tenant data without first picking a tile.
- **Switch-tenant affordance**: a persistent "Painel Admin" button + a "Trocar Tenant" menu item are injected into every tenant-scoped page's top bar, both linking back to the tile grid — impersonation is not one-way; re-picking a tile just re-calls `/impersonate` with a new `tenant_id`.
- **Impersonation indicator**: a non-clickable badge ("Impersonando tenant: X") is injected into the top bar of every page while impersonating, so it's never ambiguous whose data is on screen.

We will reuse this pattern's shape (JWT tenant claim + tile-grid landing + impersonation endpoint + per-request tenant dependency + switch-tenant affordance + impersonation banner) without modifying that project — reimplemented natively for FastAPI + Next.js + our `Professional` model.

## Scope decision: what "tenant" means here

`Professional` **is** the tenant. We will not introduce a separate `Tenant`/`Organization` table — that would be premature (YAGNI) since the existing roadmap and domain model already treat one instructor as the unit of isolation. If a future need arises for one instructor to belong to a larger organization (e.g. a tennis academy with several coaches sharing a calendar), that's a distinct, separately-scoped effort.

## Phases

### Phase A — WhatsApp number → tenant resolution
Replace `get_or_create_professional(db)`'s `.first()` with a lookup keyed on the **receiving** YCloud number (the `to_phone` extracted in `ycloud_provider.normalize_event`). Add a unique `assistant_phone` lookup (column already exists on `Professional`) so each inbound webhook resolves to the correct tenant deterministically. If no match, reject/log rather than silently defaulting.
- Verify: a message sent to instructor A's number never creates/updates rows under instructor B's `professional_id`, with two `Professional` rows present in the test DB.

### Phase B — Auth: real users + tenant-scoped JWT
Replace the single `ADMIN_USERNAME`/`ADMIN_PASSWORD` env-based login with a `User` model (id, email, hashed password, `professional_id` FK, role). JWT gains a `professional_id` (and `role`) claim, following the `geoedge_municipios` shape. `require_authenticated` dependency returns the resolved `professional_id` for use in every route.
- Verify: login issues a token scoped to the correct professional; a forged/absent tenant claim is rejected.

### Phase C — Scope every query by tenant
Add a `professional_id` filter to every dashboard read/write path (`conversations.py`, `calendar.py`, and any future routes), sourced from the auth dependency — never from the request body/query string (per CLAUDE.md tenant-isolation rule).
- Verify: with two seeded professionals and two logged-in sessions, cross-tenant reads return empty/404, not the other tenant's data.

### Phase D — Platform admin: tenant tile grid + impersonation
This is the primary way you (the platform admin) will operate the multi-tenant system day to day — not optional ops tooling. Add a `platform_admin` role (distinct from a `Professional`-scoped `User`) whose login lands on a **tenant tile grid** (one tile per `Professional`: name, status, maybe contact/appointment counts) instead of a dashboard. Clicking a tile calls `POST /api/auth/impersonate {professional_id}`, which verifies the caller is `platform_admin` and mints a fresh JWT with `professional_id` swapped in and `impersonating: true`, replacing the session cookie — same shape as `geoedge_municipios`. Every tenant-scoped page:
- force-redirects a `platform_admin` back to the tile grid if their token has no `professional_id` selected yet (impersonation is mandatory to view tenant data, never implicit),
- shows a persistent "impersonating <professional name>" indicator plus a "switch tenant" affordance back to the grid (re-picking a tile just re-calls `/impersonate`, so it's not one-way),
- logs every impersonation event (who, which tenant, when) per CLAUDE.md's audit/accountability rule.
- Verify: a `platform_admin` login always lands on the tile grid; clicking a tile enters that tenant's scoped view and the indicator/switch affordance are visible; a non-`platform_admin` cannot call `/impersonate`; impersonation events are logged.

### Phase E — Frontend account context
Replace the hardcoded name in `sidebar.tsx` with the authenticated professional's data from the session; add a `Professional`/tenant type to `types.ts`; all API calls rely on the existing cookie session (no client-supplied tenant id). Applies to both a directly-logged-in professional and a `platform_admin` currently impersonating one (Phase D).
- Verify: two different logins (and one impersonated session) render different sidebars/calendars in manual testing.

### Phase F — YCloud Tech Partner migration
As flagged in the existing POC roadmap's risk register: YCloud's self-serve tier doesn't support onboarding multiple end-customers without each touching YCloud's own login. Apply for YCloud's Tech Partner program before actually onboarding instructor #2 in production. This is an external/business step, not code, but blocks real multi-tenant launch.

## Sequencing note

Phases A–C are the hard prerequisite for a second `Professional` row to be safe at all (data isolation). D is how you'll actually operate the system once a second tenant exists, so treat it as core, not deferrable, once A–C land — but it only becomes useful after there's a second `Professional` row to click into. E can slip independently. F is external and can run in parallel with A–C.

## Decisions (2026-08-04)

1. **Onboarding**: manual onboarding first (you provision `Professional` + `User` rows directly). Self-service onboarding with online payment is a distinct future phase (Phase G, below) — not built now, but the `User`/`professional_id` model in Phase B is designed so it doesn't have to be reshaped when self-service arrives.
2. **Auth method**: password auth (Phase B as drafted) for now — appropriate for manual onboarding with few users. Magic-link/passwordless is deferred; if revisited, WhatsApp OTP via YCloud (reusing existing infra, rather than adding an email provider) is the preferred candidate over email magic-link.

### Phase G — Self-service onboarding + payment (future, not scheduled)
New instructor signs up, verifies their WhatsApp business number, and pays online (Stripe or similar) before a `Professional` row is activated. Needs: public signup flow, payment provider integration, subscription/billing state on `Professional`, and — per Phase F — YCloud Tech Partner access so new numbers can be provisioned without touching YCloud's own console per customer. Out of scope until Phases A–C are stable in production with at least one manually-onboarded second tenant.

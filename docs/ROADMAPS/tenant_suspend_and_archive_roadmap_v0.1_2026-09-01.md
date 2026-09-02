# Tenant Suspend & Archive Roadmap v0.1 — 2026-09-01

**Status: planning.** Not implemented.

## 1. Goal and product outcome

Give the platform admin two lifecycle controls over a tenant (`Professional`),
reachable from the **Configurações** modal in `/admin/select-tenant`:

- **Suspender** — a reversible full lockout. A suspended tenant cannot be
  logged into by its own users, its inbound WhatsApp / agent traffic is
  rejected, its scheduled tasks stay skipped, and a platform admin who tries
  to impersonate it must pass an explicit confirmation. Un-suspending restores
  everything.
- **Arquivar** ("delete") — a reversible soft delete. The tenant is set to
  `archived`, every one of its users is force-logged-out, and its tile drops
  out of the default admin grid. No rows are physically removed. A separate,
  deliberate hard purge is explicitly **out of scope** for this roadmap
  (see §4).

After this lands, the admin can take a tenant offline (billing lapse, abuse,
offboarding) or shelve it entirely without touching the database by hand and
without any irreversible action.

## 2. Non-goals

- No physical row deletion, no `ON DELETE CASCADE` migration, no purge script.
- No self-service tenant deletion by the tenant's own users.
- No billing / subscription state (that is multi-tenancy roadmap Phase G).
- No new generic "tenant admin settings" framework — this reuses the existing
  `Professional.status` column and the existing modal.
- No change to how tenants are *created* (`scripts/create_user.py`).

## 3. Current state and reusable assets

- **`Professional` is the tenant.** `Professional.status` already exists
  (`String(50)`, default `"active"`) — [professional.py](../../backend/app/models/professional.py).
  Today it is effectively free-text; only `scheduled_tasks.py` and
  `admin.py` branch on `== "active"`.
- **Admin surface already exists.** `GET /api/admin/tenants`
  ([admin.py](../../backend/app/api/admin.py)) returns `TenantSummary`
  (which already carries `status`); the tile grid + **Configurações** modal
  live in [select-tenant/page.tsx](../../frontend/src/app/admin/select-tenant/page.tsx)
  with a tab pattern (`assistant` / `financial` / `tasks`) and an
  optimistic-update + rollback idiom we copy verbatim for the new tab.
  All admin routes are gated by `require_platform_admin`.
- **Session revocation mechanism already exists.** `User.auth_version`
  (int, in the JWT). `require_authenticated`
  ([dependencies.py](../../backend/app/api/dependencies.py)) rejects a token
  whose `auth_version` no longer matches the row; `auth_tokens.py` already
  bumps it on password reset. Bumping every tenant user's `auth_version` is
  our force-logout on suspend/archive.
- **Login is not tenant-status-aware.** `POST /api/auth/login`
  ([auth.py](../../backend/app/api/auth.py)) checks `User.status == "active"`
  only — nothing about the user's `Professional.status`.
- **Impersonation is not status-aware.** `POST /api/auth/impersonate` loads
  the `Professional` and mints a scoped cookie with no status check.
- **Inbound resolution is not status-aware.**
  `get_professional_by_phone()` ([chat/ingestion.py](../../backend/app/chat/ingestion.py))
  and the agent-channel equivalent ([chat/agent_channel.py](../../backend/app/chat/agent_channel.py))
  match on `assistant_phone` / `agent_phone` with no status filter.
- **Audit ledger exists.** `record_event()`
  ([operational_events.py](../../backend/app/services/operational_events.py))
  is the same helper `admin.py` already uses for
  `assistant.settings.updated`; `ImpersonationLog` is the existing
  admin-action audit table.
- **Error codes.** `TENANT_NOT_FOUND` exists in
  [error_codes.py](../../backend/app/core/error_codes.py); we add
  `TENANT_SUSPENDED` / `TENANT_ARCHIVED`.

## 4. Decisions (2026-09-01)

1. **Delete = soft archive only.** No table has `ON DELETE CASCADE` for
   `professional_id` (32 model files reference it), and CLAUDE.md rule 2
   forbids destructive actions on the remote PG DB. "Delete" therefore sets
   `status = 'archived'` and is fully reversible. A hard purge, if ever
   needed, is a separate future roadmap with its own migration and a
   local-only CLI — not this one.
2. **Suspend = full lockout.** Suspended blocks: tenant-user login, inbound
   WhatsApp ingestion, agent-channel ingestion, and daily-agenda task runs
   (already skipped for non-`active`). Platform-admin impersonation of a
   suspended/archived tenant is still *possible* but requires an explicit
   `confirm=true` on the impersonate call, so the admin can still get in to
   inspect or fix the tenant.
3. **Status vocabulary is fixed by a DB check constraint:**
   `active` | `suspended` | `archived`. A migration backfills any existing
   non-conforming value to `active`.
4. **Reversibility.** `suspended → active` (Reativar) and
   `archived → active` (Restaurar) are both one-click in the same modal tab.
   Restoring from `archived` lands the tenant in `active`, not back in
   `suspended`.
5. **Force-logout on state change.** Any transition *out of* `active`
   (`active → suspended`, `active → archived`, `suspended → archived`) bumps
   `auth_version` for every `User` with that `professional_id`, invalidating
   live sessions on their next request. Transitions back to `active` do not
   need a bump (users just log in again).

## 5. Data model changes

Single migration `xxxx_tenant_status_constraint`:

- `ALTER TABLE professionals` — add
  `CHECK (status IN ('active', 'suspended', 'archived'))`, named
  `ck_professionals_status`. Backfill first:
  `UPDATE professionals SET status = 'active' WHERE status NOT IN
  ('suspended', 'archived')`.
- Add nullable columns for the audit trail on the row itself (cheap, avoids
  a ledger join for the common "why is this tenant off?" question):
  - `status_changed_at TIMESTAMPTZ NULL`
  - `status_changed_by UUID NULL REFERENCES users(id)`
  - `status_reason VARCHAR(500) NULL`
- `downgrade()` drops the constraint and the three columns.

No other table changes. `Professional` model gains the three mapped columns
and (optionally) a `TenantStatus` `StrEnum` in the model module for the three
literals, reused by the service and schemas.

## 6. Phases

### Phase A — Model, migration, status vocabulary

- Add `TenantStatus` literals (`active` / `suspended` / `archived`) in
  `app/models/professional.py`; add `status_changed_at`,
  `status_changed_by`, `status_reason` mapped columns.
- Write the migration from §5 (check constraint + backfill + 3 columns).
- **Verify:** `alembic upgrade head` then `downgrade` runs clean on a local
  copy; inserting a `Professional` with `status='deleted'` raises
  `IntegrityError`; existing rows are all `active` post-migration.

### Phase B — `tenant_lifecycle` service

New `app/services/tenant_lifecycle.py`, thin, single responsibility:

```
set_tenant_status(db, *, professional_id, target_status, admin_user_id,
                  reason, source_ip, user_agent) -> Professional
```

- Guard clauses: 404 if the tenant does not exist; no-op (return current) if
  already in `target_status`; reject unknown `target_status`.
- On any transition out of `active`: `UPDATE users SET auth_version =
  auth_version + 1 WHERE professional_id = :id` (decision §4.5).
- Write `status_changed_at / _by / _reason` on the row.
- Emit one `record_event()` per transition with
  `event_type` in `tenant.suspended` / `tenant.reactivated` /
  `tenant.archived` / `tenant.restored`, `actor_type="platform_admin"`,
  `before_state={"status": old}`, `after_state={"status": new}`,
  `payload={"reason": reason}`.
- Caller commits (matches the `admin.py` convention).
- **Verify:** unit tests for each transition + the no-op + the unknown-status
  path; assert `auth_version` bumped for the tenant's users and *not* for
  another tenant's users; assert exactly one ledger row per call.

### Phase C — Admin endpoints

In `app/api/admin.py` (all under `require_platform_admin`):

- `POST /api/admin/tenants/{professional_id}/suspend` — body
  `{ "reason": str | null }` → `set_tenant_status(..., "suspended")`.
- `POST /api/admin/tenants/{professional_id}/reactivate` →
  `set_tenant_status(..., "active")` (from `suspended`).
- `POST /api/admin/tenants/{professional_id}/archive` — body
  `{ "reason": str | null }` → `set_tenant_status(..., "archived")`.
- `POST /api/admin/tenants/{professional_id}/restore` →
  `set_tenant_status(..., "active")` (from `archived`).

All return a small `TenantStatusState { status, status_changed_at,
status_reason }` (new schema in `app/schemas/api.py`). Add
`status_changed_at` / `status_reason` to `TenantSummary` so the grid can
render them without a second call.

`GET /api/admin/tenants` gains an optional `?include_archived=bool`
(default `false`) — archived tenants are filtered out of the default grid,
per decision §1.

- **Verify:** endpoint tests for happy path + 404 + non-admin 403 + the
  archived-tenant filter; `TenantSummary` still validates.

### Phase D — Enforcement points

1. **`POST /api/auth/login`** ([auth.py](../../backend/app/api/auth.py)) —
   after the user is authenticated, if `user.role == "professional"` and the
   user's `Professional.status != "active"`, return
   `error_response(403, TENANT_SUSPENDED | TENANT_ARCHIVED, ...)` and record
   a `login_blocked_tenant_inactive` auth-security event. Do **not** issue a
   cookie.
2. **`POST /api/auth/impersonate`** — if `professional.status != "active"`,
   require `body.confirm is True`; otherwise return `409` with a
   machine-readable code so the frontend can show the confirm dialog
   (decision §4.2). Still write the `ImpersonationLog` row when confirmed,
   plus a `record_event("tenant.impersonated_while_inactive")`.
3. **`get_professional_by_phone()`**
   ([chat/ingestion.py](../../backend/app/chat/ingestion.py)) — add
   `.filter(Professional.status == "active")`. A miss here is already
   rejected-and-logged, so a suspended tenant's inbound messages get the
   existing "unknown number" treatment. Same one-line filter in the
   agent-channel resolver in
   [chat/agent_channel.py](../../backend/app/chat/agent_channel.py).
4. **Daily-agenda tasks** — already skip non-`active`
   (`scheduled_tasks.py:35`); add a regression test only.
- **Verify:** a suspended tenant's user gets 403 on login; an archived
  tenant's user gets 403; impersonation without `confirm` → 409, with
  `confirm` → 200; an inbound webhook to a suspended tenant's number does
  not create rows; re-activating restores all four paths.

### Phase E — Frontend: "Ciclo de vida" tab in Configurações

- Add a fourth tab to `TenantSettingsDialog` in
  [select-tenant/page.tsx](../../frontend/src/app/admin/select-tenant/page.tsx):
  `lifecycle` with a `ShieldOff` / `Archive` (lucide) icon, label
  **"Ciclo de vida"**.
- Tab content, driven by `tenant.status`:
  - `active`: a "Suspender" button (with an optional reason textarea) and,
    below a divider in a subdued **Zona de risco** block, an "Arquivar"
    button. Archiving opens a small inline confirm ("Digite o nome do
    tenant para confirmar") to prevent misclicks — no separate modal.
  - `suspended`: a status line ("Suspenso em <date> — <reason>") plus a
    "Reativar" button, and still an "Arquivar" option.
  - `archived`: a status line plus a "Restaurar" button only.
- Client functions in [api.ts](../../frontend/src/lib/api.ts):
  `suspendTenant`, `reactivateTenant`, `archiveTenant`, `restoreTenant`.
  Extend `TenantSummary` in [types.ts](../../frontend/src/lib/types.ts)
  with `status_changed_at`, `status_reason`.
- **Optimistic UI** (CLAUDE.md rule 12): flip `tenant.status` in local
  state immediately, call the endpoint, roll back + show an inline error on
  failure — same pattern as `handleFeatureToggle`.
- The tile's existing status badge (line ~271) already renders any status;
  give `suspended` an amber and `archived` a slate treatment. Archived
  tiles are hidden unless a new "Mostrar arquivados" toggle above the grid
  is on (calls `fetchTenants({ includeArchived: true })`).
- Impersonating from a suspended/archived tile: `handleSelect` catches the
  `409`, shows a `window.confirm`-style inline prompt, and retries
  `impersonate(id, { confirm: true })`.
- **Verify (manual, `/run`):** suspend a test tenant → its badge turns
  amber, its own login is refused, admin re-entry asks for confirmation;
  archive it → tile disappears from the default grid, returns under
  "Mostrar arquivados"; restore → back to normal.

### Phase F — Tests

- Backend: `backend/tests/test_tenant_lifecycle.py` (service + endpoints),
  additions to `test_auth.py` (login + impersonate gating) and
  `test_tenant_isolation.py` or a new `test_ingestion` case for the
  phone-resolver filter.
- Naming per CLAUDE.md: `test_<unit>_<scenario>_<expected_result>`.
- Cover happy path, then `already in target status`, then non-admin, then
  cross-tenant `auth_version` isolation.

### Phase G — Docs

- New page doc `docs/pages/admin_tenant_lifecycle.md` (or a section in an
  existing admin doc) describing the three states and their effects.
- Cross-link from `docs/ROADMAPS/multi_tenancy_roadmap_v0.1_2026-08-04.md`
  (this is operational tooling for Phase D) and from the root `README.md`
  important-docs list.
- Update `business_rules.md` with the tenant-status semantics.

## 7. Sequencing

A → B → C are a straight line and land together (backend lifecycle is
useless in pieces). D depends on B's status vocabulary but each of its four
enforcement points is independent and individually testable. E depends on C.
F is written alongside each phase, not after. G last.

Smallest shippable slice: A + B + C + the login-block half of D + a minimal
E (suspend/reactivate only, archive deferred). Archive/restore + the
`include_archived` grid toggle can follow in a second PR.

## 8. Risks and open questions

- **Impersonation UX for inactive tenants.** Decision §4.2 keeps admin
  access behind a `confirm` flag. If that friction is unwanted, the
  alternative is to block admin impersonation entirely and require
  reactivation first — simpler backend, but then a suspended tenant can
  never be inspected without being briefly brought back online.
- **`status_reason` is free text.** Not validated beyond length. If we ever
  want reporting on *why* tenants are suspended, this should become an enum
  — out of scope now (YAGNI).
- **Other read paths.** This roadmap gates login, impersonation, and inbound
  message resolution. It does **not** add a blanket `status == 'active'`
  guard to every tenant-scoped API route, because a suspended tenant has no
  valid session anyway (login blocked + `auth_version` bumped). If a route
  is ever reachable by a non-user actor scoped to a `professional_id`, it
  must be revisited.
- **Hard purge.** Deliberately deferred. When it is scoped, it needs: an
  ordered delete across all `professional_id` tables (or a cascade
  migration), a local-only CLI with typed confirmation, and a dry-run mode.
- **YCloud / provider state.** Suspending a tenant here does not touch the
  external WhatsApp provider; inbound is simply dropped at resolution. No
  outbound is attempted because tasks are skipped. Acceptable for v0.1.

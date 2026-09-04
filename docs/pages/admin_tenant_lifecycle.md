# Page: Admin — Tenant lifecycle (suspend / archive)

**Route:** `/admin/select-tenant` → **Configurações** modal → **Ciclo de vida** tab
**File:** `frontend/src/app/admin/select-tenant/page.tsx`
**Access:** `platform_admin` only.

---

## Overview

Platform admins take a tenant (`Professional`) offline or shelve it entirely
without touching the database and without any irreversible action. Two
controls, both reversible:

- **Suspender** — a full lockout. Un-suspend with **Reativar**.
- **Arquivar** — a soft delete. The tile leaves the default grid. Undo with
  **Restaurar**.

`Professional.status` is one of `active` | `suspended` | `archived`
(DB-enforced by `ck_professionals_status`).

## Tenant workspace

The platform-admin grid is a paginated workspace rather than a manual-shell
onboarding screen.

- **Sair** ends the administrator session and returns to `/login`.
- **Novo tenant** creates an active tenant and its first professional user in
  one transaction. The dialog requires the tenant name, owner email, the
  operation WhatsApp number (canonicalized to E.164, stored as
  `Professional.assistant_phone`), and IANA timezone (default
  `America/Sao_Paulo`).
- The owner begins as `pending_activation` and receives the normal activation
  email. The email belongs to the user account—not the tenant record—so the
  same address is used for login and password recovery after activation.
- The tile grid loads 12 tenants at a time and provides previous/next controls
  plus `X–Y de Z tenants`. Archived tenants remain hidden until **Mostrar
  arquivados** is selected.

Tenant creation does not send SMTP directly. It queues an `account_activation`
delivery for the email worker, records a `tenant.created` operational event,
and records the activation queue event in the authentication audit log. A
failed transaction leaves no tenant, owner, outbox item, or audit event.

The legacy `scripts/create_user.py` command remains appropriate for creating
an additional user for an existing tenant; it is no longer needed for the
initial tenant/owner pair.

| From → To | Button | Blocks tenant login | Drops inbound WhatsApp/agent | Skips daily-agenda task | Hides tile |
|---|---|---|---|---|---|
| active → suspended | Suspender | yes | yes | yes | no |
| active/suspended → archived | Arquivar | yes | yes | yes | yes (unless "Mostrar arquivados") |
| suspended → active | Reativar | — | — | — | — |
| archived → active | Restaurar | — | — | — | — |

Restoring an archived tenant lands it in `active`, not back in `suspended`.

## Behaviour

- **Force logout.** Any transition out of `active` bumps `auth_version` for
  every user of that tenant, so live sessions fail on their next request.
- **Audit.** Each transition stamps `status_changed_at / status_changed_by /
  status_reason` on the row and appends one `tenant.suspended` /
  `tenant.reactivated` / `tenant.archived` / `tenant.restored` event to the
  operational-event ledger.
- **Admin still gets in.** Impersonating a suspended/archived tenant returns
  `409 TENANT_INACTIVE_CONFIRM_REQUIRED`; the grid then asks for confirmation
  and retries with `confirm: true`. That entry logs
  `tenant.impersonated_while_inactive`.
- **Tenant-user login** of an inactive tenant returns `403` with
  `TENANT_SUSPENDED` / `TENANT_ARCHIVED` and records a
  `login_blocked_tenant_inactive` auth-security event; no cookie is issued.
- **Optimistic UI.** The tab flips `status` locally, calls the endpoint, and
  rolls back on failure — same pattern as the financial-module toggle.
- Archiving is guarded by a type-the-tenant-name confirmation in the tab's
  "Zona de risco" block.

## Endpoints

| Method | Path | Body |
|---|---|---|
| `POST` | `/api/admin/tenants/{id}/suspend` | `{ "reason": string \| null }` |
| `POST` | `/api/admin/tenants/{id}/reactivate` | — |
| `POST` | `/api/admin/tenants/{id}/archive` | `{ "reason": string \| null }` |
| `POST` | `/api/admin/tenants/{id}/restore` | — |
| `GET`  | `/api/admin/tenants?include_archived=true` | list archived tenants too |
| `POST` | `/api/admin/tenants` | `{ "name", "owner_email", "whatsapp", "timezone" }` — create tenant and queue owner activation (`whatsapp` → `INVALID_PHONE` on a bad number) |

`GET /api/admin/tenants` accepts `page` (minimum 1) and `page_size` (6–48,
default 12). Its response includes `tenants`, `page`, `page_size`, `total`,
and `total_pages`; tile summaries are calculated only for the requested page.

All return `TenantStatusState { status, status_changed_at, status_reason }`
and are gated by `require_platform_admin`.

## Key code

| Concern | Location |
|---|---|
| Transition service | `backend/app/services/tenant_lifecycle.py` |
| Endpoints | `backend/app/api/admin.py` |
| Login / impersonation gating | `backend/app/api/auth.py` |
| Inbound number resolution filter | `backend/app/chat/ingestion.py`, `backend/app/chat/agent_channel.py` |
| Migrations | `b3d9f4a1c8e2` (status constraint + audit columns), `c7e1a9d3b5f8` (event types) |
| Tests | `backend/tests/test_tenant_lifecycle.py`, `backend/tests/test_scheduled_tasks.py` |

Not implemented: physical row deletion / hard purge. See
`docs/ROADMAPS/tenant_suspend_and_archive_roadmap_v0.1_2026-09-01.md`.

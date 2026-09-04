# Page: Solicitar uma conta (account request & approval)

**Public route:** `/solicitar-conta` and the **Solicitar uma conta** view on `/login`
**Admin route:** `/admin/account-requests`
**Files:** `frontend/src/components/auth/account-request-form.tsx`,
`frontend/src/app/solicitar-conta/page.tsx`,
`frontend/src/app/admin/account-requests/page.tsx`
**Access:** submission is anonymous; every review action is `platform_admin` only.

---

## Overview

Prospective users ask for access from one shared form. A submission persists an
`account_access_requests` row and creates **no** tenant and **no** user. A
platform admin reviews the queue and either approves — which provisions the
tenant, its pending owner, and the activation email in one transaction — or
rejects with an internal reason. Approval never signs anyone in; the owner still
follows the activation link, sets a password, and logs in normally.

This replaces the previous `mailto:contato@tennisos.com.br` link. No public path
opens an email client.

## Public submission

The `AccountRequestForm` component is rendered unchanged by both the `/login`
tab and `/solicitar-conta`. Three fields:

| Field | Required | Rule |
|---|---|---|
| Nome profissional ou da operação | yes | Trimmed, 2–255 chars; becomes the proposed tenant name. |
| Email | yes | Canonicalized by `normalize_email`; max 255 chars. |
| WhatsApp da operação | yes | Canonicalized to E.164 by `normalize_mobile_phone` (Brazil default; other countries must include the calling code). Stored on the request and copied to `Professional.assistant_phone` at approval. |
| Mensagem | no | Plain text, trimmed, max 1000 chars. |

The WhatsApp control is the shared `WhatsappField` component
(`react-phone-number-input`, `defaultCountry="BR"`), reused by the login view,
`/solicitar-conta`, the admin **Novo tenant** dialog, and request approval.

The form only disables itself while the request is in flight — it does not show
success before the server responds. On `202 Accepted` it swaps to a generic
confirmation.

`POST /api/account-requests` is the only intentionally anonymous endpoint. It is
input-bounded, canonicalizes the email, applies database-backed rate limits, and
never returns request IDs, user IDs, tenant IDs, account existence, or queue
position. The response body is identical for:

- a newly persisted request,
- a repeat of an existing `pending` request (no second row, no email), and
- an email that already owns an account (no row created).

Only malformed fields return `422`; exceeded quotas return `429`.

### Duplicate and abuse controls

- A partial unique index (`uq_account_access_requests_pending_email`) permits
  one `pending` row per canonical email. A lost insert race is caught and
  answered with the same generic `202`.
- Rate limits are keyed by canonical-email digest and source-IP digest and are
  externalized:

  | Key | `.env` | Default |
  |---|---|---|
  | Per email / 24h | `ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY` | 3 |
  | Per source IP / 1h | `ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR` | 20 |

- A previously rejected email may submit again after the rate-limit window; the
  rejected decision stays terminal (there is no reopen).
- Submission records an `account_request_submitted` `AuthSecurityEvent` with
  email/IP digests only — never the raw address or message.

## Admin request inbox

`/admin/account-requests` is one of three surfaces sharing `PlatformAdminHeader`
(with **Tenants** and **Tarefas agendadas**). The **Solicitações** link carries a
pending-count badge, capped visually at `99+`, fed by
`GET /api/admin/account-requests/summary` (a count only, no PII).

The screen has **Pendentes / Aprovadas / Rejeitadas** filters, newest-first
(`submitted_at DESC, id DESC`), server-paginated at 20 rows. Each page also
returns unfiltered `status_counts`; the frontend never downloads the full set to
compute badges or pages. Reviewer email and activation state are resolved only
for the IDs on the current page.

### Approval

**Aprovar e criar tenant** opens a dialog prefilled with the request's
normalized name (editable), its canonical owner email (read-only), the requested
WhatsApp number (editable, re-normalized server-side), and a timezone selector
defaulting to `America/Sao_Paulo`. On confirm the row flips to **Aprovada**
optimistically and the badge decrements, then reconciles with the response.

`POST /api/admin/account-requests/{id}/approve` runs one transaction:

1. `SELECT ... FOR UPDATE` on the request row;
2. return the existing result if already `approved` (idempotent retry);
3. `409` if the request was `rejected`;
4. revalidate name, WhatsApp number, timezone, and owner-email availability;
5. call `create_tenant_with_owner(..., audit_source="account_request_approval",
   account_request_id=...)` — the same path as **Novo tenant** — to create the
   active `Professional`, the `pending_activation` `User`, the `account_activation`
   `EmailDelivery`, the `tenant.created` operational event, and the
   `account_activation_queued` auth event;
6. mark the request `approved`, link `professional_id` / `owner_user_id`, stamp
   `reviewed_by_user_id` / `reviewed_at`;
7. commit once.

Any failure rolls back the decision, tenant, user, delivery, and audit writes
together. The body cannot supply owner email, role, status, or user ID. If the
email became unavailable after submission, the endpoint returns `409`
`EMAIL_ALREADY_IN_USE` and the request stays `pending`; a tenant is never
created under a different email.

### Rejection

`POST /api/admin/account-requests/{id}/reject` takes an optional `reason`
(≤ 500 chars), locks the row, applies the decision only from `pending`, and
treats a repeat as idempotent. Rejecting an `approved` request returns `409`.
Rejection creates no tenant, user, token, or email.

### Activation delivery visibility and resend

Approved rows show the linked owner's activation state — `not_queued`, `queued`,
`processing`, `retry_wait`, `sent`, `failed`, `suppressed`, or
`account_activated`. SMTP error detail and tokens are never sent to the browser.

When the owner is still `pending_activation` and no delivery is active,
**Reenviar ativação** (`POST /api/admin/account-requests/{id}/resend-activation`)
queues a fresh delivery through `enqueue_auth_email`. It never calls SMTP in the
HTTP request, is unavailable once the account is active, returns an existing
active delivery rather than adding a second, and is guarded by:

| Guard | `.env` | Default |
|---|---|---|
| Cooldown since last delivery | `ACCOUNT_ACTIVATION_RESEND_COOLDOWN_SECONDS` | 60 |
| Per owner-email + per admin / 1h | `AUTH_EMAIL_MAX_SENDS_PER_HOUR` | 5 |

## Endpoints

| Method | Path | Auth | Body |
|---|---|---|---|
| `POST` | `/api/account-requests` | anonymous | `{ proposed_tenant_name, email, whatsapp, message? }` → `202` |
| `GET`  | `/api/admin/account-requests?status=&page=&page_size=` | `platform_admin` | — (`status` ∈ pending/approved/rejected, default pending; `page_size` 10–50, default 20) |
| `GET`  | `/api/admin/account-requests/summary` | `platform_admin` | — → `{ pending }` |
| `GET`  | `/api/admin/account-requests/metrics` | `platform_admin` | — (aggregate, no PII) |
| `POST` | `/api/admin/account-requests/{id}/approve` | `platform_admin` | `{ tenant_name, whatsapp, timezone }` |
| `POST` | `/api/admin/account-requests/{id}/reject` | `platform_admin` | `{ reason? }` |
| `POST` | `/api/admin/account-requests/{id}/resend-activation` | `platform_admin` | — |

Expected failures use the shared `{ "error": { code, message } }` shape with
codes from `error_codes.py` (`ACCOUNT_REQUEST_NOT_FOUND`,
`ACCOUNT_REQUEST_ALREADY_DECIDED`, `ACCOUNT_REQUEST_ACTIVATION_UNAVAILABLE`,
`ACCOUNT_REQUEST_STATUS_INVALID`, `ACCOUNT_REQUEST_MESSAGE_INVALID`,
`INVALID_PHONE`, `EMAIL_ALREADY_IN_USE`, `RATE_LIMITED`).

## Data model

`account_access_requests` (migrations `c8f1a2b3d4e5`, `d4e5f6a7b8c9`) is a
pre-account business record, deliberately separate from
`users` / `professionals` / `email_deliveries`.

- `status` ∈ `pending` | `approved` | `rejected` (`ck_account_access_requests_status`).
- `whatsapp` — canonical E.164 number, nullable at the column level so rows
  created before `d4e5f6a7b8c9` stay valid; the public API requires it for
  every new submission.
- A state-consistency check (`ck_account_access_requests_state`): `pending` rows
  have no reviewer/tenant/owner; `approved` rows require reviewer, review time,
  `professional_id`, and `owner_user_id`; `rejected` rows require reviewer and
  review time and have no tenant or owner.
- `uq_account_access_requests_pending_email` — partial unique on `email` where
  `status = 'pending'`.
- `ix_account_access_requests_status_submitted` `(status, submitted_at, id)` for
  pagination; `ix_account_access_requests_professional` for linked-tenant lookup.
- FKs to `users` / `professionals` are `ON DELETE RESTRICT`.

## Retention

`ACCOUNT_REQUEST_REJECTED_RETENTION_DAYS` (default 180) bounds how long a
rejected row's PII is kept. `scripts/purge_account_requests.py` calls
`purge_rejected_account_requests`, deleting rejected rows whose `reviewed_at` is
older than the window. Approved records follow the resulting tenant account's
retention policy. Aggregate onboarding counters (no PII labels) are available
from `scripts/account_request_metrics.py` and the `/metrics` endpoint.

## Key code

| Concern | Location |
|---|---|
| Model + status constants | `backend/app/models/account_access_request.py` |
| Schemas | `backend/app/schemas/account_requests.py` |
| Submission, decisions, summaries, purge, metrics | `backend/app/services/account_requests.py` |
| Anonymous submission route | `backend/app/api/account_requests.py` |
| Admin list / approve / reject / resend routes | `backend/app/api/admin_account_requests.py` |
| Shared tenant provisioning | `backend/app/services/admin_tenants.py` (`create_tenant_with_owner`) |
| Shared WhatsApp input | `frontend/src/components/ui/whatsapp-field.tsx` |
| Migrations | `c8f1a2b3d4e5`, `d4e5f6a7b8c9` (whatsapp column) |
| Backend tests | `backend/tests/test_account_requests.py` |
| Browser test | `frontend/e2e/account-request.spec.ts` |

See `docs/ROADMAPS/account_request_approval_onboarding_roadmap_v0.1_2026-09-03.md`
for the full rationale and out-of-scope list (no automatic approval, billing,
WhatsApp provisioning, multi-user tenants, or rejection emails in v0.1).

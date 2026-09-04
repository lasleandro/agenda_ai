# Account Request, Approval, and Onboarding Roadmap v0.1 — 2026-09-03

> **Status: implemented (2026-09-03).** This roadmap replaced the current
> email-client-based “Criar conta” experience with a persisted access-request
> workflow reviewed by a platform admin. Approval creates the tenant and pending
> owner atomically and queues the existing account-activation email. See
> `docs/pages/solicitar_conta.md` for the delivered behavior.
>
> **Amendment 2026-09-04.** A mandatory **WhatsApp da operação** field was added
> to the public request form and the admin **Novo tenant** dialog. It is
> canonicalized to E.164 (`normalize_mobile_phone`, Brazil default), stored on
> `account_access_requests.whatsapp` (migration `d4e5f6a7b8c9`), and written to
> `Professional.assistant_phone` by `create_tenant_with_owner` in both the
> direct-create and request-approval paths. No uniqueness constraint yet.
> Inline amendment notes below carry the contract changes.

## 1. Purpose

Give prospective Tennis OS users one clear way to request an account from both
the login screen and the public landing page, while preserving the existing
decision that onboarding is controlled by a platform admin.

The target lifecycle is:

```text
Visitor submits request
  → pending request appears in the platform-admin workspace
  → admin reviews and approves
  → tenant + pending owner + activation-email delivery are committed together
  → owner follows the email link and chooses a password
  → owner returns to login and signs in with the verified email
```

Approval must not sign the user in automatically. The activation link proves
mailbox control and opens the existing password-setup page; a normal login is
still required after activation.

## 2. Confirmed product decisions

1. Rename the login option from **Criar conta** to **Solicitar uma conta**.
2. Replace the current `mailto:` submission with a real persisted request. A
   successful public submission creates no tenant and no user.
3. Add the same **Solicitar uma conta** call to action to the public landing
   page. Both entry points use the same form component and backend endpoint.
4. Add a platform-admin request inbox where pending, approved, and rejected
   requests can be reviewed with bounded pagination.
5. Approval is explicit and admin-only. In one database transaction it marks
   the request approved, creates an active tenant, creates its initial owner as
   `pending_activation`, and queues the established activation email.
6. Before confirming approval, the admin may correct the proposed tenant name
   and select the tenant timezone. The requester email is canonicalized by the
   backend and cannot silently be replaced during approval.
7. Rejection records an optional internal reason and does not email the
   requester in v0.1. Rejection email and general sales/CRM automation are
   separate product decisions.
8. Public self-service activation, billing, WhatsApp provisioning, social
   login, and MFA remain out of scope. This is a request-and-approval workflow,
   not open signup.

## 3. Current state and reusable foundations

### Current behavior

- The login page labels its second view **Criar conta**, but the form only
  constructs a `mailto:contato@tennisos.com.br` link. Nothing is validated by
  the backend, persisted, assigned, or visible to an admin.
- The landing page offers **Entrar** and a floating WhatsApp contact. It has no
  dedicated account-request call to action.
- The platform-admin tenant grid can already create a tenant and its initial
  owner from **Novo tenant**.
- Account activation, password setup, SMTP delivery, durable retries, login by
  email, and password reset already work through the authentication email
  lifecycle.

### Foundations to reuse

| Need | Existing foundation | Roadmap use |
|---|---|---|
| Email identity | `normalize_email` | Canonicalize request email at submission and approval. |
| Tenant provisioning | `create_tenant_with_owner` | Reuse the same transaction-safe tenant/user/outbox behavior. |
| Account activation | `EmailDelivery` worker and `/activate` | Send the owner a one-time setup link; never collect a password from the admin. |
| Admin authorization | `require_platform_admin` | Protect all request-list and decision endpoints. |
| Public abuse controls | DB-backed `rate_limit_exceeded` plus global write limiter | Limit submissions by canonical email and source IP. |
| Error contract | `error_codes.py` and `error_response` | Return stable safe errors; do not invent endpoint-specific strings. |
| Admin navigation | `/admin/select-tenant` header and session guard | Add a visible requests destination and pending-count badge. |
| UI language | Existing login and landing design systems | Share one form without duplicating its behavior. |

### In scope

- persisted public account requests;
- one shared responsive request form;
- login and landing-page entry points;
- submission confirmation and duplicate-safe behavior;
- a paginated platform-admin request inbox;
- request detail, approve, and reject actions;
- atomic approval using the existing tenant provisioning and activation outbox;
- authorization, rate limiting, auditability, privacy controls, and automated
  tests.

### Explicitly out of scope

- automatic approval or tenant creation at public form submission;
- subscription checkout, plan selection, trials, or entitlement activation;
- automated WhatsApp/YCloud provisioning;
- multiple users per tenant, invitation management, or ownership transfer;
- a general CRM, sales pipeline, internal comments, assignment, or bulk actions;
- file uploads, email attachments, or free-form HTML;
- requester accounts for tracking request status;
- rejection emails or marketing campaigns;
- creating additional `platform_admin` accounts from this workflow.

## 4. Target public experience

### 4.1 Language and entry points

Use **Solicitar uma conta** consistently. Avoid **Criar conta** because the
visitor is requesting review, not creating an immediately usable identity.

- **Login:** rename the existing tab to **Solicitar uma conta** and retain the
  form inside the authentication card.
- **Landing header:** keep **Entrar** and add a secondary **Solicitar uma conta**
  action.
- **Landing hero and final CTA:** show the request action alongside the login
  action where layout permits. On small screens, stack the actions with the
  request as the primary acquisition action.
- **Direct route:** add `/solicitar-conta` so landing links, support messages,
  and future campaigns have a stable destination.

The login view and `/solicitar-conta` render one shared `AccountRequestForm`
component. They must not maintain separate validation or submission logic.

### 4.2 Request form

Keep the first release intentionally short:

| Field | Required | Rule |
|---|---:|---|
| Nome profissional ou da operação | yes | Trimmed, 2–255 characters; becomes the proposed tenant name. |
| Email | yes | Canonicalized and validated by the backend; maximum 255 characters. |
| WhatsApp da operação | yes | *(2026-09-04 amendment)* Canonicalized to E.164 by `normalize_mobile_phone` (Brazil default). Stored on the request; copied to `Professional.assistant_phone` at approval. |
| Mensagem | no | Plain text, trimmed, maximum 1,000 characters. |

Do not ask for a password, role, plan, tenant status, WhatsApp Business API
credentials, or payment data. The WhatsApp field added on 2026-09-04 is the
operation's plain phone number, not a provider credential. Tenant timezone is
selected by the admin during approval and defaults to `America/Sao_Paulo`.

Submit optimistically only as far as disabling the form against accidental
double-clicks; request creation is not a safe case for displaying success before
the server accepts it. After a `202 Accepted` response, replace the form with:

> Solicitação recebida. Se os dados estiverem corretos, nossa equipe entrará em
> contato ou enviará as instruções de acesso.

The public response must remain generic for new, duplicate, and already-owned
emails. This prevents the endpoint from becoming an account-enumeration tool.
Validation errors for malformed fields may remain specific because they reveal
only input supplied in the same request.

### 4.3 Duplicate and repeat submissions

- Permit at most one `pending` request per canonical email, enforced by a
  partial unique database index.
- Repeating a pending request returns the same `202` response and does not add a
  second admin-row or send email.
- An email already present in `users` also receives the generic public `202`
  response and creates no request. The UI may point generally to **Entrar** and
  **Esqueci minha senha**, but must not disclose that the email has an account.
- A previously rejected email may submit a new request after the configured
  rate-limit window. The rejected decision remains terminal, subject to the
  documented PII-retention policy.
- Rate-limit by canonical-email digest and source-IP digest. Suggested initial
  configuration: 3 submissions per email per 24 hours and 20 per source IP per
  hour, externalized in `.env`.

## 5. Target platform-admin experience

### 5.1 Navigation and request inbox

Add **Solicitações** to the platform-admin header, with a small badge containing
the pending count. The badge is informational and capped visually at `99+`.

The `/admin/account-requests` screen contains:

- tabs or filters for **Pendentes**, **Aprovadas**, and **Rejeitadas**;
- newest-first results with server-side pagination, 20 rows per page;
- requester/operation name, email, submitted timestamp, status, and reviewer;
- a detail panel for the optional message and decision history; and
- an empty state appropriate to the selected filter.

The backend provides both the paginated result and total/pending counts. The
frontend must not download all requests to calculate badges or pages.

### 5.2 Approval

The **Aprovar e criar tenant** action opens a confirmation dialog prefilled
with:

| Field | Editable | Source/default |
|---|---:|---|
| Tenant name | yes | Request's normalized name. |
| Owner email | no | Request's canonical email. |
| Timezone | yes | `America/Sao_Paulo`, using the existing supported list. |

The dialog states that approval will create the tenant and email a password
setup link. On confirmation, disable decision controls for that request until
the response arrives. On success, update the row immediately to **Aprovada**,
decrement the pending badge, and show links to **Ver tenant** and the tenant
grid. Reconcile those optimistic changes with the response and restore the row
if the request fails.

If the email became unavailable after the request was submitted, return a
stable conflict and keep the request pending. The admin can then reject it; the
system must never create a tenant under a different email implicitly.

### 5.3 Rejection

The **Rejeitar** action requests an optional internal reason of at most 500
characters and records the reviewing admin and timestamp. Rejection creates no
tenant, user, token, or email delivery. It is reversible only by a new public
request in v0.1; there is no reopen action.

### 5.4 Activation delivery visibility

For approved requests, show the linked owner's activation state and latest
delivery state: **na fila**, **processando**, **aguardando nova tentativa**,
**enviado**, **falhou**, **suprimido**, or **conta ativada**. Do not expose SMTP
error details or tokens in the browser.

When the owner is still `pending_activation` and no delivery is active, provide
an admin-only **Reenviar ativação** action. It queues a fresh delivery through
`enqueue_auth_email`, is rate-limited, audit-recorded, and never invokes SMTP in
the HTTP request. It must be unavailable once the account is active.

## 6. Data model and migration

Add an `account_access_requests` table:

| Column | Type / constraint | Purpose |
|---|---|---|
| `id` | UUID primary key | Stable request identity. |
| `proposed_tenant_name` | varchar(255), required | Requester's proposed operation/instructor name. |
| `email` | varchar(255), required | Canonical email needed for review and provisioning. |
| `whatsapp` | varchar(20), nullable *(added 2026-09-04, migration `d4e5f6a7b8c9`)* | Canonical E.164 number for the operation. Nullable for pre-amendment rows; required by the public API. |
| `message` | text, nullable | Plain-text context, maximum enforced at the API boundary. |
| `status` | varchar(20), check | `pending`, `approved`, or `rejected`. |
| `submitted_at` | timezone-aware timestamp | Queue ordering and response-time reporting. |
| `reviewed_at` | timezone-aware timestamp, nullable | When a terminal decision was committed. |
| `reviewed_by_user_id` | nullable FK to `users`, `RESTRICT` | Platform admin responsible for the decision. |
| `decision_reason` | varchar(500), nullable | Internal rejection context. |
| `professional_id` | nullable FK to `professionals`, `RESTRICT` | Tenant created by approval. |
| `owner_user_id` | nullable FK to `users`, `RESTRICT` | Initial owner created by approval. |
| `created_at`, `updated_at` | timezone-aware timestamps | Standard persistence metadata. |

Database invariants:

- a partial unique index permits only one `pending` row per canonical email;
- `pending` rows have no reviewer, review time, tenant, or owner;
- `approved` rows require reviewer, review time, tenant, and owner;
- `rejected` rows require reviewer and review time and have no tenant or owner;
- indexes support `(status, submitted_at DESC, id)` pagination and linked-tenant
  lookup; and
- application validation remains necessary, but database constraints are the
  final authority under concurrent requests.

Register the model in `app/models/__init__.py` and create one forward Alembic
migration. Do not retrofit this workflow into `users`, `professionals`, or
`email_deliveries`: a request is a pre-account business record with a distinct
lifecycle.

### Audit and privacy

The request row stores the email because approval genuinely needs it. Do not
copy the raw address, message, token, or SMTP detail into general logs or
operational-event payloads.

- Submission and decision events use `AuthSecurityEvent` with email/IP digests.
- `reviewed_by_user_id` and `reviewed_at` provide durable decision
  accountability.
- Once approved, the existing tenant-created and account-activation audit events
  remain authoritative for the resulting tenant and user.
- Request-list APIs are `platform_admin` only; ordinary tenant-professional
  sessions cannot see prospective-user data, and impersonation never grants
  that permission to the tenant's users.
- Define `ACCOUNT_REQUEST_REJECTED_RETENTION_DAYS` (initially 180) and add a
  maintenance task that deletes or anonymizes expired rejected-request PII while
  preserving non-identifying audit evidence. Approved records follow the tenant
  account's retention policy.

## 7. API contracts

All expected failures use the existing `{ "error": { "code", "message" } }`
shape and stable codes from `error_codes.py`.

### 7.1 Public submission

```http
POST /api/account-requests
Content-Type: application/json

{
  "proposed_tenant_name": "João Silva",
  "email": "joao@example.com",
  "whatsapp": "11987654321",
  "message": "Dou aulas em São Paulo e quero conhecer a plataforma."
}
```

`whatsapp` is required *(2026-09-04 amendment)* and returns `422` `INVALID_PHONE`
when it is not a valid mobile number.

Return `202 Accepted` for a newly persisted request, an existing pending
request, and an email that already owns an account:

```json
{
  "message": "Solicitação recebida. Nossa equipe analisará os dados informados."
}
```

Return `422` only for malformed fields and `429` for exceeded public quotas.
The body never returns request IDs, user IDs, tenant IDs, account existence, or
queue position.

This is the only intentionally anonymous endpoint in this roadmap. Its route
must explicitly document that choice and apply input bounds, canonicalization,
database-backed rate limits, the global write burst guard, CORS policy, and safe
logging. CAPTCHA is not required initially; add a provider-neutral challenge
only if measured abuse exceeds the configured controls.

### 7.2 Admin list and counts

```http
GET /api/admin/account-requests?status=pending&page=1&page_size=20
```

```json
{
  "requests": [
    {
      "id": "...",
      "proposed_tenant_name": "João Silva",
      "email": "joao@example.com",
      "message": "...",
      "status": "pending",
      "submitted_at": "2026-09-03T18:00:00Z",
      "reviewed_at": null,
      "reviewer_email": null,
      "professional_id": null,
      "owner_user_id": null,
      "activation_state": null
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1,
  "total_pages": 1,
  "status_counts": {
    "pending": 1,
    "approved": 0,
    "rejected": 0
  }
}
```

Allow only the three known statuses; default to `pending`; bound `page_size` to
10–50. Sort by `submitted_at DESC, id DESC`. Fetch reviewer and activation
summary only for IDs on the current page.

Provide a separate lightweight endpoint for the shared admin-header badge:

```http
GET /api/admin/account-requests/summary
```

```json
{ "pending": 4 }
```

This endpoint performs a count only and does not return request PII.

### 7.3 Approve

```http
POST /api/admin/account-requests/{request_id}/approve
Content-Type: application/json

{
  "tenant_name": "João Silva",
  "whatsapp": "11987654321",
  "timezone": "America/Sao_Paulo"
}
```

Return `200 OK` with the approved request and created tenant summary. Approval
uses the request's stored canonical email; the body cannot supply owner email,
role, status, or user ID. *(2026-09-04 amendment)* `whatsapp` is required and
editable — the dialog pre-fills it from the request and it is re-normalized to
E.164 before `create_tenant_with_owner` writes it to `Professional.assistant_phone`.

The service transaction must:

1. lock the request row with `SELECT ... FOR UPDATE`;
2. return the existing approved result if the same request was already approved
   (idempotent retry);
3. reject a previously rejected request with `409`;
4. revalidate tenant name, timezone, and owner-email availability;
5. call the shared tenant-provisioning behavior to create the active
   `Professional`, pending `User`, activation `EmailDelivery`, and existing
   tenant/auth audit events;
6. mark the request `approved`, link the tenant and owner, and stamp the admin
   and review time; and
7. commit everything once.

Any failure rolls back the request decision, tenant, user, delivery, and audit
writes together. Refactor `create_tenant_with_owner` only enough to accept an
audit source/correlation reference so direct **Novo tenant** creation continues
to work unchanged and approval can identify its originating request. Remove raw
source IP from the tenant operational-event payload while making this change;
the existing `AuthSecurityEvent` digest remains the correct place for source-IP
audit evidence.

### 7.4 Reject

```http
POST /api/admin/account-requests/{request_id}/reject
Content-Type: application/json

{
  "reason": "Fora da área atendida no piloto."
}
```

Return `200 OK` with the rejected request. Lock the row, apply the decision only
from `pending`, and treat the same repeated rejection as idempotent. Attempting
to reject an approved request returns `409`.

### 7.5 Activation resend

```http
POST /api/admin/account-requests/{request_id}/resend-activation
```

Allow only an approved request whose linked owner remains
`pending_activation`. If an active delivery already exists, return that delivery
summary without adding another. Otherwise queue a new activation delivery.
Rate-limit by admin, owner-email digest, and source IP; return only safe delivery
state, never transport details.

## 8. Backend architecture

Keep the implementation flat and focused:

- `app/models/account_access_request.py`: persistence model and status
  constants;
- `app/schemas/account_requests.py`: public/admin request and response schemas;
- `app/api/account_requests.py`: anonymous submission only;
- `app/api/admin_account_requests.py`: platform-admin list, approve, reject, and
  resend endpoints;
- `app/services/account_requests.py`: submission, duplicate handling, row
  locking, decisions, and response summaries; and
- one Alembic migration plus focused service/API tests.

Do not put HTTP parsing in the service or SMTP calls in either router. Do not
duplicate tenant creation: both manual **Novo tenant** and request approval must
reach `create_tenant_with_owner`. Derive the approving admin from the session,
never the request body.

Use configuration keys such as:

```dotenv
ACCOUNT_REQUEST_MAX_PER_EMAIL_PER_DAY=3
ACCOUNT_REQUEST_MAX_PER_IP_PER_HOUR=20
ACCOUNT_REQUEST_APPROVAL_MAX_PER_ADMIN_PER_HOUR=20
ACCOUNT_ACTIVATION_RESEND_COOLDOWN_SECONDS=60
ACCOUNT_REQUEST_REJECTED_RETENTION_DAYS=180
```

Add these with safe development defaults to `.env.example`; production values
belong in the deployment secret/configuration store. No new production
dependency is required.

## 9. Frontend architecture and behavior

### Shared public form

Extract `components/auth/account-request-form.tsx` from the current login-page
request markup. The component owns field values, client validation, submit
state, generic success, and retryable error display. Its parent controls only
layout and the route back to login.

Use it in:

- the renamed **Solicitar uma conta** login view; and
- `app/solicitar-conta/page.tsx`, using the existing authentication visual
  language and a clear **Já tenho uma conta** link.

The form posts through one typed helper in `lib/auth.ts` or a focused
`lib/account-requests.ts`. It never uses `mailto:`, stores the form in browser
storage, or includes the email in the URL.

### Landing page

Add a dedicated `LandingRequestCta` that points to `/solicitar-conta`. Keep
`LandingEnterCta` responsible only for login/return-to-app behavior. The request
CTA appears in the header, hero, and final conversion section with responsive
styling in `landing.css`.

Use the exact label **Solicitar uma conta**. Supporting copy should set the
expectation that access is reviewed by the team; avoid “comece agora”, “crie sua
conta”, or language implying immediate activation.

### Admin workspace

Add `app/admin/account-requests/page.tsx` and typed API/result models. At the
third admin surface, extract the repeated session-aware navigation into a small
`PlatformAdminHeader` shared by tenant selection, scheduled tasks, and account
requests. It shows the signed-in admin, **Tenants**, **Solicitações**, **Tarefas
agendadas**, and **Sair** without changing impersonation rules.

For approve/reject, reflect the expected row status and badge count immediately,
then reconcile with the server result. On failure, restore the previous row and
count and display a safe actionable error. Opening dialogs and submitting the
public form are not optimistically considered successful before their server
responses.

All controls must be keyboard reachable; dialogs restore focus; status is not
communicated by color alone; submission/decision messages use appropriate live
regions; tables collapse into labeled cards on small screens.

## 10. Incremental implementation plan

> **All phases delivered (2026-09-03).** Per-phase notes below record what
> landed; see `docs/pages/solicitar_conta.md` for the behavior contract.

### Phase 0 — Lock the contracts — done

> `app/models/account_access_request.py` (status constants),
> `app/schemas/account_requests.py`, eight codes in `error_codes.py`, migration
> `c8f1a2b3d4e5` (single Alembic head, upgrade/downgrade verified locally), and
> `backend/tests/test_account_requests.py` (11 cases).

1. Add model/status constants, schemas, stable error codes, and service
   signatures.
2. Write failing backend integration tests for anonymous submit, admin list,
   approval, rejection, and resend.
3. Create and inspect the Alembic migration, including partial unique and status
   consistency constraints.

**Verify:** migration upgrade/downgrade passes locally; tests demonstrate the
old application lacks each contract; Alembic reports one head.

### Phase 1 — Persist safe public requests — done

> `submit_account_request` in `app/services/account_requests.py`:
> `normalize_email` canonicalization, generic duplicate / existing-user path,
> partial-unique race caught to the same `202`, per-email + per-IP DB limits,
> `account_request_submitted` `AuthSecurityEvent` with digests only.
> `POST /api/account-requests` registered as an anonymous route in `main.py`.

1. Implement canonicalized validation and generic duplicate/account-exists
   behavior.
2. Apply database-backed per-email and per-IP limits and redacted security
   events.
3. Register `POST /api/account-requests` as an explicitly anonymous route.

**Verify:** a valid request creates one pending row; concurrent/repeated submits
do not duplicate it; known and unknown emails receive indistinguishable success;
malformed and rate-limited inputs follow the documented contract; logs contain
no raw email or message.

### Phase 2 — Replace the public `mailto:` experience — done

> `components/auth/account-request-form.tsx` (shared), rendered by the renamed
> **Solicitar uma conta** login view and `app/solicitar-conta/page.tsx`;
> `components/landing/landing-request-cta.tsx` in the landing header, hero, and
> final CTA. `mailto:` removed. `tsc` and `eslint` clean. Browser coverage:
> `frontend/e2e/account-request.spec.ts` + `playwright.config.ts`
> (`npm run test:e2e`).

1. Extract the shared request form and connect it to the public API.
2. Rename the login view to **Solicitar uma conta**.
3. Add `/solicitar-conta` and the landing-page request CTAs.
4. Validate mobile layout, focus flow, loading state, and generic success copy.

**Verify:** login and every landing CTA reach the same behavior; one submission
appears once in the database; no local email client opens; lint, type-check, and
production build pass.

### Phase 3 — Admin request inbox — done

> `get_account_request_page` + `GET /api/admin/account-requests`, `/summary`,
> `/metrics` in `app/api/admin_account_requests.py`;
> `components/admin/platform-admin-header.tsx` (pending badge, `99+` cap) now
> shared by tenant selection, scheduled tasks, and account requests;
> `app/admin/account-requests/page.tsx` (filters, pagination, detail, dialogs).

1. Add paginated list/count service and admin-only endpoint.
2. Extract the shared platform-admin header and pending-count badge.
3. Build request filters, responsive rows/cards, detail panel, empty/error
   states, and pagination.

**Verify:** platform admins can see bounded results and accurate counts; tenant
professionals and unauthenticated callers receive 403/401; page/filter races do
not render stale responses.

### Phase 4 — Atomic decisions and provisioning — done

> `approve_account_request` (`SELECT ... FOR UPDATE`, idempotent approved retry,
> `409` on rejected) calls `create_tenant_with_owner(..., audit_source=
> "account_request_approval", account_request_id=...)`; raw source IP dropped
> from the `tenant.created` payload (digest kept; IP audit stays in
> `AuthSecurityEvent`). `reject_account_request` stamps reviewer/time/reason.
> Approve/reject dialogs reconcile optimistically. **Novo tenant** unchanged.

1. Implement row-locked approval using the existing tenant-provisioning service.
2. Implement rejection with reviewer/time/reason audit fields.
3. Build confirmation dialogs and optimistic reconciliation.
4. Preserve the direct **Novo tenant** route and behavior.

**Verify:** approval produces exactly one tenant, one pending owner, one active
activation delivery, and one approved request; all share the correct links and
audit context. Forced errors leave no partial records. Two admins deciding the
same request cannot produce two tenants or overwrite a terminal decision.

### Phase 5 — Activation delivery operations — done

> `build_account_request_items` reports the safe `activation_state`;
> `resend_account_activation` + `POST /api/admin/account-requests/{id}/
> resend-activation` — approved + `pending_activation` only, returns an existing
> active delivery instead of a second, cooldown +
> per-owner/per-admin limits, `enqueue_auth_email` (never SMTP in-request).

1. Add safe activation-state summaries to approved request results.
2. Add the guarded resend service/endpoint and admin action.
3. Reuse the email worker's deduplication, retries, and token supersession.

**Verify:** resend never creates simultaneous active deliveries; failed or
suppressed delivery can be requeued after correction; active users cannot
receive activation links; no raw token or SMTP diagnostic reaches the UI.

### Phase 6 — Retention, observability, and release — done

> `purge_rejected_account_requests` + `scripts/purge_account_requests.py`
> (`ACCOUNT_REQUEST_REJECTED_RETENTION_DAYS`, default 180);
> `get_account_request_operational_metrics` + `/metrics` +
> `scripts/account_request_metrics.py`; page doc `docs/pages/solicitar_conta.md`,
> `docs/auth_email_configuration.md` "Activation email sources", README link.
> All six config keys in `.env.example`. Local Alembic head verified; no remote
> DB change performed.
>
> Follow-up (not blocking): the metrics helper emits pending/approved/rejected
> counts, oldest-pending age, and pending-over-24h, but not dedicated
> approval-conflict or activation-failure counters.

1. Add the rejected-request PII retention task and document its operation.
2. Add counts for submissions, pending age, decisions, approval conflicts, and
   activation-delivery failures without PII labels.
3. Update page documentation, auth/email operations documentation, and README.
4. Run the release matrix locally before any separately approved remote
   migration or deployment.

**Verify:** expired rejected PII follows policy; operators can identify an aging
queue or failed onboarding email; backups and migration rollback are rehearsed;
no remote database mutation occurs as part of local development.

## 11. Test and acceptance matrix

Automated coverage lives in `backend/tests/test_account_requests.py` (11 cases:
submission/canonicalization, generic-for-duplicate-and-existing-user, admin
auth 401/403, atomic approval + idempotent retry + no `source_ip` in payload,
rejection without provisioning + idempotent, resend requeue, per-email
rate-limit boundary, malformed email `422`, previously-rejected resubmit,
two-admin terminal-state conflict, retention purge) and
`frontend/e2e/account-request.spec.ts` (shared form on both surfaces, no
`mailto:`, stubbed success/error, landing CTA destinations). Rows not yet
automated — forced rollback at each write boundary, true concurrent duplicate
inserts, listing stale-response race, accessible-dialog assertions — remain on
the manual journey below.

| Area | Required coverage |
|---|---|
| Submission | Valid request; whitespace/case canonicalization; invalid name/email/message; repeated pending request; existing user; previously rejected email; concurrent duplicate inserts. |
| Privacy | Identical successful public response for new, duplicate, and account-owned email; no raw PII/token in general logs or audit metadata. |
| Abuse | Independent email/IP limits; boundary and reset-window behavior; global write limiter compatibility. |
| Authorization | Public can submit only; unauthenticated and professional users cannot list or decide; platform admin succeeds outside tenant impersonation context. |
| Listing | Status filter; deterministic newest-first pagination; bounded page size; counts; empty pages; stale frontend response protection. |
| Approval | Happy path; invalid corrected name/timezone; email conflict; already approved retry; rejected conflict; forced rollback at each write boundary; two-admin race. |
| Rejection | Happy path; optional reason bounds; repeated rejection; approved conflict; no tenant/user/delivery side effects. |
| Activation | Delivery queued on approval; worker send; password setup; activation token one-time use; resend deduplication/rate limit; no resend after activation. |
| Regression | Direct **Novo tenant**, login, reset password, tenant pagination/lifecycle, impersonation, CSRF, and tenant isolation remain green. |
| Frontend | Shared-form behavior from both surfaces; CTA destinations; accessible dialogs/status; optimistic rollback; mobile cards; lint, TypeScript, and production build. |

Backend service and API behavior belongs in the existing pytest suite under the
`agenda` conda environment. Browser interactions need automated coverage; if no
frontend browser-test harness exists when implementation starts, add one pinned
test-only tool (prefer Playwright) rather than treating manual clicking as the
only regression protection.

Manual acceptance journey:

1. From the landing page, open **Solicitar uma conta**, submit a fresh address,
   and see the generic confirmation.
2. Log in as platform admin, observe the pending badge, and open the request.
3. Approve after reviewing tenant name and timezone.
4. Confirm one new tenant tile, one pending owner, and a queued/sent activation
   delivery.
5. Open the email link, set a password, and log in as that owner.
6. Confirm the session is tenant-scoped and cannot access admin request APIs.
7. Repeat the public submission with the active email and confirm the public
   response does not reveal account existence or create another row.

## 12. Security review

- **Broken access control:** every list/decision/resend route requires
  `require_platform_admin`; the public route can only create a pending request.
- **Tenant isolation:** approval derives owner role and tenant linkage on the
  server. No public/admin body can choose `professional_id`, `user_id`, role, or
  status.
- **Injection/XSS:** use Pydantic bounds, ORM parameters, and normal React text
  rendering. Messages remain plain text and are never rendered as HTML.
- **Account enumeration:** generic `202` response and body for duplicate,
  existing-user, and new email paths; no public status endpoint.
- **Spam/resource exhaustion:** durable email/IP quotas, partial uniqueness,
  bounded message lengths, global write throttling, and no email on submission.
- **CSRF:** admin writes use existing cookie/CSRF protection. Anonymous
  submission has no authenticated authority to exploit and is protected through
  rate limiting and origin/CORS deployment policy.
- **Race conditions:** database uniqueness and row locks are authoritative;
  frontend disabled states are convenience only.
- **Sensitive data exposure:** admin-only PII, no token/SMTP details in response,
  no raw request data in general logs, and explicit retention.
- **Auditability:** decision row records actor/time; security events record
  digests/source; tenant creation and activation retain existing audit records.

## 13. Operational metrics and alerts

Track aggregate, non-PII metrics:

- requests submitted, deduplicated, approved, and rejected;
- current pending count and age of oldest pending request;
- approval conflicts and failed approval transactions;
- time from submission to decision and decision to activation;
- activation deliveries queued, retrying, failed/suppressed, and sent; and
- approved owners still pending activation after 24 hours.

Suggested alerts: oldest pending request exceeds two business days; any
activation delivery reaches terminal failure; or approved-but-not-activated
count grows unexpectedly. SMTP health remains part of the existing authentication
email runbook.

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Public form becomes a spam sink | No submission email, strict input bounds, durable email/IP limits, generic response, and CAPTCHA only when evidence supports it. |
| Duplicate requests create duplicate tenants | Partial unique pending-email index, approval row lock, global user-email uniqueness, and idempotent approval. |
| Two admins make conflicting decisions | Terminal state guards under `SELECT ... FOR UPDATE`; loser receives the committed result/conflict. |
| Email outage leaves an approved owner waiting | Durable outbox retries, visible safe delivery state, admin resend, and queue alerts. |
| Request message exposes unneeded personal data | Short plain-text field, admin-only access, warning copy, redacted logs, and retention policy. |
| “Approve” is mistaken for immediate access | Confirmation copy explicitly says it queues setup instructions; activation and normal login remain required. |
| Roadmap drifts into full self-service | Keep billing, automated provisioning, multi-user invitations, and automatic approval in separately approved work. |

## 15. Definition of done

Met as of 2026-09-03:

- [x] **Solicitar uma conta** replaces **Criar conta** and no public request path
  launches an email client;
- [x] login and landing entry points use one request form and one API;
- [x] public submissions are validated, persisted, duplicate-safe, rate-limited,
  generic, and visible only to platform admins;
- [x] the admin inbox is navigable, paginated, filterable, responsive, and shows a
  reliable pending count;
- [x] approval atomically creates exactly one tenant, pending owner, activation
  delivery, and linked approved request;
- [x] rejection is auditable and has no provisioning side effects;
- [x] activation delivery state and safe resend are operable from the admin screen;
- [x] the owner can activate, choose a password, and log in with the requested email
  (existing activation lifecycle, unchanged);
- [x] automated backend and browser coverage plus the related regression suite
  pass (`test_account_requests.py` 11/11, `frontend/e2e` 5/5; unrelated
  `test_makeup_credits` / `test_passive_escalation` failures pre-date this work);
- [x] documentation and local migration/release checks are complete, with remote
  changes requiring a separate explicit authorization.

## 16. Relationship to earlier roadmaps

This roadmap preserves **manual onboarding first** from the authentication and
multi-tenancy roadmaps. It refines “manual” from an off-platform email exchange
into a persisted, admin-reviewed workflow. It reuses the implemented admin
tenant-creation and activation lifecycle rather than introducing a second
provisioning path.

It does not implement multi-tenancy roadmap Phase G. A visitor still cannot
self-create an active tenant, pay, provision WhatsApp, or bypass admin review.
If full self-service is approved later, the access-request history can remain a
lead/audit record while approval is replaced or complemented by billing and
automated eligibility decisions.

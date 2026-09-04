# Admin Tenant Workspace Roadmap v0.1 — 2026-09-03

> **Status: implemented locally on 2026-09-03.** The platform-admin tenant
> workspace now has logout/navigation, server-side pagination, and atomic
> tenant plus initial-owner provisioning through the activation-email outbox.

## Purpose

Make the platform-admin tenant selection screen a complete and escapable
workspace: an administrator can leave the screen, create a tenant with its
initial login, and navigate a growing tenant population without loading an
unbounded tile grid.

This roadmap covers only `/admin/select-tenant`, its platform-admin API
contract, and the creation flow it requires. It deliberately preserves the
existing tenant lifecycle, impersonation behavior, and email-activation
delivery path.

## Confirmed problems

1. The tenant tile screen has no visible logout action. A platform admin who
   does not intend to impersonate a tenant has no clear exit.
2. The empty state directs administrators to `scripts/create_user.py`, but the
   admin UI cannot create a `Professional` tenant or its first user. The
   current script also requires a pre-existing professional UUID.
3. `GET /api/admin/tenants` returns every matching tenant and the frontend
   renders every tile. This is not suitable for a tenant count that grows over
   time.

## Scope and decisions

### In scope

- A platform-admin header with logout and a clear route back to the tenant
  grid from admin subpages.
- A platform-admin-only create-tenant flow that creates one active tenant and
  one pending-activation professional user atomically.
- Server-side, page-number pagination for tenant tiles, with archived tenants
  remaining an explicit, separate view.
- Auditing, tenant isolation, CSRF, validation, API tests, and UI tests for
  each state-changing path.

### Explicitly out of scope

- Self-service public sign-up, billing, invitations for multiple users, hard
  deletion, and tenant migration/import.
- Configuring WhatsApp, scheduled tasks, pricing, or assistant rules during
  creation. Those remain tenant configuration tasks after activation.
- Changing the existing suspend/archive/restore semantics or the email
  transport/outbox.

### Product decisions

- **One initial owner:** creation collects a tenant name and the initial
  professional user's email. The user receives the established activation
  email and chooses a password; no password is collected or logged by admin.
- **Active on creation:** the `Professional` row starts `active` and the user
  starts `pending_activation`. This makes the tenant visible to admins while
  preventing user login until activation.
- **Paginated archived inclusion:** active/suspended tenants are the default
  result. The existing archived toggle keeps its current meaning—include
  archived tenants alongside the normal result—and resets to page one.
- **Stable ordering:** results are ordered case-insensitively by tenant name,
  then UUID, so a tile cannot move ambiguously between pagination requests.

## Existing foundations to reuse

| Need | Existing component | Reuse approach |
|---|---|---|
| Admin authorization | `require_platform_admin` | Require it on every new endpoint; never accept a role from the request body. |
| Tenant lifecycle | `Professional.status`, `tenant_lifecycle` service | Create only an `active` tenant and retain current archive/restore controls. |
| User activation | `enqueue_auth_email`, auth token/outbox worker | Queue the normal `account_activation` mail within the successful transaction. |
| Email validation | `normalize_email` | Canonicalize and validate the initial owner email before persistence. |
| Security/audit | `record_auth_event`, `record_event` | Record tenant creation without logging raw activation tokens or SMTP secrets. |
| State-change protection | Existing CSRF middleware | Use the frontend `apiRequest`/CSRF helper for creation and logout. |
| Optimistic lifecycle UX | `handleLifecycleAction` | Keep the existing optimistic pattern for archive/restore; use a clear submitting state for creation to prevent duplicate submissions. |

## Success criteria

- A platform admin can always log out from the tenant grid and reaches
  `/login` with the session cookie cleared.
- A platform admin can create a valid tenant plus initial professional user in
  the UI; the user receives one activation email and can activate then log in.
- A failed create leaves no orphan `Professional`, `User`, activation token, or
  email-delivery row.
- The tenant grid fetches a bounded page and shows deterministic previous/next
  navigation, total count, and an accessible empty state.
- The archive toggle keeps its current meaning and never causes an archived
  tenant to appear in the default active view.
- Existing tenant lifecycle, authentication-email, and tenant-isolation tests
  remain green.

## Target experience

### Admin header and logout

The `/admin/select-tenant` header has three clear actions: **Novo tenant**,
**Tarefas agendadas**, and an account menu containing the signed-in admin email
and **Sair**. Logout calls the existing auth logout function, clears the local
session view, and routes to `/login`. The account menu must be keyboard
operable and have an accessible label.

`/admin/scheduled-tasks` receives the same lightweight header or an explicit
**Voltar para tenants** control. This prevents an admin subpage becoming a
second navigation dead end. Tenant impersonation remains a separate, explicit
tile action; it must not be triggered by opening the create dialog or changing
pages.

### Create tenant

The **Novo tenant** button opens a focused dialog rather than a separate
route. It contains only:

| Field | Required | Validation / default |
|---|---:|---|
| Tenant name | yes | Trimmed, 2–255 characters, not blank. |
| Initial owner email | yes | Canonical email validation via the existing service. |
| Time zone | yes | Defaults to `America/Sao_Paulo`; choose only from an approved IANA list. |

The confirmation copy says that a tenant will be created and an activation
email sent. On submit, disable only the submit/cancel controls to prevent
double creation; do not show a fake success before the server commits.
On success, close the dialog, show a concise confirmation, reset the default
tenant page to one, refetch it, and highlight the new tile if it is on that
page. If alphabetical ordering puts it on another page, provide a link to
search/filter only once that capability is explicitly approved; it is not part
of this initial scope.

The dialog never asks for a password, WhatsApp number, commercial-financial
module choice, tenant impersonation, or life-cycle reason. These are either
security-sensitive or follow-up configuration concerns.

### Paginated tile grid

The grid keeps the current responsive 1/2/3-column tile layout. Above or below
the tiles, show:

- `X–Y de Z tenants`;
- previous and next buttons, disabled at their boundaries;
- a compact current-page indicator; and
- the existing archived inclusion toggle, which resets the page to one.

The initial page size is **12** (a practical four rows on the desktop grid).
The backend accepts only a bounded range of 6–48 and defaults to 12. There is
no page-size picker in this iteration. A new request replaces the current page
only when its response corresponds to the current filter/page state, so a slow
prior response cannot overwrite a later navigation action.

Archived tiles retain their status badge and lifecycle restore action. An empty
first page distinguishes `Nenhum tenant cadastrado` from `Nenhum tenant neste
filtro`; a requested page past the final page is normalized by the client to
the final available page after a refetch rather than leaving a blank grid.

## API and persistence design

### Read contract

Replace the unbounded response with a backward-compatible versioned shape on
the same endpoint:

```http
GET /api/admin/tenants?page=1&page_size=12&include_archived=false
```

```json
{
  "tenants": ["...TenantSummary"],
  "page": 1,
  "page_size": 12,
  "total": 42,
  "total_pages": 4
}
```

`page` is at least 1, `page_size` is 6–48, and `total_pages` is 0 only when
`total` is zero. `include_archived=false` continues to exclude only
`archived`; suspended tenants remain visible. Query the count and current page
after the status filter. Apply the deterministic `lower(name), id` ordering
before `LIMIT/OFFSET`.

Do not build counts, task summaries, or feature sets for every tenant and then
slice in Python. First obtain the bounded tenant page, then fetch/aggregate
only related data for those IDs. This preserves current `TenantSummary` fields
without turning pagination into a cosmetic frontend-only optimization.

### Create contract

Add a platform-admin-gated endpoint:

```http
POST /api/admin/tenants
Content-Type: application/json

{
  "name": "João Silva",
  "owner_email": "joao@example.com",
  "timezone": "America/Sao_Paulo"
}
```

It returns `201 Created` with a minimal creation response containing the new
tenant summary and `owner_email`; it never returns an activation token, raw
SMTP result, password, or mail secret. The route must use the project's
standard `{ data, error }` error envelope for expected errors, consistent with
the project’s existing response pattern.

Within one database transaction, the service must:

1. normalize and validate `owner_email`;
2. reject an email already held by any `User` with a stable project error code;
3. validate the allowed timezone and normalized tenant name;
4. create an active `Professional` with the established defaults;
5. create a `professional`-role `User` in `pending_activation` state, bound to
   that professional;
6. enqueue the normal `account_activation` delivery; and
7. append tenant-creation and activation-queued audit records before commit.

If any step fails, roll back the full transaction. This prevents a tenant with
no owner or a user pointing to an incomplete tenant. The route must not invoke
SMTP directly; the email worker retains ownership of delivery and retry.

The implementation should add any required stable duplicate-email/invalid-timezone
codes to `backend/app/core/error_codes.py`, and use
`error_response` rather than ad-hoc client strings. A database uniqueness
constraint is the final authority for `users.email`; handle a concurrent
unique-violation as the same safe duplicate-email response.

### Data migration

No database schema migration is expected: `professionals` and `users` already
contain the necessary fields, the owner-user relationship is enforced by a
database check constraint, and the email outbox already supports activation.
Confirm this with an Alembic autogenerate review; only create a migration if
the chosen timezone allowlist or audit event taxonomy actually needs stored
data.

## Implementation phases

### Phase 0 — Establish the contracts

**Goal:** make the desired behavior testable before changing the UI.

1. Add paginated request/response schemas and creation request/response
   schemas in `backend/app/schemas/api.py`.
2. Add only the new stable error codes that the create route needs; reuse
   `INVALID_EMAIL`, `RATE_LIMITED`, and the existing CSRF/auth codes where
   applicable.
3. Extract a small admin tenant-creation service responsible for validation,
   row creation, outbox enqueueing, and audit writes. It receives an already
   authorized admin identity; it does not parse HTTP input.
4. Write service and endpoint tests for the contracts below.

**Verify:** contract tests fail against the old unbounded list and missing
create route, then pass without needing a browser.

### Phase 1 — Paginate the backend

**Goal:** bound tenant-list work and make result ordering reliable.

1. Add `page` and `page_size` query parameters to `list_tenants`.
2. Apply the lifecycle filter, calculate the filtered total, and select the
   page of `Professional` IDs in deterministic order.
3. Reuse/refactor the current tile-summary assembly to query only page IDs.
4. Return the metadata contract above and update its OpenAPI description.
5. Preserve `include_archived` behavior and platform-admin authorization.

**Verify:** a fixture with 25+ tenants produces page boundaries with no
duplicates or omissions, and a suspended tenant remains in the default result
while an archived one does not.

### Phase 2 — Complete navigation and paginated tiles

**Goal:** make the platform-admin workspace navigable without altering tenant
operations.

1. Update `fetchTenants` types and query construction in `frontend/src/lib/api.ts`.
2. Replace the tile screen's plain array state with page/filter/result state.
3. Add the pager, range text, filter-reset behavior, and stale-response guard.
4. Add the header account/logout control using the existing `logout` helper.
5. Add a visible return-to-tenant-grid control on the scheduled-task admin
   page.
6. Preserve current lifecycle optimistic updates. When an archive action
   removes the final tile on a non-first page, reload the preceding valid page.

**Verify:** browser checks cover logout, back navigation, initial/last page,
archived inclusion, archive from a page boundary, and mobile-width layout.

### Phase 3 — Implement atomic tenant creation

**Goal:** let a platform admin provision a tenant safely from the grid.

1. Implement the create service and `POST /api/admin/tenants` endpoint.
2. Use an IANA timezone allowlist from an existing standard-library or current
   project facility; do not add a dependency merely for a three-field form.
3. Record the actor admin ID, tenant ID, correlation ID, source channel, and
   non-sensitive name/email digest in audit data. Do not persist or log
   activation links, raw email content, credentials, or passwords.
4. Add a `Novo tenant` dialog and its API helper.
5. On successful response, update/refetch the first page and display the
   pending-activation state in an appropriate tile detail if the response is
   visible. Do not automatically impersonate the new tenant.
6. On API failure, keep entered values, render the safe returned error, and
   make no optimistic tile insertion.

**Verify:** a real local test email can activate the created account; duplicate
email and forced outbox failures leave no orphan data.

### Phase 4 — Documentation and release

**Goal:** make the workflow supportable rather than script-dependent.

1. Update the admin tenant lifecycle page with the create flow, pagination,
and archived-toggle behavior.
2. Update `README.md` links and replace the tenant-grid empty-state reference
to manual script-only onboarding.
3. Keep `scripts/create_user.py` for controlled operations; clarify that it
provisions an additional user for an existing tenant, while admin creation
provisions the initial tenant/owner pair.
4. Run the focused tests, the affected frontend lint/type check, and the
appropriate regression suite in the `agenda` conda environment.
5. Test locally before any remote migration or data action. This roadmap does
not authorize remote database changes.

**Verify:** the deployment runbook can create, activate, list, archive,
restore, and log out of a tenant without shell access.

## Test matrix

| Area | Required behavior tests |
|---|---|
| Authorization | Unauthenticated requests return 401; a professional user cannot list or create tenants; only `platform_admin` succeeds. |
| Pagination | Defaults, min/max validation, metadata math, stable sorting, final partial page, empty collection, archived inclusion, and no global related-data load. |
| Tenant creation | Valid creation produces one active tenant, one pending professional user, one queued activation delivery, and audit records. |
| Validation | Blank/oversized names, malformed/canonicalized emails, duplicate emails, invalid timezones, missing CSRF, and concurrent duplicate-email requests. |
| Transactionality | Simulated failure after each creation stage rolls back all newly created tenant/user/outbox/audit data. |
| Activation | Email worker renders the existing activation link; activation establishes a password; login succeeds after activation and fails before it. |
| Lifecycle interaction | Archived tenants stay absent by default; toggle includes them; restore returns them to active; archiving a final tile repairs pagination state. |
| Logout/navigation | Logout clears the cookie and redirects to login; protected admin routes reject the old session; scheduled-task screen can return to the grid. |
| Accessibility | Dialog focus trap/return, labelled controls, keyboard paging/logout, disabled boundary controls, and status/error announcements. |
| Regression | Existing `test_tenant_lifecycle.py`, `test_auth_email_lifecycle.py`, auth, CSRF, and tenant-isolation suites remain green. |

## Security and operational controls

- Every new read/write endpoint uses `require_platform_admin`; the client UI is
  never treated as the authorization boundary.
- Creation is a state-changing request protected by the existing CSRF policy.
- Validate all request fields with Pydantic, normalize the email server-side,
  and use ORM/parameterized access only.
- Rate-limit tenant creation by authenticated platform-admin identity and
  source IP. Set a conservative configurable limit before production rather
  than allowing a compromised admin session to queue unlimited mail.
- Keep activation delivery in the durable outbox: the `POST` response means
  queued, not inbox-delivered. Monitor failed/expired email deliveries using
  the existing worker/outbox operations.
- Audit creation and lifecycle actions with actor, target, timestamp, and
  source; redact user identifiers as the established audit implementation
  requires.
- Do not return tenant existence details to unauthenticated users. Within the
  platform-admin workspace, a duplicate email can be safely reported as an
  administrative conflict.
- Continue tenant scoping everywhere after impersonation. Creating a tenant
  must not implicitly alter the admin's current impersonation session.

## Rollout and acceptance checklist

1. Create a platform-admin test account and start the API/frontend plus the
   email worker locally.
2. Create a test tenant through the new dialog using a controlled mailbox.
3. Verify the database has exactly the expected tenant, pending owner,
   activation outbox row, and audit events.
4. Receive and complete activation; verify old/absent credentials cannot log
   in and the activated account can.
5. Create more than 12 fixture tenants; verify pagination, stable sorting,
   archive inclusion, restore, and final-page correction.
6. Log out from the tenant grid; verify `/api/auth/me` returns 401 and the UI
   is at `/login`.
7. Validate keyboard-only interaction and a narrow mobile viewport.
8. Run the stated test suites and document the local results before considering
   a remote rollout.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| A partial create leaves an unusable tenant | One transaction around tenant, user, outbox, and audit writes; roll back on any failure. |
| Duplicate clicks/email creates multiple owners | Disable dialog controls while submitting, rate-limit, and rely on the database email uniqueness constraint. |
| Pagination becomes slow despite a small UI page | Count/filter in SQL and load related summaries only for page IDs. |
| A newly created alphabetically distant tenant is not visible | Return its summary and clear success feedback; defer search/filter to a separately approved scope. |
| A logout control accidentally loses an impersonation context | It intentionally ends the authenticated session; label it clearly and test the redirect/cookie behavior. |
| Email delivery fails after successful creation | Surface “activation queued,” not “email sent”; expose resend/support work only when it is separately designed. |

## Follow-ups deliberately deferred

- Tenant search, sort selection, filters beyond archived inclusion, and direct
  jump-to-created-tenant.
- Resend activation, cancel pending activation, add/remove additional tenant
  users, or transfer ownership.
- Billing plans, trial expiration, provider connection, and a first-run
  configuration wizard.
- Cursor pagination. Offset pagination is the simpler fit for the initial
  bounded admin grid; revisit once tenant volume or concurrent churn makes it
  insufficient.

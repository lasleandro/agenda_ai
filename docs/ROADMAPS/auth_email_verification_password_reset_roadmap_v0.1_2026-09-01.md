# Authentication, Email Verification, and Password Reset Roadmap v0.1 — 2026-09-01

**Status:** implemented locally on 2026-09-01; remote production rollout remains an operator-controlled release step.

## Implementation status

The activation/reset lifecycle, provider-neutral SMTP outbox, password policy,
frontend routes, session invalidation, local migrations, and focused regression
coverage in this roadmap are implemented. Existing active accounts remain active
for backward compatibility; newly provisioned users are `pending_activation`.
No Azure database was changed. Production still requires the documented GoDaddy
mailbox credentials, DNS authentication, real-mail acceptance test, and an
explicit forward migration rollout.

Local verification completed with Alembic head `a7d8b2e9f401`, 18 focused
authentication/email tests, Python compilation, TypeScript validation, frontend
linting, and a production dependency audit with no reported vulnerabilities.
The wider backend suite currently has six unrelated make-up-credit failures
caused by historical August 2026 fixture dates; the auth coverage is green.

## 1. Goal and success criteria

Prepare Tennis OS authentication for the first production deployment while
preserving the current tenant and platform-admin authorization model. Reuse the
useful parts of HoraH's email-verification and password-reset experience, but do
not copy security-sensitive behavior that can be bypassed or that does not fit
Agenda's architecture.

The work is successful when:

- manually provisioned users receive an activation email, prove control of the
  address, choose their own password, and only then become active;
- a user can request a password reset without revealing whether an account
  exists, use a short-lived single-use link, set an acceptable password, and
  return to the normal login flow;
- email delivery is independent of Zoho/GoDaddy product names and all SMTP,
  sender, link, expiry, and rate-limit settings come from environment variables;
- GoDaddy Professional Email and GoDaddy Microsoft 365 can be selected through
  configuration, without changing application code;
- email addresses are normalized and validated consistently at every boundary;
- weak passwords receive immediate, actionable, accessible feedback, while the
  backend remains the policy authority;
- a password reset or account disablement invalidates existing authenticated
  sessions;
- all new endpoints have rate limits, generic client responses, safe logs,
  audit events, tenant-safe behavior, and automated tests; and
- production acceptance includes real delivery, SPF/DKIM/DMARC, expiration,
  replay, enumeration, and rollback checks.

## 2. Scope decisions and assumptions

This roadmap interprets “email strongness” as both email-address quality and
password strength. Email addresses do not have a useful “strength” score: the
system should validate syntax, canonicalize consistently, and verify
deliverability by proving mailbox control. Passwords do have a strength policy
and need explicit user feedback.

The current product decision remains **manual onboarding first**. Public signup,
payment, WhatsApp-number provisioning, social login, MFA, email-address change,
and account recovery without access to the mailbox remain out of scope. The
existing `platform_admin` and tenant-bound `professional` roles and the rule that
tenant identity comes from the authenticated session remain unchanged.

For the fastest safe production path, activation and reset will use emailed URL
tokens rather than HoraH's six-digit code modal. OWASP identifies URL tokens as
the simplest web reset mechanism; high-entropy links also remove a low-entropy
code-entry endpoint and its brute-force surface. The email and UI presentation
can still reuse HoraH's language, multipart layout, expiry notice, resend states,
and password-match feedback.

## 3. Current Agenda assessment

### What is already sound and should remain

- `backend/app/models/user.py` has real UUID users, explicit roles, tenant
  ownership through `professional_id`, and a database constraint that separates
  global admins from tenant professionals.
- `backend/app/api/dependencies.py` derives tenant context from the signed
  session rather than request input. New auth flows must not alter this boundary.
- Passwords are salted and hashed with bcrypt; login uses an HttpOnly cookie and
  returns the same visible error for an unknown email and a wrong password.
- Admin impersonation is role-checked and audit-logged, and current auth and
  tenant-isolation behavior has integration coverage in
  `backend/tests/test_auth.py` and `backend/tests/test_tenant_isolation.py`.
- The Next.js login page already has a simple branded form and a single generic
  credential error, so activation/reset can extend the same design system rather
  than introduce a second auth application.

### Missing capabilities

- There is no account activation, mailbox confirmation, forgot-password, reset,
  change-password, notification email, or email transport.
- Accounts are created by `scripts/create_user.py`, which accepts a password on
  the command line. That exposes the password to shell history and potentially
  process inspection, and makes an operator choose a credential on the user's
  behalf.
- `User` has no `email_verified_at`, `password_changed_at`, session/auth version,
  or token lifecycle. `status` defaults to active, so there is no pending
  activation state.
- Email is accepted as an unconstrained `str`; it is not trimmed, canonicalized,
  length-bounded, or parsed with `EmailStr`. PostgreSQL uniqueness and login are
  case-sensitive, allowing inconsistent identities such as differently-cased
  copies of the same practical mailbox.
- There is no shared password-policy function. The provisioning script can
  create any password that bcrypt accepts, and there is no frontend strength or
  confirmation feedback.

### Production security gaps adjacent to the requested flows

- Login has no per-account or per-IP throttling. A missing user also skips the
  bcrypt comparison, creating a timing discrepancy despite the generic message.
- The session cookie is HttpOnly and `SameSite=Lax`, but it does not set
  `Secure`; cookie name, session duration, CORS origins, and production cookie
  behavior are not fully externalized. State-changing cookie-authenticated
  requests have no explicit CSRF/Origin defense.
- JWTs have no `iat`, `jti`, issuer, audience, or session version. Authentication
  trusts claims until the fixed 24-hour expiry without checking the current user
  status, so disabling a user or changing a password cannot revoke an existing
  token. Logout only clears the current browser cookie.
- A missing `JWT_SECRET_KEY` creates a random in-memory key instead of failing
  production startup. Production mode is not used to enforce safe auth/email
  configuration.
- `docs/ROADMAPS/multi_tenancy_roadmap_v0.1_2026-08-04.md` records a shared
  development password in plaintext. Treat it as compromised: remove the value
  from documentation, rotate every account that used it, and activate those
  accounts through the new flow before production.
- The project-specific instructions require centralized error codes/responses,
  but no `error_codes.py` or `error_responses.py` currently exists. Establish the
  minimal shared auth error contract before adding endpoints rather than adding
  more ad-hoc strings.

These gaps make email activation/reset part of an auth hardening release, not an
isolated SMTP feature.

## 4. HoraH reuse assessment

The source assessment used HoraH's real implementation, especially:

- `horah_platform/backend/email_service.py`;
- `horah_platform/backend/routers/auth.py`;
- `horah_platform/frontend/js/email-verification.js`;
- `horah_platform/frontend/js/password-reset.js`;
- `horah_platform/frontend/js/auth-main.js`;
- `docs/EMAIL_VERIFICATION_SETUP.md`; and
- `docs/PASSWORD_RESET_IMPLEMENTATION.md`.

### Reuse or adapt

- The standard-library `smtplib` and `email.mime` approach is sufficient; Agenda
  does not need a provider SDK for GoDaddy SMTP.
- Preserve multipart HTML plus plain-text fallback, branded sender name/address,
  a clear expiry notice, a “not requested by you” warning, and separate subjects
  for activation, reset, and reset-completed notification.
- Preserve the transport exception taxonomy for server-side diagnostics:
  authentication failure, refused recipient, disconnect, timeout, generic SMTP
  failure, and unexpected failure. Map all of them to safe generic client
  responses and never return raw SMTP details.
- Reuse the frontend flow concepts: clear steps, resend/cooldown state,
  password/confirmation matching, visible inline success/error regions, and a
  return-to-login action.
- Reuse the intent of short expiry, attempt limits, generic unknown-account reset
  responses, parameterized queries, and single-use consumption.

### Do not copy verbatim

- HoraH gates signup in JavaScript after a verification modal, but the signup API
  itself does not require proof. A direct API request can therefore create an
  account without verification. Agenda must enforce activation and active status
  entirely on the backend.
- HoraH generates numeric codes with `random.randint` and stores them in plaintext
  in Redis. Agenda must use `secrets.token_urlsafe`, store only a digest, compare
  safely, expire tokens, and consume them atomically.
- HoraH's reset flow separately marks a code verified and later consumes it. It
  consumes the code before validating the proposed password/database update, so
  a weak password or database failure can strand the user. Agenda should validate
  first and consume the token in the same transaction as the state change.
- Reset rate-limit keys are inconsistent in HoraH: the service reads a hashed
  email key but increments a raw lowercase-email key. The router limiter also
  fails open when Redis is unavailable. Agenda's security limits must use one
  canonical key scheme and have an explicit production failure policy.
- Verification and reset SMTP sending are nearly duplicated and assume STARTTLS
  on port 587. GoDaddy Professional Email uses implicit SSL on port 465, while
  GoDaddy Microsoft 365 uses STARTTLS on port 587, so transport security must be
  a validated configuration choice.
- Provider-specific `ZOHO_*` settings, hardcoded brand/domain/year, emoji-heavy
  templates, inline styling, and user-visible infrastructure errors do not fit
  Agenda. Templates must use Tennis OS branding, escaped variables, accessible
  markup, and professional SVG/image assets where an icon is necessary.
- HoraH logs recipient addresses/names and some infrastructure detail broadly.
  Agenda should log event IDs and user IDs, redact mailbox details, and never log
  passwords or raw tokens.
- HoraH's composition rule (uppercase + lowercase + digit + special character)
  is duplicated in backend and frontend. Current NIST/OWASP guidance favors
  length, compromised/common-password blocking, and useful feedback instead of
  mandatory character classes.

The practical reuse target is therefore the email content, transport behavior,
and UX state model—not a file copy of HoraH's 700-line email service or its
1,100-line auth router.

## 5. Target design

### 5.1 User lifecycle and canonical email

Use explicit statuses: `pending_activation`, `active`, and `disabled`. Add
`email_verified_at`, `password_changed_at`, and `auth_version` to `User`; allow
`hashed_password` to be null only while pending activation, enforced by a
database check constraint. An active user must have a verified email and a
password hash.

Create one canonicalization function used by provisioning, activation, reset,
and login:

1. trim surrounding whitespace;
2. validate as an email address and enforce the database length limit;
3. canonicalize the domain (including IDNA handling from the validator) and use
   one documented lowercase identity rule; and
4. store/query the canonical value under a case-insensitive database uniqueness
   constraint or functional unique index.

Do not perform synchronous MX lookups or reject disposable domains in the first
release. Syntax validation prevents malformed input; the activation link proves
that the mailbox can receive product email. Public self-signup abuse is not yet
in scope.

### 5.2 Shared action-token lifecycle

Add an `auth_action_tokens` table for `account_activation` and `password_reset`
with `id`, `user_id`, `purpose`, `token_digest`, `expires_at`, `consumed_at`,
`created_at`, and request/audit metadata. Generate at least 128 bits of entropy
with `secrets`, put the raw token only in the email URL, and store a keyed digest
or SHA-256 digest in PostgreSQL. A digest lookup must be unique and constant-time
comparison should be used where comparison occurs in application code.

Issuing a token invalidates prior unconsumed tokens for the same user/purpose.
Consumption must lock the row and atomically perform all of the following in one
transaction: verify purpose/expiry/unused state, validate the new password where
applicable, update the user, increment `auth_version`, mark the token consumed,
and append the security audit event. A failed validation or database operation
must not consume the token.

Use PostgreSQL rather than adding Redis solely for these flows. Agenda already
depends on PostgreSQL/Alembic, tokens are low-volume durable security records,
and one source of truth makes expiry, replay, audit, and atomic consumption
simpler. Cleanup can delete old consumed/expired rows through the existing
scheduled-task pattern after the security retention window.

### 5.3 Email delivery boundary and durable outbox

Keep SMTP outside auth route code:

- `backend/app/integrations/email/contracts.py` — provider-neutral message and
  sender contract;
- `backend/app/integrations/email/smtp.py` — one SMTP connection path supporting
  `ssl` and `starttls`;
- `backend/app/integrations/email/templates.py` — escaped HTML/plain activation,
  reset, and reset-completed templates; and
- `backend/app/services/auth_emails.py` — auth-specific orchestration and links.

Use a small `email_deliveries` outbox table and a worker following Agenda's
existing durable worker conventions. The request transaction stores a deduplicated
delivery job for the eligible user/purpose; the API can then return the same
response shape/timing for known and unknown accounts without waiting on GoDaddy.
The worker generates the raw action token in memory, persists only its digest,
renders/sends the message, and records attempt count, next attempt,
provider-neutral failure category, and sent time. A retry invalidates the prior
unsent token before issuing another. Retries must be bounded with backoff. Never
persist the raw password, raw action token, or rendered token-bearing message,
and protect outbox access as sensitive data. If the team chooses synchronous
SMTP for a first local slice, the durable outbox remains the production gate.

### 5.4 Endpoint behavior

- Manual provisioning creates a tenant-bound `pending_activation` user and
  queues an activation email; it never accepts or prints a password.
- `POST /api/auth/activate` accepts the activation token, new password, and
  password confirmation. It activates and verifies the user
  atomically, then directs the UI to ordinary login rather than auto-login.
- `POST /api/auth/forgot-password` returns a normal validation error for malformed
  syntax, then always returns `202` with the same generic response for valid,
  unknown, disabled, and pending identities. It queues mail only for eligible
  users.
- `POST /api/auth/reset-password` accepts the raw token and new password in the
  JSON body, never in a backend query parameter, and performs atomic reset/token
  consumption. It queues a password-changed notification and requires normal
  login afterward.
- Existing login remains `POST /api/auth/login`, but canonicalizes the email,
  performs a dummy hash verification for unknown/ineligible users, rate-limits
  independently by account key and source IP, and only authenticates active,
  verified users.

The frontend email link may contain the token in its query string. The reset and
activation pages must immediately capture it, remove it from the visible URL,
set `Referrer-Policy: no-referrer`, avoid third-party resources on that page, and
submit it to the API only in the request body.

### 5.5 Session invalidation and cookie baseline

Include `auth_version`, `iat`, `jti`, issuer, and audience in newly issued JWTs.
`require_authenticated` must load the current user, require active status and a
matching auth version, and continue deriving role/tenant from authoritative
server state. Reset, disablement, and security-sensitive credential changes
increment the version, invalidating existing tokens. Preserve the current
impersonation audit behavior.

Externalize session duration and cookie flags. Production requires HttpOnly,
`Secure`, an explicitly selected `SameSite` value, a narrow path/domain, HTTPS,
and configured allowed origins. Add an Origin/CSRF control to state-changing
cookie-authenticated routes; do not treat CORS or `SameSite` alone as the CSRF
control.

## 6. Environment contract and GoDaddy selection

Add documented placeholders to `.env.example` and keep real values only in the
local `.env` or the production secret/environment store. Do not log values or
silently default credentials.

| Variable | Purpose |
|---|---|
| `APP_ENV` | Enables production startup validation. |
| `FRONTEND_BASE_URL` | Allowlisted HTTPS origin used to build activation/reset links; never derive it from the request `Host` header. |
| `CORS_ALLOWED_ORIGINS` | Explicit comma-separated frontend origins. |
| `EMAIL_ENABLED` | Explicit local/test delivery switch; production must be true. |
| `EMAIL_SMTP_HOST` | SMTP server hostname. |
| `EMAIL_SMTP_PORT` | SMTP port. |
| `EMAIL_SMTP_SECURITY` | Enum: `ssl` or `starttls`; no plaintext production option. |
| `EMAIL_SMTP_USERNAME` | Authenticated mailbox username, normally the full address. |
| `EMAIL_SMTP_PASSWORD` | Mailbox/app password; secret. |
| `EMAIL_FROM_ADDRESS` | Visible sender; must be the authenticated mailbox or an approved alias. |
| `EMAIL_FROM_NAME` | `Tennis OS` unless product naming changes. |
| `EMAIL_REPLY_TO` | Optional monitored support address. |
| `EMAIL_SMTP_TIMEOUT_SECONDS` | Bounded connect/read timeout. |
| `EMAIL_MAX_ATTEMPTS` | Bounded outbox retry count. |
| `EMAIL_RETRY_BASE_SECONDS` | Backoff base for delivery retries. |
| `EMAIL_PROCESSING_TIMEOUT_SECONDS` | Recovery threshold for a delivery interrupted while a worker was processing it. |
| `AUTH_ACTIVATION_TOKEN_TTL_MINUTES` | Activation lifetime. |
| `AUTH_RESET_TOKEN_TTL_MINUTES` | Reset lifetime. |
| `AUTH_EMAIL_MAX_SENDS_PER_HOUR` | Per-account delivery quota. |
| `AUTH_LOGIN_MAX_ATTEMPTS` | Account/IP login throttle policy input. |
| `AUTH_SESSION_EXPIRE_MINUTES` | Session absolute lifetime. |
| `AUTH_COOKIE_NAME` | Existing configurable cookie name. |
| `AUTH_COOKIE_SECURE` | Must be true in production. |
| `AUTH_COOKIE_SAMESITE` | Validated `lax`, `strict`, or explicitly justified `none`. |
| `AUTH_COOKIE_DOMAIN` | Optional narrowly scoped production domain. |
| `JWT_SECRET_KEY` | Required stable signing secret; production startup fails if absent. |
| `JWT_ISSUER` / `JWT_AUDIENCE` | Token binding values. |

GoDaddy currently has two relevant products with different settings:

| GoDaddy mailbox product | Host | Port | Security | Deployment note |
|---|---:|---:|---|---|
| Professional Email powered by Titan | `smtpout.secureserver.net` | 465 | implicit SSL | Authenticate with the mailbox address/password. |
| Microsoft 365 from GoDaddy | `smtp.office365.com` | 587 | STARTTLS | SMTP AUTH must be enabled; use the account/app-password flow appropriate to its MFA policy. |

Do not hardcode either profile until the actual mailbox product is confirmed.
Set all three transport values explicitly in each environment and add a startup
configuration check that rejects mismatched combinations. Before release,
configure and verify SPF, DKIM, and DMARC for the sending domain, confirm the
From address is permitted, and test delivery to at least Gmail, Outlook, and the
product's own domain.

## 7. Password policy and weak-password feedback

### Backend policy authority

Agenda currently has no MFA, so adopt the current NIST single-factor baseline:

- minimum 15 Unicode characters and maximum at least 64 characters;
- allow spaces, printable characters, Unicode, paste, browser password managers,
  and generated passwords;
- do not require uppercase/lowercase/digit/symbol composition and do not schedule
  periodic password changes;
- normalize accepted Unicode consistently before hashing without trimming or
  silently changing the password;
- reject common, expected, context-specific, and known-compromised whole
  passwords with a local blocklist in the request path; and
- reject passwords containing the canonical email, Tennis OS name/domain, or
  trivial account-specific terms when they make the password readily guessable.

Do not make a runtime third-party breach API a prerequisite for activation or
reset. Start with a versioned local blocklist and document its update process;
evaluate a privacy-preserving breached-password service or larger offline corpus
as a separately monitored enhancement.

Migrate new hashes to Argon2id with benchmarked parameters meeting OWASP's
minimum profile. Keep bcrypt verification for existing PHC/prefix-detectable
hashes and rehash to Argon2id after a successful login. This supports long
Unicode passphrases without bcrypt's 72-byte input limit. Pin `argon2-cffi` and
`email-validator` in `requirements.txt`; benchmark hashing on the production
compute class before selecting final parameters.

### Frontend feedback

Create one reusable password field/checklist for activation and reset:

- show the non-negotiable 15-character minimum and confirmation match state;
- use a pinned `@zxcvbn-ts/core` dependency for immediate qualitative feedback
  (`Muito fraca`, `Fraca`, `Razoável`, `Forte`) and localized suggestions; do not
  hand-roll entropy math or treat the client score as authorization;
- show actionable wording such as “Use a longer phrase with unrelated words” or
  “This password is commonly used; choose a different one,” instead of only
  “weak password”;
- update feedback as the user types without network requests, preserve paste and
  autofill, add a show/hide-password button, and do not clear input after a
  server rejection;
- connect messages through `aria-describedby` and an appropriate live region,
  and never rely on red/green color alone; and
- submit optimistically from the user's perspective: validate locally
  immediately, retain entered values, disable only duplicate submission, and
  reconcile with stable backend error codes if the server rejects the password.

Return structured auth errors through the project's centralized error contract,
for example `PASSWORD_TOO_SHORT`, `PASSWORD_BLOCKLISTED`, `PASSWORD_MISMATCH`,
`TOKEN_INVALID_OR_EXPIRED`, and `RATE_LIMITED`. The client maps these codes to
Portuguese copy; it never displays raw backend or SMTP exceptions.

## 8. Incremental implementation roadmap

### Phase 0 — Confirm deployment inputs and remove known credential risk

1. Confirm whether the GoDaddy mailbox is Professional Email/Titan or Microsoft
   365, the approved From/Reply-To addresses, production frontend origin, and
   where injected production secrets will live.
2. Remove the shared password value from the historical multi-tenancy roadmap,
   rotate affected accounts, and inventory all manually created users.
3. Add `.env.example` placeholders and production startup validation without
   inserting real credentials.
4. Establish the minimal centralized auth error-code/response helpers required
   by the project rules.

**Verify:** repository/history review finds no current credential value in
tracked files; missing or inconsistent production auth/email configuration fails
startup with a redacted diagnostic; local email-disabled mode remains explicit.

### Phase 1 — Identity, password, token, and audit foundations

1. Add canonical email and password-policy services with unit tests first.
2. Add pinned `email-validator` and Argon2id support; preserve and test bcrypt
   login with rehash-on-success.
3. Add `User` activation/verification/session fields and constraints, plus
   `AuthActionToken`, `EmailDelivery`, and auth security-event persistence through
   an Alembic migration.
4. Implement secure token issue/validate/consume services and database-backed
   rate-limit keys using canonical email digests and source-IP digests.
5. Update `require_authenticated` and JWT claims to enforce current user state and
   `auth_version`; externalize secure cookie/session configuration.

**Verify:** migration upgrade/downgrade works locally; old bcrypt users can log in
and are upgraded; invalid/expired/replayed tokens fail; weak-password validation
does not consume a valid token; disabled/reset users' old sessions fail; tenant
and role claims cannot be supplied or changed by the client.

### Phase 2 — One provider-neutral email path

1. Extract only the reusable HoraH message/SMTP behaviors into the small Agenda
   modules listed in section 5.3.
2. Implement SSL and STARTTLS branches with certificate verification, timeout,
   redacted logging, a single send method, and safe error classification.
3. Build accessible Tennis OS HTML/plain templates for activation, reset, and
   reset completion. Escape every interpolated value and use an allowlisted
   `FRONTEND_BASE_URL`.
4. Implement the durable outbox worker, bounded retry/backoff, deduplication, and
   operational counters without persisting raw tokens or rendered links.

**Verify:** fake-SMTP tests cover SSL, STARTTLS, authentication/refusal/timeout,
and retry exhaustion; snapshot/content tests cover HTML escaping and plain-text
fallback; a local sink receives all message types; no raw token, credential, or
recipient address appears in logs.

### Phase 3 — Manual provisioning becomes verified account activation

1. Refactor `scripts/create_user.py` to call the same provisioning service as any
   future admin endpoint. Accept only canonical email, role, and professional ID;
   create `pending_activation`; queue activation; never accept a password CLI
   argument.
2. Add backend activation endpoint/service enforcement. No frontend-only flag or
   call ordering may activate a user.
3. Add `/activate` with token capture/removal, new-password/confirmation UI,
   password feedback, invalid/expired/replayed states, resend/support guidance,
   and return-to-login success state.
4. Preserve role and `professional_id` from the operator-created record; the
   activation request cannot set either value.

**Verify:** a pending user cannot log in; direct endpoint calls cannot bypass
activation; an activation token works once; activation cannot change tenant or
role; weak input retains the usable token; successful activation verifies the
email, stores Argon2id, increments `auth_version`, audits the event, and permits
normal login.

### Phase 4 — Forgot/reset password end to end

1. Add tested forgot/reset schemas and endpoints using the shared token,
   outbox, password-policy, rate-limit, and error services.
2. Add “Esqueci minha senha” to the existing login page and dedicated request and
   reset pages in the same design system.
3. Return the same status, response body, and approximately uniform asynchronous
   behavior for eligible and ineligible accounts. Do not reveal whether mail was
   queued.
4. On success, update the password and `password_changed_at`, increment
   `auth_version`, consume the token atomically, append an audit event, queue a
   notification, and require ordinary login.

**Verify:** valid, unknown, disabled, and pending emails receive the same public
forgot response; per-account and per-IP quotas prevent mail flooding; invalid,
expired, superseded, and replayed links fail safely; a weak-password rejection
does not burn the link; reset invalidates all old normal and impersonated
sessions; password confirmation mail contains no token or password.

### Phase 5 — Login, cookie, CSRF, and abuse hardening

1. Apply independent account and source-IP login throttles, dummy-hash timing
   work, generic errors, audit categories, and safe input bounds.
2. Apply production cookie attributes, issuer/audience validation, CORS origin
   configuration, CSRF/Origin protection, security headers, and `Cache-Control:
   no-store` across auth responses/pages.
3. Ensure platform-admin impersonation, logout, inactive accounts, token version,
   and tenant isolation still work after authoritative user lookup is added.
4. Add alertable metrics for login failures, reset/activation requests, token
   failures/replay, rate limits, SMTP outcomes, retry exhaustion, and queue age;
   use event/user IDs rather than raw PII.

**Verify:** cookie/header assertions pass in production-mode tests; cross-origin
state-changing calls fail; limits work across multiple application workers and
fail according to the documented production policy; security logs contain no
password, raw token, cookie, JWT, or full mailbox address.

### Phase 6 — Production delivery and controlled cutover

1. Configure GoDaddy secrets and DNS authentication outside source control; run
   a startup connectivity check as an operator command, not on every request.
2. Test real activation/reset/completion delivery and rendering across the
   agreed mailbox matrix; inspect spam placement and headers.
3. Back up the local database, apply migrations locally, activate test accounts,
   and run the complete auth plus tenant-isolation regression suite.
4. Only after local acceptance, apply the forward migration to the remote
   database. Do not destructively alter remote data. Provision/activate accounts
   deliberately and retain the migration rollback/runbook.
5. Mark existing accounts pending activation or force a reset according to the
   approved cutover list; do not silently mark unverified addresses verified.

**Verify:** the production smoke test covers activate → login → forgot → reset →
old-session rejection → new login for both a professional and platform admin;
tenant isolation and impersonation remain intact; rollback can disable email
sending and restore login policy without deleting user/security history.

## 9. Expected file-level change map

The exact names can follow existing project style, but the responsibility split
should remain small and explicit.

| Area | Expected change |
|---|---|
| `backend/app/models/user.py` | Activation, verification, password-change, and auth-version state. |
| `backend/app/models/` | Focused action-token, email-delivery, and auth-security-event models exported from `models/__init__.py`. |
| `backend/migrations/versions/` | One reviewed forward migration for the new state/tables/indexes/constraints. |
| `backend/app/core/security.py` | Argon2id/bcrypt compatibility, JWT binding/version claims, and externalized session settings. |
| `backend/app/core/error_codes.py` and response helper | Minimal stable auth error contract, because the required project module is currently absent. |
| `backend/app/services/email_identity.py` | Canonical email parsing/normalization. |
| `backend/app/services/password_policy.py` | Single backend password policy and blocklist check. |
| `backend/app/services/auth_tokens.py` | Secure issue, digest lookup, invalidation, and atomic consumption. |
| `backend/app/services/auth_emails.py` | Activation/reset orchestration and allowlisted link construction. |
| `backend/app/integrations/email/` | Contract, SMTP transport, and templates. |
| `backend/app/api/auth.py` | Thin schemas/routes delegating to services; preserve login/impersonation responsibilities. |
| `backend/app/api/dependencies.py` | Authoritative user status/auth-version checks without weakening tenant isolation. |
| `scripts/create_user.py` | Passwordless pending-user provisioning and activation queueing. |
| existing worker launcher/modules | Start and monitor the email outbox worker using existing process conventions. |
| `frontend/src/lib/auth.ts` | Typed activation/forgot/reset clients and stable error-code mapping. |
| `frontend/src/components/auth/` | Reusable password field, strength feedback, and auth status panels. |
| `frontend/src/app/login/page.tsx` | Forgot-password entry point and autocomplete/show-password improvements. |
| `frontend/src/app/activate/` and reset routes | Dedicated token-safe workflows using the existing visual language. |
| `requirements.txt` | Exact pins for new Python dependencies; no runtime installs. |
| `frontend/package.json` / lockfile | Exact strength-meter dependency and lock update. |
| `.env.example` and deployment docs | Redacted environment contract and GoDaddy runbook. |
| `backend/tests/` | Unit/integration/security regression coverage described below. |

Avoid creating a parallel auth package, copying HoraH's router, adding Redis, or
putting SMTP calls directly in endpoints. Each new module has one production use
and a clear test seam.

## 10. Required test matrix

### Unit tests

- email trim/case/domain normalization, invalid syntax, maximum length, Unicode
  domains, and duplicate canonical identity;
- password length in Unicode code points, spaces/paste-compatible characters,
  blocklisted/context password, long-passphrase hashing, bcrypt verification,
  Argon2id rehash detection, and no composition requirement;
- token entropy shape, digest-only persistence, purpose binding, expiry,
  supersession, replay rejection, and non-consumption on validation failure;
- HTML escaping, trusted link origin, plain-text alternative, and no secrets in
  template/log snapshots;
- SMTP SSL versus STARTTLS selection and categorized failures; and
- outbox deduplication, row locking, bounded retry/backoff, and terminal failure.

### API/integration tests

- pending/disabled/unverified login rejection and active verified login success;
- generic login and forgot responses for every account state, including timing
  work/dummy verification behavior;
- independent per-account and per-IP throttles across app instances;
- activation/reset happy paths plus invalid, expired, superseded, wrong-purpose,
  weak-password, database-failure, and replay paths;
- immutable role/professional ID through activation and reset;
- password reset, disablement, and auth-version changes invalidate prior normal
  and impersonation JWTs;
- cookie flags, issuer/audience, CORS, Origin/CSRF, no-store headers, logout, and
  current `/me` behavior; and
- all current admin impersonation and tenant-isolation tests remain green.

### Frontend/manual behavior

- keyboard, screen-reader messaging, narrow viewport, password manager/autofill,
  paste, show/hide, strength suggestions, confirmation mismatch, and preserved
  input after server errors;
- the token disappears from the address bar and is absent from referrers,
  analytics, console output, and API URLs;
- request/reset/activation states never disclose account existence or raw server
  errors; and
- real mailbox rendering, expiry, resend/supersession, spam-folder guidance, and
  return-to-login behavior.

Run the focused tests after every logical unit, then the full local suite in the
`agenda` conda environment. Add frontend type-check, lint, and production build
to the release gate; the frontend currently has no dedicated test runner, so add
one only if component behavior cannot be covered proportionately by the chosen
implementation.

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| HoraH reuse imports a bypass or duplicated legacy design | Reuse behavior/templates selectively; enforce activation/token consumption in Agenda backend services and tests. |
| Wrong GoDaddy product profile blocks all mail | Confirm product in Phase 0; explicit host/port/security variables; startup validation and operator connectivity test. |
| SMTP credentials or tokens leak through logs/outbox | Redact identifiers; persist token digests only; generate/render raw tokens in worker memory; never log message bodies, headers, JWTs, cookies, or secrets. |
| Reset endpoint enumerates accounts by response, status, or time | Same `202` body for all account states, asynchronous durable queue, bounded uniform validation, and automated enumeration tests. |
| Mail flooding or token brute force | Independent account/IP quotas, high-entropy link tokens, single use, short expiry, supersession, monitoring, and optional edge challenge after abuse evidence. |
| Multiple workers send duplicates | Deduplicated pending jobs plus PostgreSQL row locking/`SKIP LOCKED`; idempotency tests. |
| Weak-password UI diverges from backend | One documented backend policy and stable error codes; client meter is advisory; shared contract tests. |
| Argon2 parameters exhaust production compute | Benchmark on deployment class, use OWASP-compliant lower profile if necessary, bound input, and rate-limit hash endpoints. |
| Bcrypt migration locks out existing users | Detect hash format, verify bcrypt, rehash only after success, and retain rollback coverage until migration is complete. |
| Token in frontend URL leaks | HTTPS, allowlisted base URL, immediate URL cleanup, `Referrer-Policy: no-referrer`, no third-party reset-page resources, short lifetime. |
| Password changes leave stolen JWTs active | Authoritative user lookup and `auth_version` validation on every authenticated request. |
| Email outage blocks onboarding/recovery | Durable bounded retries, queue-age alerts, operator resend/support path, and no automatic account mutation before token completion. |
| DNS/authentication problems send mail to spam | SPF, DKIM, DMARC, permitted From address, mailbox-matrix tests, and delivery monitoring before cutover. |
| Migration disrupts current users or tenant isolation | Local backup/rehearsal, explicit cutover list, forward-only remote rollout, existing auth/tenant tests, and no silent verification backfill. |
| Scope expands into public signup/MFA | Keep this release on manual activation and reset; track public signup and MFA as separate product/security roadmaps. |

## 12. Production release gates

Do not deploy merely because the happy path works. All gates below are required:

- actual GoDaddy product/settings and allowed sender confirmed;
- no real secret or shared password in tracked documentation/configuration;
- migrations rehearsed on local `agenda_db` with backup and rollback notes;
- activation and reset are backend-enforced, atomic, expiring, single-use, and
  digest-only at rest;
- password policy, Argon2id migration, weak-password feedback, and password
  manager behavior accepted;
- generic enumeration-resistant responses and multi-key rate limits verified;
- password reset invalidates all prior sessions;
- production cookie, CSRF, CORS, HTTPS, headers, JWT issuer/audience, and stable
  signing-secret checks pass;
- SMTP TLS, SPF/DKIM/DMARC, real mailbox delivery, retries, queue monitoring, and
  redacted logs pass;
- existing auth, impersonation, tenant isolation, and full backend regressions
  pass in the `agenda` conda environment;
- frontend type-check, lint, build, accessibility, and mobile auth-flow checks
  pass; and
- remote rollout is additive and non-destructive, with no remote database action
  until the local result is accepted.

## 13. References

- [NIST SP 800-63B, Password Authenticators](https://pages.nist.gov/800-63-4/sp800-63b.html#password-authenticators)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [GoDaddy Professional Email (Titan) IMAP/SMTP settings](https://www.godaddy.com/es/help/usar-la-configuracion-del-imap-para-agregar-mi-professional-email-a-un-cliente-32204)
- [GoDaddy Microsoft 365 SMTP setup](https://www.godaddy.com/en-in/help/set-up-microsoft-365-email-with-smtp-on-a-multifunction-device-41962)
- HoraH source files listed in section 4, inspected locally on 2026-09-01.

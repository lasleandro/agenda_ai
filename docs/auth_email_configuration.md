# Authentication email configuration

Authentication email is provider-neutral SMTP and runs through the durable
`email_deliveries` outbox. Copy the relevant values from `.env.example` into
the deployment secret store; never commit a mailbox password.

## Required production settings

Set `APP_ENV=production`, a stable `JWT_SECRET_KEY`, `FRONTEND_BASE_URL`,
`CORS_ALLOWED_ORIGINS`, `AUTH_COOKIE_SECURE=true`, and `EMAIL_ENABLED=true`.
The API refuses to start when those production safeguards are absent. Activation
and reset links always use `FRONTEND_BASE_URL`, never an incoming request host.

## GoDaddy SMTP profiles

Choose the profile for the mailbox actually provisioned; the application does
not hardcode a provider.

| GoDaddy product | `EMAIL_SMTP_HOST` | `EMAIL_SMTP_PORT` | `EMAIL_SMTP_SECURITY` |
|---|---|---:|---|
| Professional Email powered by Titan | `smtpout.secureserver.net` | 465 | `ssl` |
| Microsoft 365 from GoDaddy | `smtp.office365.com` | 587 | `starttls` |

Use the full sending mailbox as `EMAIL_SMTP_USERNAME`. `EMAIL_FROM_ADDRESS`
must be that mailbox or an alias it is authorized to send as. For Microsoft 365,
enable SMTP AUTH and use the organization-approved password or app-password
policy. Keep `EMAIL_SMTP_PASSWORD` only in the environment/secret manager.

`EMAIL_MAX_ATTEMPTS`, `EMAIL_RETRY_BASE_SECONDS`, and
`EMAIL_PROCESSING_TIMEOUT_SECONDS` control bounded retries and recovery after a
worker interruption. Keep the processing timeout longer than the SMTP timeout.

## Activation email sources

An `account_activation` delivery is queued (never sent inline in the HTTP
request) by:

- **Novo tenant** on `/admin/select-tenant`;
- approving a request on `/admin/account-requests` — same
  `create_tenant_with_owner` path; and
- **Reenviar ativação** on an approved request whose owner is still
  `pending_activation`. Resend returns an already-active delivery instead of
  adding a second one, and is bounded by
  `ACCOUNT_ACTIVATION_RESEND_COOLDOWN_SECONDS` (default 60) plus
  `AUTH_EMAIL_MAX_SENDS_PER_HOUR` per owner-email and per admin.

If an approved owner is still `pending_activation` after 24h, or any activation
delivery reaches terminal `failed` / `suppressed`, treat it as an onboarding
incident: inspect `email_deliveries` for that user, correct the cause, then use
**Reenviar ativação**. See `docs/pages/solicitar_conta.md`.

## Operating and release checks

Run `python start_server.py --worker` so the authentication-email worker claims
queued outbox records. Provision users without a password:

```bash
conda run -n agenda python scripts/create_user.py \
  --email owner@example.com --role professional --professional-id <tenant-uuid>
```

Before enabling production mail, apply migrations locally, then verify the full
flow with a dedicated account: activation, login, reset request, reset link,
old-session rejection, and new login. Verify SPF, DKIM, and DMARC for the
sending domain and test inbox placement with Gmail and Outlook. Only after that
local acceptance should the forward migration be applied to the remote database.

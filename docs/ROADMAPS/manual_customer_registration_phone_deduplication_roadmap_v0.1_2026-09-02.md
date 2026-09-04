# Manual Customer Registration & WhatsApp Deduplication Roadmap v0.1 — 2026-09-02

**Status: implemented locally; production migration pending preflight.** This
roadmap adds tenant-scoped manual customer registration while preserving one
customer identity per WhatsApp cellphone number.

## 1. Goal and product outcome

An authenticated instructor can register a customer from **Clientes** before
the first WhatsApp interaction. The registration requires the customer's name
and a valid mobile number from any country. Brazil is the default input region,
while foreign numbers require an explicit country calling code. When a later
WhatsApp event carries that number, ingestion attaches the message and
conversation to the existing customer instead of creating another `Contact`.

The invariant is:

> Within one tenant (`professional_id`), one canonical WhatsApp cellphone
> number identifies at most one `Contact`.

The same cellphone number may exist in different tenants because each
instructor owns an independent customer book.

### Success criteria

- The **Clientes** page exposes a clear **Novo cliente** action.
- Name and a valid international mobile number are mandatory for manual
  registration.
- Inputs such as `(11) 99999-0000`, `11 99999-0000`, and
  `+55 11 99999-0000` resolve to one canonical stored value:
  `+5511999990000`.
- A foreign number entered with its calling code (for example, a US number
  beginning with `+1`) is accepted and stored in the same E.164 format.
- A second manual registration of the same number in the same tenant returns a
  stable `409 Conflict`; no second row is created.
- A subsequent inbound or outbound WhatsApp event reuses the manually-created
  contact and does not replace its instructor-maintained name.
- Concurrent manual/webhook creation cannot bypass deduplication.
- Tenant isolation, CSRF/origin protection, and the operational audit trail
  remain intact.

## 2. Scope and non-goals

In scope:

- Manual creation from `/clientes`.
- Shared international-mobile validation and E.164 normalization, with Brazil
  as the default region for national-format input.
- Tenant-scoped database uniqueness and race-safe WhatsApp resolution.
- A safe preflight/backfill path for existing contact phones.
- Audit events, API/frontend error handling, tests, and page/business-rule
  documentation.

Out of scope for v0.1:

- Importing customers from CSV, phone contacts, or third-party CRMs.
- Automatically merging two existing `Contact` rows and their appointments,
  conversations, credits, waitlist entries, and financial history.
- Deleting customers.
- Editing the identity phone after creation. Phone changes need their own
  conflict-aware workflow and audit semantics; the existing detail page keeps
  the number read-only in this version.
- Verifying that the entered number currently has an active WhatsApp account.
  Number-format validity and WhatsApp-account existence are different checks;
  v0.1 validates the former only.
- Guessing a foreign country from an unqualified national-format number. The
  user must select/provide the country calling code; only Brazilian input may
  omit it because Brazil is the product's default region.

## 3. Current state and reusable assets

- `Contact` already represents the tenant's customer and already carries
  `professional_id`, `phone`, `display_name`, and `normalized_name`. A new
  customer model is unnecessary.
- `GET /api/contacts`, `GET /api/contacts/{id}`, and
  `PATCH /api/contacts/{id}` are tenant-scoped through
  `require_professional_id`; there is no production `POST /api/contacts`.
- `/clientes` already owns the list state, search, notices, and dialog-based
  actions. A focused `ContactFormDialog` can follow those local patterns.
- WhatsApp ingestion calls `get_or_create_contact()` and matches
  `(professional_id, phone)` by exact string equality. It preserves a known
  name and only backfills the WhatsApp profile name when the stored display
  name is the phone itself.
- The database has no unique constraint on contact phone. The existing
  select-then-insert path is therefore vulnerable to formatting differences
  and concurrent requests.
- Provider adapters currently copy sender/recipient strings into canonical
  WhatsApp events without phone normalization. No shared phone utility or
  phone-validation dependency exists.
- `phone` is nullable and `VARCHAR(50)`. There is no database constraint for
  canonical international E.164 shape.
- `OperationalEvent` supports `contact.updated` but not `contact.created`.
- Frontend mutations already send CSRF headers through `apiRequest()` and
  several Clientes actions use optimistic state with rollback.

### Local preflight observed on 2026-09-02

The initial aggregate, read-only audit of local `agenda_db` found 10 invalid
legacy mock contacts under one mock tenant. On 2026-09-02 that disposable
tenant, its user, and its associated mock data were removed through a targeted
local transaction. The strict migration then completed locally, and the
follow-up audit reported zero contacts, missing phones, invalid phones, and
normalization-equivalent duplicates.

This local result says nothing about production. Run the same aggregate,
read-only preflight against production before approving its migration. Do not
update or merge remote rows as part of discovery.

## 4. Decisions and assumptions

1. **Canonical identity:** store every customer phone as international E.164
   (`+` plus country calling code and national number, maximum 15 digits).
   Formatting is a presentation concern.
2. **Validation authority:** the backend is authoritative. The frontend may
   mask and pre-validate for convenience, but it submits to the same backend
   contract used by WhatsApp ingestion.
3. **Validated mobile, not merely digit count:** use Google's libphonenumber
   metadata through the Python `phonenumbers` package, pinned in
   `requirements.txt`. Parse local-format input with default region `BR`; parse
   foreign numbers only when a country calling code is supplied. Require a
   valid mobile number, while accepting `FIXED_LINE_OR_MOBILE` in countries
   where numbering metadata cannot distinguish the types. Keep a generic
   E.164 database shape check as defense in depth; do not reproduce country
   numbering plans in SQL or regular expressions.
4. **Tenant-local uniqueness:** enforce `UNIQUE (professional_id, phone)`, not
   global phone uniqueness.
5. **Name precedence:** a manually supplied name wins. A later WhatsApp profile
   name only replaces a placeholder whose current display name equals the
   phone, preserving today's behavior.
6. **Duplicate manual request:** return `409` with a stable application error
   code and keep the existing contact unchanged. Do not silently treat a
   duplicate form submission as an update.
7. **Duplicate WhatsApp event:** reuse the existing contact and continue normal
   conversation/message ingestion. This is not an error visible to the user.
8. **No automatic historical merge:** if preflight finds two existing rows
   that normalize to the same tenant/phone, stop rollout and review them. A
   merge would need to re-home every dependent record and reconcile conflicting
   names and financial settings, which is outside this feature.
9. **Phone required at the domain boundary:** after production preflight is
   clean, make `contacts.phone` non-null. All supported creation paths have a
   phone, and the requirement is stronger when represented in the schema.

## 5. Target behavior

### Manual registration

```text
Instructor opens Novo cliente
  -> frontend shows an international phone input with country selector (BR default)
  -> POST /api/contacts with name + phone
  -> backend derives tenant and actor from the authenticated session
  -> shared phone service parses BR number and emits E.164
  -> insert Contact under (professional_id, canonical phone)
  -> record contact.created in the same transaction
  -> return 201 and replace the optimistic list row with the server row
```

If the tenant already owns that canonical phone, the insert is rejected with
`409 CONTACT_PHONE_ALREADY_EXISTS`; the frontend rolls back its optimistic row,
keeps the entered data available, and explains that the customer is already
registered.

### Later WhatsApp interaction

```text
Provider webhook
  -> provider adapter emits the provider-neutral event
  -> ingestion canonicalizes the customer phone with the shared service
  -> atomic insert-or-resolve by (professional_id, canonical phone)
  -> existing manual Contact is returned
  -> get/create Conversation for that Contact
  -> persist Message and schedule processing as today
```

The contact uniqueness race must be handled independently from the existing
`provider_message_id` retry path. A contact uniqueness collision must resolve
the winning contact and continue; it must not be mistaken for a duplicate
message and dropped.

## 6. API and data contracts

### Request

Add `ContactCreate` to `backend/app/schemas/ontology.py`:

```json
{
  "display_name": "Ana Martins",
  "phone": "(11) 99999-0000"
}
```

For v0.1, only these two fields belong in the create dialog. Level, habitual
place, address, and financial overrides remain on the existing detail page.
Trim the name, reject an empty result, impose the existing 255-character
maximum, and generate `normalized_name` server-side.

### Response and errors

- `POST /api/contacts` returns the existing `ContactSummary` shape with
  `201 Created`.
- `422` covers a missing/invalid name or a phone that is not a valid supported
  international mobile number.
- `409` uses a new stable `CONTACT_PHONE_ALREADY_EXISTS` error code.
- Add `INVALID_CONTACT_PHONE` only if phone validation is translated from
  Pydantic's normal `422` structure into the project's structured error
  envelope. Whichever convention is selected must be consistent between the
  endpoint and `frontend/src/lib/api.ts`; do not introduce a one-off string
  contract.
- Error messages exposed to the client stay generic and contain no other
  tenant's data. The duplicate check is always scoped to the authenticated
  tenant.

### Database invariant

After cleanup, `contacts` should have:

- `phone VARCHAR(16) NOT NULL` (leading `+` plus up to 15 E.164 digits);
- `CONSTRAINT uq_contacts_professional_phone UNIQUE (professional_id, phone)`;
- a lightweight check that stored values have canonical international E.164
  shape. Full country/mobile validity stays in the phone service because
  numbering metadata evolves.

No unique rule is added to `provider_contact_id`; WhatsApp identity for this
feature is the canonical phone.

## 7. Implementation phases

### Phase A — Shared phone value boundary

- Add a focused module such as `backend/app/services/phone_numbers.py` with
  public, typed functions that:
  - parse national-format input using default region `BR`;
  - parse foreign input only with an explicit country calling code;
  - reject extensions, malformed values, definite fixed lines, and
    impossible/unallocated numbers, while allowing numbers whose metadata type
    is `FIXED_LINE_OR_MOBILE`;
  - return one E.164 string for valid mobiles.
- Add and pin `phonenumbers` in the root `requirements.txt`; frontend validation
  remains advisory. Add a pinned international phone-input package to
  `frontend/package.json` / lockfile rather than hand-rolling country
  calling-code selection and formatting.
- Unit-test equivalent formats, whitespace/punctuation, missing Brazilian DDD,
  definite landline, accepted foreign mobile, foreign national format without
  country context, invalid country/subscriber, and already-canonical input.
- Update mock-customer constants and numeric test helpers so they exercise
  valid international-mobile shapes rather than `+550...` or UUID hex.
- **Verify:** focused phone tests pass in `conda` env `agenda`, and every
  supported input example produces exactly one E.164 representation.

### Phase B — Read-only audit and schema migration

- Add a decoupled read-only audit command under `scripts/` that reports counts
  by category without printing full PII by default:
  - null/blank phones;
  - values that cannot normalize to a supported international mobile;
  - exact duplicates within a tenant;
  - normalization-equivalent duplicates within a tenant.
- Run it locally first. Run it against production in a read-only transaction
  only after separate approval. It must never mutate the Azure remote DB.
- If any production collision exists, stop. Produce a tenant/contact-ID report
  for authorized review and write a separate consolidation plan. Do not choose
  a winner based only on creation date or move foreign keys automatically.
- Once the audit is clean, create one Alembic migration from the current head
  that:
  1. normalizes all parseable existing phone values to E.164;
  2. aborts with an actionable error if invalid/null/colliding rows remain;
  3. changes `phone` to `VARCHAR(16)` and `nullable=False`;
  4. adds the canonical-shape check and
     `uq_contacts_professional_phone`;
  5. updates the operational-event check constraint to allow
     `contact.created`.
- Mirror the constraints in `Contact.__table_args__` and add
  `contact.created` to the model event vocabulary.
- Write a reversible downgrade that removes the new constraints and restores
  the prior width/nullability. It need not restore punctuation removed by
  canonicalization; document that normalization is intentionally irreversible
  presentation cleanup.
- **Verify:** upgrade/downgrade/upgrade on a disposable local database; direct
  duplicate insert fails within one tenant and succeeds across two tenants;
  invalid/null inserts fail after migration.

### Phase C — Contact creation and race-safe resolution service

- Keep phone/name rules out of the route by extending
  `backend/app/services/contacts.py` with focused creation/resolution
  functions.
- Manual creation must normalize first and rely on the database constraint as
  the final concurrency guard. Catch only the named contact uniqueness
  violation and translate it to the domain duplicate outcome; unexpected
  `IntegrityError`s must propagate for server-side logging.
- Rework WhatsApp `get_or_create_contact()` to normalize before lookup and use
  a PostgreSQL atomic insert-or-resolve operation (`ON CONFLICT` on the named
  tenant/phone key, or an equivalently safe savepoint retry). Two simultaneous
  messages or a form submission racing a webhook must return one contact.
- Keep name precedence explicit: retain a manual/known name; only backfill a
  phone-placeholder name from a later WhatsApp profile.
- Ensure `Contact`, optional `contact.created` event, `Conversation`, `Message`,
  and debounce scheduling retain clear transaction ownership. Do not broaden
  the existing catch for duplicate provider messages.
- **Verify:** service/integration tests force manual-vs-webhook and
  webhook-vs-webhook races and assert one `Contact`, one expected conversation,
  and no lost non-duplicate message.

### Phase D — Tenant-scoped API and audit

- Add authenticated `POST /api/contacts` with `status_code=201`. Derive both
  `professional_id` and the actor user ID from the session; accept neither from
  the request body.
- Preserve the current tenant route behavior for platform admins: creation is
  allowed only while explicitly impersonating/selecting a tenant, because
  `require_professional_id` otherwise returns `403`.
- Record `contact.created` in the same transaction as the contact:
  - manual: `actor_type="user"`, session user ID, `source_channel="web"`;
  - first WhatsApp sighting: `actor_type="system"`, no actor ID,
    `source_channel="whatsapp"`.
- Keep event payloads minimal: creation source and canonical phone are enough;
  never include raw webhook content. The ledger already contains customer data,
  so access remains tenant-scoped and logs must not print full phone numbers.
- Classify a provider event with an invalid international customer phone as a
  permanent input failure so the durable webhook worker marks it dead instead
  of retrying forever. A valid foreign E.164 sender proceeds normally. Log only
  a redacted suffix plus provider/message IDs.
- Add stable codes in `backend/app/core/error_codes.py` and use the project's
  structured error helper. Update `apiRequest()` only as needed to surface that
  envelope consistently.
- **Verify:** API integration tests cover unauthenticated (`401`), no selected
  tenant (`403`), create (`201`), invalid phone (`422`), same-tenant duplicate
  (`409`), cross-tenant reuse (`201`), and audit actor/source attribution.

### Phase E — Clientes creation experience

- Add `ContactCreateInput` and `createContact()` to the existing frontend
  types/API modules.
- Add a compact reusable dialog under `frontend/src/components/ontology/` with:
  - **Nome** text input;
  - **Celular / WhatsApp** international telephone input with a searchable
    country selector, Brazil selected initially, and `inputMode="tel"`;
  - a hint that foreign customers require the correct country calling code;
  - accessible labels, inline validation, cancel, and submit actions;
  - no level/address/place fields in this first flow.
- Add a primary **Novo cliente** button beside the existing list actions. Keep
  mobile layout stacked and touch-friendly.
- Follow the project optimistic-UI rule:
  1. create a temporary row from the normalized-looking form values and close
     the dialog immediately;
  2. call `POST /api/contacts`;
  3. replace the temporary ID/row with the server response on success;
  4. remove it and restore the form values with an inline/notice error on
     failure.
- On a `409`, explain in pt-BR that the WhatsApp number is already registered.
  Refetch contacts after rollback so a concurrent webhook-created customer is
  visible. Do not overwrite or merge the existing record.
- Reset pagination/search behavior deliberately: after success, clear a filter
  that would hide the new row or show a success notice explaining where it was
  added.
- Render stored E.164 values in the appropriate international/national display
  format for their region while keeping `tel:`/future `wa.me` values canonical.
- **Verify:** component/page tests cover required fields, masking, optimistic
  insertion/replacement, generic rollback, duplicate rollback/refetch, keyboard
  focus, and a narrow mobile viewport.

### Phase F — Documentation and release gate

- Update `docs/pages/clientes.md`, `docs/business_rules.md`, and
  `docs/data_architecture.md` with the create action, canonical-phone invariant,
  endpoint, audit event, and schema constraint.
- Keep the root README link to this roadmap and update its status only after
  implementation is actually complete.
- Run backend formatting/static checks already used by the project, the focused
  tests, then the regression suite in `conda` env `agenda`.
- Run frontend lint/build/tests from `frontend/`, respecting its generated
  Next.js instructions.
- **Verify:** all release checks pass, or every pre-existing unrelated failure
  is documented with a clean-tree reproduction.

## 8. Required test matrix

| Layer | Scenario | Expected result |
|---|---|---|
| Phone unit | National, formatted, and E.164 forms of one BR mobile | Same E.164 value |
| Phone unit | Valid mobiles from representative foreign regions with calling code | Accepted as E.164 |
| Phone unit | Definite landline, missing BR DDD, foreign local format without country context, malformed/impossible number | Rejected |
| Phone unit | Valid `FIXED_LINE_OR_MOBILE` region | Accepted because metadata cannot distinguish |
| Database | Same tenant + same canonical phone | Unique violation |
| Database | Different tenants + same canonical phone | Allowed |
| API | Valid manual create | `201`, canonical phone, normalized name, audit event |
| API | Duplicate formatting variant | `409`, original contact unchanged |
| API | Invalid input or missing name/phone | `422`, no contact/event |
| API security | No session / no selected tenant | `401` / `403` |
| Ingestion | Manual contact then WhatsApp message | Existing contact/conversation used |
| Ingestion | Manual name then different WhatsApp profile name | Manual name retained |
| Ingestion | Placeholder phone-name then WhatsApp profile name | Profile name backfilled |
| Concurrency | Two new messages for one phone | One contact; both unique messages persist |
| Concurrency | Manual create races first WhatsApp event | One contact; no message lost |
| Webhook worker | Valid foreign sender | Contact/message ingested normally |
| Webhook worker | Invalid international sender | Receipt ends terminally; no retry loop/contact |
| Frontend | Successful create | Optimistic row replaced by server row |
| Frontend | Duplicate or server failure | Optimistic row removed; form/error restored |

The ingestion race tests must use separate database sessions/transactions; two
sequential calls do not prove the unique constraint and conflict path are safe.

## 9. Rollout plan

1. Complete Phases A–F locally against `agenda_db`; do not point migrations or
   remediation commands at Azure.
2. Run the aggregate preflight on a recent local copy of production data if
   available.
3. Request explicit approval for a read-only production preflight. Record only
   counts and opaque IDs; do not expose customer phone numbers in logs or the
   roadmap.
4. If preflight is not clean, stop the release. Resolve invalid values and
   duplicates through a separately reviewed, backup-first procedure.
5. Back up production, confirm the Alembic revision/head, and rehearse the
   upgrade on a restored local copy.
6. Deploy the migration and compatible backend before exposing the frontend
   button. For the current small dataset, a normal unique constraint is likely
   sufficient; re-evaluate lock strategy from actual production row count
   before execution.
7. Smoke-test in a test tenant:
   - create a customer using formatted national input;
   - confirm canonical storage and one `contact.created` event;
   - submit a formatting-equivalent duplicate and confirm `409`;
   - ingest a provider-shaped event for that canonical phone and confirm it
     attaches to the same contact.
8. Monitor structured `409`, phone-validation, dead-webhook, and contact-create
   counts by tenant without logging raw phones.

Rollback the UI/API release if needed, but do not automatically reverse the
phone canonicalization in production. The unique/non-null constraints protect
data and are compatible with old reads; any schema downgrade requires a
separately reviewed decision.

## 10. Definition of done

- Every supported contact-creation path calls the shared phone boundary.
- `contacts.phone` is canonical and non-null for every row.
- The tenant/phone unique constraint exists in both migration and ORM metadata.
- Manual duplicate submissions are deterministic `409` responses.
- WhatsApp reuses a manually registered contact, including under concurrency.
- Manual names are not overwritten by later profile names.
- Creation is tenant-scoped, CSRF/origin protected, and audited with the
  correct actor and source channel.
- The optimistic UI succeeds instantly on the happy path and rolls back
  cleanly on failure.
- Focused, integration, concurrency, security, and frontend tests pass.
- Clientes, business-rule, data-architecture, and README documentation match
  the shipped behavior.

## 11. Product confirmations before implementation

The roadmap recommends these defaults; confirm them before coding if product
intent differs:

1. Mobile numbers from any country are accepted. Brazil is the default form
   region; foreign numbers require a country calling code. Definite landlines
   are rejected, while `FIXED_LINE_OR_MOBILE` is accepted where metadata cannot
   reliably distinguish the type.
2. Customer phone is immutable in v0.1. Corrections happen through a future
   dedicated identity-change flow, not the generic contact patch.
3. A duplicate form submission shows an error and preserves the existing
   customer; it never merges or updates names automatically.

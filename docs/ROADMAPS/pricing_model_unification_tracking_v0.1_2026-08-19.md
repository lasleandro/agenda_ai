# Pricing Model Unification — Impact Tracking v0.1

**Status: All phases complete — persistence, resolver/API/schema rework, and legacy store cleanup.**
**Date: 2026-08-19**

## 1. Decision being tracked

Unify the three pricing stores into a single rate matrix with the shape:

```
rate(professional_id, place_id NULLABLE, time_category, participant_count) → cents
```

- `place_id = NULL` is the universal default (replaces both "Valores globais"
  and "Padrão — sem local definido").
- `time_category ∈ {regular, prime}` and `participant_count ∈ {1..4}` always.
- The 8-cell regular/prime matrix is the default shape. A "same price for
  regular and prime" toggle in the UI mirrors one row into the other.

This document maps **every** consumer of the three current stores and what
changes for each. It is the source of truth for planning the migration; it
does not yet prescribe implementation order.

---

## 2. Current data model — three stores

| Store | Table / column | Key | Shape | Notes |
|---|---|---|---|---|
| Global rates | `financial_rates` (`FinancialRate`) | `(professional_id, participant_count)` | 4 cells (1–4), **no** time category | Non-null `hourly_rate_cents` |
| "No place" default | `professional_financial_settings.generic_place_rates` (JSONB) | JSON keys `"regular-1".."prime-4"` | 8 cells, nulls omitted | Stored as `str` keys; parsed with `key.split("-")` |
| Per-place rates | `place_financial_rates` (`PlaceFinancialRate`) | `(professional_id, place_id, time_category, participant_count)` | 8 cells per place, nulls omitted | Sparse — only explicit overrides exist |

`ProfessionalFinancialSettings` also carries non-pricing fields that are out of
scope for this rework but are read alongside rates:
`default_commercial_status`, `currency`, `prime_time_configured`,
`cancellation_notice_hours`.

---

## 3. Current resolution semantics

Two independent chains must not be confused:

### 3.1 Commercial status chain (`financial_resolver.resolve_commercial_status`)

`customer → group → tenant` (unaffected by this rework).

### 3.2 Hourly-rate chain (two implementations)

**A. `PricingRules.resolve`** (used by analytics, revenue, makeup recommender):

```python
place_id is not None:
    place_rates[(place_id, cat, n)]  →  global_rates[n]  →  None
place_id is None:
    generic_place_rates[(cat, n)]    →  global_rates[n]  →  None
```

**B. `_participant_rate`** (revenue occurrence snapshots), with a *four-level*
precedence before pricing rules:

```python
customer rate → group rate → place rate → generic rate (only if no place)
              → global rate → None
```

Note the asymmetry already flagged in prior discussion: **per-place falls back
to `global`, not to `generic`**. `generic` only applies when `place_id IS NULL`.

### 3.3 Customer/group detail quirk

`_customer_detail` / `_group_detail` query `PlaceFinancialRate` with
`time_category == "regular"` **only**. They never consider prime, because these
detail endpoints are place- and time-agnostic. This is a pre-existing
simplification to preserve during the rework.

---

## 4. Backend consumer inventory

### 4.1 `services/financial_capacity.py` — the canonical resolver

| Symbol | Reads | Change |
|---|---|---|
| `PricingRules` dataclass | 3 dict fields (`global_rates`, `place_rates`, `generic_place_rates`) | Replace with a single `rates: dict[(place_id \| None, cat, n), int]` |
| `PricingRules.resolve(place_id, cat, n)` | 3-level fallback | Simplify to `rates[(place_id, cat, n)]` then `rates[(None, cat, n)]` |
| `load_pricing_rules(db, professional_id)` | `FinancialRate`, `PlaceFinancialRate`, `settings.generic_place_rates` | Read one table; `NULL` place rows become the default |

### 4.2 `services/financial_resolver.py` — customer/group override chain

| Symbol | Reads | Change |
|---|---|---|
| `get_global_hourly_rate(db, pid, n)` | `FinancialRate` | Must resolve the `NULL`-place default row for `regular` (or accept a `time_category` arg). This function is time-agnostic; it should read the `regular` row of the default matrix. |
| `resolve_hourly_rate(...)` | takes `place_rate_cents`, `tenant_rate_cents` | Signature unchanged; callers supply the resolved place/default values. |

### 4.3 `api/financial.py` — routes

| Route / helper | Reads/Writes | Change |
|---|---|---|
| `_customer_detail` | `PlaceFinancialRate` (regular only), `get_global_hourly_rate` | Point at unified store; keep regular-only lookup. |
| `_group_detail` | same | same |
| `_configuration_detail` | `FinancialRate` + `PlaceFinancialRate` + `generic_place_rates` → builds `FinancialConfigurationDetail` | Build from one store. `generic_place` matrix becomes the `NULL`-place matrix; `places` matrices read `place_id != NULL`. `source` values `generic`/`tenant` collapse. |
| `GET /settings` | `FinancialRate` (4 cells) | **Replace or retire.** The global 4-cell matrix no longer exists as a separate concept. |
| `PATCH /settings` | upserts/deletes `FinancialRate` | **Replace or retire.** `default_commercial_status` stays here (or moves to a commercial settings endpoint). Rates move to the matrix endpoint. |
| `GET /configuration` | `_configuration_detail` | Shape changes only (see 4.3 above). |
| `POST /quote` | `get_global_hourly_rate`, `PlaceFinancialRate`, `configuration.generic_place.rates` | Rewrite resolution: `place → NULL default → None` with no separate `global` step. |
| `PUT /generic-place/rates` | writes `settings.generic_place_rates` JSONB | Becomes `PUT /rates/default` (or similar) writing `NULL`-place rows in the unified table. |
| `PUT /places/{place_id}/rates` | deletes+reinserts `PlaceFinancialRate` | Write `place_id = {id}` rows in the unified table. |

### 4.4 `api/places.py` — place deletion

| Location | Change |
|---|---|
| `db.query(PlaceFinancialRate).filter(place_id == ...).delete()` | Point at the unified table's `place_id` column. Keep cascade behavior (deleting a place removes its rate overrides). |

### 4.5 `services/financial_analytics.py` — scenarios / tradeoffs / simulation

Reads `PricingRules` only through `_resolve_rate` → `pricing.resolve`. No
direct table access. **No change required** once `PricingRules.resolve`
is updated, because all call sites pass `segment.place_id` (which may be
`None` for unattributed capacity) and `time_category`.

### 4.6 `services/revenue_occurrences.py` — recognized-revenue snapshots

| Location | Change |
|---|---|
| `_participant_rate` | Rewrite: customer → group → `pricing.resolve(place_id, cat, n)` (which now internally falls to the NULL default). The separate `generic` branch disappears; the returned `source` collapses `generic`/`tenant` into one label. |
| `preview_schedule_revenue` / `create_revenue_occurrence` | `pricing.resolve(place_id, cat, 4)` for capacity revenue — unchanged call shape. |

**Important:** `RevenueOccurrenceLine.rate_source` is an *immutable snapshot*
stored at recognition time. Its enum (`RevenueRateSource`, see 6.1) currently
includes `generic` and `tenant`. Historical rows keep their stored value; the
enum must keep accepting the legacy value (or map it) so old snapshots remain
readable.

### 4.7 `services/makeup_recommender.py`

Uses `pricing.resolve(place.id, segment.time_category, participant_count=1)`
for a cost score. **No change required** — it already goes through the
`PricingRules` abstraction.

---

## 5. Frontend consumer inventory

| File | Reads/Writes | Change |
|---|---|---|
| `lib/types.ts` | `FinancialSettingsDetail` (4-cell `rates`), `GenericPlaceRateMatrixDetail`, `PlaceRateMatrixDetail`, `FinancialConfigurationDetail` | Replace `FinancialSettingsDetail.rates` with the unified default matrix; `generic_place` and `places` become the same `PlaceRateMatrixDetail` shape (one with `place_id = null`, others with real ids). |
| `lib/api.ts` | `fetchFinancialSettings`, `updateFinancialSettings`, `fetchFinancialConfiguration`, `replaceGenericPlaceRates`, `replacePlaceRates` | Retire `updateFinancialSettings`'s `rates` field (keep `default_commercial_status`), replace `replaceGenericPlaceRates` with a `replaceDefaultRates` against the NULL row. |
| `app/(protected)/minhas-regras/page.tsx` | composes `GlobalRatesSection` + `PlaceRatesSection` | Replace with a single `PrecificacaoSection` (see below). |
| `components/financial/global-rates-section.tsx` | 4-cell editor + `default_commercial_status` | **Absorbed.** Move `default_commercial_status` out; rates become the 8-cell default matrix with mirror toggle. |
| `components/financial/place-rates-section.tsx` | dropdown + `GenericPlaceRateEditor` + `PlaceRateEditor` | The dropdown's "Padrão" option becomes the default matrix (same editor, 8 cells); per-place selection stays. |
| `app/(protected)/financeiro/page.tsx` | fetches settings + configuration for dashboard/simulator | Keep fetching configuration; settings only needed for `default_commercial_status`. |
| `components/financial/financial-simulator.tsx` | `configuredRate`: place → generic → settings.rates | Simplify: place → NULL default (both via `configuration`). |
| `app/(protected)/places/[id]/page.tsx` | per-place `PlaceRateEditor` via `configuration.places` | Unchanged except type/endpoint. |

The "replication UI tool" (auto-mirror regular ↔ prime) is purely presentational:
it writes the same value to both `regular` and `prime` rows. No backend
semantics change.

---

## 6. Schema, enum, and audit changes

### 6.1 Schemas (`schemas/financial.py`)

| Schema | Change |
|---|---|
| `GlobalRateInput` / `GlobalRateDetail` | Retire (the 4-cell global concept disappears). |
| `FinancialSettingsDetail.rates` | Remove `rates`; keep `default_commercial_status`, `currency`. |
| `FinancialSettingsUpdate.rates` | Remove `rates`. |
| `PlaceRateDetail.source` | Collapse `Literal["generic","tenant"]` → single `"default"` (or keep legacy values for read compatibility). |
| `RevenueRateSource` | Keep `generic` + `tenant` as accepted values for legacy snapshots; new writes use the collapsed label. |
| `GenericPlaceRateMatrixDetail` | Retire; use `PlaceRateMatrixDetail` with `place_id: UUID \| None`. |

### 6.2 Audit trail (`services/financial_audit.add_financial_audit`)

Current `entity_type` values in use: `tenant_financial_settings`,
`generic_place_financial_rates`, `place_financial_rates`,
`prime_time_windows`.

- `generic_place_financial_rates` and `place_financial_rates` collapse to one
  `entity_type` (e.g. `financial_rates`) with `entity_id` = `place_id or
  professional_id`.
- Historical audit rows keep their original `entity_type`; the UI/query layer
  (if any) must handle both.
- No audit loss is acceptable: the rework must still log before/after for every
  rate write.

### 6.3 Models

| Model | Change |
|---|---|
| `FinancialRate` | Retire (drop or repurpose into the unified table). |
| `PlaceFinancialRate` | Add `place_id` nullable (rename to a neutral `FinancialRate` with nullable `place_id` + `time_category`). |
| `ProfessionalFinancialSettings.generic_place_rates` | Drop JSONB column; default rates move to the unified table's NULL rows. |

---

## 7. Data migration sketch (for later refinement)

1. Create the unified table (or alter `place_financial_rates` to allow
   `place_id NULL`).
2. Backfill NULL rows from `financial_rates`: for each `participant_count`,
   write both `regular` and `prime` rows with that value (this is exactly the
   "mirror" — the current global layer is time-agnostic, so mirroring is the
   only faithful mapping).
3. Backfill NULL rows from `generic_place_rates` JSON where an explicit
   regular/prime value exists (these override step 2 per cell).
4. Move `place_financial_rates` rows as-is (place-specific).
5. Verify fallback invariants with a data-check script (add to `scripts/`).
6. Drop `financial_rates` and `generic_place_rates` after verification.

The net semantic effect on existing tenants is **zero** for the common cases
(global-only and place-override behavior is preserved), and *more* expressive
for the "sem local" case (which currently has prime splits that the global
layer did not).

---

## 8. Gotchas and open questions

1. **`get_global_hourly_rate` is time-agnostic.** Several call sites only know
   "a participant count", not a time category. They must default to the
   `regular` row of the NULL matrix. Confirm this is the intended behavior for
   customer/group detail cards.
2. **`source` label semantics in revenue snapshots.** Historical rows store
   `generic`/`tenant`. Decide whether to keep both labels on read or normalize
   them in the new resolver.
3. **`PATCH /settings` currently mixes `default_commercial_status` and rates.**
   We are separating them. Decide where `default_commercial_status` lives:
   keep `/settings` (rates removed) or move to a dedicated commercial endpoint.
4. **Prime-time windows are the third pricing input.** This doc scopes only
   rates; prime-time stays its own store/endpoint unless explicitly folded in.
5. **Tests to update:** `test_financial.py`, `test_revenue.py`,
   `test_makeup_credits.py` all seed `FinancialRate` / `PlaceFinancialRate`
   fixtures and assert `rate_source` strings. They will need fixture + assertion
   changes.
6. **Feature flag:** all of this remains behind `commercial_financials`. The
   unified model must not leak pricing config to tenants without the flag.

---

## 9. Open decision to confirm before implementation

- **Collapse label:** should the unified default be called "default" (replacing
  both "tenant"/"generic"), and should we keep legacy `rate_source` values
  readable? (Recommendation: yes — one label going forward, legacy accepted on
  read.)
- **Where `default_commercial_status` lives after the split.** (Recommendation:
  keep it on `GET/PATCH /settings`, remove only `rates`.)

---

## 10. Phase 1 — Unified persistence (complete 2026-08-19)

**Scope decision (confirmed with owner):** persistence only. Zero behavior
change. Resolver/API/frontend rework is Phase 2+.

**Table strategy decision (confirmed with owner):** alter
`place_financial_rates` in place — `place_id` made nullable — instead of
creating a new table. The table already had the exact 8-cell unified shape and
unique constraint; per-place rows needed no data move.

### What changed

| File | Change |
|---|---|
| `backend/app/models/place_financial_rate.py` | `place_id` now `nullable=True`; docstring updated to describe the unified matrix. |
| `backend/migrations/versions/6843aae760e3_unify_financial_rate_store.py` | New migration: nullable `place_id`, partial unique index, backfill. |
| `scripts/verify_pricing_unification.py` | New read-only verification script (coverage, equivalence, integrity). |

### Migration details

- Partial unique index `uq_place_financial_rates_default` on
  `(professional_id, time_category, participant_count) WHERE place_id IS NULL`.
  **Required correctness detail beyond the §7 sketch:** plain Postgres unique
  constraints treat NULLs as distinct, so `uq_place_financial_rates_rule`
  alone would allow duplicate default rows. The partial index enforces the
  unified resolution invariant (at most one default row per cell) and is the
  conflict target for the idempotent backfill.
- Backfill order (both steps idempotent via `ON CONFLICT`):
  1. Mirror `financial_rates` → `regular` + `prime` NULL rows per participant
     count (the global layer is time-agnostic, so mirroring is faithful).
  2. Override per cell from `generic_place_rates` JSONB where present.
- Per-place rows moved as-is (already in the table).
- Downgrade deletes the NULL rows, drops the index, restores `NOT NULL`.

### Verification results (local `agenda_db`)

`scripts/verify_pricing_unification.py` — all checks pass:

| Store | Rows |
|---|---|
| Legacy `financial_rates` | 1 |
| Legacy `generic_place_rates` cells | 8 |
| Legacy `place_financial_rates` | 16 |
| Unified default (`place_id IS NULL`) | 10 |
| Unified per-place | 16 |

Coverage (every legacy row has a unified counterpart), equivalence (legacy
resolution chains produce identical cents to the unified chain for every
`(place_id, category, participant_count)` combination), and integrity (no
duplicate default cells) all hold. Up/down/up cycle re-verified.

`alembic check` reports only **pre-existing** drift unrelated to this work
(`spatial_ref_sys`, `created_at`/`updated_at` nullability across many tables,
orphaned indexes on `waitlist_entries` / `work_journey_intervals` /
`financial_change_audit_logs`, trgm index on `contacts`). None touch
`place_financial_rates`. Flagged, not fixed (out of scope).

### Test suite

`pytest tests/` on local DB: **206 passed, 5 failed**. The 5 failures are all
in `test_makeup_credits.py` and are **pre-existing** — identical failures
reproduced on the clean baseline (model change stashed + migration downgraded,
i.e. old code + old DB). Not caused by Phase 1. Recommended to track
separately.

### Next phase (2 — backend services & schemas)

Per §4/§6: rework `PricingRules` + `load_pricing_rules`
(`services/financial_capacity.py`), `get_global_hourly_rate` /
(`resolve_hourly_rate` (`services/financial_resolver.py`),
`_participant_rate` (`services/revenue_occurrences.py`), schemas
(`schemas/financial.py`, keep legacy `RevenueRateSource` values readable),
and audit `entity_type` collapse (§6.2, no audit loss). Open decisions from
§9 land there.

---

## 11. Phase 2 — Resolver, API, and schema rework (complete 2026-08-19)

**Decisions confirmed (per §9 recommendations):**
- Collapse label: new writes use `"default"`; legacy `"generic"`/`"tenant"`
  remain accepted `RevenueRateSource` values for historical
  `RevenueOccurrenceLine` snapshots (never normalized on read).
- `default_commercial_status` stays on `GET`/`PATCH /api/financial/settings`;
  the retired 4-cell `rates` field was removed from both.

### Backend changes

| File | Change |
|---|---|
| `services/financial_capacity.py` | `PricingRules` now holds a single `rates: dict[(place_id \| None, cat, n), int]`; `resolve()` is `explicit place cell → NULL default cell → None`. `load_pricing_rules` reads only `PlaceFinancialRate`. |
| `services/financial_resolver.py` | `get_global_hourly_rate` reads the unified `place_id IS NULL` row (added optional `time_category` param, defaults to `"regular"` for the time-agnostic customer/group detail callers per §8.1). `resolve_hourly_rate` signature unchanged. |
| `services/revenue_occurrences.py` | `_participant_rate` rewritten: customer → group → place cell → NULL default cell → `"unset"`. New default resolutions are labeled `"default"` (not `"generic"`/`"tenant"`). |
| `schemas/financial.py` | Retired `GlobalRateInput`/`GlobalRateDetail`/`GenericPlaceRateMatrixDetail`. `FinancialSettingsDetail`/`Update` dropped `rates`. `PlaceRateMatrixDetail.place_id` is now `UUID \| None` (used for both the default row and per-place rows). `PlaceRateDetail.source` and `PricingQuoteSegment.source` collapsed to `Literal["place", "default", "unset"]`. `RevenueRateSource` gained `"default"` (keeps `"generic"`/`"tenant"` for legacy reads). |
| `api/financial.py` | `_configuration_detail` now builds both the default matrix and per-place matrices from one query against `PlaceFinancialRate`; `FinancialConfigurationDetail.default_rates` replaces `.generic_place`. `GET`/`PATCH /settings` dropped `rates`. `POST /quote` resolves `place → NULL default → None` (no separate global step) — fixed a NULL-vs-`IN` SQL pitfall (`place_id.in_([None, None])` never matches NULL rows; must use `place_id.is_(None)` via `or_()`). `PUT /generic-place/rates` renamed to `PUT /rates/default`, writing `place_id = NULL` rows directly (no more JSONB). Audit `entity_type` for both default-rate and per-place-rate writes collapsed to `"financial_rates"`. |
| `api/places.py` | No change needed — already deletes `PlaceFinancialRate` rows scoped by `place_id`, which is unaffected by the resolver rework. |
| `services/financial_analytics.py`, `services/makeup_recommender.py` | No change — both already went through `PricingRules.resolve()`. |

### Migration: `dc0d10e10deb_allow_default_rate_source`

Discovered mid-implementation: `revenue_occurrence_lines` has a DB-level
`ck_revenue_occurrence_lines_source` CHECK constraint listing allowed
`rate_source` values. It only ever allowed `customer/group/place/tenant/unset`
— **`"generic"` was never actually persistable**, so the pre-unification
"place has no override → try generic (no-place matrix) → fall back to
global" path would have hit this same `IntegrityError` had a real request
ever exercised the generic-with-a-place-set-appointment case. Since
`"generic"` never made it to the DB, no backfill was needed — the migration
just widens the constraint to also allow `"default"`.

### Test suite

`pytest tests/` on local DB: **206 passed, 5 failed** — the same 5
pre-existing `test_makeup_credits.py` failures tracked in §10 (unrelated to
this work). `test_financial.py` and `test_revenue.py` updated: settings/rates
calls split into `PATCH /settings` (status only) + `PUT /rates/default`
(rates); `"generic"`/`"tenant"` source assertions changed to `"default"`;
fixtures that seeded `FinancialRate` rows now seed unified `place_id=NULL`
`PlaceFinancialRate` rows instead (mirroring both `regular` and `prime` where
the old test relied on a category-agnostic global fallback).

### Frontend changes

| File | Change |
|---|---|
| `lib/types.ts` | Removed `GlobalRateDetail`, `GenericPlaceRateMatrixDetail`; `FinancialSettingsDetail` dropped `rates`; `PlaceRateMatrixDetail.place_id` is `string \| null`; `PlaceRateDetail.source`/`RevenueRateSource` updated to match the backend collapse. |
| `lib/api.ts` | `updateFinancialSettings` body dropped `rates`; `replaceGenericPlaceRates` renamed to `replaceDefaultRates` (`PUT /api/financial/rates/default`). |
| `components/financial/global-rates-section.tsx` | Stripped the 4-cell rate editor; now only edits `default_commercial_status`. |
| `components/financial/place-rates-section.tsx` | `GenericPlaceRateEditor` renamed `DefaultRateEditor`; `PlaceRatesSection` props renamed `defaultRates`/`onDefaultSaved` (was `genericPlace`/`onGenericSaved`), backed by the unified `place_id = null` matrix. |
| `app/(protected)/minhas-regras/page.tsx` | Wired to the renamed props/fields above. |
| `components/financial/financial-simulator.tsx` | `configuredRate` simplified to `place → NULL default (via configuration.default_rates) → null`; the old three-tier place/generic/settings-global fallback is gone. |
| `components/financial/financial-dashboard-section.tsx`, `components/financial/revenue-section.tsx` | Minor type-follow fixes (nullable `place_id`, added `"default"` source label). |

No separate "replication UI tool" (mirror regular↔prime) was added in this
pass — out of scope for Phase 2's resolver/schema rework; the 8-cell editor
already lets the user set both rows manually.

### Deferred to a later phase

- Dropping the now-unused `financial_rates` table and
  `professional_financial_settings.generic_place_rates` JSONB column (§7
  step 6) — left in place; nothing in the app reads or writes them anymore.
- Normalizing historical `"generic"`/`"tenant"` `rate_source` values to
  `"default"` — intentionally not done (§9 recommendation: keep legacy
  values readable, no rewrite of historical snapshots).

---

## 12. Phase 3 — Legacy store cleanup (complete 2026-08-19)

**Scope:** remove the now-dead legacy pricing storage that Phase 2 stopped
reading and writing, per §7 step 6.

**Precondition note:** the plan below originally called for waiting through
a production stability window before this destructive change. This project
has no production deployment yet (local-only development per
`AGENTS.md` — "Develop locally, and sync local to remote new data
thereafter"), so that precondition doesn't apply here: there is no rollback
risk to a live tenant, and the local `agenda_db` was re-verified with
`scripts/verify_pricing_unification.py` immediately before dropping (see §10
results — coverage/equivalence/integrity all held going into this phase).
Owner confirmed proceeding immediately instead of waiting.

### What changed

| Item | Change |
|---|---|
| `financial_rates` table (`FinancialRate` model) | Dropped. Deleted `backend/app/models/financial_rate.py` and its export from `app/models/__init__.py`. |
| `professional_financial_settings.generic_place_rates` (JSONB column) | Dropped from the `ProfessionalFinancialSettings` model and via migration. |
| `scripts/verify_pricing_unification.py` | Repurposed (not retired) into a plain unified-table integrity check: at most one default (`place_id IS NULL`) row per cell, and every per-place row's `place_id` still references an existing `Place`. The legacy-vs-unified coverage/equivalence checks were removed since the legacy tables no longer exist. |
| `backend/migrations/versions/e62d256cf621_drop_legacy_pricing_stores.py` | New migration: `op.drop_column("professional_financial_settings", "generic_place_rates")` then `op.drop_table("financial_rates")`. Downgrade recreates both empty (shape only — the docstring calls out explicitly that data is not recoverable on downgrade). |
| `docs/business_rules.md` §3.2, `docs/data_architecture.md` §7 ER diagram | Updated to describe the single unified `PlaceFinancialRate` matrix; removed `FinancialRate` entity and references to a separate "generic-location" / "tenant-global" fallback tier. |
| `backend/app/models/place_financial_rate.py` | Docstring updated: "replacing" → "replaced ... both dropped", pointing at this doc. |
| `backend/tests/test_financial.py`, `backend/tests/test_makeup_credits.py` | Removed now-dead `FinancialRate` imports and cleanup queries (the fixtures already seeded the unified table directly since Phase 2). |

### Verification performed

- `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` cycle
  on the local DB: clean in both directions.
- `python scripts/verify_pricing_unification.py` after the upgrade: "All
  checks passed: no duplicate defaults, no orphaned rows" (12 default rows,
  16 per-place rows on the local dataset).
- `pytest tests/` on local DB: **200 passed, 11 failed**. Reconfirmed via
  `git stash` against the pre-Phase-2 baseline that all 11 failures are
  **pre-existing and unrelated to this work**: the 5 known
  `test_makeup_credits.py` failures (tracked since §10), plus 4 in
  `test_candidate_resolution.py` and 2 in `test_passive_escalation.py` that
  fail identically on the clean baseline — date-relative test flakiness,
  not caused by the pricing rework.
- Grepped the codebase for `FinancialRate` (bare) and `generic_place_rates`
  after the change: no remaining references outside migration history and
  historical roadmap prose (§1–§11 above, kept as-is for the record).

### Explicitly out of scope for Phase 3

- Normalizing historical `"generic"`/`"tenant"` `RevenueOccurrenceLine.rate_source`
  values to `"default"` — these remain accepted enum values indefinitely per
  the Phase 2 decision (§11); rewriting immutable historical snapshots is not
  planned.
- Any further resolver/API behavior changes — Phase 3 is schema cleanup only,
  zero behavior change (mirrors the Phase 1 framing in §10).

This closes out the pricing model unification effort tracked in this
document — all three phases (persistence, resolver/API/schema, legacy
cleanup) are complete.


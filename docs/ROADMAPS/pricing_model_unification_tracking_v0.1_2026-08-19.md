# Pricing Model Unification — Impact Tracking v0.1

**Status: analysis only — no code changed yet.**
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


# Capacity Evaluation & the Make-up Slot Recommender

Two different features compute "how busy/available is the instructor,"
for two different purposes, and they **don't share code** beyond one
common building block. This doc verifies both against the shipped
implementation (not a pre-implementation plan) and calls out where they
diverge.

| | Financial capacity dashboard | Make-up slot recommender |
|---|---|---|
| File | `app/services/financial_analytics.py` | `app/services/makeup_recommender.py` |
| Question it answers | "How utilized is my practice, and what would a different pricing/mix look like?" | "Where should I book this specific student's make-up class?" |
| Output | Aggregate occupancy %, revenue projections, what-if scenarios | A ranked top-5 list of concrete (date, place, time) candidates |
| Surface | Financeiro dashboard (`GET /api/financial/dashboard`, `/scenarios/evaluate`) | The AI assistant's `recommend_makeup_slots` tool |
| Built | Commercial/financial-module roadmap (pre-existing) | Make-up class credits roadmap, this session |

---

## Shared foundation: `build_capacity_segments`

Both features start from the same primitive:
`app/services/financial_capacity.py::build_capacity_segments(db,
professional_id, date_from, date_to, places, prime_ranges)`.

For every date in range, for every place, it computes:

```
net_ranges  = WorkJourneyInterval "work" rows for that weekday
              minus WorkJourneyInterval "break" rows for that weekday
place_ranges = active place-stay rows (`slot_kind="availability"`) at that
               place covering that weekday and effective date
               (via _load_place_availability_ranges, in scheduling.py)
capacity    = intersect(net_ranges, place_ranges)
```

Each resulting interval is then split at part-of-day boundaries
(morning/afternoon/evening) and prime-time boundaries
(`PrimeTimeWindow`), producing one `CapacitySegment` per (date, place,
sub-interval) with a `time_category` ("prime" | "regular") and
`part_of_day`.

**Important, easy-to-miss consequence:** named-place capacity here requires
*both* a configured work journey *and* an explicit active place stay covering
that time — a place with zero stay rows on a given
weekday contributes **zero** capacity for that weekday, regardless of how
broad the work journey is. This is a different (stricter) notion of
"available" than one-off appointment booking uses: `propose_create_appointment`
/ `assert_no_conflict` (`app/services/appointments.py`) only checks the
real conflicts and uses work journey only as an advisory — it does **not** require a
pre-declared `RecurringSlot` window. So a time slot can be legitimately
bookable via chat/dashboard, including an explicitly confirmed journey
exception, while still showing as zero capacity in the
named-place Financeiro breakdown and invisible to the recommender if no
stay covers it. Financeiro still retains that time as generic capacity under
`Sem local definido`; the recommender omits it because a concrete recommendation
must identify a real place. If make-up recommendations feel sparser than
expected, configure a place stay for that place/time.

---

## 1. Financial Capacity Dashboard (`build_financial_dashboard`)

Entry point: `app/services/financial_analytics.py::build_financial_dashboard(db, professional_id, date_from, date_to, place_ids?)`, called from `GET /api/financial/dashboard`.

### What it computes

1. **Available/booked minutes come from two different sources**, per
   `docs/business_rules.md` §3.5:
   - **Top-line** `available_minutes`/`booked_minutes` (and therefore the
     top-line `occupancy_pct`/`unused_minutes`) are place-agnostic:
     `available_minutes` is `total_work_journey_minutes` — the raw Work
     Journey (work minus break intervals) summed over the range, with no
     `RecurringSlot` requirement — and `booked_minutes` is the raw sum of
     every booked occurrence's duration, uncapped to any capacity segment.
   - **Per-bucket breakdowns** (`by_place`, `by_weekday`, `by_part_of_day`,
     `by_time_category`, and the daily `time_series`) still use
     `CapacitySegment.duration_minutes` from `build_capacity_segments`,
     which **does** require a `RecurringSlot` at that place/weekday (see
     the capacity caveat above) — a booking's time range is split the same
     way (prime/part-of-day boundaries) and **overlapped against the
     capacity segments** for that exact (date, place) via
     `_capacity_overlap`, so booked time outside any capacity segment
     contributes to a bucket's `booked_minutes` but not its
     `available_minutes`.
   - This split exists because top-line occupancy was found to collapse
     to a misleadingly high number for tenants who hadn't fully declared
     per-place `RecurringSlot` availability — see `docs/business_rules.md`
     §3.5 for the full rationale.
2. **Projected revenue** — for each booked segment, resolves a rate via
   `PricingRules.resolve(place_id, time_category, participant_count)`
   and multiplies by duration; bookings with no resolvable rate are
   counted (`unpriced_booking_count`) but contribute 0 revenue, not an
   error. Top-line `projected_revenue_cents` sums every booking
   regardless of capacity overlap (always has, unaffected by the split
   above).
3. **`occupancy_pct`** — `booked_minutes / available_minutes * 100`,
   rounded to 1 decimal, `0` if `available_minutes` is `0`. The top-line
   value and each per-bucket value are computed independently from their
   respective sources (see point 1) — a per-bucket `occupancy_pct` can
   still exceed 100% in principle, since bucket-level bookings aren't
   clipped to their capacity segment.
4. **Observed participant mix** — how booked minutes are distributed
   across participant counts (1 vs 2 vs 3 vs 4), normalized to
   percentages; used as the default mix for what-if scenarios.
5. **Capacity presets** — three fixed reference points computed at
   100% occupancy for comparison: "all individual," "observed demand,"
   "full groups of 4." Unlike the per-bucket breakdowns, these also fold
   in Work Journey time that falls outside any place's `RecurringSlot`
   coverage (`build_uncovered_capacity_minutes`), priced against the
   **generic-location regular/prime matrix** with tenant-global fallback —
   see `docs/business_rules.md` §3.5. Only applies to the unfiltered "all
   places" view.
6. **Capacity sources** — `capacity_sources` reconciles the observed-demand
   preset into `Em locais definidos` and `Sem local definido`. Each source
   reports its capacity minutes and revenue contribution; the two values add
   exactly to the month capacity headline. A place-filtered request reports a
   zero generic contribution rather than assigning unattributed time to the
   selected place.

### What-if scenarios (`evaluate_financial_scenario`)

Takes a participant mix (`all_individual` | `full_groups` | `observed_demand`
| `custom`), an assumed `occupancy_pct`, and optional rate overrides, and
projects revenue at that hypothetical occupancy — same capacity segments
**plus the same uncovered-work-journey time as the capacity presets**,
different assumed utilization and pricing. Also computes
`_tradeoffs`: for each participant count 1–4, the capacity-weighted
average rate, full-class revenue, revenue vs. an individual class, and
the **break-even occupancy** (the occupancy % at which a group class
matches an individual class's revenue) — this powers the "is it worth
running groups vs. 1:1s" comparison in the Simulador tab.
`_tradeoffs` deliberately stays scoped to `RecurringSlot`-covered capacity
only (no uncovered-time credit) since it answers "of my configured
places/rates," not "at full potential."

### Explicitly excluded from this model

The dashboard's own `_assumptions()` states this outright (surfaced to
the frontend as `FinancialAnalyticsAssumptions.excluded_constraints`):
attendance/cancellations/no-shows, taxes/costs/delinquency, travel time
between places, and customer availability/preferences. It's a capacity
*ceiling* model, not a forecast net of real-world friction.

---

## 2. Make-up Slot Recommender (`recommend_makeup_slots`)

Entry point: `app/services/makeup_recommender.py::recommend_makeup_slots(db, professional_id, contact_id, *, max_recommendations=5, lookahead_days=14, flow_lookback_weeks=4, cost_weight=0.5, flow_weight=0.5)`, exposed as the agent tool of the same name.

Returns `[]` immediately if the contact has zero available make-up
credits (`get_available_credits_count`) or doesn't exist — no ranking
work happens for an ineligible contact.

### Step 1 — Candidate generation

- Resolves the contact's typical session length from their
  `RecurringSlotParticipant` memberships (most common duration among
  their groups, falling back to `Professional.default_duration_minutes`,
  then `60`), plus the set of places they usually attend
  (`preferred_places`) and their most common class `level`
  (`preferred_level`) — both feed bonuses in step 3.
- Window: **tomorrow through `lookahead_days` days out** (14 by default)
  — never today, never the past.
- Pulls `CapacitySegment`s (same shared foundation as §1 above — so the
  same "needs a `RecurringSlot` at that place/weekday" caveat applies
  here too) and existing bookings for the window, and subtracts booked
  intervals from each segment per (date, place).
- Every free sub-interval long enough for the contact's duration becomes
  one candidate, carrying its resolved hourly rate
  (`PricingRules.resolve(..., participant_count=1)` — always priced as
  if the make-up class is a 1:1, regardless of whether the original
  class was a group) and whether its place is one of the contact's
  preferred places.

### Step 2 — Historical "flow" score

`_compute_flow_ratios`: over the trailing `flow_lookback_weeks` (4 by
default, ending yesterday), buckets every past schedule occurrence
(`list_schedule_occurrences`, including cancelled/no-show ones — the
bucket cares about historical demand at that time slot, not whether it
ultimately happened) by `(weekday, hour-of-day)`, and computes
`total_participants / total_hours` for that bucket — participants-per-hour,
not a percentage. **Lower ratio = historically quieter = scores better.**
A candidate whose `(weekday, start_hour)` never appeared in the lookback
window gets no flow ratio at all (falls through to the default midpoint
score in step 3, not a computed one).

### Step 3 — Combine into `combined_score` (0–100, higher = better)

For every candidate, independently for cost and flow:

```
percentile_rank(value, all_values) =
    (count of values in the candidate pool strictly greater than `value`)
    / (pool size) * 100
```

i.e. a **percentile rank among this batch's own candidates**, not
against any absolute/historical scale — the same slot could score
differently on a different day just because the *other* available slots
that day changed.

- **`cost_score`** = percentile rank of `hourly_rate_cents` among all
  priced candidates (cheaper ranks higher), **+5 flat bonus** if the
  slot's `time_category` is `"regular"` (not `"prime"`) and it has a
  resolvable rate — a deliberate nudge to keep prime-time capacity free
  for full-price bookings rather than free make-ups. Candidates with no
  resolvable rate default to `50.0` (the exact middle), neither
  penalized nor rewarded for being unpriced.
- **`flow_score`** = percentile rank of the flow ratio among all
  candidates that have one (also defaults to `50.0` if this candidate's
  bucket has no historical data).
- **`place_bonus`** = flat `+5` if the candidate's place is one of the
  contact's preferred places (from step 1), `0` otherwise — a bonus, not
  an exclusion; non-preferred places are still fully eligible and are
  simply sorted after preferred ones as a tie-break during candidate
  generation.
- **`level_bonus`** = flat `+5` if the candidate's time range overlaps an
  *active* `RecurringSlot` at the same place/weekday whose `level`
  matches the contact's `preferred_level` (`_level_matches`), `0`
  otherwise (including when the contact has no `preferred_level` at
  all). Also a bonus, not an exclusion or a penalty for a level
  mismatch — a candidate next to a *different*-level class scores the
  same as one next to no class at all.
- **`combined_score = cost_weight * cost_score + flow_weight * flow_score
  + place_bonus + level_bonus`** — with the 0.5/0.5 defaults and the
  three flat +5 bonuses, the theoretical max is 110, though
  `cost_score`/`flow_score` are each individually capped at 100 before
  combining.

Candidates are sorted descending by `combined_score` and the top
`max_recommendations` (5 by default) are returned, each carrying its
`date`, `place_id`/`place_name`, `start_time`/`end_time`,
`time_category`, `part_of_day`, `hourly_rate_cents`, `level_match`
(bool), and the three scores (`cost_score`, `flow_score`,
`combined_score` — note `level_bonus` itself isn't returned separately,
only folded into `combined_score`) — the agent receives these directly
and can use them to explain the ranking to the instructor, but the
*choice* of which one to book always goes through `list_makeup_credits`
→ `propose_redeem_makeup_credit` for confirmation, same as every other
write in this app.

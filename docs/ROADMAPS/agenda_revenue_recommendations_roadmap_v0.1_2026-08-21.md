# Agenda Revenue Recommendations Roadmap v0.1 — 2026-08-21

**Status: proposed for product review.**

## 1. Product direction

Add a read-only recommendation layer to the Agenda that helps an instructor
improve revenue without silently changing bookings, prices, or customer terms.
Recommendations are attached to a concrete dated occurrence or open interval
when the action is local to that time; broader pricing and schedule-pattern
recommendations appear in a compact Agenda insights surface and link to the
affected slots.

The feature should answer four questions in this order:

1. **What is the opportunity?** For example, a prime-time individual class is
   blocking demonstrated unmet demand.
2. **Why was it detected?** Show the observed evidence and evaluation window.
3. **What could improve?** Show an estimated revenue or capacity effect as a
   range or scenario, never as guaranteed income.
4. **What can the instructor do next?** Offer a review or draft action; keep
   all commercial and schedule changes behind explicit confirmation.

### 1.1 Product principles

- Optimize sustainable realized revenue, not only theoretical capacity.
- Protect customer trust: never move a customer, change a price, or convert a
  class type without instructor review and any required customer consent.
- Use deterministic, testable rules for eligibility, prioritization, and
  financial calculations. Use the platform LLM only to turn structured facts
  into a short explanation or conversation draft.
- Prefer a small number of high-confidence recommendations over a noisy feed.
- Make every estimate auditable: display its baseline, horizon, assumptions,
  and missing inputs.
- Keep recommendations tenant-scoped, dismissible, and reversible where an
  eventual action supports reversal.

### 1.2 Scope boundary

The first release is decision support. It does not implement dynamic pricing,
automatic roster changes, customer messaging, or autonomous rescheduling.
It reuses the existing Agenda, pricing, prime-time, waitlist, group-capacity,
makeup-credit, occurrence-override, and financial-capacity models.

### 1.3 Relationship to group-capacity work

The [Group Capacity & Slot Promotion roadmap](group_capacity_and_slot_promotion_roadmap_v0.1_2026-08-21.md)
remains authoritative for explicit class format/capacity, empty groups,
promotion, occurrence-only guests, joinable-group discovery, and the related
write workflows. This roadmap consumes that read model and proposes actions
through those confirmation-gated workflows; it must not introduce a second
group, roster, or promotion implementation.

The first **Fill an existing group** rule can initially support current group
records whose capacity and roster are already unambiguous. Full coverage of
zero-participant groups, per-occurrence guests, and explicit appointment
capacity depends on the group-capacity roadmap.

## 2. Recommendation catalog

The initial catalog should focus on opportunities the current data can support
reliably. Threshold values below are tenant configuration, not hard-coded
policy, and should ship with conservative defaults.

| Priority | Recommendation | Evidence and trigger | Suggested action | Estimated effect |
|---|---|---|---|---|
| P0 | Fill an existing group | A future group has free seats and one or more compatible waitlist entries overlap its time, place, and level | Review matches and invite a customer | Incremental participant price for the remaining occurrences in the horizon |
| P0 | Place a makeup off-peak | A customer has an available makeup credit and compatible regular-time capacity exists | Offer the ranked regular-time options | Prime capacity preserved; show avoided prime-time opportunity cost |
| P0 | Recover a newly opened slot | A cancellation or reschedule freed a future slot and a compatible waitlist entry exists | Review matches and offer the slot | Expected slot revenue if filled |
| P1 | Review a prime-time individual class | A recurring individual class occupies prime time, prime occupancy is high, and compatible unmet demand exists | Compare a price review, group conversion, or move to regular time | Scenario delta among current, repriced individual, and group options |
| P1 | Convert an individual arrangement to a group offer | A customer repeatedly reschedules or has low attendance stability, a compatible group/open demand exists, and the contract permits an offer | Start a customer conversation; do not change the booking automatically | Reduced dedicated-capacity exposure plus group revenue scenario |
| P1 | Complete an underfilled group | A recurring group is below capacity and compatible customers exist in the waitlist or other individual slots | Review candidates for the free seat | Incremental group revenue net of any displaced booking |
| P1 | Consolidate low-demand individual slots | Two or more compatible individual customers occupy nearby low-demand periods and could be offered one group | Review a proposed group time and affected customers | Group revenue minus displaced individual revenue; show only positive deltas |
| P2 | Review prime-time pricing | Prime-time occupancy and rejected/waitlisted demand remain above configured thresholds for a sustained window | Open a future-effective pricing scenario | Projected delta on affected future renewals; no retrospective price change |
| P2 | Release or relocate persistently unused capacity | A recurring availability interval remains materially underused while another window has unmet demand | Reduce or move declared availability | Capacity reallocation; label as operational, not guaranteed revenue |
| P2 | Tighten the reschedule offer, not a past contract | Makeup liability or prime-time redemptions are repeatedly consuming saleable capacity | Review a future policy such as notice limits or off-peak makeup windows | Historical opportunity-cost reference and forward scenario |

### 2.1 Interpretation of frequent rescheduling

Frequent rescheduling is not itself proof that a group class will earn more.
It is a risk signal: the customer consumes a dedicated recurring position and
may transfer an already-paid delivery obligation into another future slot
through a makeup or rescheduled class, reducing capacity available for a new
sale unless the vacated slot is refilled.
The recommendation is eligible only when the system can show a compatible
alternative and a positive scenario after accounting for displaced revenue.

The customer must not be penalized twice. A rescheduled occurrence should be
classified using the authoritative occurrence override and makeup-credit
relationships. The engine must not count both the source class and its
replacement as two independent reschedule failures.

### 2.2 Recommendations deferred until more data exists

- Profit optimization by place, because the current model excludes court,
  travel, payment, tax, and other delivery costs.
- Churn-sensitive price optimization, because there is no measured price
  elasticity or renewal/churn model.
- Attendance-probability optimization by customer without a stable attendance
  history and a reviewed fairness policy.
- Automatic demand forecasting beyond transparent trailing-window counts.

## 3. Decision model and financial semantics

### 3.1 Separate facts, rules, and language

The recommendation pipeline has three explicit stages:

```text
tenant-scoped schedule and financial facts
        -> deterministic eligibility and scenario engine
        -> structured recommendation snapshot
        -> optional LLM explanation from snapshot fields only
```

The LLM receives no authority to select customers, calculate money, decide
eligibility, or execute a mutation. If explanation generation fails, the UI
renders the deterministic title, evidence, and action unchanged.

### 3.2 Recommendation contract

Persist recommendation snapshots so dismissals, expiry, decisions, and later
outcome measurement are possible. A snapshot should include:

- tenant/professional owner, rule key and rule version;
- target type and stable target identity: dated occurrence, open time range,
  recurring slot, or agenda-level pattern;
- generated and expiry timestamps plus `active`, `dismissed`, `accepted`,
  `superseded`, and `expired` lifecycle states;
- severity (`opportunity`, `attention`) and confidence (`high`, `medium`);
- structured evidence with named date windows and sample sizes;
- baseline revenue, scenario revenue, estimated delta, horizon, and explicit
  assumptions; nullable amounts when pricing is incomplete;
- suggested action type and IDs of compatible candidate slots/customers;
- explanation status/text, dismissal reason, and resulting action reference.

Store only the minimum customer information needed for the decision. Resolve
display names at read time and never include phone, email, free-text notes, or
conversation content in the recommendation snapshot or LLM prompt.

### 3.3 Eligibility before ranking

Each rule first applies hard gates:

- target and evidence belong to the authenticated tenant;
- affected future occurrence still exists and is not canceled or superseded;
- pricing needed for a monetary comparison resolves successfully;
- place, time, level, duration, and capacity compatibility are satisfied;
- the evidence meets minimum volume and lookback requirements;
- the proposed option produces a positive delta where revenue is the claim;
- the same recommendation is not already active, dismissed within its cooldown,
  or accepted for the same target and material evidence version.

Eligible recommendations receive a transparent priority score, for example:

`priority = normalized financial impact × confidence × urgency`.

Financial impact must not dominate confidence. A large hypothetical number
from one waitlist entry should rank below a smaller opportunity supported by
repeated demand. The first release should use rule-specific bands rather than
a machine-learned score.

### 3.4 Revenue calculations

- **Fill a group:** incremental participant revenue at the resolved group rate
  for the recommendation horizon; do not present full group capacity as the
  incremental gain.
- **Convert/consolidate:** proposed group revenue minus revenue from every
  booking expected to be displaced in the same horizon.
- **Price review:** new-price scenario minus current-price scenario, applied
  only from a displayed future effective date. Label it “potential” because
  renewal and retention are unknown.
- **Fill a cancellation:** resolved slot revenue multiplied by no probability
  in v1; label the full amount “if filled,” not “expected revenue.”
- **Makeup placement:** show opportunity cost preserved by selecting a regular
  slot instead of a comparable prime slot. It is not new revenue.

Never add opportunity cost, capacity potential, scheduled revenue, and realized
revenue into one headline. They answer different questions and already have
separate semantics in the financial module.

### 3.5 Suppression and safeguards

- Cap visible recommendations to three per week view and one primary card per
  selected slot; provide a separate “all insights” view for the remainder.
- Suppress a rule after dismissal for a configurable cooldown unless the
  evidence changes materially.
- Do not recommend group matching on level alone: require compatible duration,
  place/time preference or explicit flexibility, and available capacity.
- Do not recommend moving an existing paid customer merely because a higher
  paying customer is waiting.
- Do not use protected or sensitive characteristics in ranking or explanation.
- Treat thresholds as configuration and expose the applied values in “Why am I
  seeing this?” rather than hiding them in the prompt.

## 4. Agenda experience

### 4.1 Calendar placement

Show a small, accessible recommendation marker on affected calendar items or
open intervals. The marker indicates that an insight exists; it must not alter
the event color that communicates appointment status. Selecting the event
opens its existing detail panel with one recommendation card below the class
and revenue facts.

```text
Agenda event: 18:00 Individual                 [insight marker]

Details
  Current scheduled revenue: R$ ...

Opportunity: review this prime-time format
  Prime occupancy was 92% in the last 8 weeks, and 3 compatible
  customers are waiting for this period.

  If renewed as a 3-person group: +R$ ... per 4-week horizon
  Assumptions: all 3 seats filled; current configured prices

  [Compare options]  [Draft conversation]  [Dismiss]
  Why am I seeing this?
```

An Agenda-level “Insights” button shows the active count and opens a ranked,
bounded list for recommendations that concern a recurring pattern rather than
one occurrence, such as a future pricing review. Each item links back to the
affected week and slot.

### 4.2 Interaction rules

- `Compare options` opens a scenario, not a mutation, and compares keeping the
  slot, repricing from a future date, moving it, and converting it to a group
  only when each option is eligible.
- `Draft conversation` asks the LLM for editable Portuguese copy grounded in
  the recommendation snapshot. Sending is out of scope for v1.
- `Dismiss` updates the card optimistically, restores it if persistence fails,
  and optionally records a short structured reason such as irrelevant,
  customer constraint, wrong data, or revisit later.
- Any eventual schedule, roster, policy, or price change uses the existing
  explicit confirmation and audit patterns. Accepting an insight is not the
  same as executing its suggested action.
- Expired or invalidated recommendations disappear automatically; they remain
  available to internal outcome analytics, not as stale calendar cards.

### 4.3 Explanation format

The explanation should be two or three sentences and follow a fixed structure:

1. observed fact with timeframe and sample size;
2. suggested review action;
3. effect and caveat.

Prohibited explanation behavior includes claiming guaranteed revenue, implying
the customer is at fault, hiding assumptions, or adding facts not present in
the structured snapshot. The deterministic fallback copy uses the same
structure and should be good enough to ship without an LLM dependency.

## 5. Proposed architecture

### 5.1 Reuse and new modules

Reuse these authoritative sources rather than re-deriving their rules:

- `financial_capacity.py` for available/free ranges and prime segmentation;
- financial rate resolution and revenue-preview services for price scenarios;
- `scheduling.py` for projected dated occurrences;
- `waitlist.py` for open demand and compatible opening concepts;
- `makeup_credits.py` and `makeup_recommender.py` for makeup eligibility and
  ranked placement;
- occurrence overrides and operational events for cancellation/reschedule
  history;
- recurring-slot participants for group capacity and customer membership.

Add a small `recommendations` service package whose rules implement one common
interface: load tenant-scoped facts, evaluate eligibility, calculate scenarios,
and return a typed recommendation candidate. Keep rule files independent; a
single orchestrator deduplicates, ranks, snapshots, expires, and supersedes
their output.

### 5.2 Persistence and generation

Use a recommendation snapshot table plus an append-only status/audit history.
The table should have a unique deduplication fingerprint derived from tenant,
rule version, target, and material evidence. Do not store a mutable “current
score” on appointments or recurring slots.

Generate recommendations through two paths using the same idempotent service:

- a scheduled daily evaluation for the next configurable planning horizon;
- targeted reevaluation after capacity-changing events such as create,
  cancellation, reschedule, waitlist change, roster change, price change, or
  makeup-credit change.

Event-driven evaluation keeps newly opened slots useful; the scheduled pass
repairs missed events and evaluates slow-moving patterns. Neither path calls
the LLM synchronously inside a booking transaction. Explanation generation is
best-effort after the structured snapshot commits.

### 5.3 API surface

Use bounded, authorized routes under `/api/recommendations`:

- list active recommendations by date range and optional target;
- fetch one recommendation with evidence and scenarios;
- dismiss a recommendation with an optional structured reason;
- request/regenerate its explanation or conversation draft;
- later, propose a supported action through the existing candidate/confirmation
  workflow rather than a generic recommendation mutation endpoint.

Every endpoint needs an explicit role dependency and tenant predicates derived
from the authenticated session. State-changing endpoints require the existing
CSRF, rate-limit, audit, and safe error-response conventions. LLM prompts and
logs must exclude unnecessary customer PII.

### 5.4 Configuration

Externalize evaluation horizon, lookback periods, occupancy thresholds,
minimum observation counts, cooldowns, and visible-card limits through the
project's tenant/server configuration pattern. Business thresholds belong in
tenant settings; infrastructure settings and safe global defaults belong in
`.env`. The UI must show the threshold and evaluation window that actually
produced a recommendation.

Avoid a generic no-code rule builder in this phase. Versioned rules in code are
simpler to test and audit; only validated threshold values are configurable.

## 6. Incremental delivery plan

### Phase 0 — Validate facts and baselines

1. Map reschedule, cancellation, replacement, and makeup events to one
   non-duplicated customer/occurrence history.
2. Verify waitlist entries contain enough flexibility, place, duration, and
   level information for safe matching; document missing fields.
3. Define baseline metrics for the prior 8–12 weeks: group-seat fill rate,
   waitlist-to-booking conversion, prime occupancy, prime-time makeup share,
   cancellation opening refill rate, and revenue per available hour.
4. Agree on tenant defaults for lookback, horizon, confidence, and cooldown.

**Verification:** a local read-only audit report reconciles its counts with
Agenda and Financeiro samples; ambiguous states are excluded and reported.

### Phase 1 — Recommendation foundation and one end-to-end rule

1. Add typed recommendation schemas, persistence, audit history, lifecycle,
   tenant settings, and authorized read/dismiss APIs.
2. Implement **Fill an existing group** using group capacity plus compatible
   waitlist demand. This has the clearest incremental value and least customer
   disruption.
3. Add the Agenda marker, appointment/group recommendation card, Insights
   count/list, optimistic dismissal, and deterministic fallback explanation.
4. Add daily and targeted idempotent generation without an LLM dependency.

**Verification:** service and API tests cover eligibility, pricing, tenant
isolation, deduplication, expiry, dismissal cooldown, stale-target invalidation,
role checks, CSRF, and audit events. Frontend tests cover bounded display,
accessible markers, optimistic rollback, and empty/error states.

### Phase 2 — Protect and recover capacity

1. Add **Place a makeup off-peak**, delegating candidate ranking to the
   existing makeup recommender and showing preserved opportunity cost.
2. Add **Recover a newly opened slot** after cancellation/reschedule, reusing
   waitlist matching and targeted event evaluation.
3. Measure whether notifications arrive quickly enough to be actionable and
   whether repeated recommendations remain acceptably low.

**Verification:** tests prove courtesy/makeup revenue is never counted as new
revenue, source/replacement events are not duplicated, and stale openings are
superseded immediately when filled.

### Phase 3 — Scenario comparison and explanations

1. Add the compare-options UI and revenue-delta calculations for supported
   group and individual scenarios.
2. Add optional LLM explanations and editable conversation drafts generated
   only from structured recommendation evidence.
3. Store prompt template/version and generation status, but not hidden chain of
   thought or unnecessary customer data.

**Verification:** calculation tests reconcile with the financial resolver;
prompt-contract tests reject unsupported facts and preserve the deterministic
card when generation is unavailable.

### Phase 4 — Pattern recommendations

1. Add **Review a prime-time individual class** after demand and occupancy
   thresholds have been validated on real tenant history.
2. Add underfilled-group completion and carefully gated consolidation.
3. Add future-effective pricing and reschedule-policy reviews last, because
   their outcome depends on customer response and contractual context absent
   from the current model.

**Verification:** shadow-run each new rule before displaying it. Product review
samples its recommendations and false positives; only then enable it per
tenant feature flag.

## 7. Measurement and rollout

Track exposure, opened details, compared options, dismissed reason, accepted
proposal, resulting confirmed schedule change, and outcome at the end of the
recommendation horizon. Do not treat card clicks as revenue success.

Primary product measures:

- incremental realized revenue associated with completed recommendation
  actions, with the attribution method stated explicitly;
- increase in filled group seats and cancellation openings refilled;
- reduction in the share of makeup delivery occupying prime capacity;
- revenue per available instructor hour, alongside customer retention and
  cancellation rate guardrails;
- precision proxy: accepted/actioned recommendations divided by reviewed
  recommendations, plus dismissals for wrong or irrelevant data.

Roll out with a feature flag to one instructor, first in shadow mode, then as
read-only cards. Compare with the instructor's pre-launch baseline and inspect
recommendation samples weekly. Causal revenue claims require a later controlled
experiment or strong matched-period design; simple before/after movement is
directional only.

## 8. Decisions needed before implementation

1. What counts contractually as a reschedule versus a makeup, and can either be
   restricted to regular-time capacity for future customer agreements?
2. Are individual-to-group changes allowed only at renewal, or may the
   instructor offer them during an active package with explicit consent?
3. Does the waitlist capture acceptable days/time ranges and level reliably,
   or only one desired timestamp today?
4. Should estimated impact use four weeks, the remaining package, or the
   recurring slot's remaining validity as its default horizon?
5. Which roles may see customer-level commercial recommendations and generate
   conversation drafts?
6. What dismissal cooldown and weekly card limit feels useful without making
   the Agenda noisy?

Recommended defaults for a pilot are an 8-week lookback, 4-week impact horizon,
three visible recommendations per Agenda week, a 14-day dismissal cooldown,
and high-confidence P0 rules only. These are starting hypotheses to validate,
not permanent business policy.

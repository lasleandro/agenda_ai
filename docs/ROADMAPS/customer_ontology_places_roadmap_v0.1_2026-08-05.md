# Customer Ontology & Places Roadmap v0.1 — 2026-08-05

> **Superseded for future planning.** The canonical continuation is
> [Operational Ontology & AI Agent Roadmap v0.2](operational_ontology_and_agent_roadmap_v0.2_2026-08-05.md).
> This document remains the implementation history for the completed customer
> ontology and places work.

## Implementation status (2026-08-05)

**Phases 1–4 are all implemented and test-covered**, per your decision to build both "Meus Locais" and "Clientes" in one pass, with `level`/`class_type` kept as plain strings (not DB enums) for the "modular, easy to adjust later" requirement.

- **Models/migration** (`d4f2a8c1e6b9`): `Place`, `RecurringSlot`, `RecurringSlotParticipant`, and `Contact` enrichment (`level`, address fields, `home_place_id`). `CONTACT_LEVELS`/`CLASS_TYPES` are plain Python tuples in the model modules, not DB enums — adding a new level or class type later is a one-line change, no migration.
- **Backend APIs**: [places.py](../../backend/app/api/places.py) (CRUD, cascades to its recurring slots + clears `home_place_id` on delete), [recurring_slots.py](../../backend/app/api/recurring_slots.py) (CRUD + overlap rejection across all of a professional's places + participant assign/unassign with capacity enforcement), [contacts.py](../../backend/app/api/contacts.py) (list/detail/update, detail includes `fixed_slots`). All scoped via `require_professional_id`, same tenant-isolation pattern as the multi-tenancy work.
- **Tests**: [test_ontology.py](../../backend/tests/test_ontology.py) — 5 tests covering tenant isolation, overlap rejection, capacity enforcement (individual=1, group up to 4), and place-delete cascade. Full suite (17 tests across all roadmaps) passing.
- **Frontend**: [`AddressAutocomplete`](../../frontend/src/components/ontology/address-autocomplete.tsx) (Photon-backed, reusable — used by both the Place and Contact forms), **Meus Locais** (`/places`, `/places/[id]`) with inline recurring-slot management, **Clientes** (`/clientes`, `/clientes/[id]`) with level/address/home-place editing and fixed-slot assignment (capacity-aware picker), sidebar nav wired up. The **calendar screen** renders recurring slots as a distinct visual block type using FullCalendar's native `daysOfWeek`/`startTime`/`endTime` recurring-event support (no new plugin needed) and opens the same edit dialog used in "Meus Locais" — one underlying record, two entry points, as requested.
- **Verified live**: full curl walkthrough (create place → create group slot → assign contact → capacity/overlap rejection → contact detail reflects assignment → cascade delete) against the running dev server, plus a clean `npm run build`.

**Bug found and fixed during live verification**: `DELETE /api/places/{id}` originally just deleted the row, which hit an unhandled FK-constraint error once a `RecurringSlot` referenced it — and that unhandled error wedged the whole local dev server (had to be restarted). Fixed by cascading the delete properly (removes dependent `RecurringSlot`/`RecurringSlotParticipant` rows, nulls `Contact.home_place_id`) and covered with a regression test. If you notice similarly slow/hung responses elsewhere, that root cause (an unhandled exception in a sync SQLAlchemy path wedging the request) is worth a closer look beyond just this one endpoint — I only fixed the instance I hit.

**Not built** (matches the roadmap's original scope — these were explicitly listed as future ideas, not requested now): recurring-slot exceptions, waitlists, attendance/check-in, skill-progression notes, map view, conflict-aware appointment suggestions, and a separate `Court`/`Quadra` sub-entity under `Place` (still just `RecurringSlot.label` for now, per the original YAGNI call).

## Why now

The multi-tenancy work ([roadmap](multi_tenancy_roadmap_v0.1_2026-08-04.md)) made `Professional` a real tenant boundary. The next gap is that inside a tenant, `Contact` is still a flat WhatsApp-derived record (phone, display name) — there's no notion of *where* a lesson happens, whether a customer is a fixed weekly regular or a drop-in, or whether they train alone or in a group. `docs/ROADMAPS/MEU_DIARIO.md` already names this exact hierarchy as a future idea ("quadra → horário → grupo → aluno") — this doc turns it into a concrete, sequenced plan, and treats it as the start of a proper **customer ontology**: normalized entities and enums rather than free text, so a future AI agent (or you) can reliably query "who's in Tuesday's group at Club X" instead of parsing prose.

## Current state (checked 2026-08-05)

- `Contact` ([contact.py](../../backend/app/models/contact.py)): `professional_id`, `phone`, `display_name`, `normalized_name`, a free-form `metadata` JSONB column, no address/level/class-type fields.
- No `Place`/venue concept anywhere in the schema or frontend.
- `Appointment` ([appointment.py](../../backend/app/models/appointment.py)) has a `recurrence_rule: str | None` column that's declared but not yet used by any read/write path (grep confirms no writer sets it) — a fixed weekly reservation has nowhere to live today.
- Frontend sidebar ([sidebar.tsx](../../frontend/src/components/layout/sidebar.tsx)) already has a disabled **"Contatos"** nav placeholder (`href: undefined`) — the natural slot for the "Clientes" screen requested here. No "Meus Locais" placeholder exists yet.
- No geocoding/address library in `frontend/package.json` — only FullCalendar for the calendar grid.

## Address autocomplete: Photon assessment

[Photon](https://photon.komoot.io/) (Komoot's open-source geocoder, OpenStreetMap-based) is a good MVP fit:

- **Free, no API key**, worldwide coverage via OSM data — sources: [komoot/photon](https://github.com/komoot/photon), [photon-package docs](https://jslth.github.io/photon/reference/photon-package.html).
- Public demo API (`photon.komoot.io`) is usable directly for low-volume use (a handful of instructors registering venues is nowhere near its throughput concerns) — Komoot's own guidance is "reasonable" request volume is fine, ~1 req/sec is the informal default; heavy/production traffic should self-host, which is just running a Docker container with no query volume left to negotiate ([source](https://github.com/komoot/photon)).
- Supports search-as-you-type, typo tolerance, and location-biasing (bias results near the professional's city) — exactly what an address-autocomplete field needs.
- **Caveat for Brazil**: OSM address coverage (house-number-level) is uneven outside major city centers, but named venues/POIs — tennis clubs, sports centers, parks — are generally present as OSM points, and that's the more likely search pattern here (an instructor searching "Clube X" rather than typing a raw street address). Worth a quick spot-check against 3–4 real venue names during Phase 1 before committing further.

**Recommendation**: use the public Photon API directly from the frontend for MVP (no backend proxy needed, no key to manage); revisit self-hosting only if usage or reliability becomes a problem. This avoids adding Google Maps billing/API-key complexity for an MVP with a handful of users, matching CLAUDE.md's "don't add configurability that wasn't requested" — Google is explicitly a later swap-in per your message, not a now decision.

## Ontology decisions

Modeling this as the "quadra → horário → grupo → aluno" hierarchy from MEU_DIARIO, made explicit as first-class entities rather than free text — this is what makes it "AI-agent-ready": stable IDs, typed enums, explicit relationships an agent can traverse or query instead of re-parsing prose.

- **`Place`** ("Local") — a venue the professional works at: name, structured address, lat/lng (from Photon), `professional_id`. One professional can have several places.
- **`RecurringSlot`** ("Horário Fixo") — the professional's own standing reservation at a `Place`: day of week, start/end time, optional label (e.g. "Quadra 2"), `class_type` (`individual` | `group`), `max_participants` (1 for individual, up to 4 for group — tennis' real-world group cap, per your note). This is the entity editable from **both** "Meus Locais" and the calendar screen, per your request — it's one underlying record, not two.
- **`RecurringSlotParticipant`** — join table (`recurring_slot_id`, `contact_id`) linking up to `max_participants` contacts to a slot. This is the "grupo" — a group class is just a `RecurringSlot` with 2–4 participants; an individual class is the same entity with exactly 1.
- **`Contact` gets new fields**: structured address (their own, separate from `Place`), `level` (enum: `beginner` | `intermediate` | `advanced`, extensible), `home_place_id` (FK to `Place`, nullable — their usual venue). Whether a contact is "fixed" and in which slot is derived from `RecurringSlotParticipant`, not a new boolean — one source of truth, no risk of the two disagreeing.

This intentionally does **not** introduce a separate `Court`/`Quadra` sub-entity under `Place` yet (e.g. "Club X has courts 1–6") — MEU_DIARIO mentions it, but you only asked for `Place`-level registration here. `RecurringSlot.label` (free text, e.g. "Quadra 2") covers the common case cheaply; promote it to a real `Court` entity later only if you need court-level scheduling/conflict rules, not just a label (YAGNI).

## Phases

### Phase 1 — `Place` model + "Meus Locais" screen
- `Place` model + migration, scoped by `professional_id` (same tenant-isolation pattern as every other table — see multi-tenancy roadmap Phase C).
- Backend CRUD (`GET/POST/PATCH/DELETE /api/places`), scoped via `require_professional_id`.
- Frontend: new **"Meus Locais"** screen (sidebar item, replacing a currently-unused slot or added alongside "Painel"), list + create/edit form with a Photon-backed address-autocomplete field (debounced search-as-you-type, select a result to fill structured address + lat/lng).
- Verify: create two places under different tenants, confirm cross-tenant isolation (reuse the `test_tenant_isolation.py` pattern); confirm autocomplete returns sane results for 3–4 real Brazilian tennis-club names.

### Phase 2 — `RecurringSlot` + fixed-timetable editing (Meus Locais + Calendar)
- `RecurringSlot` model + migration, FK to `Place` and `Professional`.
- Backend CRUD, scoped by tenant.
- Frontend: within each Place's detail view in "Meus Locais", list/add/edit its recurring slots (day/time/label/class_type/max_participants). On the **Calendar** screen, render recurring slots as a distinct recurring block type (visually different from one-off `Appointment`s) and allow editing them inline — same backend record, two entry points, per your request.
- Add overlap validation: reject a new slot that overlaps another active slot for the same professional+place+day (a professional can't be in two places at once).
- Verify: a slot created in "Meus Locais" appears correctly on the calendar and vice versa; overlapping-slot creation is rejected with a clear error.

### Phase 3 — `Contact` enrichment + "Clientes" screen
- Migration adding `level`, structured address fields, `home_place_id` to `Contact`.
- Backend: `GET/PATCH /api/contacts/{id}` (contacts currently have no dedicated endpoint outside the conversation view — add one), scoped by tenant.
- Frontend: new **"Clientes"** screen in the sidebar (fills the existing disabled "Contatos" slot) — list of contacts with search/filter by level, place, fixed/drop-in; detail/edit view with the same Photon address field as Phase 1, level selector, place association, and level.
- Verify: editing a contact's fields persists and is tenant-isolated; the disabled sidebar item becomes a real link.

### Phase 4 — Group/individual assignment (`RecurringSlotParticipant`)
- `RecurringSlotParticipant` model + migration, with a DB-level or application-level check that `count(participants) <= slot.max_participants`.
- Backend: add/remove a contact from a slot; surfaced from both the Contact detail view ("this student's fixed slot(s)") and the Place/slot detail view ("who's in this group").
- Frontend: in "Clientes", assign a contact to an existing slot (filtered to slots with open capacity); in "Meus Locais", show each slot's current roster and open seats.
- Verify: assigning a 5th contact to a `max_participants=4` group slot is rejected; individual slots (`max_participants=1`) reject a second participant.

## Ideas worth considering (not scheduled — flagging per your ask)

- **Recurring-slot exceptions**: a single occurrence of a weekly slot needs to be cancelled (holiday, instructor sick) without deleting the whole recurring rule. Worth designing for before Phase 2 ships if you expect this often — retrofitting exception handling onto a naive recurrence model is painful later.
- **Waitlist for full group slots**: when a group slot hits `max_participants`, let a contact join a waitlist instead of silently failing.
- **Attendance/check-in per session**: mark a specific occurrence as attended/no-show — useful both for coach ops and as a natural precursor to the financial module already noted in MEU_DIARIO (billing by attendance vs. by package).
- **Skill/progression notes per contact**: freeform or structured notes tied to `level` changes over time — feeds a future AI agent's context for personalized scheduling or progress summaries to parents/instructors.
- **Place map view**: once there are several places, a small map (Leaflet + OSM tiles, same ecosystem as Photon, no new vendor) showing pins is a cheap, on-brand visual per your "modern platform" direction — not needed for MVP list/form CRUD.
- **Conflict-aware suggestions**: when creating an `Appointment` for a contact who has a `RecurringSlotParticipant` assignment, default the time/place to their fixed slot — small UX win, meaningfully less typing for the common case.

## Open questions for you

1. Should "Meus Locais" and "Clientes" both be built end-to-end this session, or would you rather sequence them (e.g. Places first, since Clientes' place-association field depends on it)?
2. `level` as a fixed enum (beginner/intermediate/advanced) — is that granular enough, or do you already have a scale in mind (e.g. NTRP-style numeric rating) that should be modeled from the start instead of migrated later?

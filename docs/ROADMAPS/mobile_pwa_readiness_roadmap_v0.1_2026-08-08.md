# Mobile Readiness & PWA "Add to Home Screen" Roadmap v0.1 — 2026-08-08

**Status: Decisions locked 2026-08-08 (nav pattern, agenda view, branding,
offline strategy, scope). Ready to start Phase 1.**

## What this is

Today the platform is a desktop-oriented Next.js app. The ask: make it
usable on a phone, and make it installable to the phone's home screen so
it opens and feels like a native app (standalone window, its own icon, no
browser chrome) rather than a bookmarked tab. This roadmap maps every
touch point across the frontend that stands between "renders on a small
screen" and "feels like an app an instructor would keep on their home
screen and use all day between lessons."

Two separate problems are bundled here on purpose, because they're both
required for the "real app" experience the request describes:

1. **Mobile-ready UI** — every screen is usable and doesn't break at
   phone widths (~360–430px).
2. **Installable PWA** — a web app manifest, icons, and enough of the
   installability criteria that Chrome/Android and Safari/iOS offer
   "Add to Home Screen" and launch it standalone.

## What already exists to build on

Audited 2026-08-08 against the current frontend (`frontend/`, Next.js
16, App Router, Tailwind).

- **Responsive utility classes are already used in ~55% of components.**
  31 of 56 `.tsx` files use `sm:`/`md:`/`lg:` Tailwind breakpoints, so
  the pattern is established — this isn't a from-scratch responsive
  effort, it's closing gaps in specific screens.
- **Next.js 16 auto-injects a `viewport` meta tag.** Pinch-zoom and
  initial scale already behave correctly on mobile browsers without
  any explicit config in [layout.tsx](../../frontend/src/app/layout.tsx).
- **A single root layout and a single protected-route layout** already
  gate all authenticated screens
  ([src/app/(protected)/layout.tsx](../../frontend/src/app/(protected)/layout.tsx)),
  which means the mobile nav fix (below) has one place to land, not
  N places.
- **Dialogs/sheets are already the standard pattern for detail views**
  (`AppointmentFormDialog`, `GroupDetailsDialog`, etc.) — these are
  generally easier to make mobile-friendly than full-page layouts,
  since Radix-based dialogs already handle viewport constraints.

## What's genuinely missing — touch points

### A. Navigation (blocking — affects every screen)

- [sidebar.tsx:62](../../frontend/src/components/layout/sidebar.tsx#L62)
  — the entire primary nav is `hidden md:flex` with **no mobile
  replacement anywhere in the codebase** (confirmed: no hamburger,
  drawer, sheet, or bottom-nav component exists in `src/`). Below the
  `md` breakpoint (~768px) there is currently no way to navigate
  between Agenda, Clientes, Places, Financeiro, and Minhas Regras. This
  is the single blocking issue — every other fix is moot if users can't
  reach the screen.
- [(protected)/layout.tsx](../../frontend/src/app/(protected)/layout.tsx)
  — the shell that renders the sidebar alongside page content; this is
  where the mobile nav gets wired in.
- **Decided: hamburger + slide-over drawer**, not a bottom tab bar —
  reuses the existing sidebar's item list and scales to the full nav
  (Agenda, Clientes, Places, Financeiro, Minhas Regras) without needing
  a second, trimmed-down item set for a tab bar.

### B. Core screens — responsiveness gaps

- **Agenda / week calendar**
  ([week-calendar.tsx](../../frontend/src/components/calendar/week-calendar.tsx))
  — the highest-traffic screen and the least mobile-ready. It renders
  FullCalendar's `timeGridWeek` unconditionally
  (line 344), with a 3-way header toolbar (`prev,next today` /
  `title` / `timeGridWeek,timeGridDay,dayGridMonth`, lines 345–349) that
  has no responsive treatment. A 7-day time grid does not fit a
  360–430px viewport legibly. **Decided: default to FullCalendar's
  `listWeek`** below a breakpoint (reads like a native agenda list,
  needs no horizontal space, vs. `timeGridDay`'s grid metaphor), plus a
  condensed/stacked toolbar on small screens.
- **Financial tables** — three components render fixed-minimum-width
  grids/tables that will force horizontal scroll on phones:
  [place-rates-section.tsx:81](../../frontend/src/components/financial/place-rates-section.tsx#L81)
  (`min-w-[620px]` grid), [scenario-results.tsx:73](../../frontend/src/components/financial/scenario-results.tsx#L73)
  (`min-w-[620px]` table), [financial-simulator.tsx:348](../../frontend/src/components/financial/financial-simulator.tsx#L348)
  (`min-w-[560px]` table). Horizontal scroll inside a bounded container
  is an acceptable pattern on mobile *if deliberate* (wrapped in
  `overflow-x-auto`, which two of the three already do) — needs
  verification each renders usably at 375px width rather than just
  overflowing the page.
- **Financeiro screen** ([financial-dashboard-section.tsx](../../frontend/src/components/financial/financial-dashboard-section.tsx)
  and related sections) — beyond generic responsive fixes, **decided:
  simplify the mobile visualization** rather than just shrinking the
  desktop layout. Bring three numbers to the top of the screen, above
  the fold: current-month realized revenue, current-month projection,
  and current-month full capacity. This is a content-priority change
  specific to mobile, not just a breakpoint tweak — the desktop layout
  (detailed tables, scenario simulator, rate grids) stays as-is below
  that summary.
- **Clientes, Places, Minhas Regras pages** — **decided: in scope, full
  sweep.** Each needs a pass to confirm list/table layouts collapse to
  single-column cards or scrollable tables below `md`, consistent with
  the pattern in the ~55% of components that already do this.
- **Dialogs and forms** (`AppointmentFormDialog`, `GroupDetailsDialog`,
  contact/rate editors) — spot-check that dialog width/height and touch
  target sizes (buttons, dropdown items) work with on-screen keyboards
  open, a common breakage point even when the dialog library itself is
  responsive.

### C. PWA installability

- **No `manifest.json`/`.webmanifest`.** Nothing in `frontend/public/`
  or referenced from [layout.tsx](../../frontend/src/app/layout.tsx).
  Required fields: `name`, `short_name`, `icons` (minimum 192×192 and
  512×512, ideally with a maskable variant), `start_url`,
  `display: "standalone"`, `theme_color`, `background_color`.
- **No app icons.** `frontend/public/` currently only has generic
  Next.js starter SVGs and `tennis.png` — no icon set sized for
  home-screen use, no `apple-touch-icon` for iOS. **Decided: "Tennis
  OS" is the confirmed platform/home-screen app name** (matches the
  existing [layout.tsx](../../frontend/src/app/layout.tsx) title — no
  change needed there); the in-app AI assistant is separately named
  "Lob" and is not the home-screen app name. No real icon asset exists
  yet — use a placeholder icon for Phase 3 and swap it for real branding
  later without re-touching the manifest/meta-tag wiring.
- **No `theme-color` metadata** — controls the browser chrome/status
  bar color when installed.
- **No service worker.** Confirmed absent — no
  `next-pwa`/`@ducanh2912/next-pwa`/workbox in `package.json`, no
  `sw.js` anywhere. **Decided: implement one, with basic asset
  caching** (app shell/static assets — not full offline data sync).
  This also satisfies Chrome/Android's `beforeinstallprompt`
  installability requirement, which a manifest alone doesn't.
- **iOS-specific meta tags** — `apple-mobile-web-app-capable`,
  `apple-mobile-web-app-status-bar-style`, and an `apple-touch-icon`
  link are needed for iOS Safari's "Add to Home Screen" to launch
  standalone rather than opening Safari with the URL bar visible; the
  web manifest alone doesn't cover iOS.
- **`next.config.ts`** — currently only configures API rewrites; this
  is where a PWA plugin (if one is adopted) or manual manifest/service
  worker output would be wired in.

## Phased plan

### Phase 1 — Mobile navigation (blocking)

- Build hamburger + slide-over drawer nav component, wired into
  [(protected)/layout.tsx](../../frontend/src/app/(protected)/layout.tsx),
  covering Agenda / Clientes / Places / Financeiro / Minhas Regras.
- Verify: on a 375px-wide viewport, every top-level screen is reachable
  and the active route is visually indicated, matching the desktop
  sidebar's current behavior.

### Phase 2 — Core screen responsiveness (all screens)

- Agenda: switch to FullCalendar's `listWeek` view + condensed/stacked
  toolbar below `md`.
- Financeiro: simplified mobile summary (current-month realized,
  projection, full capacity) pinned to the top; verify the detailed
  tables/scenario simulator below it remain usable (see financial
  tables note below).
- Financial tables: confirm `overflow-x-auto` wrapping renders usably
  at 375px on all three flagged components; add if missing.
- Full sweep of Clientes, Places, Minhas Regras at the same 375px
  target; fix collapse-to-card/scroll behavior where missing.
- Spot-check dialogs/forms with a virtual keyboard open (touch target
  size, scroll-into-view on focus).
- Verify: manual pass on real iOS + Android devices (or DevTools device
  emulation at minimum) for each screen — no horizontal page scroll,
  no unreachable controls, no overlapping content.

### Phase 3 — PWA installability

- Add `manifest.json` (or `manifest.ts` via Next's `MetadataRoute.Manifest`)
  with name "Tennis OS" / short_name / icons / start_url /
  `display: "standalone"` / theme_color / background_color.
- Add a placeholder icon set (192×192, 512×512, maskable variant,
  `apple-touch-icon`) to `frontend/public/` — swappable later for real
  branding without touching the manifest/meta-tag wiring.
- Add `theme-color` and iOS-specific meta tags
  (`apple-mobile-web-app-capable`, `apple-mobile-web-app-status-bar-style`)
  to [layout.tsx](../../frontend/src/app/layout.tsx).
- Implement a minimal service worker with basic asset caching (app
  shell/static assets), satisfying Chrome/Android's
  `beforeinstallprompt` installability requirement.
- Verify: Chrome DevTools "Installability" audit passes (Lighthouse
  PWA category); manual "Add to Home Screen" test on both an Android
  device (Chrome) and an iOS device (Safari) confirms standalone launch
  with correct icon and name.

### Phase 4 — Polish and validation

- Full-app walkthrough on real devices covering the golden paths
  (view agenda, book/cancel an appointment, check financeiro) from the
  home-screen icon, standalone mode.
- Fix any remaining layout breakage found during the walkthrough.
- Update [README.md](../../README.md) status line for this roadmap once
  shipped.

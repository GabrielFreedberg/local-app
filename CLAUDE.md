# CLAUDE.md — Steering File for Local Deal Alert

This file is what any AI coding agent (Claude, Codex, or otherwise) should read
first when picking up work in this repo. It exists so context does not have
to be rebuilt from scratch every session. If you change something that would
make this file wrong, update this file in the same session.

## What this product is

Local Deal Alert is a local-first deal app with two account types:

- **Shoppers** save "Alert Interests" (favorites like `pizza`, `chicken`,
  `beer`). They can search *every* visible deal, but only get an alert when a
  deal matches both their zip code **and** one of their saved interests.
- **Businesses** create a company account and post local deals (title,
  address, description, expiration, active/draft status).

The core product rule that must never quietly regress: **alerts are high
signal, not noisy.** All deals stay searchable; only zip+interest matches
trigger a notification, and (as of 2026-08-17) all of a shopper's matches
from one matching run are digested into a single email rather than one
email per match. See `DEVELOPMENT_OPERATING_PLAN.md` and
`SUPABASE_AUTH_AND_SCHEMA_PLAN.md` for the full rules this was built around.

Interest matching is word-boundary, not raw substring (fixed 2026-08-17 —
substring matching had real false positives, e.g. "ice" matching
"service"), with an optional AI-assisted category-overlap signal on top
when `ANTHROPIC_API_KEY` is set (see "AI-assisted matching" in
`README.md`). Zip matching is still exact-match only — see "Deliberately
deferred: nearby-zip matching" in `README.md` before building a radius
feature; it needs a real data-model decision, not a quick heuristic.

## Repo layout

```
app.py                      Single-file Python backend (stdlib only, no
                             framework). Runs on http.server /
                             ThreadingHTTPServer. Serves the API and the
                             static frontend.
static/index.html           Frontend markup (all JS-managed IDs/classes live
                             here — see "Frontend conventions" below).
static/app.js                Frontend logic. Vanilla JS, no build step,
                             no framework. ~2,200 lines, one file.
static/styles.css           Design system + all component styles. Rewritten
                             2026-08-16 — see DESIGN_SYSTEM.md.
supabase/schema.sql          Production Postgres schema (Phase 2 target).
supabase/rls.sql             Row Level Security policies for the same.
test_phase1.py               unittest regression suite for app.py (backend
                             only — no frontend/DOM tests exist yet).
legacy-appV1/                An earlier, smaller prototype. Kept for
                             historical reference only. Not run, not tested,
                             not linked from the live app. Safe to ignore
                             unless explicitly asked to look at product
                             history.
*.md (root)                  Planning docs written during earlier sessions
                             (see "Existing docs" below). Still accurate as
                             of this write-up; read them before making
                             architecture or product-direction decisions.
```

## Running it locally

```bash
python3 app.py                        # serves http://127.0.0.1:8000
python3 -m unittest -v test_phase1.py # 29 backend regression tests
```

No dependencies to install — the backend is Python stdlib only. The
frontend has one CDN script (`@supabase/supabase-js`) and now also loads
Google Fonts (Inter) — both are progressive: the app still works if either
fails to load (Supabase-dependent features simply stay in local-prototype
mode; the font falls back to the system stack).

Local prototype mode (no env vars set) uses SQLite (`phase1.db`, gitignored)
and logs mocked emails to `notification_log.jsonl`. Setting the Supabase env
vars (see `.env.example`) switches the backend into hosted mode — see
`SUPABASE_SETUP_CHECKLIST.md` before doing that.

## Frontend conventions (read before touching CSS/HTML/JS)

`app.js` renders most of the UI by building HTML strings and injecting them
via `innerHTML`, keyed off specific class names and a fixed set of element
IDs in `index.html`. This means:

- **Every class name currently in `static/styles.css` is load-bearing.**
  Some (like `.deal-card`, `.is-saved`, `.alert-status.is-<status>`,
  `.merchant-insight-score.is-strong/okay/risk`) are constructed dynamically
  in `app.js` via template literals and `classList.toggle`. Renaming a class
  in CSS without grepping `app.js` first will silently break styling with no
  error.
- **Every `id="..."` in `index.html` is read via `getElementById` in
  `app.js`.** Don't remove or rename IDs without updating `app.js` to match.
- There is no build step and no component framework. Changes to
  `static/*` take effect on page refresh, no compile step required.
- There are no frontend/DOM tests. `test_phase1.py` only covers `app.py`.
  Manually click through (or script with Playwright, see below) after any
  frontend change before calling it done.

**Before changing frontend structure or styling**, grep `app.js` for the
class/ID you're touching:

```bash
grep -n "classList\|getElementById\|class=\"" static/app.js
```

## Design system

The current visual design (coral primary / deep teal secondary, Inter
typeface, flatter cards, tighter radii) was introduced 2026-08-16 as a
deliberate modernization pass. Full rationale, palette tokens, and component
notes live in **`DESIGN_SYSTEM.md`** — read it before making visual changes
so new work stays consistent with the system instead of drifting back
toward one-off styling.

## Operating agreement (for the agent doing the work)

Adapted from `DEVELOPMENT_OPERATING_PLAN.md`, generalized from "Codex" to
whichever agent is driving:

**Work with high autonomy by default.** Make reasonable implementation
decisions without stopping constantly, complete features end-to-end where
feasible, run local verification when possible (backend: `unittest`;
frontend: Playwright screenshot or manual click-through), document
assumptions, and only stop for approval when a decision is materially
important.

**Stop and ask before:**
- changing the core value proposition (zip + interest matching, searchable-
  but-not-noisy alerts)
- changing who the product is for (shoppers + local businesses)
- changing the monetization model
- replacing the backend/stack direction (currently: stdlib Python now,
  Supabase Auth/Postgres/RLS is the agreed Phase 2 target)
- changing the data model in a way that creates migration risk
- removing a feature already accepted into the product

**Don't stop for approval on:** bug fixes, UX cleanup, refactors that
preserve behavior, validation improvements, internal code organization,
local test scaffolding, incremental design polish within the established
system.

**When reporting progress**, include: outcome, what changed, what was
verified, open risks, and where approval is needed (if anywhere).

## Current state vs. roadmap

This is Phase 1 (Prototype Stabilization) of a 5-phase plan. See
`8-week-mvp-roadmap.md` for the full roadmap and `MVP_IMPLEMENTATION_BACKLOG.md`
for the itemized, checkbox-tracked backlog — **update the backlog checkboxes
when you complete backlog items**, don't let it drift out of sync with
reality.

Auth/data currently runs in local-prototype mode (SQLite + hashed sessions).
Supabase schema and RLS are checked in and ready (`supabase/*.sql`) but the
frontend has not been cut over to hosted Supabase sessions yet — that cutover
is the single highest-leverage next step toward Phase 2 (see
"Current production-path priority" in `README.md`).

## Existing docs (read in this order for full context)

1. `README.md` — feature list, run instructions, API endpoints
2. `DEVELOPMENT_OPERATING_PLAN.md` — phases, roles, approval gates
3. `8-week-mvp-roadmap.md` — target architecture and week-by-week plan
4. `MVP_IMPLEMENTATION_BACKLOG.md` — granular, checkbox-tracked task list
5. `SUPABASE_AUTH_AND_SCHEMA_PLAN.md` — production schema + auth model
6. `SUPABASE_SETUP_CHECKLIST.md` — concrete steps to stand up Supabase
7. `PAYMENTS_READINESS_PLAN.md` — how/when to add merchant billing
8. `FRONTEND_POLISH_NOTES.md` — frontend visual direction log (append to
   this, don't replace it, when you make another design pass)
9. `DESIGN_SYSTEM.md` — current design tokens and component rationale (new)
10. `LEARNING_GUIDE.md` — plain-language walkthrough of the architecture,
    auth/security concepts, Supabase/RLS, and testing, written for
    reference and interview prep. Also persisted as an HTML artifact.
11. `AUTOMATION.md` — the plan and checklist for GitHub + CI + Supabase +
    Railway, so the project stops depending on any single laptop being on
12. `API_CONTRACT.md` — every HTTP route `app.py` actually serves, request/
    response shapes, and known rough edges (e.g. `GET /api/users` exposure)
13. `NOTIFICATION_PROVIDER_DECISION.md` — real-email provider decision
    (Resend, over SMTP, no code changes needed)
14. `LAUNCH_CHECKLIST.md` — soft-launch QA checklist, ties together the
    other docs into one ordered pass
15. `04-23 write up.txt` — dated session log from an earlier build pass

All of these were accurate as of this write-up (last updated 2026-08-19).
If something here conflicts with what you find in the code, trust the
code and fix the doc.

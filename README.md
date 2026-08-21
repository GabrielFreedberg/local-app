# Phase 1 Prototype

This is the current local prototype for the deal alert product as of Wednesday, July 29, 2026.

## What this app is

This product is a local-first deal app with two distinct experiences:

- shoppers save favorites and only receive alerts when a local deal matches both their zip code and their saved interests
- businesses create accounts and post deals that nearby shoppers can discover

The product is currently optimized around local business deals, favorites-driven matching, and simple zip-based relevance.

## Current product shape

The prototype currently supports:

- separate customer and business account creation
- automatic login immediately after account creation
- local hashed passwords and hashed session token storage in prototype mode
- password reset request and password reset confirmation flows
- in-session password changes that revoke older sessions
- separate shopper and merchant tabs after login
- shopper search across visible local business deals
- shopper favorites with add, edit, remove, and quick-add flows
- shopper alerts that only appear when both zip code and favorite matching conditions are met
- business deal posting, editing, archiving, and lifecycle visibility
- expiration-aware company deal states
- centered deal-detail modal cards with keyboard-close support
- hosted Supabase-backed auth-aware flows on the production path
- checked-in Supabase schema and RLS files for the migration path
- SMTP-backed real email when configured
- mock notification logging when SMTP is not configured
- automatic in-process matching on a repeating schedule while the app server is running
- live in-app status showing whether the app is in real-email or mock-email mode
- automated regression coverage for core auth, favorites, company deals, and matching flows

## Core product rules

- all visible deals remain searchable
- alerts only trigger when both are true:
  - the deal zip code matches the user zip code
  - the deal text matches one of the user's saved favorites (whole-word
    match, not a raw substring — see "Matching quality" below)
- a shopper gets at most one email per matching run, digesting every match
  found in that run, not one email per match
- shopper and business experiences stay separate
- business accounts only manage their own deals
- shoppers browse deals, manage favorites, and review alerts
- the visible UI is currently focused on local business deals rather than grocery inventory

### Matching quality

`matching_interest_for_deal` (in `app.py`) matches an interest against a
deal's title/description/store name using a word-boundary regex, not a raw
substring check — this avoids false positives like an interest in "ice"
matching "service" or "price", while still catching simple plurals
("pizza" → "pizzas"). See `AI-assisted matching` below for an optional
second layer that catches synonyms a keyword match can't ("tacos" matching
"Mexican food night").

## Run locally

```bash
python3 app.py
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

Run it on a different port/host with `APP_PORT` / `APP_HOST`, e.g.:

```bash
APP_PORT=8080 python3 app.py
```

Then open [http://127.0.0.1:8080](http://127.0.0.1:8080). Run this
directly in your own terminal on your machine (not through a mounted/
network filesystem) — SQLite needs real POSIX file locking that
bridge-mounted paths don't reliably provide.

## Run regression tests

```bash
python3 -m unittest -v test_phase1.py
```

## Optional environment setup

### SMTP for real email

If you want real emails instead of mocked local delivery, set:

```bash
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your-email@example.com"
export SMTP_PASSWORD="your-app-password"
export EMAIL_FROM="your-email@example.com"
export APP_BASE_URL="http://127.0.0.1:8000"
```

If these variables are not set, the prototype still runs and records notifications as mocked.

### Matching scheduler

The prototype now starts an in-process matching scheduler automatically while `python3 app.py` is running.

Optional controls:

```bash
export MATCHING_SCHEDULER_ENABLED="true"
export MATCHING_SCHEDULER_INTERVAL_SECONDS="300"
```

- default interval is every 5 minutes
- minimum interval is 30 seconds
- `POST /api/match` still works for manual trigger testing

### Supabase for hosted auth and production-path data

If you want to use the hosted auth/data path, also set:

```bash
export NEXT_PUBLIC_SUPABASE_URL="https://your-project.supabase.co"
export NEXT_PUBLIC_SUPABASE_ANON_KEY="your-anon-key"
export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"
export SUPABASE_DB_URL="postgresql://postgres:password@db-host:5432/postgres"
```

If your Supabase dashboard labels the frontend key as `publishable key`, this app also accepts:

```bash
export NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY="your-publishable-key"
```

When these variables are present, the app switches into hosted Supabase mode for:

- auth-aware account syncing
- deal reads and writes
- notification persistence
- hosted password recovery and verification flows
- demo deal seeding for shared hosted environments

### AI-assisted matching (optional)

Keyword matching alone misses real matches: a shopper interested in "tacos"
won't match a deal titled "Cinco de Mayo Fiesta Special." Setting an
Anthropic API key turns on a second matching signal that catches these:

```bash
export ANTHROPIC_API_KEY="your-anthropic-api-key"
export AI_CATEGORY_MODEL="claude-3-5-haiku-latest"  # optional, this is the default
```

How it works: both a deal's text and a shopper's saved interest get
classified against the same fixed list of ~30 categories (`pizza`,
`mexican`, `coffee`, `bar`, ...) defined in `AI_CATEGORY_TAXONOMY` in
`app.py`. If a deal and an interest land on any shared category, that
counts as a match — even with zero words in common. Two design choices
matter here and are worth understanding, not just using:

- **Closed taxonomy, not free-form tags.** Asking a model to freely tag
  "tacos" and separately tag "Cinco de Mayo Fiesta Special" won't reliably
  produce the same string. Asking it to classify both against the same
  fixed list reliably lands both on `mexican`.
- **Computed at write time, cached, never on the matching hot path.**
  Categories are computed once per distinct deal/interest string
  (`functools.lru_cache` in `ai_extract_categories`), not once per
  user-times-deal pair. A matching run over many users never makes more API
  calls than there are distinct deals/interests — it's O(unique text), not
  O(users x deals).

Without this key set, matching is keyword-only (word-boundary matching, no
external calls) — everything above is a pure recall booster, never a
requirement, and any failure (no key, network error, timeout, bad model
output) silently falls back to keyword-only matching for that item.

## Current UI flow

1. A shopper or business creates an account or logs in.
2. Shoppers land inside the logged-in app and can:
   - browse local deals
   - search by keyword
   - filter by zip code
   - save favorites
   - review personalized alerts
3. Businesses land on Company Deals and can:
   - post a deal
   - edit a deal
   - archive a deal
   - review active, draft, and expired lifecycle states
4. Prototype controls currently allow:
   - manually running the matching process
5. While the server is running, automatic matching can also run in the background on a schedule.

## Useful API endpoints

- `GET /api/deals`
- `GET /api/system-status`
- `POST /api/signup`
- `POST /api/login`
- `POST /api/logout`
- `POST /api/password-reset/request`
- `POST /api/password-reset/confirm`
- `POST /api/account/password`
- `PUT /api/users/:id/interests`
- `POST /api/company-deals`
- `PUT /api/company-deals/:id`
- `DELETE /api/company-deals/:id`
- `POST /api/ingest`
- `POST /api/match`

## Local files

- app data: `phase1.db`
- notification log: `notification_log.jsonl`
- matching run log: `match_run_log.jsonl`
- frontend: `static/index.html`, `static/app.js`, `static/styles.css`
- backend: `app.py`
- production schema: `supabase/schema.sql`
- production RLS policies: `supabase/rls.sql`
- Supabase setup checklist: `SUPABASE_SETUP_CHECKLIST.md`
- payments planning: `PAYMENTS_READINESS_PLAN.md`
- frontend direction notes: `FRONTEND_POLISH_NOTES.md`
- regression tests: `test_phase1.py`

## Notes

- `GET /api/system-status` tells the UI whether notifications are running in `live_email` or `mock_email` mode.
- `GET /api/system-status` also reports whether the app is still in `local_prototype` auth mode or has enough configuration to move into `hosted_supabase` mode.
- `GET /api/system-status` now also reports matching scheduler state, including last run timing and last run result.
- Password recovery uses real email when SMTP is configured, and a prototype-safe local flow when SMTP is not configured.
- In hosted Supabase mode, signup can require email verification before first login, and the login view supports resending that verification email.
- Logged-in users can change their password from the app, and older sessions are revoked when they do.
- Prototype-mode auth tokens are not stored in raw form in the local database.
- Password reset links use `APP_BASE_URL` when it is set, so local links can later become deployed links without code changes.
- The app currently uses a local SQLite database for prototype speed.
- Search, alert, and merchant panels support smoother scroll behavior for larger result sets.
- Deal cards open into a centered detail modal, return focus when closed, and support `Escape` to close.
- The frontend currently uses a warm neutral palette with restrained bronze and sage accents.
- Shopper favorites and alerts surface summary chips and small insight cards for easier scanning.
- Prototype controls report success and failure inside the hero panel instead of relying on browser alerts.
- Automated regression coverage currently checks signup, auth protection, hosted seeding paths, favorites normalization, company deal CRUD, password reset, matching dedupe, matching word-boundary/AI-category behavior, and system status behavior.
- Secure payments are not yet live in the prototype. The recommended production direction is documented in `PAYMENTS_READINESS_PLAN.md`.
- Matching notifications are digested: a shopper gets one email per matching run (covering every match found in that run), not one email per match. Individual matches are still recorded as separate notification rows and shown separately in the UI.
- Matching now also supports an optional AI-assisted category signal alongside keyword matching — see "AI-assisted matching (optional)" above.

## Current production-path priority

The next major production-path step is finishing the frontend Supabase session cutover and validating the full password recovery and hosted auth experience against the checked-in schema, RLS files, and setup checklist.

## Deliberately deferred: nearby-zip matching

Zip matching today is exact-match only (`deal.zip_code == user.zip_code`).
The natural next improvement is a "nearby zip" radius so a shopper one zip
over from a deal isn't silently excluded — this was considered and
intentionally **not** built in the same pass as the changes above, for two
reasons:

1. **No reliable geo data is available offline.** A defensible radius match
   needs real zip-to-lat/long data (or a geocoding API); a shortcut like
   "same 3-digit zip prefix" is unreliable enough — prefix groups vary
   enormously in size, especially in rural areas — that shipping it silently
   risked producing confidently wrong matches, which is worse than the
   current honest limitation.
2. **It's a real data-model change** (a new column at minimum, arguably a
   join table if a shopper should ever watch more than one zip), and
   `CLAUDE.md`'s operating agreement calls out "changing the data model in a
   way that creates migration risk" as something to stop and confirm
   direction on first, rather than bundle into an unrelated matching-quality
   pass.

Recommended next step when ready: pull in a static USPS/Census zip-centroid
dataset (or a geocoding API), add a nullable `latitude`/`longitude` pair to
`users`/`deals`, and add a radius option to the shopper's alert settings.

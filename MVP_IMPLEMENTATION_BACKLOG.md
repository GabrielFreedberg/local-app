# MVP Implementation Backlog

## Purpose

This backlog translates the roadmap into execution-ready work items for Codex to implement over time.

## Paused For Later

- Supabase cutover is partially prepared and should resume after real project credentials are available.
- Resume point:
  - fill in `.env` from [.env.example](/Users/gabrielfreedberg/Documents/Codex/2026-04-23/files-mentioned-by-the-user-readme/.env.example)
  - create the real Supabase project
  - run [supabase/schema.sql](/Users/gabrielfreedberg/Documents/Codex/2026-04-23/files-mentioned-by-the-user-readme/supabase/schema.sql)
  - run [supabase/rls.sql](/Users/gabrielfreedberg/Documents/Codex/2026-04-23/files-mentioned-by-the-user-readme/supabase/rls.sql)
  - test hosted signup, login, logout, and password reset in browser

## Phase 1: Prototype Stabilization

### Auth and account flow

- [x] ensure user and company flows are fully separated
- [x] improve signup validation
- [x] improve login error handling (2026-08-19: required-field check, and
      in-memory per-email rate limiting after 8 failed attempts — see
      "Login rate limiting" in `API_CONTRACT.md`)
- [x] improve session persistence behavior
- [x] remove prototype-only auth shortcuts (2026-08-19: password-reset
      responses no longer include the raw `resetToken` once the app is
      running on a hosting platform, i.e. `PORT` is set — that exposure is
      now local-dev-only, gated by `running_on_hosting_platform()`)

### Favorites / alert interests

- [x] support add/remove/edit flows cleanly (already implemented — add,
      inline edit with save/cancel, and remove all present in `app.js`;
      verified 2026-08-19)
- [x] prevent duplicate favorites
- [x] improve mobile interaction for favorites (2026-08-19: touch targets
      bumped to 40-48px, more breathing room between action buttons on
      narrow viewports)
- [x] improve empty states

### Search

- [x] improve mobile layout for search
- [x] improve result formatting
- [x] support cleaner loading and error states
- [x] ensure company and grocery deals are clearly distinguishable

### Company deal posting

- [x] improve company onboarding flow (verified 2026-08-19 — signup
      auto-logs a company in and lands them on a dashboard that already
      walks through what to do first: merchant setup tips, a "next
      steps" card, and a merchant-insight card that unlocks after the
      first deal. No gap found worth building over.)
- [x] improve deal form validation
- [x] support deal expiration field (already implemented — `expiresOn`
      input, default +7 days, live preview, and an "expiring soon"
      warning on the dashboard; verified 2026-08-19)
- [x] improve success/error messaging

### Testing and regression safety

- [x] add automated regression coverage for signup and login
- [x] add automated regression coverage for favorites updates
- [x] add automated regression coverage for company deal CRUD
- [x] add automated regression coverage for password reset
- [x] add automated regression coverage for matching dedupe
- [x] add automated regression coverage for matching word-boundary/AI-category behavior

### Matching quality (2026-08-17)

- [x] fix interest matching to use word-boundary matching instead of raw
      substring matching (was producing false positives, e.g. "ice"
      matching "service")
- [x] digest a user's matches from one run into a single email instead of
      one email per match
- [x] add optional AI-assisted category matching (`ANTHROPIC_API_KEY`) as a
      recall layer on top of keyword matching, closed taxonomy, cached,
      fails closed
- [ ] nearby-zip / radius matching — deliberately deferred, see
      "Deliberately deferred: nearby-zip matching" in `README.md` for why
      and what it needs (real geo data + a data-model decision)

## Phase 2: Production Foundation

### Supabase setup

- [ ] create Supabase project
- [x] create schema
- [x] create RLS policies
- [ ] connect app to Supabase Auth
- [ ] connect app to Supabase Postgres
- [x] add Supabase setup checklist

### Data migration

- [ ] map prototype user accounts to profiles
- [ ] map favorites to alert_interests
- [ ] map company deals into deals table
- [ ] define notification migration strategy

## Phase 3: Real Notifications

### Email delivery

- [ ] choose provider
- [ ] implement provider client
- [ ] store send status
- [ ] store failure reason
- [ ] add retry-safe send logic

### Matching jobs

- [ ] define matching worker entrypoint
- [ ] query active deals by zip
- [ ] match against alert interests
- [ ] dedupe notifications

## Phase 4: Merchant Readiness

- [ ] company dashboard basics
- [ ] active deals view
- [ ] expired deals view
- [ ] edit deal
- [ ] archive deal

## Phase 5: Launch Readiness

- [ ] analytics events
- [ ] onboarding polish
- [ ] small pilot checklist
- [ ] launch QA checklist

## High-priority architecture docs

- [x] development operating plan
- [x] 8-week roadmap
- [x] auth and schema plan
- [x] API contract doc (`API_CONTRACT.md`, 2026-08-19)
- [x] notification provider decision doc (`NOTIFICATION_PROVIDER_DECISION.md`,
      2026-08-19 — recommends Resend over SMTP, zero code changes needed)
- [x] launch checklist (`LAUNCH_CHECKLIST.md`, 2026-08-19)

## Design pass 2 (2026-08-19)

- [x] deal cards without a real photo now get a colored monogram instead
      of a flat empty placeholder box (5 palette-derived variants)
- [x] hero section got a second background accent + a subtle entrance
      animation (respects `prefers-reduced-motion`)
- [x] system status badge got a color-coded status dot (pulses when live)

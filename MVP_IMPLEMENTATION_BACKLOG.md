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
- [ ] improve login error handling
- [x] improve session persistence behavior
- [ ] remove prototype-only auth shortcuts

### Favorites / alert interests

- [ ] support add/remove/edit flows cleanly
- [x] prevent duplicate favorites
- [ ] improve mobile interaction for favorites
- [x] improve empty states

### Search

- [x] improve mobile layout for search
- [x] improve result formatting
- [x] support cleaner loading and error states
- [x] ensure company and grocery deals are clearly distinguishable

### Company deal posting

- [ ] improve company onboarding flow
- [x] improve deal form validation
- [ ] support deal expiration field
- [x] improve success/error messaging

### Testing and regression safety

- [x] add automated regression coverage for signup and login
- [x] add automated regression coverage for favorites updates
- [x] add automated regression coverage for company deal CRUD
- [x] add automated regression coverage for password reset
- [x] add automated regression coverage for matching dedupe

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
- [ ] API contract doc
- [ ] notification provider decision doc
- [ ] launch checklist

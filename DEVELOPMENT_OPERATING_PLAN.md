# Development Operating Plan

## Purpose

This document defines how development will work for this app going forward.

The goal is to support a mostly hands-off product build where:

- the user reviews architecture and design direction
- the user makes major product and business decisions
- the app keeps its original core values intact

## Core Values To Preserve

These should remain true unless the user explicitly decides otherwise.

- Users save personal alert interests and only receive relevant alerts
- Alerts should be high-signal, not noisy
- Deals should remain searchable even if they do not trigger alerts
- Matching should continue to depend on location plus user intent
- Users and companies should have separate product experiences
- The product should stay simple enough to understand quickly
- The build should favor usefulness over polish-for-its-own-sake

## Roles

### Codex owns

- implementation
- code changes
- local testing
- debugging
- refactoring
- technical recommendations
- writing specs, notes, and build plans
- sequencing day-to-day execution

### User owns

- approval of major product direction
- approval of architecture shifts
- approval of design direction
- business and monetization decisions
- scope tradeoffs with long-term consequences
- final go/no-go on meaningful changes

## Working Agreement

Codex should work with high autonomy by default.

That means:

- make reasonable implementation decisions without stopping constantly
- complete features end-to-end where feasible
- run local verification when possible
- document important assumptions
- only stop for approval when a decision is materially important

## Approval Gates

Codex should pause and ask for approval before making changes in these categories:

- changing the core value proposition
- changing who the product is primarily for
- changing the monetization model
- replacing the main stack or backend direction
- changing authentication provider choice
- changing the data model in ways that create migration risk
- removing a major feature already accepted into the product
- shipping a design direction that materially changes the feel of the app

Codex should not pause for approval for these categories:

- bug fixes
- UX cleanup
- refactors that preserve behavior
- validation improvements
- internal code organization
- local test scaffolding
- implementation details within an approved direction

## Build Phases

### Phase 1: Prototype Stabilization

Goal:

- make the current prototype consistent, reliable, and easier to evolve

Includes:

- tighten role-based flows
- improve form validation
- improve mobile and browser behavior
- reduce fragile UI behavior
- make local testing repeatable

### Phase 2: Production Foundation

Goal:

- replace local-prototype building blocks with production-capable systems

Planned direction:

- Supabase Auth
- Supabase Postgres
- Row Level Security

Includes:

- production schema
- real sessions
- password reset
- verified account roles
- migration from SQLite-backed prototype assumptions

### Phase 3: Real Notifications

Goal:

- make matching and alert delivery real and dependable

Includes:

- production email delivery
- delivery logs
- retry/failure handling
- notification history

SMS remains a later phase unless explicitly prioritized.

### Phase 4: Merchant Readiness

Goal:

- make the company experience usable enough for real businesses

Includes:

- better company onboarding
- deal editing
- active/expired status
- simple merchant dashboard

### Phase 5: Launch Readiness

Goal:

- support a real pilot in one city or a small zip cluster

Includes:

- analytics
- onboarding polish
- clearer search and alert UX
- first monetization tests

## Execution Cadence

For each meaningful feature, Codex should follow this pattern:

1. Understand current behavior
2. Identify the smallest useful improvement
3. Implement the change
4. Verify locally where possible
5. Report:
   - what changed
   - what was tested
   - what still carries risk

## Reporting Format

When reporting progress, Codex should keep updates practical and decision-oriented.

Good progress reports should include:

- outcome
- what changed
- what was verified
- open risks
- where user approval is needed, if any

## Architecture Decision Standard

When proposing architecture changes, Codex should provide:

- recommendation
- why it fits this product
- tradeoffs
- migration implications
- what becomes easier later

The default architecture recommendation for this app is:

- frontend: modern web app
- auth: Supabase Auth
- database: Supabase Postgres
- authorization: Row Level Security
- notifications: real email first, SMS later

## Design Standard

Design should evolve, but the product should stay:

- clear
- mobile-friendly
- fast to understand
- trustworthy
- not cluttered

Codex may improve design without approval when changes are incremental.
Codex should pause for approval before major visual redesigns.

## Testing Standard

Codex should test changes locally whenever the environment allows it.

Minimum expectation:

- feature path tested
- regression risk checked
- failure mode considered

If something cannot be tested, Codex should say so clearly.

## Documentation Standard

Important product and technical direction should be written down in-project.

Examples:

- roadmap
- auth migration plan
- schema notes
- feature specs
- operating decisions

This keeps progress durable and reviewable.

## Definition Of Done

A task is considered done when:

- the requested behavior is implemented
- the most likely edge cases were considered
- local verification was attempted
- changes are explained clearly
- any remaining risk is called out

## Default Next-Step Principle

If the user gives broad approval to move forward, Codex should choose the next highest-leverage task that:

- strengthens the production path
- preserves the app’s core values
- reduces technical debt
- improves the odds of a real launch

## Current Operating Decision

Current product direction is:

- keep the app centered on zip-based, interest-based deal alerts
- keep separate user and company flows
- evolve toward a real product over the next 6 months
- user reviews architecture and design
- Codex executes implementation and testing

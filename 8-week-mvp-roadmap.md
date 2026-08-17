# 8-Week MVP Roadmap

## Goal

Turn the current prototype into a real MVP that can support a focused soft launch, real user accounts, real company accounts, and early monetization tests.

## Core product thesis

Users save **Alert Interests** like `chicken`, `beer`, `rice`, or `avocados`.
They receive alerts only when:

- the deal is in their zip code
- the deal matches one of their alert interests

Companies create company accounts and post local deals.

## Recommended stack

- Frontend: Next.js
- Auth: Supabase Auth
- Database: Supabase Postgres
- Permissions: Supabase Row Level Security
- Email: Resend or Postmark
- SMS later: Twilio or Amazon SNS
- Hosting: Vercel + Supabase

## Why Supabase Auth

- Email/password support now
- Password reset and email verification
- Works cleanly with role-based Postgres tables
- Supports secure sessions without custom auth work
- Lets us move from prototype to production without rewriting the whole data layer

## Account model

Two account roles:

- `user`
- `company`

User accounts can:

- search deals
- manage favorites / alert interests

Company accounts can:

- create and manage local deals

## Week 1: Architecture reset

- Lock MVP scope to one city or one small zip cluster
- Finalize the product rules:
  - all deals are searchable
  - only zip + interest matches trigger alerts
- Define production schema for:
  - auth users
  - user profiles
  - company profiles
  - alert interests
  - deals
  - notifications
  - delivery history

## Week 2: Real auth

- Replace prototype auth with Supabase Auth
- Add secure sessions
- Add password reset
- Add email verification
- Add profile creation after signup
- Add role assignment:
  - user
  - company

## Week 3: Production database

- Move from SQLite to Supabase Postgres
- Add Row Level Security policies
- Ensure:
  - users can only edit their own alert interests
  - companies can only edit their own deals
  - company data is separated cleanly from user data

## Week 4: Deals and company workflow

- Build company deal creation and editing
- Add expiration fields
- Add status fields:
  - draft
  - active
  - expired
- Make company deal posting stable on mobile

## Week 5: User workflow

- Build polished user onboarding
- Save alert interests in production DB
- Improve favorites management
- Build mobile-first search flow
- Keep search readable and fast

## Week 6: Matching and notifications

- Build scheduled matching jobs
- Match only on:
  - zip code
  - alert interests
- Add real email delivery
- Track:
  - queued
  - sent
  - failed

## Week 7: Merchant and product polish

- Add simple company dashboard
- Show active and expired deals
- Add success/error states
- Add basic analytics:
  - deals posted
  - alerts triggered
  - notification sends

## Week 8: Soft launch

- Launch with a small set of users and companies
- Stay focused on one area
- Measure:
  - signups
  - favorites saved
  - deal posts
  - alerts sent
  - repeat usage

## Non-goals during the first 8 weeks

- Nationwide rollout
- Native app
- Broad grocery chain integrations everywhere
- Full SMS rollout
- Complex recommendation engine

## Early monetization path

Best first revenue path:

- charge companies first

Example:

- free company tier: limited active deals
- paid company tier: unlimited active deals or boosted placement

## Success criteria

By the end of 8 weeks, the product should have:

- real auth
- role-based accounts
- production database
- company deal posting
- user favorites / alert interests
- zip + interest matching
- real email delivery
- first users and first companies

## Biggest risk

The biggest risk is alert quality.

If alerts do not feel personal and useful, people will ignore them.
The core of the business is high-signal matching, not just sending more notifications.

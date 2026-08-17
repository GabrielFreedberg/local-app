# Supabase Auth And Schema Plan

## Goal

Define the production auth and database structure for the app so implementation can move quickly and cleanly from prototype to MVP.

## Recommended production stack

- Auth: Supabase Auth
- Database: Supabase Postgres
- Authorization: Supabase Row Level Security
- Email notifications: Resend or Postmark
- Frontend: Next.js or another modern web app framework

## Why Supabase

- supports email/password immediately
- supports password reset and email verification
- works naturally with Postgres
- supports role-based access patterns well
- avoids writing custom auth/session logic too early

## Core product rules

- users only get alerts for deals matching both:
  - their zip code
  - one of their alert interests
- all deals remain searchable even if they do not trigger alerts
- users and companies have different product experiences
- company accounts can only manage their own deals
- user accounts can only manage their own alert interests and preferences

## Auth model

Supabase Auth handles:

- sign up
- sign in
- password reset
- session management
- email verification

Application profile data lives in Postgres tables linked to the auth user id.

## Roles

Two application roles:

- `user`
- `company`

Store the role in profile data and enforce access with RLS.

## Proposed tables

### `profiles`

Purpose:

- one profile row per authenticated account

Columns:

- `id uuid primary key`
  - matches Supabase auth user id
- `account_type text not null`
  - `user` or `company`
- `email text not null`
- `phone_number text`
- `zip_code text not null`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

### `user_profiles`

Purpose:

- user-specific fields

Columns:

- `id uuid primary key references profiles(id)`
- `display_name text`
- `alert_channel_email boolean not null default true`
- `alert_channel_sms boolean not null default false`

### `company_profiles`

Purpose:

- company-specific fields

Columns:

- `id uuid primary key references profiles(id)`
- `company_name text not null`
- `contact_name text`
- `status text not null default 'active'`

### `alert_interests`

Purpose:

- user favorites / alert interests

Columns:

- `id uuid primary key default gen_random_uuid()`
- `user_id uuid not null references user_profiles(id) on delete cascade`
- `label text not null`
- `normalized_label text not null`
- `created_at timestamptz not null default now()`

Constraint:

- unique on `(user_id, normalized_label)`

### `deals`

Purpose:

- single searchable deal table for grocery and company deals

Columns:

- `id uuid primary key default gen_random_uuid()`
- `deal_type text not null`
  - `grocery` or `company`
- `company_id uuid null references company_profiles(id)`
- `source_store_name text`
- `source_store_id text`
- `title text not null`
- `description text not null`
- `category text`
- `sale_price numeric`
- `regular_price numeric`
- `unit text`
- `zip_code text not null`
- `status text not null default 'active'`
  - `draft`, `active`, `expired`
- `starts_at timestamptz`
- `ends_at timestamptz`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

### `notifications`

Purpose:

- all alert attempts and sends

Columns:

- `id uuid primary key default gen_random_uuid()`
- `user_id uuid not null references user_profiles(id) on delete cascade`
- `deal_id uuid not null references deals(id) on delete cascade`
- `channel text not null`
  - `email`, `sms`
- `status text not null`
  - `queued`, `sent`, `failed`
- `subject text`
- `message text not null`
- `matched_interest text`
- `error_message text`
- `created_at timestamptz not null default now()`
- `sent_at timestamptz`

Constraint:

- unique on `(user_id, deal_id, channel, matched_interest)`

## Recommended indexes

- `profiles(account_type)`
- `profiles(zip_code)`
- `alert_interests(user_id)`
- `alert_interests(normalized_label)`
- `deals(zip_code, status)`
- `deals(deal_type, status)`
- `notifications(user_id, created_at desc)`

## Row Level Security rules

### Profiles

- users can read and update only their own profile

### User profiles

- user accounts can read and update only their own row

### Company profiles

- company accounts can read and update only their own row

### Alert interests

- user accounts can create, read, update, and delete only their own alert interests
- company accounts cannot access alert interests

### Deals

- all authenticated users can read active deals
- company accounts can create and update only their own company deals
- user accounts cannot create company deals

### Notifications

- users can read only their own notifications
- companies cannot read user notification history

## Matching logic

For each active user:

1. load user zip code
2. load user alert interests
3. find active deals in that zip code
4. match deal title + description against normalized alert interests
5. create notification rows for new matches
6. send through email provider

## Data normalization

Normalize alert interests and searchable deal text by:

- lowercasing
- trimming whitespace
- collapsing duplicate spaces

Later improvements:

- synonyms
- category mapping
- stemming / tokenization

## Migration path from prototype

1. replace local account creation with Supabase Auth sign up
2. create profile rows after signup
3. move favorites into `alert_interests`
4. move company deals into `deals`
5. move grocery feed results into `deals`
6. move notifications into `notifications`

## First implementation priority

Build these in order:

1. Supabase project setup
2. schema creation
3. RLS policies
4. auth wiring
5. user signup/login flow
6. company signup/login flow
7. favorites save/remove flow
8. company deal posting flow
9. search flow
10. matching job

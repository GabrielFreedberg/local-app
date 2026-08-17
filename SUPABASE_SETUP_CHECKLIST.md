# Supabase Setup Checklist

This checklist is the concrete production-auth starting point as of Thursday, July 23, 2026.

## Goal

Stand up Supabase Auth and Supabase Postgres for this app without losing the current core behavior:

- separate user and company account flows
- zip-based plus favorites-based alert matching
- searchable deal browsing for everyone
- business-only deal management

## Environment variables to prepare

Frontend and app shell:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` or `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`

Server-side or worker-side:

- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_DB_URL`
- `APP_BASE_URL`

Email:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `EMAIL_FROM`

Where to find them:

- `NEXT_PUBLIC_SUPABASE_URL`: Supabase project settings → API → Project URL
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Supabase project settings → API → anon public key
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: Supabase project settings → API Keys → publishable key
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase project settings → API → service_role secret key
- `SUPABASE_DB_URL`: Supabase project settings → Database → connection string
- `APP_BASE_URL`: the public base URL where this app runs, or `http://127.0.0.1:8000` for local testing

## Initial Supabase project steps

1. Create a new Supabase project.
2. Enable email/password sign-in.
3. Turn on email confirmation.
4. Configure the site URL and redirect URLs for local development and production.
5. Add the environment variables above to the app environment.

## Database setup steps

1. Run [supabase/schema.sql](/Users/gabrielfreedberg/Documents/Codex/2026-04-23/files-mentioned-by-the-user-readme/supabase/schema.sql).
2. Run [supabase/rls.sql](/Users/gabrielfreedberg/Documents/Codex/2026-04-23/files-mentioned-by-the-user-readme/supabase/rls.sql).
3. Confirm the following tables exist:
   - `profiles`
   - `user_profiles`
   - `company_profiles`
   - `alert_interests`
   - `deals`
   - `notifications`
4. Confirm the auth-user trigger creates the correct profile shape after signup.

## Auth metadata contract

When creating a Supabase account, send these metadata fields:

- `account_type`
- `zip_code`
- `phone_number`
- `display_name` for users when available
- `company_name` for companies
- `contact_name` for companies when available

## App migration order

1. Replace frontend login/signup/logout/reset calls with Supabase Auth methods.
2. Replace local session-token storage with Supabase session handling.
3. Read user role and zip data from `profiles`.
4. Move favorites UI reads and writes to `alert_interests`.
5. Move company deal creation/editing/deletion to `deals`.
6. Move notifications/history reads to `notifications`.
7. Keep local mock ingest and matching only until a Supabase-backed worker replaces them.

## Verification checklist

- user signup creates `profiles` + `user_profiles`
- company signup creates `profiles` + `company_profiles`
- password reset email works through Supabase Auth
- users can only edit their own favorites
- companies can only edit their own deals
- authenticated users can read active deals
- users can only read their own notifications

## Notes

- The current Python prototype can keep running during migration, but it should be treated as transitional once Supabase Auth is live.
- The next production-safe step after this checklist is wiring the frontend to Supabase sessions and moving deal/favorites writes off the local SQLite path.

# API Contract

This documents the actual HTTP surface of `app.py` as of 2026-08-19 — every
route it registers, what it expects, and what it returns. It reflects the
code, not aspiration; if this ever disagrees with `app.py`, the code wins
and this file needs an update in the same session.

## Conventions

- All request/response bodies are JSON. `Content-Type: application/json`.
- Authenticated routes require `Authorization: Bearer <sessionToken>`. The
  token is opaque (not a JWT) — see `LEARNING_GUIDE.md` §5 for the
  selector/secret pattern behind it.
- Every route runs through both a local-prototype (SQLite) and a hosted
  (Supabase) implementation, selected by `supabase_is_configured()`. The
  response shapes below are the same either way; only the storage behind
  them differs.
- Error responses are always `{"error": "<message>"}`. There is no
  structured error code field — match on the message string or the HTTP
  status.
- CORS is wide open (`Access-Control-Allow-Origin: *`) — a known,
  deliberate prototype simplification, not an oversight. Revisit before a
  real production deployment if the frontend and API ever live on
  different origins for real (today they don't — same server, same port).

## Auth & account

### `POST /api/signup`
Body: `{accountType: "user"|"company", email, password, phoneNumber, zipCode, companyName?}`
(`companyName` required when `accountType` is `"company"`.)
Response `201`: `{message, sessionToken, user}` — signup auto-logs-in in
local-prototype mode.
Errors: `400` validation, `409` email already registered.

### `POST /api/login`
Body: `{email, password}`.
Response `200`: `{ok: true, sessionToken, user}`.
Errors: `400` missing email/password, `401` invalid credentials, `429`
too many failed attempts for that email (see "Login rate limiting" below).

### `POST /api/logout`
Auth required. Revokes the current session token.
Response `200`: `{ok: true}`.

### `GET /api/session`
Auth required. Response `200`: `{ok: true, sessionToken, user}` — used to
restore a session on page load.

### `POST /api/password-reset/request`
Body: `{email}`. Always returns `200` (never reveals whether the email
exists — `{ok: true, message, ...systemStatus}`). When SMTP isn't
configured AND the app isn't running on a hosting platform (see
`running_on_hosting_platform()` in `app.py`), the response also includes
`resetToken` directly, since there's no email to deliver it through in
local dev. That field is omitted once deployed, even without SMTP.

### `POST /api/password-reset/confirm`
Body: `{token, newPassword}`. Response `200`: `{ok: true, message,
sessionToken, user}` — also revokes all of that user's other sessions.
Errors: `400` invalid/expired/already-used token, or weak password.

### `POST /api/account/password`
Auth required. Body: `{currentPassword, newPassword}`. Response `200`:
new `sessionToken` (all other sessions revoked). Errors: `400` weak
password, `401` current password wrong.

## Deals

### `GET /api/deals`
No auth required. Response `200`: `{deals: [...]}` — every active deal,
regardless of viewer's zip/interests (search stays open to everyone; only
*alerts* are filtered — see `README.md` "Core product rules").

### `GET /api/company-deals`
Auth required, company account only. Response `200`: `{deals: [...]}` —
that company's own deals (active, draft, and expired; archived excluded).
Errors: `403` if the authenticated account isn't a company.

### `POST /api/company-deals`
Auth required, company account only. Body: `{companyName, zipCode,
address, description, status: "active"|"draft", expiresOn?}`
(`expiresOn` is `YYYY-MM-DD`; defaults to 7 days out if omitted). Creating
an exact duplicate of an existing active deal auto-archives the older one
(see `test_duplicate_company_deal_create_archives_older_exact_match`).
Response `201`: the created deal.

### `PUT /api/company-deals/:id`
Auth required, owning company only. Same body shape as create. Response
`200`: the updated deal. `403` if the deal belongs to a different company.

### `DELETE /api/company-deals/:id`
Auth required, owning company only. Archives (soft-deletes) the deal.
Response `200`: `{ok: true}`.

## Favorites / alert interests

### `PUT /api/users/:id/interests`
Auth required, must be `:id`'s own account. Body: `{alertInterests:
[string, ...]}` — normalized (trimmed, lowercased, deduped) server-side
via `normalize_alert_interests`. Response `200`: the updated user record.

## Matching & notifications

### `POST /api/match`
Auth required (any authenticated user can trigger it — this is a
prototype convenience; a real deployment would restrict this to the
scheduler and/or an admin role). Runs `run_matching_job("manual")`
synchronously. Response `200`: `{ok: true, notificationsSent,
...systemStatus}`. `notificationsSent` counts individual matches, not
emails sent — see "Notification digesting" in `README.md`: multiple
matches for one user in one run still send as a single email.

### `GET /api/notifications`
Auth required. Response `200`: `{notifications: [...]}` — only the
authenticated user's own notification history.

### `POST /api/ingest`
Auth required. Seeds the mock grocery + pizza demo deals if they don't
already exist. Response `200`: `{ok: true, dealsIngested, ...systemStatus}`.

## System

### `GET /api/system-status`
No auth required. Response `200`:
```json
{
  "authProvider": "local_prototype" | "supabase",
  "authMode": "local_session_tokens" | "hosted_supabase",
  "supabaseUrl": "...",
  "supabaseAnonKey": "...",
  "appBaseUrl": "...",
  "smtpConfigured": true | false,
  "notificationMode": "mock_email" | "live_email",
  "passwordResetMode": "manual_token" | "email" | "hosted_email_link",
  "matchingScheduler": { "enabled": ..., "intervalSeconds": ..., "lastTrigger": ..., "lastRunNotifications": ..., "lastRunError": ..., "runCount": ... },
  "serverTime": "..."
}
```
This is what the frontend polls to decide which mode banner to show and
whether hosted-Supabase-only UI (like resend-verification) should appear.

### `GET /api/users`
Auth required (any authenticated user). Response `200`: `{users: [...]}`
— used by the prototype's own debug/inspection views. Worth narrowing or
removing before any real multi-tenant deployment; today any logged-in
account can list every other account's public profile fields (no
passwords/tokens are ever included, but this is broader than a real
product should expose).

## Login rate limiting

Local-prototype login (`POST /api/login`) locks out an email after
`LOGIN_MAX_ATTEMPTS` (8) failed attempts within `LOGIN_LOCKOUT_MINUTES`
(15), returning `429`. This is in-memory and per-process — it resets on
restart and doesn't coordinate across multiple app instances. Hosted mode
doesn't use this path at all (the frontend talks to Supabase Auth
directly, which has its own limits). See `app.py`'s `login_locked_out` /
`record_login_failure` for the implementation.

## Static files

### `GET /`, `GET /static/*`
Serves `static/index.html`, `static/app.js`, `static/styles.css` with
`Cache-Control: no-store` (deliberate for a fast-moving prototype —
revisit before production, where you'd want real caching + cache-busting).

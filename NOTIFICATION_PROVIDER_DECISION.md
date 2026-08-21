# Notification Provider Decision

## Recommendation: Resend, over SMTP, no code changes required

Use **Resend** (resend.com) for real email delivery. Second choice:
**Postmark** — nearly identical tradeoffs, pick it if Resend's free tier
or deliverability data doesn't hold up in testing. Skip Amazon SES for now
(see "Why not SES" below) and skip SendGrid (see "Why not SendGrid").

The concrete reason this is an easy call: **`app.py` already sends email
over plain SMTP** (`smtplib`, see `send_match_email` and
`send_password_reset_email`). Resend and Postmark both expose a
transactional-SMTP endpoint alongside their HTTP APIs, so switching from
mocked email to real Resend-delivered email is a pure configuration
change — set `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/`SMTP_PASSWORD` in
`.env` to Resend's SMTP credentials, done. No new dependency, no rewrite
of the sending code, nothing to test beyond what `test_phase1.py` already
covers for the SMTP-configured path. That's the deciding factor over
providers that are HTTP-API-only.

## Setup (when ready)

1. Create a Resend account, verify a sending domain (or use their shared
   test domain while iterating).
2. Resend dashboard → SMTP credentials → copy host/port/username/password.
3. Set in `.env` (or Railway's environment variables once deployed):
   ```bash
   SMTP_HOST="smtp.resend.com"
   SMTP_PORT="587"
   SMTP_USERNAME="resend"
   SMTP_PASSWORD="<your Resend API key>"
   EMAIL_FROM="alerts@yourdomain.com"
   ```
4. That's it — `smtp_is_configured()` flips to true, `/api/system-status`
   reports `notificationMode: "live_email"`, and `send_match_email` /
   `send_password_reset_email` start sending for real instead of logging
   to `notification_log.jsonl`.

## Why not SES

Amazon SES is the cheapest option at scale and a reasonable long-term
choice once volume justifies the operational overhead, but it starts
every new account in a sandbox that only sends to verified addresses
until you request production access (a manual AWS review, can take days),
and its SMTP credentials are IAM-derived rather than a one-click API key.
For a prototype-to-early-launch project, that setup friction isn't worth
it yet. Worth revisiting once monthly send volume is large enough that
Resend/Postmark's per-email pricing actually matters.

## Why not SendGrid

Functionally comparable to Resend/Postmark and also supports SMTP, but
has a worse reputation for deliverability consistency and account
reviews/holds on new senders in recent years. No specific advantage over
Resend for this project's scale, so no reason to prefer it.

## What this doesn't change

- **Mocked mode still works exactly as today** when no SMTP env vars are
  set — nothing about this decision requires acting on it immediately.
- **The matching/digest logic is unaffected.** This is purely about the
  transport for `send_match_email`/`send_password_reset_email`; see
  `README.md`'s "AI-assisted matching" and `LEARNING_GUIDE.md` §4.5 for
  how those messages get built and to whom.
- **SMS (Phase beyond this doc)**: `8-week-mvp-roadmap.md` lists Twilio or
  Amazon SNS for later SMS support — not addressed here since no SMS
  sending code exists in `app.py` yet.

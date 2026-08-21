# Launch QA Checklist

Scope: a small, focused soft launch per `8-week-mvp-roadmap.md` Week 8 (one
zip cluster, a handful of real shoppers and businesses) — not a general
public launch. Work through this top to bottom; each section links to the
doc that has the full detail behind it.

## 1. Infrastructure is real, not local

- [ ] GitHub repo is the source of truth and CI is green — see
      `AUTOMATION.md` step 1 (done as of 2026-08-17, confirm still green
      before launch).
- [ ] Supabase project is live, `supabase/schema.sql` and
      `supabase/rls.sql` have been run against it, and hosted
      signup/login/logout/password-reset have been manually verified in a
      real browser — see `AUTOMATION.md` step 2 and
      `SUPABASE_SETUP_CHECKLIST.md`. **Not yet done as of this writing.**
- [ ] Railway (or equivalent) is hosting the live app 24/7, deployed
      *after* Supabase is confirmed live (ordering matters — see the
      "gotcha" in `AUTOMATION.md` step 3, ephemeral disk + SQLite data loss).
- [ ] Real email sending is configured per
      `NOTIFICATION_PROVIDER_DECISION.md` (Resend via SMTP) — confirm
      `/api/system-status` reports `notificationMode: "live_email"` on the
      deployed instance, not `mock_email`.
- [ ] `ANTHROPIC_API_KEY` set if AI-assisted matching should be live at
      launch (optional — the app works fully without it, see README
      "AI-assisted matching").

## 2. Data model matches what's actually live

- [ ] Confirm the deployed app is genuinely running in `hosted_supabase`
      auth mode (`GET /api/system-status`), not silently still on
      local-prototype SQLite.
- [ ] RLS policies verified with a real second account: a shopper cannot
      read/edit another shopper's alert interests, a company cannot
      edit/archive another company's deals. See `LEARNING_GUIDE.md` §6
      for the specific policies to spot-check.

## 3. Core product rule still holds

- [ ] All deals remain searchable regardless of a shopper's saved
      favorites (open search).
- [ ] Alerts fire only on zip + interest match, and only one digest email
      per user per matching run — not one per match. See "Core product
      rules" and "Matching quality" in `README.md`.
- [ ] Run the regression suite one final time against the deployed
      configuration's code path: `python3 -m unittest -v test_phase1.py`
      — all tests green, including the matching/AI-category/rate-limiting
      tests added 2026-08-17/19.

## 4. Security basics

- [ ] `resetToken` is confirmed absent from `/api/password-reset/request`
      responses on the deployed instance (it should auto-hide once
      Railway's `PORT` env var is present — verify, don't just trust the
      code path; see `running_on_hosting_platform()` in `app.py`).
- [ ] Login rate limiting confirmed working against the deployed instance
      (8 failed attempts locks out for 15 minutes) — note this is
      per-process/in-memory, see "Login rate limiting" in
      `API_CONTRACT.md`; acceptable for a single-instance soft launch,
      revisit if you ever run more than one instance.
- [ ] `GET /api/users` exposure reviewed — see the note in
      `API_CONTRACT.md`; decide whether to restrict it before real user
      data is in there.
- [ ] All secrets (Supabase keys, SMTP password, Anthropic key) live in
      Railway's environment variables, not committed to the repo — spot
      check `.gitignore` covers `.env`.

## 5. Manual smoke test (do this on the actual deployed URL, not localhost)

- [ ] Sign up as a shopper, save 2-3 favorites, confirm they persist on
      reload.
- [ ] Sign up as a business, post a deal with an expiration date, confirm
      it shows up in shopper search within the same zip.
- [ ] Trigger matching (`POST /api/match` or wait for the scheduler),
      confirm exactly one email arrives (check the real inbox, not
      `notification_log.jsonl`).
- [ ] Password reset: request it, confirm a real email arrives (not a
      `resetToken` in a JSON response), complete the flow.
- [ ] Test on one real mobile device, not just a resized browser window.

## 6. Basic analytics (per roadmap Week 7-8)

- [ ] Decide what to track before launch, not after: signups, favorites
      saved, deal posts, alerts sent, repeat usage — see "Success
      criteria" in `8-week-mvp-roadmap.md`. No analytics code exists yet;
      this is a placeholder for that decision, not a claim it's built.

## 7. Rollback plan

- [ ] Confirm you can redeploy the previous Railway build in under a few
      minutes if something breaks post-launch.
- [ ] Confirm Supabase has point-in-time recovery or at least a recent
      manual backup before go-live.

## Explicitly out of scope for this launch

Per "Non-goals during the first 8 weeks" in `8-week-mvp-roadmap.md`:
nationwide rollout, native app, broad grocery chain integrations, full SMS
rollout, a recommendation engine. Also out of scope per README's
"Deliberately deferred" section: nearby-zip/radius matching.

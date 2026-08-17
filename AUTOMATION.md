# Automation Plan — Local Deal Alert

Why this exists: "fully automated by Claude" only means something concrete
once you know what Claude actually has and doesn't have. This documents
the real architecture that gets there, what's already done, and exactly
what's left — for both of us to track.

## The honest constraint this plan is built around

Claude doesn't have its own always-on server. Compute only exists during a
session — either you're actively chatting, or a scheduled task wakes a
fresh session up briefly to do something and then it ends again. That
means "automated" can't mean "Claude runs the app 24/7" — it has to mean:
the project's source of truth and running instance live on infrastructure
that stays up on its own, and Claude (interactively or via scheduled
check-ins) acts on that infrastructure rather than being it.

Three pieces of persistent infrastructure make that true:

| Piece | Role | Status |
|---|---|---|
| **GitHub repo** | Source of truth (not "whatever's on your laptop right now"); enables real CI | You're connecting one now |
| **Supabase project** | Persistent database + auth, always up regardless of any laptop | Credentials requested, pending |
| **Railway** | Runs the actual live app 24/7, independent of your laptop or any Claude session | Not yet connected |

Once all three exist, "automated" is real: push code → GitHub Actions runs
the test suite automatically → Railway redeploys automatically → the app
stays live and correct without anyone's laptop needing to be open. Claude's
role at that point is making changes, verifying them, and pushing — the
same shape as any engineer working against real infrastructure.

## Setup checklist

### 1. GitHub (in progress)

- [ ] Create an empty repo (no README/gitignore/license — this project
      already has its own) at github.com/new
- [ ] On your Mac: place the CI workflow file (sent separately, since
      Claude's device-write tool is blocked from writing into `.github/`
      for security reasons) at
      `Documents/LocalDealsApplication/.github/workflows/tests.yml`
- [ ] Run the git init/commit/push commands (given in chat) to push the
      whole project, including that workflow file
- [ ] Once pushed, GitHub Actions runs the 29-test regression suite on
      every push automatically — check the "Actions" tab on the repo to
      confirm it went green

### 2. Supabase (requested, pending credentials)

- [ ] Create a project at supabase.com if you don't have one
- [ ] Share the 4 values (Project URL, anon/publishable key, service role
      key, DB connection string — see `SUPABASE_SETUP_CHECKLIST.md` for
      exactly where to find each)
- [ ] Claude runs `supabase/schema.sql` then `supabase/rls.sql` against it
      and verifies hosted signup/login/reset end to end

### 3. Railway (chosen, not yet connected)

- [ ] Sign up at railway.app (free tier is enough for this)
- [ ] New Project → Deploy from GitHub repo → select this repo (needs
      step 1 done first)
- [ ] Railway auto-detects Python and uses the `Procfile`
      (`web: python3 app.py`) as the start command — no extra config
      needed there
- [ ] Set environment variables in Railway's dashboard: the 4 Supabase
      values from step 2, plus SMTP values if/when you want real email
      instead of mocked
- [ ] `app.py` already auto-detects Railway's injected `PORT` variable and
      binds `0.0.0.0` automatically (this was a small code change made
      specifically to support this — see commit history once pushed)

**One real gotcha to know going in:** Railway's filesystem resets on
every redeploy unless you attach a persistent volume. That's exactly why
step 2 (Supabase) matters for this step — once hosted mode is live, the
app stops touching local SQLite entirely, so Railway's ephemeral disk
stops being a problem. Doing Railway *before* Supabase would mean losing
all data on every deploy; doing them in the order above avoids that.

### 4. Ongoing automation, once all three exist

- Push a change → GitHub Actions runs tests automatically
- Merge to main → Railway redeploys automatically
- The existing daily scheduled Claude check can be re-pointed from
  "stage files from your Mac" to "clone the GitHub repo" once it exists
  — strictly more reliable, since it no longer depends on your desktop
  app being open

## Current status

See the chat thread for the live status of each checklist item — this
file gets updated as steps complete, but the conversation is the
authoritative "what's done right now."

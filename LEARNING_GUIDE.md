# Local Deal Alert — Technical Deep Dive & Interview Reference

A reference doc, not a skim doc. Written so you can explain this project's
architecture, security model, and data model in real technical depth — and
talk credibly about how it was built with an AI coding agent, which is
increasingly a real interview topic in its own right.

---

## 1. Project overview

A two-sided local marketplace: shoppers save "alert interests" (favorites)
and get notified only when a deal matches both their zip code and a saved
interest; businesses post deals scoped to a zip code. Single Python
backend, no framework, SQLite in local mode, fully wired (but not yet
switched on) for Supabase Postgres + Auth + Row Level Security in
production mode.

---

## 2. System architecture, in depth

### Request lifecycle

`app.py` uses `http.server.ThreadingHTTPServer`, which spawns **one OS
thread per incoming request**. That matters for two reasons worth being
able to explain:

- **Concurrency, not parallelism, for CPU-bound work.** Python's Global
  Interpreter Lock (GIL) means only one thread executes Python bytecode at
  a time. Threading here buys you concurrency for I/O-bound work (waiting
  on SQLite disk I/O, waiting on an SMTP connection, waiting on a Supabase
  HTTP call) — while one request is blocked on I/O, another thread's
  Python code can run. It would *not* buy you speedup for CPU-heavy work.
  For a deal-matching app doing small string comparisons and disk I/O,
  this tradeoff is fine.
- **Shared mutable state needs explicit locking.** The scheduler state
  dict (`MATCHING_SCHEDULER_STATE`) is touched from both the background
  scheduler thread and request-handling threads, so it's wrapped in
  `SCHEDULER_STATE_LOCK` (a `threading.Lock`). The DB-schema-ready flag
  (`DB_SCHEMA_READY`) has the same pattern with `DB_SCHEMA_LOCK`. If you
  removed those locks, you'd get a classic race condition — two threads
  reading `False`, both proceeding to run schema setup redundantly, or
  worse, reading a state dict mid-mutation. This is a legitimate thing to
  point at if asked "show me somewhere in this codebase you had to think
  about concurrency."

### Connection-per-request database pattern

`get_db()` opens a **new SQLite connection on every call**, not a pooled
connection. For SQLite specifically this is reasonable (SQLite connections
are cheap, and SQLite itself serializes writes at the file level), but if
you were asked "how would this change on Postgres," the honest answer is:
you'd want a **connection pool** (e.g. `psycopg2.pool` or an async pool),
because opening a fresh TCP + auth handshake to a real Postgres server on
every request is comparatively expensive. Supabase's REST API (which is
what this app actually talks to in hosted mode, via `supabase_rest_request`)
sidesteps this entirely — you're making HTTP calls to PostgREST, which
manages its own connection pool server-side.

### Two backends behind one interface

Nearly every data-access function in `app.py` has this shape:

```python
def all_deals():
    if supabase_is_configured():
        return supabase_all_deals()
    # ...local SQLite path...
```

This is a manual, ad hoc version of the **strategy pattern** — same
function signature, different implementation selected at runtime by
configuration. It's a legitimate way to talk about "how do you migrate a
system's data layer without a big-bang rewrite," but the honest tradeoff
(worth saying out loud in an interview, it shows maturity) is that it
roughly doubles the surface area for bugs, since every change has to be
made in two places or the paths silently drift apart.

---

## 3. HTTP & REST API design

The API is resource-oriented: `/api/deals`, `/api/company-deals`,
`/api/users/:id/interests`. Verbs map the way REST conventions expect:
`GET` reads, `POST` creates, `PUT` replaces/updates, `DELETE` removes.
Worth being able to explain the status codes actually used and why:

| Code | Used for | Why this one |
|---|---|---|
| `200 OK` | successful read/update | default success |
| `201 Created` | successful signup, deal creation | a resource now exists that didn't before |
| `400 Bad Request` | validation failures | client sent something the server can't accept as-is |
| `401 Unauthorized` | missing/invalid/expired session | *authentication* failed — who are you? |
| `403 Forbidden` | wrong account type, not the resource owner | *authorization* failed — I know who you are, you can't do this |
| `404 Not Found` | unknown route, missing resource | |
| `409 Conflict` | duplicate email on signup | the request is valid but conflicts with existing state |

That 401 vs 403 distinction is a very common interview question — this
codebase actually gets it right consistently (e.g. `handle_company_deal`
returns 403 for a logged-in *user* account hitting a company-only route,
but 401 via `get_authenticated_user` for a missing/bad token).

**Idempotency** is worth knowing cold: `PUT /api/users/:id/interests`
replaces the full favorites list rather than appending, which makes it
idempotent (send it twice with the same body, same end state). Contrast
with a hypothetical `POST /api/users/:id/interests/add` — that would not
be idempotent (send it twice, you'd risk duplicate entries, though this
particular app also normalizes/dedupes interests defensively either way).

---

## 4. Data modeling, in depth

### Local vs. production schema

Local mode uses one flat `users` table with an `account_type` discriminator
column. The production schema (`supabase/schema.sql`) normalizes this into
`profiles` (shared shape) plus `user_profiles` / `company_profiles`
(role-specific extension tables) — a standard **table-per-subtype**
pattern. Trade-off worth articulating: the flat version is simpler to
query (no joins) but mixes concerns and wastes columns (a `company_name`
column that's always NULL for shoppers); the normalized version is
cleaner and enforces shape at the schema level, at the cost of a join
whenever you need the full picture.

### Indexes, and why each one exists

```sql
create index idx_deals_zip_status on public.deals(zip_code, status);
create index idx_deals_type_status on public.deals(deal_type, status);
create index idx_notifications_user_created_at on public.notifications(user_id, created_at desc);
```

These aren't decorative — they exist because of specific query patterns
in the app. `idx_deals_zip_status` supports "find active deals in this
zip" (the core search query). Composite index column order matters: it's
built `(zip_code, status)` because queries filter by zip first and status
second — a composite index can efficiently serve queries on the leading
column(s) but not on the trailing column alone. If you were asked "why
this order and not the reverse," that's the answer.

### Constraints doing application logic

```sql
unique (user_id, deal_id, channel, matched_interest)
```

on `notifications` is a database-enforced dedupe — the matching job can
attempt to insert the same notification twice (e.g. two overlapping runs)
and the second insert simply fails, rather than the app needing to
`SELECT` first to check. This is a real technique worth naming:
**push the invariant into the schema, don't just check it in code** — it's
strictly stronger, because it holds even if some future code path forgets
the check.

### Triggers

`supabase/schema.sql` defines `touch_updated_at()` (a trigger function
that stamps `updated_at = now()` on every update, attached to five
tables) and `handle_new_auth_user()`, which fires `after insert on
auth.users` and creates the matching `profiles` row (plus
`user_profiles`/`company_profiles`) automatically. This is the mechanism
that keeps "a Supabase Auth user exists" and "our application profile
exists" in sync without the application code having to remember to do it
in two places — the database guarantees it.

---

## 4.5 The matching engine, in depth (updated 2026-08-17)

This is a good section to know cold for an interview, because it's a real
bug that shipped, got caught, and got fixed — not a hypothetical.

### The bug: substring matching

The original `matching_interest_for_deal` did this:

```python
return next((interest for interest in interests if interest in haystack), None)
```

`in` on strings is a substring check. That means an interest of `"ice"`
matched any deal whose text contained `"service"`, `"price"`, or
`"spice"` — none of which have anything to do with ice. It also meant an
interest of `"pizza"` did *not* reliably match `"pizzas"` in a
boundary-sensitive way, which happened to work only by the same accident
that caused the false positives.

### The fix: word-boundary matching

```python
def interest_matches_haystack(interest, haystack):
    pattern = r"(?<![a-z0-9])" + re.escape(interest) + r"(?:es|s)?(?![a-z0-9])"
    return re.search(pattern, haystack) is not None
```

This uses zero-width lookaround assertions (`(?<!...)` negative lookbehind,
`(?!...)` negative lookahead) to require that the interest appears as its
own token — not embedded inside a longer alphanumeric run — while
explicitly allowing a trailing `s`/`es` so simple plurals still match. This
is the kind of regex detail worth being able to explain precisely in an
interview: lookaround assertions match a *position*, not characters, so
they don't consume input and don't affect what `re.escape(interest)`
itself matched.

### The recall gap that's left, and how AI closes some of it

Word-boundary matching is *correct* but still only catches shared words. A
shopper interested in `"tacos"` still won't match a deal titled `"Cinco de
Mayo Fiesta Special"` — there's no shared token, so no keyword match can
ever catch this class of miss. That's a real product gap (recall, not
precision), and it's the concrete, defensible answer to "how would you use
AI to improve this" in an interview, as opposed to a vague "we could add
AI somewhere."

The implementation (`ai_extract_categories` in `app.py`) makes two
deliberate choices that are worth being able to defend:

1. **Closed taxonomy, not free-form tags.** If you ask a model to freely
   generate tags for `"tacos"` and separately for `"Cinco de Mayo Fiesta
   Special"`, there's no guarantee the two tag sets share a string — free
   generation is high-entropy. Asking the model to classify both against
   the *same fixed list* of ~30 categories (`AI_CATEGORY_TAXONOMY`)
   collapses that entropy: both plausibly land on `"mexican"`. This is a
   general pattern for making independently-generated AI output
   comparable — constrain the output space until it can only vary along
   the dimension you actually care about.
2. **Write-time computation with process-lifetime caching, not
   request-time.** The naive way to add this would be: for every
   (shopper, deal) pair in the matching job, ask the model "do these
   match?" That's O(users × deals) API calls — slow, expensive, and adds
   external-network flakiness to the one job that's supposed to be
   reliable and fast. Instead, categories are computed once per *distinct*
   piece of text (one deal description, one saved interest string) via
   `functools.lru_cache`, and reused for every user who shares that
   interest and every run that sees that deal again. That's O(unique
   deals + unique interests), computed once, not O(users × deals),
   computed every run. This distinction — push expensive/uncertain work to
   write time and cache it, keep the hot read/matching path fast and
   deterministic — is a real system design principle, not specific to AI.

It also fails closed by design: no API key, a network error, a timeout, or
a model response that isn't valid JSON from the fixed taxonomy all just
return an empty result, silently falling back to keyword-only matching.
The feature can never make matching *worse* or block a deal/interest from
saving — it can only add matches a shopper would otherwise have missed.

### The other change: digesting

The matching job also changed from "one email per match" to "one email per
user per run, covering every match found in that run." The dedupe
invariant (`unique(user_id, deal_id, matched_interest, channel)` on
`notifications`, see above) didn't change — every individual match is
still written as its own row and still shown separately in the UI. Only
the *delivery* step changed, from N `send_match_email` calls to 1. This is
the same "alerts are high signal, not noisy" product rule the app was
built around, extended to a place it hadn't been applied yet: matching
being correct doesn't help if five correct matches in one run means five
separate emails.

---

## 5. Security, in depth

### Password hashing

```python
hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
```

PBKDF2 is a **key derivation function**: it's deliberately slow (200,000
rounds of HMAC-SHA256) so that an attacker who steals the password
database still has to spend real compute per guess. The **salt** (random
per user, `secrets.token_hex(16)`) defeats precomputed rainbow-table
attacks and ensures two users with the same password get different stored
hashes. If asked "why not just SHA-256 the password," the answer is:
plain SHA-256 is *fast* — that's exactly the wrong property for password
hashing, since fast hashing means fast brute-forcing. (For what it's
worth, bcrypt/scrypt/Argon2 are generally preferred over PBKDF2 today for
new systems because they're also memory-hard, resisting GPU-parallelized
attacks better — a good thing to mention if asked how you'd improve this.)

### The selector/secret session token pattern

```python
def generate_opaque_token():
    selector = secrets.token_urlsafe(12)
    secret = secrets.token_urlsafe(32)
    raw_token = f"{selector}.{secret}"
    return selector, raw_token, hash_token(raw_token)
```

This is a slightly more sophisticated pattern than "just hash the token."
The session lookup in `get_authenticated_user` hashes the *entire*
presented token and looks it up by that hash — meaning the lookup itself
is by hash, not by a separate plaintext selector column, but the raw
token is still never stored. Combined with `hmac.compare_digest()` for
password comparison (not `==`), this avoids **timing attacks**: `==`
short-circuits on the first mismatched byte, so an attacker who can
measure response time precisely enough could theoretically learn how many
leading bytes were correct; `compare_digest` always takes the same time
regardless of where the mismatch is.

### What's genuinely NOT handled — say this plainly if asked

- No rate limiting or lockout on login/signup attempts (brute-force risk
  on weak passwords).
- No CSRF token — mitigated somewhat by using `Authorization: Bearer`
  headers instead of cookies (a browser won't auto-attach a bearer token
  to a cross-site request the way it auto-attaches cookies), but this is
  a *side effect* of the auth scheme, not an intentional CSRF defense.
- No audit logging of security-relevant events (failed logins, password
  changes) beyond what's incidentally in `notification_log.jsonl`.

Naming these unprompted in an interview is a stronger signal than having
a perfect app — it shows you know what "production-ready" actually
requires, not just what makes a demo work.

---

## 6. Supabase, Postgres, and Row Level Security — in depth

### What Supabase actually is

A hosted Postgres database, plus **GoTrue** (their auth service, issuing
JWTs), plus **PostgREST** (auto-generates a REST API directly from your
Postgres schema — this is what `supabase_rest_request()` in `app.py`
talks to). You're not writing a backend so much as configuring one.

### JWTs, concretely

A JWT is three base64url segments joined by dots:
`header.payload.signature`. The payload contains claims — for Supabase,
critically `sub` (the user's UUID, exposed to Postgres as `auth.uid()`)
and an expiry. The signature is computed over `header.payload` with a
secret only the issuer (Supabase) holds, so anyone can *read* the claims
(don't put secrets in them) but only Supabase can *mint a valid one*.
Contrast with this app's current local-mode session tokens, which require
a database round-trip to validate (`SELECT ... WHERE token_hash = ?`) —
JWTs can be verified with pure cryptography, no database hit needed,
which is why they scale better across multiple backend services.

### RLS, walked through with a real policy

```sql
create policy "deals_update_company_own"
on public.deals
for update
using (
  public.current_account_type() = 'company'
  and auth.uid() = company_id
);
```

`auth.uid()` is a Postgres function Supabase provides that returns the
current request's authenticated user id, extracted from the verified JWT
— this only works because the request arrived with a valid Supabase
session; RLS policies are evaluated *inside Postgres*, so they apply no
matter what client or API path reaches the row. `current_account_type()`
is this project's own helper function (also in `rls.sql`):

```sql
create function public.current_account_type() returns text
language sql stable as $$
  select account_type from public.profiles where id = auth.uid()
$$;
```

The `using` clause is evaluated for every row a query would touch;
rows that don't satisfy it are simply invisible/uneditable to that
query — not an error, just excluded, the same way a `WHERE` clause
would exclude rows, except you can't forget to write it because it's not
optional at the query-writing layer.

**The interview-grade way to frame this:** RLS moves the authorization
check from "trusted only if every code path remembers to check it" to
"enforced by the database regardless of which code path reaches it." It's
the same idea as a `NOT NULL` constraint versus "the application always
remembers to set this field" — pushing an invariant as low in the stack
as it can go.

### The auth trigger

```sql
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_auth_user();
```

This is what turns "someone signed up through Supabase Auth" into "a
`profiles` row (and role-specific extension row) exists" — automatically,
transactionally, without the application needing a second API call that
could fail or be forgotten. `security definer` on the function means it
runs with the *definer's* privileges (not the caller's), which is
necessary here because a newly-signing-up user shouldn't otherwise have
insert rights on `profiles` yet.

---

## 7. Frontend architecture

No framework, no build step, no virtual DOM. `app.js` builds HTML via
template literals and injects with `innerHTML`, gated by manual
`classList.toggle()` calls for state (`.is-active`, `.hidden`, `.is-saved`,
etc.). The honest tradeoff: this is dramatically simpler to reason about
for a codebase this size (no framework version to keep current, no build
step to debug, view source shows you exactly what runs) — and it gets
meaningfully harder to maintain past a certain size, because there's no
guardrail (like React's component boundaries) stopping one render
function from stepping on another's DOM.

**XSS defense** is handled the straightforward way: every piece of user-supplied text
goes through `escapeHtml()` before landing in a template literal that
becomes `innerHTML`. This is correct but fragile — it relies on
discipline (every call site remembering to escape) rather than a
structural guarantee (the way React's JSX escapes by default unless you
explicitly opt out with `dangerouslySetInnerHTML`). Worth knowing the
difference if asked to compare approaches.

**State** lives in a mix of module-level JS variables (`currentUser`,
`supabaseClient`) and `localStorage` (session persistence across page
reloads, active-tab memory). There's no formal state management library
— fine at this scale, the thing to know is *why* a larger app reaches for
one (predictable updates, time-travel debugging, avoiding prop-drilling
equivalent problems) rather than assuming it's just extra ceremony.

---

## 8. The design system

Documented in full in `DESIGN_SYSTEM.md`. The technical mechanism worth
naming: **CSS custom properties** (`--coral`, `--radius-md`, etc.) defined
once on `:root` and referenced everywhere via `var(--token-name)`. This is
what makes a coherent design *system* rather than a pile of one-off
values — change the token once, every component that references it
updates. It's the CSS-native version of the same "define once, reference
everywhere" idea RLS embodies at the database layer and the notifications
unique constraint embodies at the schema layer — a theme worth noticing
across this whole codebase: **push invariants and shared values to one
place instead of repeating them.**

---

## 9. Testing strategy

`test_phase1.py` uses Python's built-in `unittest`. These are more
precisely **integration tests** than pure unit tests — they spin up the
actual HTTP handler and hit it with real requests
(`Phase1ApiTests`), rather than calling internal functions directly with
mocked collaborators. That's a legitimate, common choice: for a codebase
this size, testing through the same interface real clients use catches
more real bugs per test than isolated unit tests would, at the cost of
being somewhat slower and coarser-grained about *where* a failure is.

Where the suite does use test doubles, it's for **hosted Supabase
paths** — since hitting a real Supabase project in CI isn't desirable,
those tests monkeypatch `app.supabase_is_configured` and the
`supabase_*_request` functions to return canned data, so the *branching
logic* ("does the app correctly call the Supabase path when configured")
is tested without a live network dependency.

---

## 10. Building this with AI — how this project is actually being built

This is worth being able to talk about directly and specifically, not in
vague "I used AI to help" terms — the how matters more than the fact.

### The steering file pattern

`CLAUDE.md` (in the project root) is what's called a **steering file** or
**context file** — a document an AI coding agent reads at the start of a
session to load project-specific context that would otherwise need to be
re-explained every single time. Without it, every new session starts from
zero: no knowledge of which classes in `app.js` are load-bearing, no
knowledge of the local/Supabase dual-path pattern, no knowledge of the
approval-gate rules for what needs a human sign-off before changing. With
it, the agent picks up mid-project the way a new engineer would after
reading a good README and architecture doc — except it happens on every
session, automatically.

This project's steering file evolved across two different AI coding
tools — it references an earlier "Codex" (OpenAI's CLI agent) operating
plan (`DEVELOPMENT_OPERATING_PLAN.md`) that was generalized into
tool-agnostic guidance in `CLAUDE.md` when the work continued with Claude.
That's a real, practical point: **a good steering file outlives the
specific tool that wrote it**, because it's really documenting the
project, not the tool.

### The operating-agreement pattern

`DEVELOPMENT_OPERATING_PLAN.md` (and the generalized version in
`CLAUDE.md`) defines an explicit **autonomy boundary** — a list of
categories the AI can act on without asking ("bug fixes, UX cleanup,
refactors that preserve behavior") and a list that require a stop-and-ask
("changing the monetization model, replacing the backend stack, shipping
a design direction that materially changes the feel of the app"). This is
a genuinely transferable engineering-management idea, not an AI-specific
one — it's the same shape as a junior engineer's onboarding doc that says
"ship these kinds of changes freely, page me before you touch these
others." Framing AI collaboration this way (explicit scope + explicit
escalation triggers) is a much stronger interview answer than "I reviewed
everything it did," because it shows you designed the *process*, not just
supervised the output.

### Verification as the actual safety mechanism

The reason it's reasonable to let an AI agent modify a live codebase with
meaningful autonomy is the **regression test suite acting as a guardrail**
— every substantive change in this project has been checked against
`python3 -m unittest test_phase1.py` before being considered done, and the
full visual redesign was verified with actual Playwright screenshots
(desktop + mobile, logged in as both account types) rather than trusting
that CSS changes "probably look fine." This is the honest core of
responsible AI-assisted development: **the agent's claim that something
works is not evidence; running it and checking is.** Worth stating
directly if asked "how do you know the AI didn't break something" — the
answer isn't "I trust it," it's "there's an automated suite it has to
pass, plus a scheduled daily re-run of that suite independent of any
particular coding session."

### What went wrong once, and why that's worth mentioning too

During this build, a file-sync step run through Claude's remote-device
bridge hit an unguarded empty shell variable and accidentally copied
~1.7GB of an unrelated filesystem into this project's folder on my
machine. It was caught, disclosed immediately and specifically (not
glossed over), and cleaned up. This is worth including in an interview
answer, not hiding: **a real AI-assisted workflow includes the agent
making mistakes**, and the actual signal isn't "did it ever go wrong" but
"was it caught, was it disclosed plainly, and was there a real mechanism
(here: transparency plus the ability to move/undo rather than silently
proceeding) that limited the blast radius." That's a more credible answer
than implying AI-assisted work is mistake-free.

### Likely follow-up questions on this topic, and how to answer them

- **"Doesn't this mean you didn't really write the code?"** — I made the
  product and architecture decisions (what the app does, what stays
  approval-gated, what the data model looks like, what the visual
  direction should communicate), and directed and reviewed every change.
  The agent executed within boundaries I set and verified against tests I
  can also run myself. That's closer to how you'd describe working with a
  very fast, very literal contractor than "the AI wrote my app for me."
- **"What would you do if the AI generated something insecure?"** — Point
  at §5 above: I can (and did, while preparing this) read the actual
  hashing/session code and evaluate it against known-good practice (PBKDF2
  iteration counts, `compare_digest` for timing-safe comparison,
  hashed-not-raw token storage) rather than assuming correctness.
- **"How do you keep context across sessions?"** — The steering file
  pattern in §10 above, plus checked-in docs that get updated as part of
  the same change that made them stale (not a separate later cleanup
  step).

---

## 11. Interview Q&A bank (grounded in this project)

**"Walk me through the architecture."**
Two-mode Python backend (stdlib HTTP server, no framework) serving a
vanilla JS frontend; local SQLite for the prototype, fully wired but not
yet live Supabase (Postgres + Auth + RLS) for production. Data flows:
browser → `/api/*` JSON routes → either direct SQLite queries or
PostgREST calls to Supabase, selected by whether Supabase env vars are
present.

**"How is authentication handled, and is it secure?"**
PBKDF2-hashed passwords (200k iterations, per-user salt), opaque session
tokens where only a SHA-256 hash is ever persisted, `hmac.compare_digest`
for timing-safe comparisons, session revocation on password change. Known
gaps: no rate limiting, no audit log — see §5.

**"What's Row Level Security and why does it matter here?"**
Database-enforced, per-row access policies evaluated inside Postgres
regardless of which API path reaches the row — defense in depth versus
relying solely on application-layer checks. See §6 for a real policy
walked through line by line.

**"What would you change before this goes to production?"**
In priority order: finish the Supabase cutover (mostly configuration at
this point, not new code), add rate limiting on auth endpoints, replace
the hand-rolled HTTP server with a real framework (better tooling,
observability hooks, ecosystem), add CI, add real payment/merchant billing
per `PAYMENTS_READINESS_PLAN.md`.

**"How would you scale this?"**
Today's biggest scaling constraint isn't the web tier (ThreadingHTTPServer
handles moderate concurrency fine for I/O-bound work) — it's SQLite,
which serializes writes at the file level. The Supabase/Postgres cutover
already solves that; beyond it, the matching job (currently full-scan over
users × deals) would need to become a proper indexed query or a queued
background worker once deal/user volume grows past what an in-process
loop comfortably handles on a schedule.

**"Tell me about a mistake in this project and what you learned."**
See §10's disclosure above — a concrete, real one, not a hypothetical.

**"How would you use AI to actually improve a matching/search feature, beyond just 'call an LLM'?"**
See §4.5. The concrete answer here: classify both sides (deal text and
saved interest) against the same fixed taxonomy rather than generating
free-form tags, because a closed vocabulary is what makes two independent
classifications comparable at all. And compute it once per distinct
input, cached, at write time — never per (user, deal) pair at request
time — so the feature can't turn an O(n) job into an O(users × deals) one
or make the matching job depend on network reliability.

**"Give an example of finding and fixing a real bug, not just a feature."**
§4.5's substring-matching bug: an interest of "ice" matched deal text
containing "service" or "price" because the original code used Python's
`in` operator (substring containment) instead of a word-boundary check.
Caught by reasoning about the matching function directly, fixed with a
regex using lookaround assertions, covered with a regression test
asserting the specific false positive no longer matches.

---

## 12. Glossary

- **RLS (Row Level Security)** — database-enforced per-row access rules; §6.
- **PBKDF2** — slow, salted password-hashing key derivation function; §5.
- **JWT** — signed token (`header.payload.signature`) verifiable without a database lookup; §6.
- **PostgREST** — auto-generates a REST API from a Postgres schema; what Supabase's REST layer is built on.
- **GIL (Global Interpreter Lock)** — the reason Python threads give concurrency, not parallelism, for CPU-bound work; §2.
- **Idempotent** — same effect whether an operation runs once or many times; §3.
- **Timing attack** — inferring secret data from how long a comparison takes; why `hmac.compare_digest` exists; §5.
- **CSRF** — tricking a browser into an authenticated request via cookies it already holds.
- **XSS** — injecting malicious script into rendered HTML; defended here via `escapeHtml()`.
- **Composite index** — a multi-column index where column order determines which query shapes it can serve; §4.
- **security definer** — a Postgres function that runs with its owner's privileges, not the caller's; §6.
- **Strategy pattern** — selecting an implementation at runtime behind one interface; the local/Supabase dual-path shape; §2.

---

## 13. Open items

- Supabase live cutover — status: see chat thread for latest
- CI via GitHub Actions once this is in a real git remote
- Rate limiting on auth endpoints
- Loading skeletons, real merchant image uploads
- Optional: custom Datadog/APM metrics (see chat for the honest scoping of this)

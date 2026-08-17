# Design System — Local Deal Alert

Written 2026-08-16 alongside a full visual redesign of `static/styles.css`.
This documents *why* the design looks the way it does, not just what the
tokens are, so future passes extend it instead of drifting into one-offs.

## What changed and why

The previous design (documented in the original `FRONTEND_POLISH_NOTES.md`
entries above this one) used three loosely-related accent colors — a bronze
tone for merchant-facing components, a sage green for shopper-facing
components, plus ad hoc grays — layered with heavy gradients, blur, and
inconsistent border radii (18px–38px depending on component). It looked
handmade rather than designed as one system, and the merchant and shopper
experiences didn't visually read as the same product.

The new system:

- **Two accent colors, used consistently everywhere:** coral for primary
  actions and "this needs attention / this is live" signals, deep teal for
  structural/trust elements (pills, secondary chips, merchant-neutral
  status). Every component picks from this pair instead of introducing a
  new one-off color.
- **One radius scale** (`--radius-sm` through `--radius-xl`) instead of
  arbitrary per-component values.
- **Flatter surfaces.** Cards are still elevated but shadows are smaller and
  fewer gradients are stacked on top of each other — faster to render,
  easier to keep consistent, reads as more "product" and less "mockup."
  Motion (fade-up, modal transitions) is kept but shortened and gated behind
  `prefers-reduced-motion`.
  - **Inter** for all type (was a serif display face for `h1` + a system
  sans for body). One typeface is easier to keep consistent at a glance and
  reads as more contemporary; weight (800 for display, 700 for headings,
  400/600 for body) carries the hierarchy instead of a font pairing.
- **A real brand header** (`.site-header`, new markup in `index.html`) —
  the old page opened directly into a hero with no persistent brand
  identity above it.

## Tokens (`static/styles.css` `:root`)

| Token | Value | Use |
|---|---|---|
| `--bg` | `#faf7f2` | Page background (warm paper, not stark white) |
| `--ink` / `--ink-soft` | `#16181d` / `#3a3f47` | Primary / secondary text |
| `--muted` / `--muted-soft` | `#6b7280` / `#9299a3` | Tertiary text, placeholders |
| `--coral` / `--coral-dark` | `#ff5a36` / `#dd4420` | Primary CTA, "live/urgent" |
| `--teal` / `--teal-dark` | `#0e6b63` / `#0a4f49` | Secondary, structure, trust |
| `--success` / `--warn` / `--danger` / `--info` | green / amber / red / violet | Status semantics (active/mocked/expired/draft) |
| `--radius-sm..xl` | `10px..26px` | One consistent scale, used everywhere |
| `--shadow-sm..lg` | see file | Elevation scale |

All status colors (`alert-status.is-*`, `merchant-insight-score.is-*`,
`merchant-feed-chip.is-*`) are semantic, not decorative — don't repurpose
`--danger` for something that isn't actually a failure/expired state.

## Component notes

- **Deal cards / modal** (`.deal-card`, `.deal-modal-*`) contain defensive
  list-marker resets (`list-style: none !important` etc.) — these were
  already present before the redesign to fix stray bullet markers some
  browsers rendered on the JS-generated `<article>` lists. They're
  preserved intentionally; don't remove them without checking that bug
  hasn't reappeared.
- **`.deal-card`** deliberately zeroes `font-size`/`color` on the card
  itself and resets it on `.deal-card > *` — this is existing (pre-redesign)
  defensive CSS, not new. Leave the pattern alone unless you're
  specifically investigating it.
- **Merchant vs. shopper surfaces** now share the same card/chip/button
  vocabulary. If you add a new merchant-only component, reach for `--teal`
  first (matches the "trust/structure" role), not a new hue.

## Verifying visual changes

There's no visual regression test suite. The fastest check is Playwright
against the running dev server:

```bash
python3 app.py &
python3 - <<'EOF'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    page = b.new_page(viewport={'width': 1440, 'height': 950})
    page.goto('http://127.0.0.1:8000/')
    page.screenshot(path='/tmp/check.png', full_page=True)
    b.close()
EOF
```

(Chromium path is specific to the Anthropic cloud sandbox — on a normal
machine with Playwright installed, just use the default `p.chromium.launch()`.)

Note: full-page screenshots can render `position: sticky` elements (like
`.tabs`) in a visually duplicated/overlapping way because Playwright
stitches multiple scroll positions together. That's a screenshot artifact,
not a real bug — confirm anything that looks sticky-related with a
viewport-sized (non-full-page) screenshot before treating it as a defect.

## Next opportunities (not yet done)

- Loading skeletons for search results / merchant feed (currently just a
  brief blank state while `fetch` resolves).
- Real merchant image uploads — `.deal-thumb` currently always renders a
  gradient placeholder; `has-image` styling exists but nothing populates it
  yet.
- Dark mode was not attempted — the token structure (CSS custom properties)
  would support it fairly directly if wanted later.
- No custom 404/500 page styling — `serve_static` in `app.py` returns raw
  JSON errors for missing static files.

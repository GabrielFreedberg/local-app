# Frontend Polish Notes

This document records the current frontend direction for the prototype as of Thursday, July 23, 2026.

## Visual direction

The current UI direction is:

- warm neutral surfaces instead of stark white
- dark ink text for strong readability
- one restrained bronze action color for primary actions
- one muted sage tone for structure, status, and secondary emphasis
- soft gradients and subtle depth instead of loud visual effects

## Why this direction fits the product

- it feels local and human instead of overly corporate
- it stays subtle while still looking intentional
- it supports both shopper and merchant workflows without feeling like two different products
- it keeps the interface calm even when there is a lot of information on screen

## Current frontend improvements included

- refined background gradients and surface layering
- tighter card styling for deal browse cards
- more polished hero panel feedback
- improved status, hover, and focus states
- centered modal behavior for deal details
- cleaner result and empty-state presentation
- better visual separation between primary and secondary actions

## Frontend testing standard for Phase 1

- auth flows should have regression coverage
- favorites save/remove behavior should have regression coverage
- company deal create/update/delete should have regression coverage
- password reset should have regression coverage
- matching behavior should have regression coverage

## Next frontend opportunities

- richer mobile spacing pass
- more intentional loading skeletons
- image support for real merchant uploads
- merchant-side analytics summary cards

## 2026-08-16 redesign

Replaced the direction above with a full visual redesign. Full rationale
and token reference now live in `DESIGN_SYSTEM.md` — summary:

- Consolidated three loosely related accent colors (bronze, sage, ad hoc
  grays) into two: coral (primary/urgent) and deep teal (structure/trust),
  used consistently across both the shopper and merchant experiences so
  they read as one product.
- Switched typography to Inter throughout (was a serif display face +
  system sans body pairing).
- Normalized the radius scale (previously 18px–38px per component,
  arbitrary) and lightened shadows/gradients for a flatter, faster-reading
  surface.
- Added a persistent brand header above the hero (previously the page
  opened directly into the hero with no standing brand identity).
- Softened prototype-facing copy ("Phase 1 Prototype" eyebrow, "Prototype
  Controls" panel label) into product-facing copy, without changing any
  functional behavior.
- No HTML element IDs or JS-referenced class names were changed — this was
  a styling and copy pass only. All 29 backend regression tests still pass
  unchanged; verified visually with Playwright screenshots at desktop and
  mobile widths, logged-in as both a shopper and a company account.

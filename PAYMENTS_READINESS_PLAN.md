# Payments Readiness Plan

This document outlines the safest payment direction for the product as of Thursday, July 23, 2026.

## Goal

Prepare the app for paid merchant plans without storing raw card data in this codebase.

## Recommended Direction

- use hosted checkout instead of building custom card collection first
- use a provider like Stripe for subscriptions, invoices, and saved payment methods
- keep this app responsible for account state, plan access, and feature gating
- let the payment provider handle card entry, PCI-sensitive flows, receipts, and billing portal actions

## Why this is the right prototype-to-product path

- it reduces security risk
- it avoids storing payment details locally
- it keeps the app focused on deal alerts, search, favorites, and merchant workflows
- it gives a realistic path to charging businesses within the MVP window

## What should happen before real payments go live

- move auth from local prototype sessions to production auth
- move data from local SQLite assumptions to hosted Postgres
- define merchant plans and feature gates
- create billing state fields for plan, trial status, renewal state, and subscription id
- add webhook handling for successful checkout, failed payment, cancellation, and renewal
- add billing history and plan management UI for merchants

## Security rules

- do not collect raw card numbers in this app
- do not store CVV, expiration, or primary account number locally
- do not build a homegrown password reset plus billing system for production
- require verified business identity before paid merchant features are enabled

## Suggested MVP billing model

- one business subscription tier
- free trial or pilot access for first merchants
- paid access unlocks active deal posting and future analytics

## Near-term implementation steps

1. finish prototype stabilization
2. migrate auth and database to production-ready infrastructure
3. add merchant plan fields and server-side entitlement checks
4. integrate hosted checkout
5. add webhook-driven billing state sync
6. expose billing status inside the company experience

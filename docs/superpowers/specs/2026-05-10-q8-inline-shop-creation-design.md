# Q8 — Inline Shop Creation Design

**Date:** 2026-05-10
**Phase:** Audit Q8 (~3 hour quick win)

## Problem
Creating a shop today navigates to `/shops/new` (a full page with one input). Inconsistent with the rest of the app (suppliers, channels, customers, etc.) which use inline create modals or `?new=1` deep links.

## Solution
Replace `/shops/new` with an inline create modal on `/shops`. Follow the existing `?new=1` deep-link pattern from polish week.

## Files
| File | Change |
|---|---|
| `apps/admin-web/src/app/(main)/shops/page.tsx` | Add inline modal + `?new=1` handler; replace Link with modal-trigger button |
| `apps/admin-web/src/app/(main)/shops/new/page.tsx` | DELETE — superseded by modal |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | Update New Entry menu Shop item href: `/shops/new` → `/shops?new=1` |

## Modal contents
- Single text input: shop name
- Same POST to `/api/ims/v1/admin/shops` with `{ name }`
- 409 → "A shop with this name already exists"
- Success → close modal, refresh list

## Out of scope
Adding more shop fields (timezone, address, etc.) — keep modal minimal, mirroring current `/shops/new` form.

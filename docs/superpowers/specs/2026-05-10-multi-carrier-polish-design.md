# Multi-Carrier Polish Design

**Date:** 2026-05-10
**Phase:** Q-tier (~2-3 hours)

## Problem
Today's `ShippingTab` on the channels page implicitly assumes Shiprocket — there's no provider picker, no signal that other carriers might come in the future. Merchants comparing carriers don't see any roadmap.

## Solution
Add a provider picker at the top of the ShippingTab. Show Shiprocket as the only active option; show Delhivery, DTDC, and Bluedart as disabled cards with "Coming soon" badges so merchants know what's planned.

## Files
| File | Change |
|---|---|
| `apps/admin-web/src/app/(main)/channels/page.tsx` | Add a provider picker at the top of `ShippingTab`. Active = Shiprocket (existing form). Disabled cards for Delhivery, DTDC, Bluedart with "Coming soon" badge. |

## UX
At the top of ShippingTab (after the channel selector), render a 4-card grid:
- **Shiprocket** (primary, clickable) — opens existing Shiprocket setup form
- **Delhivery** (disabled, dimmed) — "Coming soon" badge
- **DTDC** (disabled, dimmed) — "Coming soon" badge
- **Bluedart** (disabled, dimmed) — "Coming soon" badge

Selecting Shiprocket reveals the existing setup form. Selecting a "coming soon" card does nothing (or shows a toast: "Coming soon").

## Out of scope
Backend carrier abstraction changes — registry already supports adding new providers via `services/api/app/services/shipping/`. That's separate work when a real second carrier ships.

# L5 — Command Palette Design

**Date:** 2026-05-10
**Phase:** Audit L5 — last UX item before backend features

## Problem
Non-technical merchants navigate the app by clicking through the sidebar. Power users want a keyboard-driven shortcut to jump anywhere. There's a header search input today (scope-aware per-page); a global command palette is the natural complement: search for *anything* — pages, actions, products — from any page.

## Goals
1. Cmd+K (Mac) / Ctrl+K (Win/Linux) opens the palette from anywhere.
2. Single search input with live results across three sections:
   - **Actions** (e.g. "Create Channel")
   - **Pages** (e.g. "Settings → Email")
   - **Products** (live entity search)
3. Type-aware — actions and pages filter by business type, same way the sidebar does.
4. Esc closes; arrow keys navigate; Enter selects.

## Component
New file `apps/admin-web/src/components/dashboard/CommandPalette.tsx`. Mounted in `AppShell` so the keyboard listener works from any page.

## Trigger
- Global keydown listener: `(e.metaKey || e.ctrlKey) && e.key === "k"` → open. `e.preventDefault()` to suppress browser default.
- Click outside or Esc → close.

## Result sections

### Actions (static, type-filtered)
Same list as `NEW_ENTRY_ITEMS` already defined in `AppShell.tsx`:
- Create Product (all)
- Create Customer (all)
- Create Shop (retail/hybrid)
- Create Channel (online/hybrid)
- Create Discount (online/hybrid)

Each renders as: icon + "Create X". Click → navigate to corresponding href (same as current New Entry menu).

### Pages (static, type-filtered)
Same list as `NAV_GROUPS` flattened, filtered by permission AND business type. Each: icon + group label + page label. Click → navigate.

### Products (live)
- Debounced 250ms fetch to `/api/ims/v1/admin/products?q=<query>` after 2+ characters typed
- Show top 8 results: SKU + product name
- Click → navigate to `/products?q=<query>` (existing search-aware page)

## Layout
Modal overlay, centred near top of viewport. Width ~640px, max-height 70vh, scrollable result list. Search input at top, Esc/⌘K hint at right.

## Files
| File | Status |
|---|---|
| `apps/admin-web/src/components/dashboard/CommandPalette.tsx` | NEW |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | Mount `<CommandPalette>` + add global keydown listener |

## Out of scope
- Searching orders, customers, audit events — start with products as exemplar; expand later
- Recently-used / frecency ranking — start with simple alphabetical
- Hot-key hints in the sidebar ("⌘K") — visual polish for a follow-up

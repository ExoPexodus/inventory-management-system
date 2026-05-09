# Admin Web UX Audit — Phase 2

**Date:** 2026-05-09
**Status:** Discovery output (not a spec; informs future implementation specs)
**Scope:** All 25 admin-web pages under `apps/admin-web/src/app/(main)/`
**Goal:** Identify the highest-friction workflows, propose concrete fixes, rank them quick-win → larger-refactor.

This document is a **prioritised backlog** — each finding is a candidate spec for a future Phase. Pick what to ship first.

---

## Methodology

For each page I checked:
- **Click cost** — how many clicks/page transitions a common workflow takes today
- **Cognitive load** — how many separate UI surfaces (forms, modals, separate pages) a user has to track for one outcome
- **Empty / first-time experience** — what a new merchant sees with no data
- **Business-type awareness** — does the page adapt to online/retail/hybrid (now that Phase 1 ships type-aware nav)?
- **Discoverability** — can a non-technical user find a setting without knowing the answer in advance?

Friction was scored from observation, not from instrumented analytics. Numbers are estimates intended to compare *relative* pain.

---

## Top 5 highest-friction surfaces (deep dive)

### 1. Settings — the 900-line monolith

**File:** `apps/admin-web/src/app/(main)/settings/page.tsx`

**What's wrong:**

A single vertical-scroll page contains **twelve distinct concerns**:

1. Staff invite email provider (SMTP/SendGrid + credentials)
2. Currency
3. Device security (offline minutes, session timeout)
4. Reconciliation auto-resolve thresholds
5. Localisation (timezone, financial year start month)
6. Customer Groups (CRUD)
7. Notifications (placeholder toggles, **no save action**)
8. Security (placeholder toggles for 2FA / session notify / API key rotation, **no save action**)
9. Appearance (placeholder toggles for compact tables / high contrast / reduced motion, **no save action**)
10. Business type
11. Danger zone

Sections 7–9 are particularly bad — they look interactive but flipping the toggle doesn't persist. New users will lose state and assume the app is broken.

**Click cost to find any one setting:** scroll through ~900 lines, no anchor nav, no search, no sub-tabs.

**Recommendation:**

- **L1**: Split into a Settings Index page + sub-pages. Every concern is its own route (`/settings/email`, `/settings/currency`, `/settings/devices`, etc.). The index is a clean grid of cards. Each card is one click into the focused form.
- **Q1** (do first as a quick win): **Delete** the placeholder Notifications/Security/Appearance sections, or hide them behind a "Coming soon" disclosure. They're actively misleading right now.

**Effort estimate:** L1 = 3-5 days. Q1 = 1 hour.
**User impact:** High. This is the page non-technical users get most lost on. Sub-pages also reduce cognitive load on first login.

---

### 2. Channel setup — the multi-page ritual

**Files:** `apps/admin-web/src/app/(main)/channels/page.tsx`, `inventory-pools/page.tsx`, `ecommerce/page.tsx`

**What's wrong:**

To launch one working ecommerce channel today, the merchant has to:

1. Navigate to **Inventory Pools** → create a pool (assign shops to it)
2. Navigate to **Channels** → click "Add channel" → pick the pool from a dropdown → save
3. Click into the new channel → expand the **Payment** form → enter Stripe keys → save
4. Expand the **Shipping** form → enter Shiprocket creds (if used) → save
5. Optionally navigate to **E-commerce** to configure email templates and outbound webhooks

That's **4–5 separate page surfaces and ~10 clicks** to go from "I want to sell online" to "my checkout works". The pool requirement in particular is a gotcha — merchants often try to create the channel first and have to backtrack.

**Recommendation:**

- **L2**: Build a guided **"Set up your store"** wizard. A single 3-step modal/page:
  - Step 1: Pick which shops fulfil online orders (auto-creates the pool)
  - Step 2: Channel basics (name, currency)
  - Step 3: Payment provider (one form, choose Stripe or Razorpay)
  - On finish: dropped into the channel detail page with shipping/email as optional next-steps
- The wizard should be linked from a "Set up online store" CTA on the dashboard for online/hybrid tenants who don't have a channel yet.

**Effort estimate:** 4-7 days. The backend endpoints already exist; this is a frontend orchestration task.
**User impact:** Very high — this is the demo killer. Compressing 5 pages to 1 wizard makes "watch us set up a store in 2 minutes" demos plausible.

---

### 3. Product creation — five surfaces for one product

**Files:** `apps/admin-web/src/app/(main)/products/page.tsx`, `entries/page.tsx`

**What's wrong:**

`/entries` (the "Create Product" page reached via the "New Entry" button) only handles **basic fields**: SKU, name, price, MRP, cost, barcode, HSN. To fully launch one product, the merchant then has to:

1. Navigate back to `/products`
2. Click into the new product → opens **EditProductDialog** → upload images
3. Open **VariantsModal** → add size/colour variants
4. Open **PricesModal** → add per-currency prices (multi-currency tenants only)
5. Maybe go to **Channels** to set publish status per channel

**Five surfaces** for one product. Worse: until last week, image upload was completely impossible during initial creation (we shipped a fix). Variants and prices still require post-creation visits.

**Recommendation:**

- **L3**: Replace `/entries` with a unified create flow on `/products` itself. Either:
  - **(a)** A full-screen modal with **Details / Images / Variants / Prices** as side-tab sections — single save commits everything atomically
  - **(b)** A multi-step "New Product" wizard with the same sections
- For the existing edit flow, consolidate the three modals (EditProductDialog, VariantsModal, PricesModal) into one tabbed dialog — same outcome, half the modal-stacking.

**Effort estimate:** 5-8 days for the unified create flow + 2-3 days to consolidate edit modals.
**User impact:** High. Products are the single most common merchant action. The current fragmentation is invisible to power users but bewildering for first-timers.

---

### 4. Dashboard not business-type aware (and broken links)

**File:** `apps/admin-web/src/app/(main)/overview/page.tsx`

**What's wrong:**

After Phase 1 we hide nav items by business type, but the dashboard itself doesn't adapt:

- The **Pending Orders** card uses `pending_order_count` which is POS-scoped. An online-only merchant sees a "Pending Orders" stat that only counts POS orders, never their actual ecommerce orders.
- The **"View all orders"** link points to `/orders` (POS), which is hidden for online merchants → **broken click for online-only tenants**.
- The **"Recent Activity"** table mixes POS sales, stock adjustments, and movements — fine for hybrid, irrelevant for online-only (whose activity is mostly orders).
- **No quick-action shortcuts** anywhere on the dashboard — a new tenant lands here, sees stats with all zeros, and has no obvious "do this next" affordance.

**Recommendation:**

- **Q2** (quick fix): Make "View all orders" link to `/orders` for retail/hybrid and `/ecommerce-orders` for online. Same for the pending count source. This is a 30-minute change.
- **L4**: Redesign the dashboard with three changes:
  - **Type-aware cards** — different metric set for online vs retail vs hybrid
  - **Setup checklist** — when a tenant has incomplete setup (no products, no channel, no payment provider), show a card with "Next step: set up a payment provider →" linking into the wizard
  - **Quick actions block** — type-aware: retail sees [New Order / New Product / Open POS], online sees [Set up channel / Add product / View latest order]

**Effort estimate:** Q2 = 30 min. L4 = 4-6 days.
**User impact:** Q2 fixes a real bug. L4 is the demo opener — first impression of the entire product.

---

### 5. No global search; top-bar search is a placeholder

**File:** `apps/admin-web/src/components/dashboard/AppShell.tsx`

**What's wrong:**

The header has a search input with a magnifying-glass icon and the placeholder *"Search archive..."* — it's wired to nothing. Typing does nothing, pressing Enter does nothing. This is **actively misleading** — users will assume a power feature exists and find it broken.

**Recommendation:**

- **Q3** (quick win, ~1 hour): If global search is not coming this quarter, remove the input or change it to a simple SKU/order-number lookup that scopes to the current page (which would be useful immediately — many list pages don't have inline search).
- **L5** (Phase 6 in roadmap): Build a **Cmd+K command palette** — search across products, orders, customers, settings, and actions ("Create discount", "View today's sales"). This is the single biggest power-user feature for non-technical users — they don't have to learn the nav structure to find anything.

**Effort estimate:** Q3 = 1 hour. L5 = 5-7 days.
**User impact:** Q3 removes a trap. L5 is transformative — once it exists, every demo improves.

---

## Lighter pass — remaining pages

### Inventory (`/inventory`, 589 lines)

- One in-page modal (`AdjustStockDialog`) for stock adjustments — fine.
- "Movement journal" and "Recent activity" sections coexist; not always obvious which to use.
- **Q4**: Add inline filters for shop/product/date on the journal table. Currently it shows everything in a long list.
- **Effort:** 1-2 days.

### Orders (`/orders`, 577 lines, POS)

- `ReceiptDialog` modal for transaction details — clean.
- `FlaggedPendingModal` shows pending sales requiring attention — good pattern, well-scoped.
- Filters (date range, status, shop) are limited.
- **Q5**: Inline date-range picker (today / 7d / 30d / custom). Currently requires URL manipulation or no date filter at all.
- **Effort:** 1 day.

### E-commerce Orders (`/ecommerce-orders`, 480 lines)

- Has refund modal, looks clean.
- Same date-filter gap as POS Orders — apply Q5 here too.

### Team (`/team`, 1160 lines)

- Two modals: `InviteUserDialog` and `EditUserModal` — appropriate for the use case.
- Page is large because it inlines RBAC permission editing — that's actually fine; it's a power-user surface.
- **Minor:** The invite flow shows a "created" success modal that requires a manual close. Consider auto-dismissing after 5s with a toast instead.

### Integrations (`/integrations`, 761 lines)

- Three concerns mixed: Webhooks, API tokens, Channel-binding (Shopify/WooCommerce). Each is an inline-toggled form (`showForm` state).
- Looks like another mini-monolith similar to settings.
- **M1** (medium refactor): Split into 3 sub-tabs: Webhooks / API Tokens / Connected Stores.
- **Effort:** 1-2 days.

### Purchase Orders (`/purchase-orders`, 551 lines)

- Inline-toggled "Create PO" form — works fine.
- Each line item requires picking a supplier from a dropdown — supplier selection comes via a separate fetch, no autocomplete on type-ahead. Works but feels heavy for tenants with many suppliers.
- **Q6**: Add type-ahead search to the supplier dropdown.
- **Effort:** 2-3 hours.

### Discounts (`/discounts`, 550 lines)

- Inline-toggled create form.
- Three discount types (percentage / fixed / free shipping) crammed into one form with conditional fields.
- **Minor:** Could use a 3-card type picker as the first step instead of a dropdown.

### Tax (`/tax`, 421 lines)

- Region + rule CRUD via inline forms — fine.

### Suppliers (`/suppliers`, 359 lines)

- Inline-toggled create form. Pattern matches discounts/PO/tax — consistent here.

### Reconciliation (`/reconciliation`, 350 lines)

- Pending → approved workflow. Approval requires multi-step confirmation today.
- **Q7**: Bulk approve action for low-variance reconciliations (e.g., shortages under threshold X auto-resolve, batch-approve the rest).
- **Effort:** 2-3 days (small spec).

### Inventory Pools (`/inventory-pools`, 350 lines)

- Simple list + create. Will be folded into the Channel Setup Wizard (item L2 above).

### Analytics (`/analytics`, 502 lines)

- Multi-chart dashboard. Reasonable; no obvious friction.
- Overlap with Reports (`/reports`, 126 lines, much smaller). Worth merging into one page with tabs.
- **M2**: Merge Analytics + Reports into a single "Insights" page.
- **Effort:** 1-2 days.

### Audit Log (`/audit`, 172 lines)

- Lookup-only. Fine. Rare visit.

### Billing (`/billing`, 412 lines)

- Already plan-aware. After Phase 1 it correctly shows storage usage. Minor: the "Cancel" modal could show what data is preserved.

### Apps (`/apps`, 93 lines)

- Static download links + QR. Fine.

### Customers (`/customers`, 245 lines)

- Inline create modal. Fine.

### Shops (`/shops`, 114 lines + `/shops/new`)

- Create-shop is a separate page — could be a modal on the list. Same pattern as Products `/entries`.
- **Q8**: Inline shop creation modal on `/shops`.
- **Effort:** 2-4 hours.

### Staff (`/staff`, 6 lines)

- Almost empty file — likely a redirect to Team. Worth verifying it's not orphaned. Remove if dead.

---

## Cross-cutting issues

### A. Inconsistent create patterns

Some pages use modals (Products, Customers, Team), some inline-toggled forms (Suppliers, Discounts, Channels, Integrations, Tax, PO), and a couple use full pages (Entries → Create Product, /shops/new).

The functional differences don't justify the inconsistency. **Pick one** — modal for short forms, full-page only for genuinely complex flows (Channel Setup Wizard) — and standardise.

**M3**: Standardise create UI as a "create modal" pattern. Document it in `components/ui/primitives.tsx`.

**Effort:** 3-4 days (touch ~6 pages).

### B. Empty states are developer-y

`Recent Activity` says *"No recent activity. Seed demo data to populate."* That's a message for engineers, not merchants. Most list pages either say nothing or show a generic "No items" placeholder.

**Q9**: Audit every list/empty state. Replace with merchant-friendly copy + an "Add your first X" primary CTA. Use a consistent EmptyState component (it already exists in `primitives.tsx` — under-used).

**Effort:** 1-2 days.

### C. The "New Entry" sidebar button is under-used

The `AppShell` has a prominent gradient button labelled "New Entry" that opens a menu of just two items: **Create Product** and **Create Shop**. This is prime real estate.

**Q10**: Make the "New Entry" menu type-aware:
- All types: New Product, New Customer
- retail/hybrid: New Order (POS quick-sale), New Shop
- online/hybrid: New Channel (→ wizard), New Discount

**Effort:** 1 day.

### D. Bulk actions are inconsistent

Products has bulk reorder-point editing. Other lists have nothing. Power users will eventually need bulk archive, bulk publish/unpublish, bulk export.

**M4**: Standardise a row-selection toolbar component, apply across Products, Orders, Customers, Discounts.

**Effort:** 4-6 days.

---

## Ranked recommendations

### Quick wins (Q-series — small effort, high relative impact)

| ID | What | Effort | Impact |
|---|---|---|---|
| **Q1** | Remove the misleading placeholder toggles in Settings (Notifications/Security/Appearance) | 1h | High |
| **Q2** | Fix dashboard "Pending Orders" + "View all orders" link to be business-type-aware | 30m | High |
| **Q3** | Remove the broken top-bar search placeholder (until L5 ships) | 1h | Medium |
| **Q4** | Add date/shop/product filters to Inventory movement journal | 1-2d | Medium |
| **Q5** | Date-range picker on Orders + Ecommerce-Orders | 1d | Medium |
| **Q6** | Type-ahead search on Purchase Order supplier dropdown | 2-3h | Medium |
| **Q7** | Bulk approve for low-variance reconciliations | 2-3d | Medium |
| **Q8** | Inline shop creation modal (replace `/shops/new`) | 2-4h | Low |
| **Q9** | Audit + rewrite empty states across all list pages | 1-2d | High |
| **Q10** | Make "New Entry" sidebar menu type-aware | 1d | High |

### Medium refactors (M-series)

| ID | What | Effort | Impact |
|---|---|---|---|
| **M1** | Split Integrations into 3 sub-tabs: Webhooks / API Tokens / Connected Stores | 1-2d | Medium |
| **M2** | Merge Analytics + Reports into one "Insights" page | 1-2d | Medium |
| **M3** | Standardise create UI pattern across all list pages | 3-4d | Medium |
| **M4** | Standard row-selection + bulk actions toolbar | 4-6d | Medium |

### Larger refactors (L-series)

| ID | What | Effort | Impact |
|---|---|---|---|
| **L1** | Split Settings into Index + sub-pages | 3-5d | Very high |
| **L2** | Channel Setup Wizard (compress 5 pages → 3 steps) | 4-7d | Very high |
| **L3** | Unified product creation (Details + Images + Variants + Prices in one flow) | 5-8d | Very high |
| **L4** | Type-aware dashboard with setup checklist + quick-action shortcuts | 4-6d | Very high |
| **L5** | Cmd+K command palette / global search | 5-7d | Very high |

---

## Suggested next steps

The user explicitly asked for "less clicks, easier for non-technical users to get into". The four highest-leverage items for that goal are:

1. **L4 — Type-aware dashboard** (first impression for every demo)
2. **L2 — Channel Setup Wizard** (the demo killer — compresses launching online from 10 clicks to 3)
3. **L3 — Unified product creation** (most common workflow becomes one surface)
4. **L1 — Settings split** (every demo eventually goes here; today it's a wall of text)

A reasonable order is **Q1 + Q2 + Q3 + Q9 + Q10 first** (a single "polish week" sprint, ~1 week total), then pick **L1 or L4** for the next focused phase.

L5 (command palette) is probably the single biggest power-user win, but it depends on the rest of the UI being stable first — it shouldn't ship before L1 lands or it'll need rework.

After this audit, a typical Phase 3 spec would pick **one** of {L1, L2, L3, L4} and follow the same brainstorm → spec → plan → implement loop we've been using.

---

## What this audit deliberately doesn't cover

- **Visual design / typography / colour** — out of scope; the existing design system is acceptable.
- **Accessibility** — separate audit warranted (keyboard navigation, screen reader, contrast).
- **Performance** — separate concern; nothing observed was a click cost issue.
- **Mobile responsiveness** — admin-web is desktop-first by design.
- **The Cashier and Admin-Mobile Flutter apps** — separate platforms, separate audits if needed.

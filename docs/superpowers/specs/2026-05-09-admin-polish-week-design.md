# Admin Polish Week Design Spec

**Date:** 2026-05-09
**Status:** Approved
**Phase:** 3 of 6 (UI declutter roadmap)
**Source audit:** `docs/superpowers/audits/2026-05-09-admin-ux-audit.md`

---

## Problem

Five low-effort, high-impact UX fixes from the audit, bundled as one focused phase. Each removes a real source of friction or confusion for non-technical users:

- **Q1:** Settings has placeholder toggles (Notifications/Security/Appearance) that don't persist — users flip them and lose state, assuming the app is broken.
- **Q2:** Dashboard "Pending Orders" card uses POS-only data, and its "View all orders" link points to a page hidden from online merchants — broken click for that segment.
- **Q3:** Top-bar search input is wired to nothing; typing does nothing, pressing Enter does nothing — actively misleading.
- **Q9:** Empty-state copy across the app is developer-y or absent (e.g. *"Seed demo data to populate"*) — no clear next-step affordance for new merchants.
- **Q10:** "New Entry" sidebar menu only offers two items (Create Product, Create Shop) regardless of business type — under-used CTA real estate.

---

## Goals

1. Remove every misleading or non-functional UI element identified in the audit.
2. Make the dashboard's order metrics correct for every business type.
3. Wire the top-bar search to scope-aware page search via URL `?q=` param.
4. Standardise empty states with a CTA pattern via an extended `EmptyState` primitive.
5. Surface contextually-relevant create actions in the "New Entry" menu by business type.

---

## Non-goals

- Cmd+K global command palette (Phase 6 / L5)
- Settings page split into sub-pages (Phase 4 / L1)
- Channel Setup Wizard (L2)
- Unified product creation (L3)
- Full dashboard redesign with setup checklist (L4)

These all wait for their own dedicated phases per the roadmap.

---

## Backend changes

### `GET /v1/admin/dashboard-summary` gains one field

Add `pending_ecommerce_order_count: int` to the response alongside existing `pending_order_count`. Counts orders in the ecommerce flow (channel-scoped) with `status` indicating awaiting fulfilment.

Single endpoint change; no new endpoint, no migration, no schema change.

---

## Frontend changes

### Q1 — Settings cleanup

**File:** `apps/admin-web/src/app/(main)/settings/page.tsx`

Delete the entire JSX blocks for:
- Notifications section (lines ~755–784, headed "Notifications")
- Security section (lines ~786–812, headed "Security")
- Appearance section (lines ~814–847, headed "Appearance")

Delete the now-unused state hooks:
- `emailDigest`, `lowStockAlerts`, `pushNotify`
- `twoFactor`, `sessionNotify`, `apiKeyRotation`
- `compactTables`, `highContrast`, `reducedMotion`

Net effect: ~150 lines removed, no replacement, no migration.

If/when these features are actually built, they'll be added back with real persistence.

### Q2 — Dashboard Pending Orders card (type-aware)

**Important context discovery:** The existing `pending_order_count` field on `DashboardSummaryOut` actually counts `PurchaseOrder.status == "ordered"` — these are *purchase orders awaiting delivery from suppliers*, not POS sales or ecommerce orders. The card label "Pending Orders" with link to `/orders` (the POS transaction ledger) is mislabeled — the link target doesn't match the data source. The audit's framing was off; the underlying issue is bigger than just business-type-awareness.

**Files:**
- `services/api/app/routers/admin_web.py` — `DashboardSummaryOut` (line 330) and `dashboard_summary()` (line 344). Add `pending_ecommerce_order_count: int = 0` and `business_type: str` fields. Populate `pending_ecommerce_order_count` by counting `Order` rows where `tenant_id == tenant_id AND fulfillment_status == "pending"`. Populate `business_type` by reading `tenant.business_type`.
- `apps/admin-web/src/app/(main)/overview/page.tsx`

The existing `OverviewPage` is a Server Component that already fetches `dashboard-summary`. Update the card rendering using the new `business_type` field:

| business_type | Card label | Count source | Link target |
|---|---|---|---|
| `retail` | "Open Purchase Orders" | `pending_order_count` | `/purchase-orders` |
| `online` | "Pending Online Orders" | `pending_ecommerce_order_count` | `/ecommerce-orders` |
| `hybrid` | "Pending Online Orders" | `pending_ecommerce_order_count` | `/ecommerce-orders` |

The "View all orders" link in the Recent Activity section follows the same logic — pointing to `/purchase-orders` for retail, `/ecommerce-orders` for online/hybrid.

Rationale: POS sales resolve at the till and aren't actionable from a dashboard. Open POs (incoming inventory) are meaningful for retail. Pending ecommerce orders are time-sensitive across all types that have ecommerce. Hybrid prioritises ecommerce because PO awareness is already covered by the existing `/purchase-orders` flow.

### Q3 — Header scope-aware search

**Files:**
- New: `apps/admin-web/src/lib/search-context.tsx`
- Modify: `apps/admin-web/src/components/dashboard/AppShell.tsx`
- Modify: 6 list pages (see below)

**`search-context.tsx` shape:**

```ts
export interface PageSearchConfig {
  placeholder: string;
  paramName: string; // always "q" for now; reserved for future flexibility
}

export const PAGE_SEARCH_CONFIG: Record<string, PageSearchConfig> = {
  "/products":         { placeholder: "Search products...",     paramName: "q" },
  "/inventory":        { placeholder: "Search inventory...",    paramName: "q" },
  "/orders":           { placeholder: "Search transactions...", paramName: "q" },
  "/ecommerce-orders": { placeholder: "Search online orders...", paramName: "q" },
  "/customers":        { placeholder: "Search customers...",    paramName: "q" },
  "/audit":            { placeholder: "Search audit events...", paramName: "q" },
};

export function getSearchConfig(pathname: string): PageSearchConfig | null { ... }
```

The lookup tolerates tenant prefixes (e.g. `/some-tenant/products` should resolve to the `/products` config) — strip the leading prefix the same way `AppShell` already does for the active path.

**Header behaviour:**

- On every render, read `usePathname()`, look up the config.
- If config is `null` (unsupported page) — render no input at all (the magnifying-glass spot becomes empty / the layout collapses gracefully).
- If config exists — render an input with the matching placeholder, value bound to `searchParams.get("q") ?? ""`, debounce typing 300ms, then `router.replace` with the new query string.

**Per-page migration (6 pages):**

Each page currently has local `q` state used for its filter fetch. Replace with:

```tsx
const params = useSearchParams();
const q = params.get("q") ?? "";
```

Remove inline `<SearchBar>` if present (header is now the single search surface). Keep the existing `useEffect` that re-fetches when `q` changes.

The 6 affected pages: products, inventory, orders, ecommerce-orders, customers, audit.

### Q9 — Empty states with CTAs

**Files:**
- Modify: `apps/admin-web/src/components/ui/primitives.tsx` — extend `EmptyState`
- Modify: 11 list/dashboard pages (see below)

**Extended `EmptyState` shape:**

```tsx
export function EmptyState({ title, detail, actionLabel, actionHref }: {
  title: string;
  detail?: string;
  actionLabel?: string;
  actionHref?: string;
}) {
  return (
    <div className="px-4 py-12 text-center">
      <p className="font-headline text-base font-bold text-on-surface">{title}</p>
      {detail ? <p className="mt-1 text-sm text-on-surface-variant">{detail}</p> : null}
      {actionLabel && actionHref ? (
        <Link
          href={actionHref}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-on-primary hover:opacity-90"
        >
          {actionLabel}
        </Link>
      ) : null}
    </div>
  );
}
```

Backwards compatible — existing call sites that pass only `{ title, detail }` keep working.

**Per-page rewrites:**

| Page | Old | New |
|---|---|---|
| `overview` (recent activity) | "No recent activity. Seed demo data to populate." | EmptyState — "Recent activity will appear here once you make sales." (no CTA — passive informational) |
| `overview` (revenue chart) | "No transactions in the last 30 days." | "No sales in the last 30 days yet — your revenue chart will fill in as orders come in." (no CTA) |
| `orders` | "No transactions for this page." | EmptyState — "No transactions yet" / "Sales will appear here when your team starts processing orders." (no CTA — POS sales come from cashier app) |
| `ecommerce-orders` | "No orders yet." | EmptyState — "No online orders yet" / "Customer orders from your storefront will appear here." (no CTA) |
| `customers/[id]` (transactions) | "No transactions yet." | EmptyState — "No transactions yet" / "This customer hasn't made any purchases." (no CTA) |
| `suppliers` | (none) | EmptyState — "No suppliers yet" / "Add suppliers to track purchase orders and inventory restocks." / Action: "Add your first supplier" (opens inline form via `?new=1`) |
| `channels` | (none) | EmptyState — "No channels yet" / "Channels are sales surfaces (your storefront, Shopify, etc.). Create one to start selling online." / Action: "Set up your first channel" (`?new=1`) |
| `discounts` | (none) | EmptyState — "No discounts yet" / "Create promo codes or automatic discounts to drive sales." / Action: "Create your first discount" (`?new=1`) |
| `tax` | (none) | EmptyState — "No tax regions yet" / "Configure tax rules so the right rates apply at checkout." / Action: "Add a tax region" (`?new=1`) |
| `purchase-orders` | (none) | EmptyState — "No purchase orders yet" / "Track inventory restocks from suppliers." / Action: "Create a purchase order" (`?new=1`) |

`audit` is intentionally omitted — its existing message ("No audit events match your search") is fine for a search-context page.

`integrations` is intentionally omitted — too varied (webhooks vs API tokens vs Shopify), better handled by M1 (split into sub-tabs) later.

### Q10 — Type-aware New Entry menu

**File:** `apps/admin-web/src/components/dashboard/AppShell.tsx`

The existing menu is a popover that opens above the gradient "New Entry" button. Currently shows two items unconditionally: Create Product, Create Shop.

Rewrite to filter by `useBusinessType()`:

| Item | Label | Href | Visible for |
|---|---|---|---|
| Product | "Create Product" | `/entries` | all types |
| Customer | "Create Customer" | `/customers?new=1` | all types |
| Shop | "Create Shop" | `/shops/new` | retail, hybrid |
| Channel | "Create Channel" | `/channels?new=1` | online, hybrid |
| Discount | "Create Discount" | `/discounts?new=1` | online, hybrid |

Total items per type:
- **online**: 4 — Product, Customer, Channel, Discount
- **retail**: 3 — Product, Customer, Shop
- **hybrid**: 5 — Product, Customer, Shop, Channel, Discount

**Page wiring for `?new=1`:**

The pages `customers`, `channels`, `discounts`, `suppliers`, `tax`, `purchase-orders` already have a `setShowForm(true)` (or `setShowCreate(true)`) flag triggered from a button. Add a tiny `useEffect` to each:

```tsx
const params = useSearchParams();
useEffect(() => {
  if (params.get("new") === "1") setShowForm(true);
}, [params]);
```

This connects the New Entry menu items, the empty-state CTAs (Q9), and any future deep-links to a single mechanism.

---

## Files

| File | Change | Reason |
|---|---|---|
| `services/api/app/routers/admin_web.py` | Add `pending_ecommerce_order_count` + `business_type` fields to `DashboardSummaryOut` and `dashboard_summary()` | Q2 backend |
| `apps/admin-web/src/lib/search-context.tsx` | NEW — page search config map | Q3 |
| `apps/admin-web/src/components/ui/primitives.tsx` | Extend `EmptyState` with optional CTA | Q9 |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | Header search wiring + type-aware New Entry menu | Q3, Q10 |
| `apps/admin-web/src/app/(main)/settings/page.tsx` | Delete 3 placeholder sections + unused state | Q1 |
| `apps/admin-web/src/app/(main)/overview/page.tsx` | Type-aware Pending Orders card + recent-activity link + better empty states | Q2, Q9 |
| `apps/admin-web/src/app/(main)/products/page.tsx` | Migrate `q` state to URL param | Q3 |
| `apps/admin-web/src/app/(main)/inventory/page.tsx` | Migrate `q` state to URL param | Q3 |
| `apps/admin-web/src/app/(main)/orders/page.tsx` | Migrate `q` state to URL param + empty state | Q3, Q9 |
| `apps/admin-web/src/app/(main)/ecommerce-orders/page.tsx` | Migrate `q` state to URL param + empty state | Q3, Q9 |
| `apps/admin-web/src/app/(main)/customers/page.tsx` | Migrate `q` state to URL param + `?new=1` deep link | Q3, Q10 |
| `apps/admin-web/src/app/(main)/customers/[id]/page.tsx` | Empty state for transactions list | Q9 |
| `apps/admin-web/src/app/(main)/audit/page.tsx` | Migrate `q` state to URL param | Q3 |
| `apps/admin-web/src/app/(main)/suppliers/page.tsx` | Add EmptyState + `?new=1` deep link | Q9, Q10 |
| `apps/admin-web/src/app/(main)/channels/page.tsx` | Add EmptyState + `?new=1` deep link | Q9, Q10 |
| `apps/admin-web/src/app/(main)/discounts/page.tsx` | Add EmptyState + `?new=1` deep link | Q9, Q10 |
| `apps/admin-web/src/app/(main)/tax/page.tsx` | Add EmptyState + `?new=1` deep link | Q9, Q10 |
| `apps/admin-web/src/app/(main)/purchase-orders/page.tsx` | Add EmptyState + `?new=1` deep link | Q9, Q10 |

---

## What does NOT change

- Existing search behaviour on pages outside the Q3 scope (analytics filters, billing, etc.)
- Existing primitive components other than `EmptyState`
- Backend RLS, permission checks, or any tenant-scoped logic
- The dashboard's other cards (Monthly Revenue, Avg. Transaction) — they're correct already
- The audit page's existing "No audit events match your search" message — it's appropriate for a search context
- Any feature gating from Phase 1 (BusinessTypeContext, RequiresBusinessType)

---

## Risk notes

1. **Q3 input being absent on unsupported pages may feel inconsistent.** Acceptable trade-off — the alternative (a disabled-looking input) is worse. The header search is meant to be a contextual tool, not a constant element.
2. **Q10's `?new=1` mechanism is a small bit of routing convention.** Documenting it in a brief comment on each page keeps it discoverable. If a future deep-link mechanism evolves (e.g. `/customers/new` as a real route), the convention can be replaced cleanly — pages just need to swap one effect for another.
3. **Deleting the Settings placeholder toggles is irreversible by `git revert` only.** That's fine — they were never functional.

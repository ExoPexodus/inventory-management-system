# Dashboard Setup Checklist Design Spec

**Date:** 2026-05-09
**Status:** Approved
**Phase:** 4 of 6 (UI declutter roadmap / L4)

---

## Problem

The admin dashboard is the first page every user sees after login. For new merchants it's discouraging — a grid of zeros with no guidance on what to do next. For demo prospects, it's a missed opportunity: there's no narrative of "here's what you do to launch your store". Established merchants fare better but the layout is identical regardless of whether they've sold anything.

Phase 3 (polish week) already made the Pending Orders card type-aware. L4 finishes the job by adding a setup checklist card that acts as a self-guided onboarding hub for new tenants and disappears entirely once they're operational.

---

## Goals

1. New tenants see a clear "what to do next" checklist on first login, filtered to their business type.
2. The checklist card disappears once all items are complete — no nagging established merchants.
3. No new HTTP requests — checklist state comes from the existing `dashboard-summary` endpoint.
4. The overview page remains a Server Component (fast, no hydration).

---

## Non-goals

- Quick-actions block (YAGNI — nav + New Entry menu already covers this)
- Changing the page title / "Operations Pulse" header
- Changing the existing 3 bento stat cards beyond polish-week fixes
- Client-side "skip" / dismiss button — done state is computed server-side only
- Animated progress / real-time checklist updates

---

## Backend changes

### `DashboardSummaryOut` — 5 new boolean fields

**File:** `services/api/app/routers/admin_web.py`

Add to the `DashboardSummaryOut` Pydantic model:

```python
has_first_product:      bool = False
has_first_shop:         bool = False
has_first_channel:      bool = False
has_payment_configured: bool = False
has_email_configured:   bool = False
```

All five default to `False` — additive, backward-compatible.

### Query logic inside `dashboard_summary()`

Compute each boolean after the existing queries, reusing already-computed values where possible:

```python
# Reuse existing product_count and shop_count:
has_first_product = product_count > 0
has_first_shop    = shop_count > 0

# Any non-POS channel exists for this tenant:
has_first_channel = bool(db.execute(
    select(func.count())
    .select_from(Channel)
    .where(Channel.tenant_id == tenant_id, Channel.type != "pos")
).scalar_one())

# Any channel has 'payment_provider' key in its JSONB config:
has_payment_configured = bool(db.execute(
    select(func.count())
    .select_from(Channel)
    .where(
        Channel.tenant_id == tenant_id,
        func.jsonb_typeof(Channel.config["payment_provider"]).isnot(None),
    )
).scalar_one())

# TenantEmailConfig row exists and is active:
has_email_configured = bool(db.execute(
    select(func.count())
    .select_from(TenantEmailConfig)
    .where(
        TenantEmailConfig.tenant_id == tenant_id,
        TenantEmailConfig.is_active.is_(True),
    )
).scalar_one())
```

`Channel` and `TenantEmailConfig` must be imported in the file. Check for them and add if absent.

Add all five values to the `return DashboardSummaryOut(...)` call.

---

## Frontend changes

### New component: `SetupChecklist`

**File:** `apps/admin-web/src/components/dashboard/SetupChecklist.tsx`

A pure Server Component (no `"use client"`, no hooks, no state). Receives a pre-filtered list of checklist items and renders the card.

**Checklist item definition:**

```tsx
export interface ChecklistItem {
  key: string;
  label: string;
  detail: string;
  href: string;
  icon: string;
  done: boolean;
}
```

**Card layout:**
- Full-width rounded card (`rounded-2xl`, `border border-outline-variant/10`, `bg-surface-container-lowest`)
- Header row: title `"Get started"` + subtitle `"X of Y steps complete"`
- Item rows sorted: unchecked first, checked (dimmed) below
- Each item row:
  - Left: Material Symbol icon (`text-[20px]`) + label (`font-semibold`) + detail (`text-xs text-on-surface-variant`)
  - Right: if done → green `check_circle` icon; if not done → `<Link href={item.href}>` arrow-right button

**Checked item styling:** `opacity-50` on the whole row. Done icon is `text-success` (or `text-green-500` if `success` token not in theme).

### Item definitions (in `overview/page.tsx`)

```tsx
type SetupItemDef = {
  key: string;
  label: string;
  detail: string;
  href: string;
  icon: string;
  types: ("online" | "retail" | "hybrid")[];
  done: (d: DashboardSummary) => boolean;
};

const SETUP_ITEMS: SetupItemDef[] = [
  {
    key: "first_product",
    label: "Add your first product",
    detail: "Products are what you sell — add at least one to get started.",
    href: "/entries",
    icon: "category",
    types: ["online", "retail", "hybrid"],
    done: (d) => d.has_first_product ?? false,
  },
  {
    key: "first_shop",
    label: "Add a shop",
    detail: "Shops are your physical locations. Your cashier app uses shops to manage sales.",
    href: "/shops/new",
    icon: "storefront",
    types: ["retail", "hybrid"],
    done: (d) => d.has_first_shop ?? false,
  },
  {
    key: "first_channel",
    label: "Set up a sales channel",
    detail: "Channels connect your inventory to storefronts and other selling surfaces.",
    href: "/channels?new=1",
    icon: "hub",
    types: ["online", "hybrid"],
    done: (d) => d.has_first_channel ?? false,
  },
  {
    key: "payment",
    label: "Configure a payment provider",
    detail: "Connect Stripe or Razorpay to start accepting payments at checkout.",
    href: "/channels",
    icon: "credit_card",
    types: ["online", "hybrid"],
    done: (d) => d.has_payment_configured ?? false,
  },
  {
    key: "email",
    label: "Configure email",
    detail: "Send order confirmations and receipts to your customers.",
    href: "/settings",
    icon: "mail",
    types: ["online", "retail", "hybrid"],
    done: (d) => d.has_email_configured ?? false,
  },
];
```

### Overview page wiring

**File:** `apps/admin-web/src/app/(main)/overview/page.tsx`

**1. Extend `DashboardSummary` type:**

```tsx
type DashboardSummary = {
  // existing fields…
  has_first_product?:      boolean;
  has_first_shop?:         boolean;
  has_first_channel?:      boolean;
  has_payment_configured?: boolean;
  has_email_configured?:   boolean;
};
```

**2. Compute visible items and render condition:**

```tsx
const businessType = d.business_type ?? "retail";
// … existing pendingCard derivation (from polish week) …

const visibleSetupItems: ChecklistItem[] = SETUP_ITEMS
  .filter((item) => item.types.includes(businessType as "online" | "retail" | "hybrid"))
  .map((item) => ({ ...item, done: item.done(d) }))
  .sort((a, b) => Number(a.done) - Number(b.done)); // unchecked first

const anyUnchecked = visibleSetupItems.some((item) => !item.done);
```

**3. Page layout — insert checklist before the bento cards:**

```tsx
{anyUnchecked && (
  <SetupChecklist
    items={visibleSetupItems}
    tenantPrefix={tenantPrefix}
  />
)}
```

`tenantPrefix` is needed so the `<Link>` elements in `SetupChecklist` correctly prefix their hrefs. The overview page already computes `tenantPrefix` from the URL (via server-side logic or implicit from the layout). If it doesn't expose it, the component can fall back to relative paths (since the Links resolve relative to the current tenant URL automatically in Next.js App Router).

---

## Files

| File | Change |
|---|---|
| `services/api/app/routers/admin_web.py` | 5 new fields on `DashboardSummaryOut`; 5 new queries in `dashboard_summary()` |
| `apps/admin-web/src/components/dashboard/SetupChecklist.tsx` | NEW — checklist card Server Component |
| `apps/admin-web/src/app/(main)/overview/page.tsx` | Extended type; `SETUP_ITEMS` definition; compute visible items; conditional render |

---

## Spec self-review

**Placeholder scan:** None — all queries, types, and copy are fully specified.

**Internal consistency:**
- `SETUP_ITEMS[*].done(d)` uses `?? false` — safe even before the backend ships the new fields.
- Sort puts unchecked first: `Number(false) - Number(true) = -1` (unchecked before checked). ✅
- `has_first_product = product_count > 0` reuses an already-computed variable — no redundant query. ✅
- `has_first_shop = shop_count > 0` same. ✅

**Scope:** Single focused feature with 3 file changes. Right-sized for one plan. ✅

**Ambiguity:**
- "SetupChecklist disappears when all done" — implemented by `anyUnchecked` gate: no client state, no localStorage, no dismiss. ✅
- "Unchecked items on top" — implemented by `.sort((a, b) => Number(a.done) - Number(b.done))`. ✅
- `tenantPrefix` — specified that `SetupChecklist` receives it as a prop; fallback noted. ✅

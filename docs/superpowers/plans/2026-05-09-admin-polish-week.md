# Admin Polish Week Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship five audit items as one focused phase: delete misleading Settings placeholders (Q1), make the dashboard's Pending Orders card business-type-aware and correctly labelled (Q2), wire the top-bar search to scope-aware page search via URL params (Q3), standardise empty states with a CTA pattern across list pages (Q9), and make the "New Entry" sidebar menu adapt to the merchant's business type (Q10).

**Architecture:** One small backend addition (two new fields on `DashboardSummaryOut`). All other changes are frontend-only. Two new shared utilities (`search-context.tsx`, extended `EmptyState`) are introduced so per-page changes are mechanical. The existing `BusinessTypeContext` from Phase 1 is reused for Q2, Q10, and the menu filtering — no new context. Search state moves from per-page local `useState` into URL `?q=` params; the header reads `usePathname()` to choose a placeholder and pushes URL changes.

**Tech Stack:** Next.js 15 / React 19 / TypeScript / Tailwind on frontend; FastAPI / SQLAlchemy 2.x on backend. No frontend test framework — validation is via `docker compose up --build` and manual smoke test.

---

## Codebase context

### Reused from Phase 1

- `apps/admin-web/src/lib/business-type-context.tsx` — `useBusinessType()` returns `{ flags, loading, invalidate }` where `flags.business_type` is `"online" | "retail" | "hybrid"`

### Pre-existing primitives

- `apps/admin-web/src/components/ui/primitives.tsx` — exports `EmptyState({ title, detail })`, `SearchBar`, `Panel`, `PrimaryButton`, etc.

### Backend findings (verified before writing plan)

- `services/api/app/routers/admin_web.py:330` — `DashboardSummaryOut` model
- `services/api/app/routers/admin_web.py:344` — `dashboard_summary()` endpoint
- `services/api/app/routers/admin_web.py:381` — the existing `pending_order_count` query counts `PurchaseOrder.status == "ordered"` (incoming inventory), NOT POS or ecommerce orders. The audit's framing was wrong; the spec is corrected.
- `services/api/app/models/tables.py:1024` — `Order` class. `Order.fulfillment_status` defaults to `"pending"` and reflects ecommerce fulfillment state.

### Frontend findings (verified before writing plan)

- All 6 search-target pages currently use local `q` state with inline `<SearchBar>`. None already use URL params for q. Migration is mechanical.
- `?new=1` deep-link convention: the destination pages already have `setShowForm(true)` or `setShowCreate(true)` triggered by a button. Adding a tiny `useEffect` keyed on `searchParams.get("new") === "1"` plugs into the existing handler.

### Manual deploy + smoke-test pattern

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
docker compose logs admin-web --tail=10
```

For backend changes:
```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/routers/admin_web.py $CONTAINER:/app/app/routers/admin_web.py
docker compose restart api && sleep 5
docker compose logs api --tail=5
```

---

## File map

| File | Status | Responsibility |
|---|---|---|
| `services/api/app/routers/admin_web.py` | MODIFY | Add `business_type` + `pending_ecommerce_order_count` to `DashboardSummaryOut` and the query |
| `apps/admin-web/src/components/ui/primitives.tsx` | MODIFY | Extend `EmptyState` with optional `actionLabel` + `actionHref` |
| `apps/admin-web/src/lib/search-context.tsx` | NEW | Page-search config map + helper |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | MODIFY | Header search wiring; type-aware New Entry menu |
| `apps/admin-web/src/app/(main)/settings/page.tsx` | MODIFY | Delete Q1 placeholder sections + unused state hooks |
| `apps/admin-web/src/app/(main)/overview/page.tsx` | MODIFY | Type-aware Pending Orders card; better empty states |
| `apps/admin-web/src/app/(main)/products/page.tsx` | MODIFY | q from URL param; remove inline SearchBar |
| `apps/admin-web/src/app/(main)/inventory/page.tsx` | MODIFY | q from URL param |
| `apps/admin-web/src/app/(main)/orders/page.tsx` | MODIFY | q from URL param; remove inline SearchBar; empty state |
| `apps/admin-web/src/app/(main)/ecommerce-orders/page.tsx` | MODIFY | q from URL param; empty state |
| `apps/admin-web/src/app/(main)/customers/page.tsx` | MODIFY | q from URL param; remove inline SearchBar; `?new=1` handler |
| `apps/admin-web/src/app/(main)/customers/[id]/page.tsx` | MODIFY | Empty state for transactions list |
| `apps/admin-web/src/app/(main)/audit/page.tsx` | MODIFY | q from URL param; remove inline SearchBar |
| `apps/admin-web/src/app/(main)/suppliers/page.tsx` | MODIFY | EmptyState + `?new=1` handler |
| `apps/admin-web/src/app/(main)/channels/page.tsx` | MODIFY | EmptyState + `?new=1` handler |
| `apps/admin-web/src/app/(main)/discounts/page.tsx` | MODIFY | EmptyState + `?new=1` handler |
| `apps/admin-web/src/app/(main)/tax/page.tsx` | MODIFY | EmptyState + `?new=1` handler |
| `apps/admin-web/src/app/(main)/purchase-orders/page.tsx` | MODIFY | EmptyState + `?new=1` handler |

---

## Task 1: Backend — DashboardSummaryOut adds business_type + pending_ecommerce_order_count

**Files:**
- Modify: `services/api/app/routers/admin_web.py`

- [ ] **Step 1: Locate the model and query**

Read lines 320–470 of `services/api/app/routers/admin_web.py` to confirm the structure of `DashboardSummaryOut` and `dashboard_summary()`. The model is around line 330; the existing `pending_order_count` query is around line 381; the return statement is around line 450.

- [ ] **Step 2: Add fields to `DashboardSummaryOut`**

Find this block (around line 330):

```python
class DashboardSummaryOut(BaseModel):
    posted_transaction_count: int
    gross_sales_cents: int
    stock_alert_count: int
    supplier_count: int
    shop_count: int
    product_count: int
    tenant_count: int
    avg_transaction_cents: int = 0
    pending_order_count: int = 0
    revenue_delta_pct: float = 0.0
    recent_activity: list[RecentActivityItem]
```

Add two new fields:

```python
class DashboardSummaryOut(BaseModel):
    posted_transaction_count: int
    gross_sales_cents: int
    stock_alert_count: int
    supplier_count: int
    shop_count: int
    product_count: int
    tenant_count: int
    avg_transaction_cents: int = 0
    pending_order_count: int = 0
    pending_ecommerce_order_count: int = 0
    revenue_delta_pct: float = 0.0
    business_type: str = "retail"
    recent_activity: list[RecentActivityItem]
```

- [ ] **Step 3: Add the new query and tenant lookup inside `dashboard_summary()`**

After the existing `pending_order_count` query (around line 381), add a new query for ecommerce pending orders. Locate this block:

```python
    pending_order_count = int(
        db.execute(
            select(func.count())
            .select_from(PurchaseOrder)
            .where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.status == "ordered")
        ).scalar_one()
    )
```

Add immediately after it:

```python
    pending_ecommerce_order_count = int(
        db.execute(
            select(func.count())
            .select_from(Order)
            .where(Order.tenant_id == tenant_id, Order.fulfillment_status == "pending")
        ).scalar_one()
    )

    tenant_row = db.get(Tenant, tenant_id)
    business_type = tenant_row.business_type if tenant_row else "retail"
```

- [ ] **Step 4: Verify `Order` and `Tenant` are imported**

Search for the `from app.models import` line near the top of `admin_web.py`. Make sure both `Order` and `Tenant` are in the import list. If not, add them.

```bash
grep -n "from app.models import" services/api/app/routers/admin_web.py | head -3
```

If `Order` or `Tenant` is missing, add them to the existing `from app.models import (...)` import.

- [ ] **Step 5: Update the return statement**

Find the `return DashboardSummaryOut(...)` block (around line 450). Add the two new fields. Original:

```python
    return DashboardSummaryOut(
        posted_transaction_count=posted_transaction_count,
        gross_sales_cents=gross_sales_cents,
        stock_alert_count=stock_alert_count,
        supplier_count=supplier_count,
        shop_count=shop_count,
        product_count=product_count,
        tenant_count=tenant_count,
        avg_transaction_cents=avg_transaction_cents,
        pending_order_count=pending_order_count,
        revenue_delta_pct=revenue_delta_pct,
        recent_activity=items,
    )
```

Updated:

```python
    return DashboardSummaryOut(
        posted_transaction_count=posted_transaction_count,
        gross_sales_cents=gross_sales_cents,
        stock_alert_count=stock_alert_count,
        supplier_count=supplier_count,
        shop_count=shop_count,
        product_count=product_count,
        tenant_count=tenant_count,
        avg_transaction_cents=avg_transaction_cents,
        pending_order_count=pending_order_count,
        pending_ecommerce_order_count=pending_ecommerce_order_count,
        revenue_delta_pct=revenue_delta_pct,
        business_type=business_type,
        recent_activity=items,
    )
```

- [ ] **Step 6: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('services/api/app/routers/admin_web.py').read()); print('OK')"
```

Expected: `OK`.

- [ ] **Step 7: Deploy and smoke-test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/routers/admin_web.py $CONTAINER:/app/app/routers/admin_web.py
docker compose restart api && sleep 5
docker compose logs api --tail=5
```

Expected: API restart cleanly, no errors. Optionally verify response shape:

```bash
docker compose exec api python -c "
from fastapi.testclient import TestClient
from app.main import app
print([f for f in app.openapi()['components']['schemas']['DashboardSummaryOut']['properties'].keys()])
" 2>&1 | tail -3
```

Expected output includes `pending_ecommerce_order_count` and `business_type`.

- [ ] **Step 8: Commit**

```bash
git add services/api/app/routers/admin_web.py
git commit -m "feat(api): add business_type + pending_ecommerce_order_count to dashboard-summary"
```

---

## Task 2: Extend EmptyState primitive with optional CTA

**Files:**
- Modify: `apps/admin-web/src/components/ui/primitives.tsx`

- [ ] **Step 1: Find the existing EmptyState**

```bash
grep -n "function EmptyState" apps/admin-web/src/components/ui/primitives.tsx
```

It's a small (~5-line) component.

- [ ] **Step 2: Replace EmptyState definition**

Find this block:

```tsx
export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="px-4 py-12 text-center">
      <p className="font-headline text-base font-bold text-on-surface">{title}</p>
      {detail ? <p className="mt-1 text-sm text-on-surface-variant">{detail}</p> : null}
    </div>
  );
}
```

Replace with:

```tsx
export function EmptyState({
  title,
  detail,
  actionLabel,
  actionHref,
}: {
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
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-on-primary transition-opacity hover:opacity-90"
        >
          {actionLabel}
        </Link>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 3: Ensure `Link` is imported in primitives.tsx**

```bash
grep -n "^import Link" apps/admin-web/src/components/ui/primitives.tsx
```

If absent, add at the top:

```tsx
import Link from "next/link";
```

- [ ] **Step 4: Verify build**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
```

Expected: `✓ Compiled successfully`. The change is backwards compatible — every existing `<EmptyState title=... detail=... />` call site keeps working.

- [ ] **Step 5: Commit**

```bash
git add apps/admin-web/src/components/ui/primitives.tsx
git commit -m "feat(admin-web): extend EmptyState with optional actionLabel + actionHref CTA"
```

---

## Task 3: Create search-context.tsx (page → search config map)

**Files:**
- Create: `apps/admin-web/src/lib/search-context.tsx`

- [ ] **Step 1: Create the file**

```tsx
"use client";

export interface PageSearchConfig {
  placeholder: string;
  paramName: string;
}

const PAGE_SEARCH_CONFIG: Record<string, PageSearchConfig> = {
  "/products":         { placeholder: "Search products...",      paramName: "q" },
  "/inventory":        { placeholder: "Search inventory...",     paramName: "q" },
  "/orders":           { placeholder: "Search transactions...",  paramName: "q" },
  "/ecommerce-orders": { placeholder: "Search online orders...", paramName: "q" },
  "/customers":        { placeholder: "Search customers...",     paramName: "q" },
  "/audit":            { placeholder: "Search audit events...",  paramName: "q" },
};

const ROOT_ROUTES = new Set([
  "overview", "inventory", "staff", "team", "orders", "analytics",
  "suppliers", "products", "purchase-orders", "shifts", "reconciliation",
  "audit", "reports", "integrations", "settings", "billing", "apps",
  "entries", "shops", "login", "channels", "ecommerce-orders", "discounts",
  "ecommerce", "inventory-pools", "tax", "customers",
]);

/** Strip a tenant prefix segment (e.g. "/some-tenant/products" -> "/products"). */
function stripTenantPrefix(pathname: string): string {
  const segs = pathname.split("/").filter(Boolean);
  if (segs.length === 0) return pathname;
  if (!ROOT_ROUTES.has(segs[0])) {
    // First segment looks like a tenant slug; drop it
    return "/" + segs.slice(1).join("/");
  }
  return pathname;
}

export function getSearchConfig(pathname: string): PageSearchConfig | null {
  const stripped = stripTenantPrefix(pathname);
  // Match either exact path or prefix (e.g. /products/123 still matches /products)
  for (const [route, cfg] of Object.entries(PAGE_SEARCH_CONFIG)) {
    if (stripped === route || stripped.startsWith(route + "/")) {
      return cfg;
    }
  }
  return null;
}
```

- [ ] **Step 2: Verify build**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
```

Expected: `✓ Compiled successfully`.

- [ ] **Step 3: Commit**

```bash
git add apps/admin-web/src/lib/search-context.tsx
git commit -m "feat(admin-web): add search-context page config map"
```

---

## Task 4: AppShell — header search + type-aware New Entry menu

**Files:**
- Modify: `apps/admin-web/src/components/dashboard/AppShell.tsx`

- [ ] **Step 1: Add imports**

At the top of the file, alongside existing imports, add:

```tsx
import { useRouter, useSearchParams } from "next/navigation";
import { getSearchConfig } from "@/lib/search-context";
```

(`usePathname` is already imported.)

- [ ] **Step 2: Replace the header search block**

Inside `AppShellInner`, find the existing header `<input>` block (around the `placeholder="Search archive..."` line):

```tsx
            <div className="relative w-full max-w-sm">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-lg text-on-surface-variant" aria-hidden="true">search</span>
              <input
                className="w-full rounded-full border-none bg-surface-container-low py-2 pl-10 pr-4 text-sm text-on-surface outline-none placeholder:text-on-surface-variant focus:ring-1 focus:ring-primary"
                placeholder="Search archive..."
                type="text"
              />
            </div>
```

Replace with:

```tsx
            <HeaderSearch />
```

Then define `HeaderSearch` near the top of the file (above `AppShell` export, after the imports and constants):

```tsx
function HeaderSearch() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const cfg = getSearchConfig(pathname);
  const [value, setValue] = useState(params.get(cfg?.paramName ?? "q") ?? "");

  // Sync from URL when navigating
  useEffect(() => {
    setValue(params.get(cfg?.paramName ?? "q") ?? "");
  }, [params, cfg?.paramName]);

  // Debounce push to URL
  useEffect(() => {
    if (!cfg) return;
    const handle = window.setTimeout(() => {
      const next = new URLSearchParams(params.toString());
      if (value.trim()) next.set(cfg.paramName, value.trim());
      else next.delete(cfg.paramName);
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname);
    }, 300);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  if (!cfg) return null;

  return (
    <div className="relative w-full max-w-sm">
      <span
        className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-lg text-on-surface-variant"
        aria-hidden="true"
      >
        search
      </span>
      <input
        className="w-full rounded-full border-none bg-surface-container-low py-2 pl-10 pr-4 text-sm text-on-surface outline-none placeholder:text-on-surface-variant focus:ring-1 focus:ring-primary"
        placeholder={cfg.placeholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        type="text"
      />
    </div>
  );
}
```

- [ ] **Step 3: Replace the New Entry menu**

Find the existing dropdown (the block triggered by `setEntryMenuOpen` containing two `<Link>` items: "Create Product" and "Create Shop"):

```tsx
            {entryMenuOpen && (
              <div className="absolute bottom-full left-0 right-0 mb-1 overflow-hidden rounded-lg border border-outline-variant/10 bg-surface-container-lowest shadow-lg">
                <Link
                  href={`${tenantPrefix}/entries`}
                  onClick={() => setEntryMenuOpen(false)}
                  className="flex items-center gap-2 px-4 py-3 text-[13px] font-medium text-on-surface hover:bg-surface-container"
                >
                  <span className="material-symbols-outlined text-[18px]" aria-hidden="true">inventory_2</span>
                  Create Product
                </Link>
                <Link
                  href={`${tenantPrefix}/shops/new`}
                  onClick={() => setEntryMenuOpen(false)}
                  className="flex items-center gap-2 border-t border-outline-variant/10 px-4 py-3 text-[13px] font-medium text-on-surface hover:bg-surface-container"
                >
                  <span className="material-symbols-outlined text-[18px]" aria-hidden="true">store</span>
                  Create Shop
                </Link>
              </div>
            )}
```

Replace with a type-aware filtered list. Add this constant near the other module-level constants in the file:

```tsx
type NewEntryItem = {
  href: string;
  label: string;
  icon: string;
  allowedTypes: BusinessType[];
};

const ALL_TYPES_NE: BusinessType[] = ["online", "retail", "hybrid"];

const NEW_ENTRY_ITEMS: NewEntryItem[] = [
  { href: "/entries",            label: "Create Product",  icon: "inventory_2", allowedTypes: ALL_TYPES_NE },
  { href: "/customers?new=1",    label: "Create Customer", icon: "person_add",  allowedTypes: ALL_TYPES_NE },
  { href: "/shops/new",          label: "Create Shop",     icon: "store",       allowedTypes: ["retail", "hybrid"] },
  { href: "/channels?new=1",     label: "Create Channel",  icon: "storefront",  allowedTypes: ["online", "hybrid"] },
  { href: "/discounts?new=1",    label: "Create Discount", icon: "local_offer", allowedTypes: ["online", "hybrid"] },
];
```

Inside `AppShellInner`, alongside the existing `useBusinessType()` call, derive the visible list:

```tsx
const visibleNewEntryItems = NEW_ENTRY_ITEMS.filter((item) =>
  typeAllows(flags, item.allowedTypes)
);
```

Then render the dropdown with the filtered items:

```tsx
            {entryMenuOpen && (
              <div className="absolute bottom-full left-0 right-0 mb-1 overflow-hidden rounded-lg border border-outline-variant/10 bg-surface-container-lowest shadow-lg">
                {visibleNewEntryItems.map((item, idx) => (
                  <Link
                    key={item.href}
                    href={`${tenantPrefix}${item.href}`}
                    onClick={() => setEntryMenuOpen(false)}
                    className={`flex items-center gap-2 px-4 py-3 text-[13px] font-medium text-on-surface hover:bg-surface-container ${
                      idx > 0 ? "border-t border-outline-variant/10" : ""
                    }`}
                  >
                    <span className="material-symbols-outlined text-[18px]" aria-hidden="true">{item.icon}</span>
                    {item.label}
                  </Link>
                ))}
              </div>
            )}
```

- [ ] **Step 4: Verify build and smoke-test**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
sleep 4 && docker compose logs admin-web --tail=10
```

Expected: `✓ Compiled successfully`. In a browser:
- Navigate to `/products` — header search shows "Search products..." placeholder
- Navigate to `/overview` — header search input is gone (no input rendered)
- Open New Entry menu — items are filtered by current business type

- [ ] **Step 5: Commit**

```bash
git add apps/admin-web/src/components/dashboard/AppShell.tsx
git commit -m "feat(admin-web): scope-aware header search + type-aware New Entry menu"
```

---

## Task 5: Settings — delete placeholder sections (Q1)

**Files:**
- Modify: `apps/admin-web/src/app/(main)/settings/page.tsx`

- [ ] **Step 1: Locate the placeholder sections**

```bash
grep -n "Notifications\|Security\|Appearance\|emailDigest\|twoFactor\|compactTables" apps/admin-web/src/app/\(main\)/settings/page.tsx | head -20
```

The three sections start at:
- Notifications: `<h3>Notifications</h3>` around line ~758
- Security: `<h3>Security</h3>` around line ~786
- Appearance: `<h3>Appearance</h3>` around line ~814

- [ ] **Step 2: Delete the three placeholder JSX blocks**

For each section, the wrapping `<div className="...">…</div>` around the `<h3>` and its toggles needs to be removed. The sections are siblings — each is a distinct top-level `<div>` containing a heading and a body.

Read lines ~750–850 to confirm the structure before deleting. Each section pattern looks like:

```tsx
        {/* Notifications */}
        <div className="...">
          <h3 className="font-headline text-lg font-bold text-primary">Notifications</h3>
          <div className="...">
            {/* ...toggle rows... */}
          </div>
        </div>
```

Delete all three blocks (Notifications, Security, Appearance) by removing each enclosing `<div>` from its opening `<div>` to its matching closing `</div>`. The "Business type" section follows Appearance — preserve it.

- [ ] **Step 3: Delete unused state hooks**

Find and remove these declarations near the top of the component (around lines 18–28):

```tsx
  const [emailDigest, setEmailDigest] = useState(true);
  const [lowStockAlerts, setLowStockAlerts] = useState(true);
  const [pushNotify, setPushNotify] = useState(false);

  const [twoFactor, setTwoFactor] = useState(false);
  const [sessionNotify, setSessionNotify] = useState(true);
  const [apiKeyRotation, setApiKeyRotation] = useState(false);

  const [compactTables, setCompactTables] = useState(false);
  const [highContrast, setHighContrast] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
```

Delete all 9 lines.

- [ ] **Step 4: Check for lingering references**

```bash
grep -nE "emailDigest|lowStockAlerts|pushNotify|twoFactor|sessionNotify|apiKeyRotation|compactTables|highContrast|reducedMotion" apps/admin-web/src/app/\(main\)/settings/page.tsx
```

Expected: no matches. If any remain (typically because a binding was missed), delete them.

- [ ] **Step 5: Verify build**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
```

Expected: `✓ Compiled successfully`. The page should be ~150 lines shorter.

- [ ] **Step 6: Commit**

```bash
git add 'apps/admin-web/src/app/(main)/settings/page.tsx'
git commit -m "feat(admin-web): remove non-functional Settings placeholder sections (Q1)"
```

---

## Task 6: Overview page — type-aware Pending Orders card + better empty states

**Files:**
- Modify: `apps/admin-web/src/app/(main)/overview/page.tsx`

This task touches both Q2 (type-aware card) and the overview-page bits of Q9 (empty-state copy). The page is currently a Server Component — keep it that way; the new fields come from the same `serverJsonGet` call.

- [ ] **Step 1: Update the response type**

Find the `type DashboardSummary = { ... }` block at the top of the file. Add the two new fields:

```tsx
type DashboardSummary = {
  posted_transaction_count: number;
  gross_sales_cents: number;
  stock_alert_count: number;
  supplier_count: number;
  shop_count: number;
  product_count: number;
  pending_order_count?: number;
  pending_ecommerce_order_count?: number;
  business_type?: "online" | "retail" | "hybrid";
  avg_transaction_cents?: number;
  revenue_delta_pct?: number;
  recent_activity: Array<{ kind: string; ref_id: string; created_at: string; detail: string }>;
};
```

- [ ] **Step 2: Derive type-aware card props**

After the existing `const d = res.data;` line, add:

```tsx
  const businessType = d.business_type ?? "retail";
  const isEcomOrientedDashboard = businessType === "online" || businessType === "hybrid";
  const pendingCard = isEcomOrientedDashboard
    ? {
        label: "Pending Online Orders",
        count: d.pending_ecommerce_order_count ?? 0,
        href: "/ecommerce-orders",
      }
    : {
        label: "Open Purchase Orders",
        count: d.pending_order_count ?? 0,
        href: "/purchase-orders",
      };
```

- [ ] **Step 3: Update the Pending Orders card JSX**

Find the third bento card (the one currently labelled "Pending Orders"):

```tsx
        <div className="flex flex-col justify-between rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <div className="flex items-start justify-between">
            <span className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Pending Orders</span>
            <div className="h-2 w-2 animate-pulse rounded-full bg-secondary" />
          </div>
          <div className="mt-4">
            <h3 className="font-headline text-4xl font-extrabold tracking-tighter text-primary">
              {d.pending_order_count ?? 0}
            </h3>
            <p className="mt-1 text-xs text-on-surface-variant/60">Awaiting processing</p>
          </div>
        </div>
```

Replace with a clickable Link card using `pendingCard`:

```tsx
        <Link
          href={pendingCard.href}
          className="flex flex-col justify-between rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm transition-colors hover:bg-surface-container-low/60"
        >
          <div className="flex items-start justify-between">
            <span className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">{pendingCard.label}</span>
            <div className="h-2 w-2 animate-pulse rounded-full bg-secondary" />
          </div>
          <div className="mt-4">
            <h3 className="font-headline text-4xl font-extrabold tracking-tighter text-primary">
              {pendingCard.count}
            </h3>
            <p className="mt-1 text-xs text-on-surface-variant/60">Awaiting processing</p>
          </div>
        </Link>
```

- [ ] **Step 4: Update the "View all orders" link in Recent Activity**

Find the existing link in the Recent Activity section header:

```tsx
            <Link href="/orders" className="rounded-full bg-secondary/10 px-3 py-1 text-xs font-bold text-on-secondary-container transition-colors hover:bg-secondary/20">
              View all orders
            </Link>
```

Replace with a type-aware version:

```tsx
            <Link
              href={isEcomOrientedDashboard ? "/ecommerce-orders" : "/purchase-orders"}
              className="rounded-full bg-secondary/10 px-3 py-1 text-xs font-bold text-on-secondary-container transition-colors hover:bg-secondary/20"
            >
              {isEcomOrientedDashboard ? "View online orders" : "View purchase orders"}
            </Link>
```

- [ ] **Step 5: Replace developer-y empty state strings**

Find the chart empty state:

```tsx
            <div className="flex h-full items-center justify-center text-sm text-on-surface-variant">
              No transactions in the last 30 days.
            </div>
```

Replace with:

```tsx
            <div className="flex h-full items-center justify-center text-sm text-on-surface-variant">
              No sales in the last 30 days yet — your revenue chart will fill in as orders come in.
            </div>
```

Find the recent-activity empty state:

```tsx
                {d.recent_activity.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-6 py-10 text-center text-sm text-on-surface-variant">
                      No recent activity. Seed demo data to populate.
                    </td>
                  </tr>
                )}
```

Replace with:

```tsx
                {d.recent_activity.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-6 py-10 text-center text-sm text-on-surface-variant">
                      Recent activity will appear here once you make sales.
                    </td>
                  </tr>
                )}
```

- [ ] **Step 6: Verify build and smoke-test**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
```

Expected: `✓ Compiled successfully`. In a browser, log in as a tenant of each business type and verify the Pending Orders card label/link match the table.

- [ ] **Step 7: Commit**

```bash
git add 'apps/admin-web/src/app/(main)/overview/page.tsx'
git commit -m "feat(admin-web): type-aware dashboard Pending Orders card + better empty-state copy"
```

---

## Task 7: Migrate 6 search pages from local q state to URL param

**Files:**
- Modify: `apps/admin-web/src/app/(main)/products/page.tsx`
- Modify: `apps/admin-web/src/app/(main)/inventory/page.tsx`
- Modify: `apps/admin-web/src/app/(main)/orders/page.tsx`
- Modify: `apps/admin-web/src/app/(main)/ecommerce-orders/page.tsx`
- Modify: `apps/admin-web/src/app/(main)/customers/page.tsx`
- Modify: `apps/admin-web/src/app/(main)/audit/page.tsx`

The migration pattern is the same for every page, but each page differs in subtle ways (some use `<SearchBar>` inline, some use `useState`, some have other related state). Apply the pattern carefully per file.

**General pattern:**

1. Add at the top of the imports: `import { useSearchParams } from "next/navigation";`
2. Replace `const [q, setQ] = useState("");` with `const params = useSearchParams(); const q = params.get("q") ?? "";`
3. Remove the `<SearchBar ... value={q} onChange={(e) => setQ(e.target.value)} />` JSX wherever it appears in the page header (the header search now drives this)
4. Remove the `SearchBar` import if it's no longer used in that file
5. Keep the existing `useEffect` that re-fetches when `q` changes — it already depends on `q`, so reading from URL works the same way

- [ ] **Step 1: Migrate products/page.tsx**

In `apps/admin-web/src/app/(main)/products/page.tsx`:

a) At the top, add the import. The file already imports from `react`. Add this line after the React imports:

```tsx
import { useSearchParams } from "next/navigation";
```

b) Find `const [q, setQ] = useState("");` and replace with:

```tsx
const params = useSearchParams();
const q = params.get("q") ?? "";
```

c) Remove this JSX block (around line 154):

```tsx
<SearchBar className="min-w-[14rem] flex-1" placeholder="Search name or SKU" value={q} onChange={(e) => setQ(e.target.value)} />
```

d) Check if `SearchBar` is still used elsewhere in the file:

```bash
grep -c "<SearchBar" apps/admin-web/src/app/\(main\)/products/page.tsx
```

If 0, remove `SearchBar,` from the imports list.

- [ ] **Step 2: Migrate inventory/page.tsx**

`inventory/page.tsx` already imports `useSearchParams` (it uses `?highlight=critical`). It still uses local `q` state. Apply the same pattern: replace local `q`/`setQ` with URL-derived `q`. Remove any inline `<SearchBar>` for product search if present. Keep the `highlightCritical` URL param logic intact.

- [ ] **Step 3: Migrate orders/page.tsx**

In `apps/admin-web/src/app/(main)/orders/page.tsx`:

a) Add `import { useSearchParams } from "next/navigation";` near the top.

b) Replace `const [q, setQ] = useState("");` (search for this pattern in the file) with:

```tsx
const params = useSearchParams();
const q = params.get("q") ?? "";
```

c) Remove the inline `<SearchBar>` block in the page header (around line 184).

d) Remove `SearchBar,` from the imports list if it's no longer used.

- [ ] **Step 4: Migrate ecommerce-orders/page.tsx**

Same pattern as Step 3. The file may not have a SearchBar at all — in that case, just wire up the URL param read. Verify by grepping for `useState.*q\|<SearchBar` first.

- [ ] **Step 5: Migrate customers/page.tsx**

Same pattern. The inline SearchBar is around line 68. Apply identically.

- [ ] **Step 6: Migrate audit/page.tsx**

Same pattern. The inline SearchBar is around line 105.

- [ ] **Step 7: Verify build**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -10
```

Expected: `✓ Compiled successfully`. If TypeScript complains about `setQ` being undefined anywhere, search the file for stale references (typically in event handlers) and remove them — none of these pages should have any `setQ` callers after migration.

- [ ] **Step 8: Smoke-test in a browser**

- Navigate to `/products`, type "widget" in the header search → URL becomes `/products?q=widget` and the list filters.
- Refresh — the URL retains the filter and the list stays filtered.
- Navigate to `/orders` — URL becomes `/orders` (q is dropped because each page renders header search fresh).
- Navigate to `/overview` — header search disappears.

- [ ] **Step 9: Commit**

```bash
git add 'apps/admin-web/src/app/(main)/products/page.tsx' \
        'apps/admin-web/src/app/(main)/inventory/page.tsx' \
        'apps/admin-web/src/app/(main)/orders/page.tsx' \
        'apps/admin-web/src/app/(main)/ecommerce-orders/page.tsx' \
        'apps/admin-web/src/app/(main)/customers/page.tsx' \
        'apps/admin-web/src/app/(main)/audit/page.tsx'
git commit -m "feat(admin-web): migrate 6 list pages from local q state to URL param"
```

---

## Task 8: Empty states + ?new=1 deep-links across remaining list pages

**Files (each gets EmptyState + `?new=1` handler where relevant):**
- Modify: `apps/admin-web/src/app/(main)/customers/page.tsx` (`?new=1` only — empty state already exists)
- Modify: `apps/admin-web/src/app/(main)/customers/[id]/page.tsx` (empty state for transactions list)
- Modify: `apps/admin-web/src/app/(main)/orders/page.tsx` (empty state)
- Modify: `apps/admin-web/src/app/(main)/ecommerce-orders/page.tsx` (empty state)
- Modify: `apps/admin-web/src/app/(main)/suppliers/page.tsx` (EmptyState + `?new=1`)
- Modify: `apps/admin-web/src/app/(main)/channels/page.tsx` (EmptyState + `?new=1`)
- Modify: `apps/admin-web/src/app/(main)/discounts/page.tsx` (EmptyState + `?new=1`)
- Modify: `apps/admin-web/src/app/(main)/tax/page.tsx` (EmptyState + `?new=1`)
- Modify: `apps/admin-web/src/app/(main)/purchase-orders/page.tsx` (EmptyState + `?new=1`)

**Common helper to copy into each `?new=1` page:**

```tsx
import { useSearchParams } from "next/navigation";

// Inside the component body, after the existing state hooks:
const newParams = useSearchParams();
useEffect(() => {
  if (newParams.get("new") === "1") {
    // The exact setter name differs per page — use whichever this page already has
    setShowForm(true);  // OR setShowCreate(true) — match the existing flag
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [newParams]);
```

(If `useSearchParams` is already imported from Task 7 on the same file, reuse it — name the variable consistently.)

- [ ] **Step 1: customers/page.tsx — `?new=1` handler**

In `apps/admin-web/src/app/(main)/customers/page.tsx`, the create-customer modal is opened via `setShowCreate(true)`. Find that state declaration. After it, add:

```tsx
const newParams = useSearchParams();
useEffect(() => {
  if (newParams.get("new") === "1") setShowCreate(true);
}, [newParams]);
```

(`useSearchParams` is already imported from Task 7 if you migrated this file there — just use the same `params` variable instead of creating `newParams`.)

- [ ] **Step 2: customers/[id]/page.tsx — empty state for transactions**

Find this block (around line 117):

```tsx
<tr><td colSpan={4} className="px-6 py-4 text-sm text-on-surface-variant">No transactions yet.</td></tr>
```

Replace with:

```tsx
<tr>
  <td colSpan={4} className="px-6 py-10">
    <EmptyState title="No transactions yet" detail="This customer hasn't made any purchases." />
  </td>
</tr>
```

Add `EmptyState` to the imports from `@/components/ui/primitives` if not already present.

- [ ] **Step 3: orders/page.tsx — empty state**

Find this line (around line 279):

```tsx
                    No transactions for this page.
```

Replace its containing element with an `EmptyState`:

```tsx
                    <EmptyState
                      title="No transactions yet"
                      detail="Sales will appear here when your team starts processing orders."
                    />
```

Add `EmptyState` import if missing.

- [ ] **Step 4: ecommerce-orders/page.tsx — empty state**

Find:

```tsx
<p className="px-6 py-8 text-center text-sm text-on-surface-variant">No orders yet.</p>
```

Replace with:

```tsx
<EmptyState
  title="No online orders yet"
  detail="Customer orders from your storefront will appear here."
/>
```

Add `EmptyState` import if missing.

- [ ] **Step 5: suppliers/page.tsx — EmptyState + `?new=1`**

a) Add `?new=1` handler. Find `setShowForm` near the top of the component. After the related state, add:

```tsx
const newParams = useSearchParams();
useEffect(() => {
  if (newParams.get("new") === "1") setShowForm(true);
}, [newParams]);
```

Add `import { useSearchParams } from "next/navigation";` if not already there.

b) Add an empty state to the suppliers list. Find where the list renders — it's a list of cards under a heading. Add a conditional rendering:

```tsx
{suppliers.length === 0 && !loading ? (
  <EmptyState
    title="No suppliers yet"
    detail="Add suppliers to track purchase orders and inventory restocks."
    actionLabel="Add your first supplier"
    actionHref="?new=1"
  />
) : null}
```

Place it where the existing empty rendering would be (or where the list normally renders, conditional on `suppliers.length === 0`).

Add `EmptyState` import.

- [ ] **Step 6: channels/page.tsx — EmptyState + `?new=1`**

a) Same `?new=1` pattern as Step 5 (uses `setShowForm`).

b) Add EmptyState:

```tsx
{channels.length === 0 && !loading ? (
  <EmptyState
    title="No channels yet"
    detail="Channels are sales surfaces (your storefront, Shopify, etc.). Create one to start selling online."
    actionLabel="Set up your first channel"
    actionHref="?new=1"
  />
) : null}
```

- [ ] **Step 7: discounts/page.tsx — EmptyState + `?new=1`**

Same pattern. Empty state copy:

```tsx
{discounts.length === 0 && !loading ? (
  <EmptyState
    title="No discounts yet"
    detail="Create promo codes or automatic discounts to drive sales."
    actionLabel="Create your first discount"
    actionHref="?new=1"
  />
) : null}
```

- [ ] **Step 8: tax/page.tsx — EmptyState + `?new=1`**

Tax uses `setShowRegionForm`. Same `?new=1` pattern (substitute the setter name). Empty state copy:

```tsx
{regions.length === 0 && !loading ? (
  <EmptyState
    title="No tax regions yet"
    detail="Configure tax rules so the right rates apply at checkout."
    actionLabel="Add a tax region"
    actionHref="?new=1"
  />
) : null}
```

- [ ] **Step 9: purchase-orders/page.tsx — EmptyState + `?new=1`**

Uses `setShowCreate`. Same pattern. Empty state copy:

```tsx
{purchaseOrders.length === 0 && !loading ? (
  <EmptyState
    title="No purchase orders yet"
    detail="Track inventory restocks from suppliers."
    actionLabel="Create a purchase order"
    actionHref="?new=1"
  />
) : null}
```

(The exact list-state variable in this file may be named differently — verify with `grep "useState.*PurchaseOrder\|setRows\|setItems"` and use whatever the file already calls the list.)

- [ ] **Step 10: Verify build and smoke-test**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -10
```

Expected: `✓ Compiled successfully`. In a browser:

- Open New Entry menu, click "Create Customer" → URL becomes `/customers?new=1` and the create-customer modal opens.
- Same for Channel, Discount.
- Visit a list page with no data — see the new EmptyState with CTA.
- Click the CTA → URL gains `?new=1` and the create form/modal opens on the same page.

- [ ] **Step 11: Commit**

```bash
git add 'apps/admin-web/src/app/(main)/customers/page.tsx' \
        'apps/admin-web/src/app/(main)/customers/[id]/page.tsx' \
        'apps/admin-web/src/app/(main)/orders/page.tsx' \
        'apps/admin-web/src/app/(main)/ecommerce-orders/page.tsx' \
        'apps/admin-web/src/app/(main)/suppliers/page.tsx' \
        'apps/admin-web/src/app/(main)/channels/page.tsx' \
        'apps/admin-web/src/app/(main)/discounts/page.tsx' \
        'apps/admin-web/src/app/(main)/tax/page.tsx' \
        'apps/admin-web/src/app/(main)/purchase-orders/page.tsx'
git commit -m "feat(admin-web): standardise empty states with CTAs + ?new=1 deep-link wiring"
```

---

## Task 9: Full rebuild + smoke matrix + push

- [ ] **Step 1: Run full backend test suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest /app/tests/ -q 2>&1 | tail -6
docker compose exec api rm -rf /app/tests
```

Expected: same pass rate as before this phase (no regression). The only backend change in this phase was additive (two new fields).

- [ ] **Step 2: Full rebuild**

```bash
docker compose down && docker compose up --build -d 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -8
sleep 12
docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

Expected: all containers Up, admin-web `✓ Compiled successfully`.

- [ ] **Step 3: Smoke matrix**

In a browser at `http://localhost:3100`:

**As `retail`:**
- Dashboard shows "Open Purchase Orders" card → links to `/purchase-orders`
- Recent Activity link reads "View purchase orders" → `/purchase-orders`
- New Entry menu shows: Create Product, Create Customer, Create Shop (3 items)
- Header search hidden on `/overview`, present on `/products` (placeholder "Search products...")

**As `online`:**
- Dashboard shows "Pending Online Orders" card → links to `/ecommerce-orders`
- Recent Activity link reads "View online orders"
- New Entry menu shows: Create Product, Create Customer, Create Channel, Create Discount (4 items)

**As `hybrid`:**
- Dashboard same as online (Pending Online Orders)
- New Entry menu shows all 5 items: Product, Customer, Shop, Channel, Discount

**Settings page:**
- Notifications, Security, Appearance sections are gone
- Business Type switcher still works
- Other sections unchanged

**Search & deep-link flow:**
- Type in header search on /products → URL gains `?q=...` → list filters → refresh preserves filter
- Click "Create Channel" in New Entry menu → /channels?new=1 → create form auto-opens
- Visit a tenant with no discounts → EmptyState with "Create your first discount" CTA → click → /discounts?new=1 → form opens

- [ ] **Step 4: Push**

```bash
git push origin main
```

---

## Self-review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Q1 — Delete Notifications/Security/Appearance + 9 unused state hooks | Task 5 |
| Q2 — Backend `pending_ecommerce_order_count` + `business_type` on summary | Task 1 |
| Q2 — Type-aware dashboard card + recent-activity link | Task 6 |
| Q3 — `search-context.tsx` config map | Task 3 |
| Q3 — Header search reads pathname, debounces URL push | Task 4 |
| Q3 — 6 pages migrate from local `q` to URL param | Task 7 |
| Q9 — `EmptyState` extended with optional CTA | Task 2 |
| Q9 — Overview empty-state copy rewrites | Task 6 |
| Q9 — 4 list-page empty-state additions/rewrites (orders, ecommerce-orders, customers/[id], + the 5 with new EmptyState) | Task 8 |
| Q10 — Type-aware New Entry menu (5 items, filtered by type) | Task 4 |
| Q10 — `?new=1` deep-link receivers on customers/channels/discounts/tax/suppliers/purchase-orders | Task 8 |

**Placeholder scan:** None present.

**Type consistency:**
- `BusinessType` ("online" | "retail" | "hybrid") used identically across `business-type-context.tsx`, AppShell `NEW_ENTRY_ITEMS`, overview `pendingCard` derivation
- `PageSearchConfig` shape consistent across `search-context.tsx` definition and `HeaderSearch` consumer
- `EmptyState` extended-prop names (`actionLabel`, `actionHref`) used identically in primitives.tsx and every consumer site
- `?new=1` query-param convention consistent across dispatching (`AppShell` New Entry items, EmptyState `actionHref`) and receiving sites (the `useEffect` in 6 pages)
- Backend response field names (`pending_ecommerce_order_count`, `business_type`) consistent between the Pydantic model, the SQL query, the return statement, and the frontend `DashboardSummary` TS type

# Dashboard Setup Checklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-guided onboarding checklist card to the admin dashboard that shows new merchants exactly what to do next, filtered by their business type, and disappears once all items are complete.

**Architecture:** Five new boolean fields are added to the existing `dashboard-summary` backend endpoint (no new endpoint). The overview page — already a Server Component that fetches this endpoint — computes which checklist items are visible and unchecked, then conditionally renders a new `SetupChecklist` Server Component above the stat cards. When all items are done the card simply isn't rendered; no client state or dismiss mechanism needed.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.x (backend); Next.js 15 Server Components / TypeScript / Tailwind / Material Symbols (frontend). No frontend test framework — validation via `docker compose up --build` and manual smoke test.

---

## Codebase context

### Backend — `services/api/app/routers/admin_web.py`

- `DashboardSummaryOut` (line ~330): the response model
- `dashboard_summary()` (line ~344): the endpoint function
- Already imported models: `Order`, `Product`, `PurchaseOrder`, `Shop`, `Supplier`, `Tenant`, `Transaction`, `User`
- **Missing imports needed:** `Channel`, `TenantEmailConfig` — add to the existing `from app.models import (...)` block

**Channel model** (`channels` table):
- `Channel.tenant_id`, `Channel.type` (str: "pos", "headless", "shopify", "woocommerce", "manual"), `Channel.status`, `Channel.config` (JSONB)
- Payment check: `Channel.config["payment_provider"].as_string().isnot(None)` — PostgreSQL returns NULL for `config->>'payment_provider'` when key doesn't exist

**TenantEmailConfig model** (`tenant_email_configs` table):
- `TenantEmailConfig.tenant_id`, `TenantEmailConfig.is_active` (bool)

### Frontend — overview page (current state)
- `apps/admin-web/src/app/(main)/overview/page.tsx`
- Pure Server Component (async function, no "use client")
- Single fetch: `serverJsonGet<DashboardSummary>("/v1/admin/dashboard-summary")`
- Already has `businessType` and `pendingCard` derivation from polish week
- Already imports `Link` from `next/link`

### Deploy patterns
```bash
# Backend hot-reload:
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/routers/admin_web.py $CONTAINER:/app/app/routers/admin_web.py
docker compose restart api && sleep 5

# Frontend (full rebuild required for Server Components):
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
```

---

## File map

| File | Status | Change |
|---|---|---|
| `services/api/app/routers/admin_web.py` | MODIFY | 5 new fields on `DashboardSummaryOut`; 5 queries + 2 new imports in `dashboard_summary()` |
| `apps/admin-web/src/components/dashboard/SetupChecklist.tsx` | NEW | Pure Server Component — checklist card |
| `apps/admin-web/src/app/(main)/overview/page.tsx` | MODIFY | Extended type; `SETUP_ITEMS` array; compute visible items; conditional `<SetupChecklist>` |

---

## Task 1: Backend — 5 new boolean fields on dashboard-summary

**Files:**
- Modify: `services/api/app/routers/admin_web.py`

- [ ] **Step 1: Add Channel and TenantEmailConfig to the model imports**

Find the `from app.models import (` block (around line 23). Add `Channel` and `TenantEmailConfig` to the list:

```python
from app.models import (
    Channel,
    Order,
    Product,
    ProductGroup,
    PurchaseOrder,
    Role,
    Shop,
    StockAdjustment,
    StockMovement,
    Supplier,
    Tenant,
    TenantEmailConfig,
    Transaction,
    TransactionLine,
    User,
)
```

- [ ] **Step 2: Add 5 fields to `DashboardSummaryOut`**

Find `class DashboardSummaryOut(BaseModel):` (around line 330). It ends with `recent_activity: list[RecentActivityItem]`. Add these 5 fields before `recent_activity`:

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
    has_first_product: bool = False
    has_first_shop: bool = False
    has_first_channel: bool = False
    has_payment_configured: bool = False
    has_email_configured: bool = False
    recent_activity: list[RecentActivityItem]
```

- [ ] **Step 3: Add 5 queries inside `dashboard_summary()`**

Find the block after `pending_ecommerce_order_count` and `business_type` are computed (these were added in Phase 3). Add immediately after `business_type = tenant_row.business_type if tenant_row else "retail"`:

```python
    # Setup checklist booleans
    has_first_product = product_count > 0
    has_first_shop = shop_count > 0

    has_first_channel = bool(db.execute(
        select(func.count())
        .select_from(Channel)
        .where(
            Channel.tenant_id == tenant_id,
            Channel.type != "pos",
            Channel.status == "active",
        )
    ).scalar_one())

    has_payment_configured = bool(db.execute(
        select(func.count())
        .select_from(Channel)
        .where(
            Channel.tenant_id == tenant_id,
            Channel.config["payment_provider"].as_string().isnot(None),
        )
    ).scalar_one())

    has_email_configured = bool(db.execute(
        select(func.count())
        .select_from(TenantEmailConfig)
        .where(
            TenantEmailConfig.tenant_id == tenant_id,
            TenantEmailConfig.is_active.is_(True),
        )
    ).scalar_one())
```

- [ ] **Step 4: Add 5 fields to the return statement**

Find `return DashboardSummaryOut(...)`. Add the 5 new values alongside the existing ones:

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
        has_first_product=has_first_product,
        has_first_shop=has_first_shop,
        has_first_channel=has_first_channel,
        has_payment_configured=has_payment_configured,
        has_email_configured=has_email_configured,
        recent_activity=items,
    )
```

- [ ] **Step 5: Verify syntax and deploy**

```bash
python3 -c "import ast; ast.parse(open('services/api/app/routers/admin_web.py').read()); print('OK')"
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/routers/admin_web.py $CONTAINER:/app/app/routers/admin_web.py
docker compose restart api && sleep 5
docker compose logs api --tail=5
```

Expected: `OK` from AST check; clean restart with no errors.

- [ ] **Step 6: Run existing tests (no regressions)**

```bash
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest /app/tests/ -q --tb=no 2>&1 | tail -4
docker compose exec api rm -rf /app/tests
```

Expected: same pass count as before (529+), only the pre-existing failure in `test_app_updates.py`.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/routers/admin_web.py
git commit -m "feat(api): add setup checklist booleans to dashboard-summary"
```

---

## Task 2: Create SetupChecklist Server Component

**Files:**
- Create: `apps/admin-web/src/components/dashboard/SetupChecklist.tsx`

- [ ] **Step 1: Create the file**

```tsx
import Link from "next/link";

export interface ChecklistItem {
  key: string;
  label: string;
  detail: string;
  href: string;
  icon: string;
  done: boolean;
}

interface Props {
  items: ChecklistItem[];
  tenantPrefix: string;
}

export function SetupChecklist({ items, tenantPrefix }: Props) {
  const doneCount = items.filter((i) => i.done).length;
  const total = items.length;

  return (
    <div className="rounded-2xl border border-primary/20 bg-primary/5 p-6">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="font-headline text-lg font-bold text-on-surface">Get started</h2>
          <p className="mt-0.5 text-xs text-on-surface-variant">
            {doneCount} of {total} steps complete
          </p>
        </div>
        {/* Progress bar */}
        <div className="flex h-2 w-32 overflow-hidden rounded-full bg-outline-variant/20">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${(doneCount / total) * 100}%` }}
          />
        </div>
      </div>

      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.key}
            className={`flex items-center gap-4 rounded-xl px-4 py-3 transition-colors ${
              item.done
                ? "opacity-50"
                : "bg-surface-container-lowest shadow-sm"
            }`}
          >
            {/* Icon */}
            <span
              className={`material-symbols-outlined text-[22px] shrink-0 ${
                item.done ? "text-on-surface-variant" : "text-primary"
              }`}
              aria-hidden="true"
            >
              {item.done ? "check_circle" : item.icon}
            </span>

            {/* Text */}
            <div className="min-w-0 flex-1">
              <p className={`text-sm font-semibold ${item.done ? "text-on-surface-variant line-through" : "text-on-surface"}`}>
                {item.label}
              </p>
              <p className="mt-0.5 text-xs text-on-surface-variant">{item.detail}</p>
            </div>

            {/* Action */}
            {!item.done && (
              <Link
                href={`${tenantPrefix}${item.href}`}
                className="shrink-0 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-on-primary hover:opacity-90"
              >
                Start →
              </Link>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
```

Expected: `✓ Compiled successfully`.

- [ ] **Step 3: Commit**

```bash
git add apps/admin-web/src/components/dashboard/SetupChecklist.tsx
git commit -m "feat(admin-web): add SetupChecklist server component"
```

---

## Task 3: Wire checklist into the overview page

**Files:**
- Modify: `apps/admin-web/src/app/(main)/overview/page.tsx`

- [ ] **Step 1: Add the SetupChecklist import**

At the top of the file, after the existing imports, add:

```tsx
import { SetupChecklist, type ChecklistItem } from "@/components/dashboard/SetupChecklist";
```

- [ ] **Step 2: Extend the DashboardSummary type**

Find `type DashboardSummary = { ... }` at the top. Add the 5 new optional fields:

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
  has_first_product?: boolean;
  has_first_shop?: boolean;
  has_first_channel?: boolean;
  has_payment_configured?: boolean;
  has_email_configured?: boolean;
  recent_activity: Array<{ kind: string; ref_id: string; created_at: string; detail: string }>;
};
```

- [ ] **Step 3: Add SETUP_ITEMS definition inside the component function**

Inside `OverviewPage()`, after the existing `pendingCard` derivation, add:

```tsx
  type SetupItemDef = {
    key: string;
    label: string;
    detail: string;
    href: string;
    icon: string;
    types: ("online" | "retail" | "hybrid")[];
    done: boolean;
  };

  const allSetupItems: SetupItemDef[] = [
    {
      key: "first_product",
      label: "Add your first product",
      detail: "Products are what you sell — add at least one to get started.",
      href: "/entries",
      icon: "category",
      types: ["online", "retail", "hybrid"],
      done: d.has_first_product ?? false,
    },
    {
      key: "first_shop",
      label: "Add a shop",
      detail: "Shops are your physical locations. Your cashier app uses shops to manage sales.",
      href: "/shops/new",
      icon: "storefront",
      types: ["retail", "hybrid"],
      done: d.has_first_shop ?? false,
    },
    {
      key: "first_channel",
      label: "Set up a sales channel",
      detail: "Channels connect your inventory to storefronts and other selling surfaces.",
      href: "/channels?new=1",
      icon: "hub",
      types: ["online", "hybrid"],
      done: d.has_first_channel ?? false,
    },
    {
      key: "payment",
      label: "Configure a payment provider",
      detail: "Connect Stripe or Razorpay to start accepting payments at checkout.",
      href: "/channels",
      icon: "credit_card",
      types: ["online", "hybrid"],
      done: d.has_payment_configured ?? false,
    },
    {
      key: "email",
      label: "Configure email",
      detail: "Send order confirmations and receipts to your customers.",
      href: "/settings",
      icon: "mail",
      types: ["online", "retail", "hybrid"],
      done: d.has_email_configured ?? false,
    },
  ];

  // Filter by business type, sort unchecked first, derive tenantPrefix from request URL
  const bt = (d.business_type ?? "retail") as "online" | "retail" | "hybrid";
  const visibleSetupItems: ChecklistItem[] = allSetupItems
    .filter((item) => item.types.includes(bt))
    .sort((a, b) => Number(a.done) - Number(b.done));
  const anyUnchecked = visibleSetupItems.some((item) => !item.done);
```

- [ ] **Step 4: Add tenantPrefix derivation**

The `SetupChecklist` component needs `tenantPrefix` to build correct hrefs. The overview page is a Server Component in Next.js App Router. Add this near the top of the function body (before the data fetches or after imports inside the function):

```tsx
  // Derive tenant prefix from the URL if running under a tenant slug route.
  // The layout or URL pattern provides this; fall back to "" for direct routes.
  // In this project the layout already handles this; pass empty string here and
  // let Link resolve relative to the current origin.
  const tenantPrefix = "";
```

Note: If the project uses tenant-prefixed routes (e.g. `/acme/overview`), the layout handles the prefix and `<Link href="/entries">` resolves correctly without an explicit prefix in a Server Component. Confirm this works in the smoke test; if not, pass the prefix from `params` if the route is dynamic.

- [ ] **Step 5: Insert the conditional SetupChecklist in the JSX**

Find the start of the `return (...)` block. After the title/subtitle `<div>` and **before** the bento stat cards `<div className="grid grid-cols-1 gap-6 md:grid-cols-3">`, insert:

```tsx
      {/* Setup checklist — shown only when any item is unchecked */}
      {anyUnchecked && (
        <SetupChecklist items={visibleSetupItems} tenantPrefix={tenantPrefix} />
      )}
```

The final layout order in the return is:
1. Title div
2. `{anyUnchecked && <SetupChecklist ... />}` ← new
3. Bento stat cards grid
4. Revenue chart
5. Archive Totals + Recent Activity

- [ ] **Step 6: Verify build and smoke test**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
```

Expected: `✓ Compiled successfully`.

In a browser at `http://localhost:3100`:

**New tenant (no products, no channels, no email):**
- Checklist card appears above the stat cards
- Items are filtered by business type
- Unchecked items show the "Start →" button; done items are dimmed with a strikethrough
- Progress bar shows 0/N or partial progress

**Add a product (via `/entries`) and reload the dashboard:**
- "Add your first product" item is now checked (dimmed, strikethrough)
- It has moved to the bottom of the list
- Progress bar advances

**Once all items are done:**
- The checklist card disappears entirely (the `{anyUnchecked && ...}` gate returns false)
- Dashboard shows the clean stat cards view

- [ ] **Step 7: Commit**

```bash
git add 'apps/admin-web/src/app/(main)/overview/page.tsx'
git commit -m "feat(admin-web): type-aware setup checklist on dashboard, dismisses when all done"
```

---

## Task 4: Full rebuild + push

- [ ] **Step 1: Run backend tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest /app/tests/ -q --tb=no 2>&1 | tail -4
docker compose exec api rm -rf /app/tests
```

Expected: 529+ passed, 1 pre-existing failure only.

- [ ] **Step 2: Full stack rebuild**

```bash
docker compose down && docker compose up --build -d 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
sleep 12
docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

Expected: all containers Up, admin-web `✓ Compiled successfully`.

- [ ] **Step 3: Push**

```bash
git push origin main
```

---

## Self-review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `Channel` and `TenantEmailConfig` imported in admin_web.py | Task 1 |
| 5 new fields on `DashboardSummaryOut` | Task 1 |
| `has_first_product = product_count > 0` | Task 1 |
| `has_first_shop = shop_count > 0` | Task 1 |
| `has_first_channel` — non-pos active channel count | Task 1 |
| `has_payment_configured` — JSONB key check on Channel.config | Task 1 |
| `has_email_configured` — TenantEmailConfig is_active check | Task 1 |
| New `SetupChecklist` Server Component | Task 2 |
| Card shows "X of Y steps complete" header | Task 2 |
| Progress bar | Task 2 |
| Unchecked items show "Start →" link; checked items dimmed with strikethrough | Task 2 |
| `DashboardSummary` type extended with 5 optional booleans | Task 3 |
| `SETUP_ITEMS` with 5 items, each with `types` and `done` | Task 3 |
| Filter by `businessType`, sort unchecked first | Task 3 |
| `{anyUnchecked && <SetupChecklist>}` — card absent when all done | Task 3 |
| Checklist above stat cards in layout | Task 3 |

**Placeholder scan:** None.

**Type consistency:**
- `ChecklistItem` interface defined in `SetupChecklist.tsx`, imported in `overview/page.tsx` for the `visibleSetupItems` type ✅
- `tenantPrefix: string` prop on `SetupChecklist` — passed from overview page as `""` ✅
- `done: boolean` on `ChecklistItem` matches how it's computed: `d.has_first_product ?? false` ✅
- 5 field names consistent across model, query variable names, return statement, TS type, and item `done` accessors ✅

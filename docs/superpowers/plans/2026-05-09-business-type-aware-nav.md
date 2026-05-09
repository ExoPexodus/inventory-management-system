# Business-Type-Aware Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat 22-item admin sidebar with a 7-group collapsible structure that hides items irrelevant to the merchant's business type (online/retail/hybrid), and fix the broken business-type switcher in settings.

**Architecture:** Add a `BusinessTypeProvider` React context that fetches `GET /v1/admin/tenant-settings/business-type` once on app shell mount and caches the result in `localStorage`. AppShell consumes the context and filters/groups nav items by combining the existing permission gate with new business-type flags. A new `RequiresBusinessType` wrapper provides soft route guards on hidden pages. The existing settings business-type form has its broken URL fixed and triggers a context cache invalidation after successful switch.

**Tech Stack:** Next.js 15, React 19 (client components), TypeScript, Tailwind CSS, Material Symbols icons. No frontend test framework exists in this repo — validation is via manual smoke test after `docker compose up --build`.

---

## Codebase context

### Existing patterns to follow
- **React contexts** already established: `lib/auth/user-context.tsx`, `lib/currency-context.tsx`, `lib/localisation-context.tsx`. Each is a `"use client"` file exporting a Provider + hook. Follow this exact shape.
- **Permission gate** uses `useHasPermission(permKey)` from `@/lib/auth/user-context`. Reuse — don't reimplement.
- **AppShell** in `apps/admin-web/src/components/dashboard/AppShell.tsx` is the single point that renders the sidebar. It already filters `NAV` by permission. We extend it with type filtering and grouping.
- **Settings page** at `apps/admin-web/src/app/(main)/settings/page.tsx` already has business-type form state (`businessType`, `btLoading`, `btSaving`, `btMsg`, `btErr`) — we fix the URL and improve messages, do not rebuild the form.

### Current bug to fix
Both fetches in settings use `/api/ims/v1/admin/business-type` — the real endpoint is `/api/ims/v1/admin/tenant-settings/business-type`. Two locations:
- GET around line 258 in `settings/page.tsx`
- POST around line 310 in `settings/page.tsx`

### Backend response shape (production-ready, no changes)
```json
{
  "business_type": "online" | "retail" | "hybrid",
  "show_shops_management": boolean,
  "show_pos_features": boolean,
  "show_ecommerce_features": boolean,
  "can_add_physical_store": boolean,
  "can_add_online_channel": boolean
}
```

### Manual deploy + smoke-test pattern
Frontend changes need `docker compose up --build -d` (not `restart`) because admin-web compiles at build time:

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
docker compose logs admin-web --tail=10
```

---

## File map

| File | Status | Responsibility |
|---|---|---|
| `apps/admin-web/src/lib/business-type-context.tsx` | NEW | Provider, hook, localStorage cache, `invalidate()` function |
| `apps/admin-web/src/components/dashboard/RequiresBusinessType.tsx` | NEW | Soft route guard component |
| `apps/admin-web/src/components/dashboard/NavGroup.tsx` | NEW | Collapsible group row in sidebar |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | MODIFY | Wrap in provider; replace flat NAV with grouped+filtered structure |
| `apps/admin-web/src/app/(main)/settings/page.tsx` | MODIFY | Fix two broken URLs; invalidate context after save; improve messages |
| `apps/admin-web/src/app/(main)/shifts/page.tsx` | MODIFY | Wrap in `RequiresBusinessType types={["retail","hybrid"]}` |
| `apps/admin-web/src/app/(main)/inventory-pools/page.tsx` | MODIFY | Wrap in `RequiresBusinessType types={["online","hybrid"]}` |
| `apps/admin-web/src/app/(main)/channels/page.tsx` | MODIFY | Wrap in `RequiresBusinessType types={["online","hybrid"]}` |
| `apps/admin-web/src/app/(main)/ecommerce-orders/page.tsx` | MODIFY | Wrap in `RequiresBusinessType types={["online","hybrid"]}` |
| `apps/admin-web/src/app/(main)/ecommerce/page.tsx` | MODIFY | Wrap in `RequiresBusinessType types={["online","hybrid"]}` |

---

## Task 1: Create BusinessTypeContext

**Files:**
- Create: `apps/admin-web/src/lib/business-type-context.tsx`

- [ ] **Step 1: Write the file**

```tsx
"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type BusinessType = "online" | "retail" | "hybrid";

export interface BusinessTypeFlags {
  business_type: BusinessType;
  show_shops_management: boolean;
  show_pos_features: boolean;
  show_ecommerce_features: boolean;
  can_add_physical_store: boolean;
  can_add_online_channel: boolean;
}

interface BusinessTypeState {
  flags: BusinessTypeFlags | null;
  loading: boolean;
  invalidate: () => void;
}

const DEFAULT_STATE: BusinessTypeState = {
  flags: null,
  loading: true,
  invalidate: () => undefined,
};

const BusinessTypeContext = createContext<BusinessTypeState>(DEFAULT_STATE);

const CACHE_KEY = "business-type-flags";

function readCache(): BusinessTypeFlags | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as BusinessTypeFlags;
    if (parsed && typeof parsed.business_type === "string") return parsed;
    return null;
  } catch {
    return null;
  }
}

function writeCache(flags: BusinessTypeFlags): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(flags));
  } catch {
    // ignore quota errors
  }
}

function clearCache(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(CACHE_KEY);
  } catch {
    // ignore
  }
}

export function BusinessTypeProvider({ children }: { children: ReactNode }) {
  const cached = useMemo(readCache, []);
  const [flags, setFlags] = useState<BusinessTypeFlags | null>(cached);
  const [loading, setLoading] = useState<boolean>(cached === null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/api/ims/v1/admin/tenant-settings/business-type");
        if (!res.ok) return;
        const data = (await res.json()) as BusinessTypeFlags;
        if (cancelled) return;
        setFlags(data);
        writeCache(data);
      } catch {
        // network error — keep cached value if any
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [version]);

  const invalidate = useCallback(() => {
    clearCache();
    setVersion((v) => v + 1);
  }, []);

  const value = useMemo<BusinessTypeState>(() => ({ flags, loading, invalidate }), [flags, loading, invalidate]);

  return <BusinessTypeContext.Provider value={value}>{children}</BusinessTypeContext.Provider>;
}

export function useBusinessType(): BusinessTypeState {
  return useContext(BusinessTypeContext);
}

/** Helper for filtering nav items: returns true when the user's type matches one of `allowed`. */
export function typeAllows(flags: BusinessTypeFlags | null, allowed: BusinessType[]): boolean {
  if (!flags) return true; // permissive while loading; AppShell renders skeleton
  return allowed.includes(flags.business_type);
}
```

- [ ] **Step 2: Type check**

```bash
cd apps/admin-web && npx tsc --noEmit src/lib/business-type-context.tsx 2>&1 | head -20 && cd -
```

Expected: clean output.

- [ ] **Step 3: Commit**

```bash
git add apps/admin-web/src/lib/business-type-context.tsx
git commit -m "feat(admin-web): add BusinessTypeProvider context with localStorage cache"
```

---

## Task 2: Create RequiresBusinessType soft route guard

**Files:**
- Create: `apps/admin-web/src/components/dashboard/RequiresBusinessType.tsx`

- [ ] **Step 1: Write the file**

```tsx
"use client";

import Link from "next/link";
import { ReactNode } from "react";
import { BusinessType, useBusinessType, typeAllows } from "@/lib/business-type-context";

interface Props {
  types: BusinessType[];
  children: ReactNode;
}

export function RequiresBusinessType({ types, children }: Props) {
  const { flags, loading } = useBusinessType();

  // While loading: render a neutral placeholder so we don't flash a guard message
  if (loading && !flags) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-on-surface-variant">
        Loading…
      </div>
    );
  }

  if (typeAllows(flags, types)) {
    return <>{children}</>;
  }

  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-outline-variant/30 bg-surface-container-low px-8 py-16 text-center">
      <span className="material-symbols-outlined text-5xl text-on-surface-variant/40" aria-hidden="true">
        block
      </span>
      <h2 className="font-headline text-lg font-bold text-on-surface">
        Not part of your current setup
      </h2>
      <p className="max-w-md text-sm text-on-surface-variant">
        This feature is available for {types.join(" or ")} businesses. Switch your business type from settings to enable it.
      </p>
      <Link
        href="/settings"
        className="mt-2 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-on-primary hover:opacity-90"
      >
        Open Settings →
      </Link>
    </div>
  );
}
```

- [ ] **Step 2: Type check**

```bash
cd apps/admin-web && npx tsc --noEmit 2>&1 | head -10 && cd -
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/admin-web/src/components/dashboard/RequiresBusinessType.tsx
git commit -m "feat(admin-web): add RequiresBusinessType soft route guard"
```

---

## Task 3: Create NavGroup component

**Files:**
- Create: `apps/admin-web/src/components/dashboard/NavGroup.tsx`

- [ ] **Step 1: Write the file**

```tsx
"use client";

import Link from "next/link";
import { useState } from "react";

export interface NavItem {
  href: string;
  label: string;
  icon: string;
}

interface Props {
  label: string;
  items: NavItem[];
  activePath: string;
  tenantPrefix: string;
  initiallyExpanded: boolean;
  onToggle: (expanded: boolean) => void;
}

export function NavGroup({ label, items, activePath, tenantPrefix, initiallyExpanded, onToggle }: Props) {
  const [expanded, setExpanded] = useState(initiallyExpanded);
  if (items.length === 0) return null;

  const handleToggle = () => {
    setExpanded((prev) => {
      const next = !prev;
      onToggle(next);
      return next;
    });
  };

  return (
    <div className="space-y-0.5">
      <button
        type="button"
        onClick={handleToggle}
        className="flex w-full items-center justify-between rounded-md px-4 py-1.5 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant/70 hover:text-on-surface-variant"
      >
        <span>{label}</span>
        <span
          className={`material-symbols-outlined text-[16px] transition-transform ${expanded ? "rotate-90" : ""}`}
          aria-hidden="true"
        >
          chevron_right
        </span>
      </button>
      {expanded && items.map((item) => {
        const active = activePath === item.href;
        return (
          <Link
            key={item.href}
            href={`${tenantPrefix}${item.href}`}
            className={`flex items-center gap-3 rounded-lg px-4 py-2.5 text-[13px] transition-colors duration-150 ${
              active
                ? "bg-primary/10 font-bold text-primary"
                : "font-medium text-on-surface-variant hover:bg-surface-container-lowest/60 hover:text-on-surface"
            }`}
          >
            <span className={`material-symbols-outlined text-[20px] leading-none ${active ? "" : "opacity-70"}`} aria-hidden="true">
              {item.icon}
            </span>
            {item.label}
          </Link>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Type check**

```bash
cd apps/admin-web && npx tsc --noEmit 2>&1 | head -10 && cd -
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/admin-web/src/components/dashboard/NavGroup.tsx
git commit -m "feat(admin-web): add collapsible NavGroup component"
```

---

## Task 4: Rewrite AppShell to use grouped, type-aware nav

**Files:**
- Modify: `apps/admin-web/src/components/dashboard/AppShell.tsx`

- [ ] **Step 1: Replace the flat NAV array with grouped structure and type-filter logic**

The full AppShell file currently uses a flat `NAV` array. Replace it with a grouped structure. Edit the file to:

1. Add imports at the top (after existing imports):

```tsx
import { BusinessTypeProvider, useBusinessType, typeAllows, BusinessType } from "@/lib/business-type-context";
import { NavGroup, NavItem } from "@/components/dashboard/NavGroup";
```

2. Replace the existing flat `NAV` array (lines ~91-114) with:

```tsx
type NavItemDef = NavItem & {
  permission: string | null;
  allowedTypes: BusinessType[];   // empty = all types
};

const ALL_TYPES: BusinessType[] = ["online", "retail", "hybrid"];

const HOME: NavItemDef = {
  href: "/overview", label: "Dashboard", icon: "dashboard", permission: null, allowedTypes: ALL_TYPES,
};

interface NavGroupDef {
  label: string;
  items: NavItemDef[];
}

const NAV_GROUPS: NavGroupDef[] = [
  {
    label: "Sell",
    items: [
      { href: "/orders",          label: "Orders",         icon: "receipt_long", permission: "sales:read",     allowedTypes: ["retail", "hybrid"] },
      { href: "/ecommerce-orders",label: "E-comm Orders",  icon: "orders",       permission: "orders:manage",  allowedTypes: ["online", "hybrid"] },
      { href: "/channels",        label: "Channels",       icon: "storefront",   permission: "channels:manage", allowedTypes: ["online", "hybrid"] },
      { href: "/discounts",       label: "Discounts",      icon: "local_offer",  permission: "discounts:read", allowedTypes: ALL_TYPES },
      { href: "/tax",             label: "Tax",            icon: "receipt",      permission: "tax:manage",     allowedTypes: ALL_TYPES },
    ],
  },
  {
    label: "Catalog",
    items: [
      { href: "/products",        label: "Products",       icon: "category",      permission: "catalog:read",     allowedTypes: ALL_TYPES },
      { href: "/purchase-orders", label: "Purchase Orders",icon: "shopping_bag",  permission: "procurement:read", allowedTypes: ALL_TYPES },
      { href: "/suppliers",       label: "Suppliers",      icon: "local_shipping",permission: "procurement:read", allowedTypes: ALL_TYPES },
    ],
  },
  {
    label: "Stock",
    items: [
      { href: "/inventory",       label: "Inventory",       icon: "inventory_2",     permission: "inventory:read",         allowedTypes: ALL_TYPES },
      { href: "/inventory-pools", label: "Inventory Pools", icon: "layers",          permission: "inventory_pools:manage", allowedTypes: ["online", "hybrid"] },
      { href: "/reconciliation",  label: "Reconciliation",  icon: "account_balance", permission: "operations:read",        allowedTypes: ["retail", "hybrid"] },
    ],
  },
  {
    label: "Insights",
    items: [
      { href: "/analytics",       label: "Analytics",       icon: "analytics",       permission: "analytics:read", allowedTypes: ALL_TYPES },
      { href: "/reports",         label: "Reports",         icon: "description",     permission: "reports:read",   allowedTypes: ALL_TYPES },
      { href: "/audit",           label: "Audit Log",       icon: "policy",          permission: "audit:read",     allowedTypes: ALL_TYPES },
    ],
  },
  {
    label: "People",
    items: [
      { href: "/team",            label: "Team",            icon: "groups",          permission: "staff:read",      allowedTypes: ALL_TYPES },
      { href: "/shifts",          label: "Shifts",          icon: "event_note",      permission: "operations:read", allowedTypes: ["retail", "hybrid"] },
    ],
  },
  {
    label: "Setup",
    items: [
      { href: "/ecommerce",       label: "E-commerce",      icon: "shopping_cart",   permission: "settings:read",     allowedTypes: ["online", "hybrid"] },
      { href: "/integrations",    label: "Integrations",    icon: "hub",             permission: "integrations:read", allowedTypes: ALL_TYPES },
      { href: "/billing",         label: "Billing",         icon: "payments",        permission: "settings:read",     allowedTypes: ALL_TYPES },
      { href: "/apps",            label: "Get Apps",        icon: "install_mobile",  permission: "settings:read",     allowedTypes: ALL_TYPES },
      { href: "/settings",        label: "Settings",        icon: "settings",        permission: "settings:read",     allowedTypes: ALL_TYPES },
    ],
  },
];

const EXPANDED_GROUPS_KEY = "nav-expanded-groups";

function readExpandedGroups(): Record<string, boolean> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(EXPANDED_GROUPS_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as Record<string, boolean>;
  } catch {
    return {};
  }
}

function writeExpandedGroups(state: Record<string, boolean>): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(EXPANDED_GROUPS_KEY, JSON.stringify(state));
  } catch {
    // ignore
  }
}
```

3. Rename the existing exported `AppShell` to `AppShellInner` and add a new exported `AppShell` that wraps with the provider:

```tsx
export function AppShell({ children, current }: { children: ReactNode; current?: string }) {
  return (
    <BusinessTypeProvider>
      <AppShellInner current={current}>{children}</AppShellInner>
    </BusinessTypeProvider>
  );
}

function AppShellInner({ children, current }: { children: ReactNode; current?: string }) {
  // ... existing AppShell body (notifications, panel, etc.)
```

4. Inside `AppShellInner`, replace the `visibleNav` calculation and the `<nav>` block.

Replace this old code:
```tsx
const hasPermission = useHasPermission;
const visibleNav = NAV.filter((item) => !item.permission || hasPermission(item.permission));
```

With:
```tsx
const { flags, loading: btLoading } = useBusinessType();
const hasPermission = useHasPermission;

// Compute which group contains the active page (for default expand)
const activeGroupLabel = NAV_GROUPS.find((g) =>
  g.items.some((i) => i.href === activePath)
)?.label ?? null;

const filterItem = (item: NavItemDef): boolean => {
  if (item.permission && !hasPermission(item.permission)) return false;
  return typeAllows(flags, item.allowedTypes);
};

const homeVisible = filterItem(HOME);
const visibleGroups = NAV_GROUPS
  .map((g) => ({ ...g, items: g.items.filter(filterItem) }))
  .filter((g) => g.items.length > 0);

const expandedFromStorage = typeof window !== "undefined" ? readExpandedGroups() : {};
const handleGroupToggle = (label: string, expanded: boolean) => {
  const next = { ...readExpandedGroups(), [label]: expanded };
  writeExpandedGroups(next);
};
const isExpanded = (label: string): boolean => {
  if (label === activeGroupLabel) return true;
  if (label in expandedFromStorage) return Boolean(expandedFromStorage[label]);
  return label === "Sell"; // default
};
```

Replace the existing `<nav>` block (which renders `visibleNav.map(...)`) with:

```tsx
<nav className="flex-1 space-y-2 overflow-y-auto px-3 pb-2">
  {btLoading && !flags ? (
    <div className="space-y-1.5 px-1">
      {[0,1,2,3,4,5].map((i) => (
        <div key={i} className="h-9 animate-pulse rounded-lg bg-surface-container-lowest/60" />
      ))}
    </div>
  ) : (
    <>
      {homeVisible && (
        <div className="space-y-0.5">
          <Link
            href={`${tenantPrefix}${HOME.href}`}
            className={`flex items-center gap-3 rounded-lg px-4 py-2.5 text-[13px] transition-colors duration-150 ${
              activePath === HOME.href
                ? "bg-primary/10 font-bold text-primary"
                : "font-medium text-on-surface-variant hover:bg-surface-container-lowest/60 hover:text-on-surface"
            }`}
          >
            <span className={`material-symbols-outlined text-[20px] leading-none ${activePath === HOME.href ? "" : "opacity-70"}`} aria-hidden="true">
              {HOME.icon}
            </span>
            {HOME.label}
          </Link>
        </div>
      )}
      {visibleGroups.map((g) => (
        <NavGroup
          key={g.label}
          label={g.label}
          items={g.items}
          activePath={activePath}
          tenantPrefix={tenantPrefix}
          initiallyExpanded={isExpanded(g.label)}
          onToggle={(expanded) => handleGroupToggle(g.label, expanded)}
        />
      ))}
    </>
  )}
</nav>
```

- [ ] **Step 2: Type check & build**

```bash
cd apps/admin-web && npx tsc --noEmit 2>&1 | head -20 && cd -
```

Expected: no errors. If errors mention `Link` or `useHasPermission`, those imports already exist — leave them.

- [ ] **Step 3: Build admin-web container**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
```

Expected: `✓ Compiled successfully`.

- [ ] **Step 4: Smoke test**

Open `http://localhost:3100` in a browser. Log in. Verify:
- Sidebar shows "Dashboard" pinned at top
- Below Dashboard: 6 group headers (Sell, Catalog, Stock, Insights, People, Setup)
- "Sell" is expanded by default; others are collapsed
- Click a group header — it expands/collapses
- The group containing the current page is auto-expanded

- [ ] **Step 5: Commit**

```bash
git add apps/admin-web/src/components/dashboard/AppShell.tsx
git commit -m "feat(admin-web): replace flat sidebar with 7-group business-type-aware nav"
```

---

## Task 5: Fix settings page broken business-type URL

**Files:**
- Modify: `apps/admin-web/src/app/(main)/settings/page.tsx`

- [ ] **Step 1: Fix both broken URLs**

In `apps/admin-web/src/app/(main)/settings/page.tsx`, find the GET fetch (around line 258):

```tsx
const r = await fetch("/api/ims/v1/admin/business-type");
```

Replace with:

```tsx
const r = await fetch("/api/ims/v1/admin/tenant-settings/business-type");
```

Find the POST fetch (around line 310):

```tsx
const r = await fetch("/api/ims/v1/admin/business-type", {
```

Replace with:

```tsx
const r = await fetch("/api/ims/v1/admin/tenant-settings/business-type", {
```

- [ ] **Step 2: Add cache invalidation after successful save**

At the top of the file with other imports, add:

```tsx
import { useBusinessType } from "@/lib/business-type-context";
```

Inside the component, near other hooks at the top, add:

```tsx
const { invalidate: invalidateBusinessType } = useBusinessType();
```

In `handleSaveBusinessType`, find the success branch (where `setBtMsg("Business type saved.")` is called). Replace it so the saved type drives a friendlier message and triggers cache invalidation:

```tsx
if (r.ok) {
  // Invalidate the cached flags so the sidebar updates immediately.
  invalidateBusinessType();
  if (businessType === "hybrid") {
    setBtMsg("Hybrid mode active — both POS and ecommerce features are now available in the sidebar.");
  } else if (businessType === "online") {
    setBtMsg("Switched to online-only. Existing POS data is preserved; you can switch back anytime.");
  } else {
    setBtMsg("Switched to retail. Ecommerce sections are hidden; existing data is preserved and can be restored anytime.");
  }
}
```

- [ ] **Step 3: Type check**

```bash
cd apps/admin-web && npx tsc --noEmit 2>&1 | head -10 && cd -
```

Expected: no errors.

- [ ] **Step 4: Rebuild and smoke test**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -3
```

Then in a browser:
1. Open Settings → find the Business Type form
2. Open browser DevTools Network tab
3. Save the form — confirm the POST goes to `/api/ims/v1/admin/tenant-settings/business-type` and returns 200 (not 404)
4. Confirm the sidebar updates immediately to reflect the new type without a page reload
5. Confirm the success message reflects the new type

- [ ] **Step 5: Commit**

```bash
git add apps/admin-web/src/app/\(main\)/settings/page.tsx
git commit -m "fix(admin-web): use correct URL for business-type endpoint, invalidate context, type-aware messages"
```

---

## Task 6: Wrap hidden pages in RequiresBusinessType

**Files:**
- Modify: `apps/admin-web/src/app/(main)/shifts/page.tsx`
- Modify: `apps/admin-web/src/app/(main)/inventory-pools/page.tsx`
- Modify: `apps/admin-web/src/app/(main)/channels/page.tsx`
- Modify: `apps/admin-web/src/app/(main)/ecommerce-orders/page.tsx`
- Modify: `apps/admin-web/src/app/(main)/ecommerce/page.tsx`

Each page in this codebase has a default export — usually a function. We wrap by renaming the original function and exporting a new default that wraps it.

- [ ] **Step 1: Wrap shifts/page.tsx**

At the top of `apps/admin-web/src/app/(main)/shifts/page.tsx`, add this import (preserve existing imports):

```tsx
import { RequiresBusinessType } from "@/components/dashboard/RequiresBusinessType";
```

Find the existing `export default function` (e.g. `export default function ShiftsPage()`). Rename it (drop `export default`):

```tsx
function ShiftsPageInner() {
  // ... existing body unchanged
}

export default function ShiftsPage() {
  return (
    <RequiresBusinessType types={["retail", "hybrid"]}>
      <ShiftsPageInner />
    </RequiresBusinessType>
  );
}
```

- [ ] **Step 2: Wrap inventory-pools/page.tsx**

Same edit pattern. Import `RequiresBusinessType`, rename the original default export to `InventoryPoolsPageInner`, and add:

```tsx
export default function InventoryPoolsPage() {
  return (
    <RequiresBusinessType types={["online", "hybrid"]}>
      <InventoryPoolsPageInner />
    </RequiresBusinessType>
  );
}
```

- [ ] **Step 3: Wrap channels/page.tsx**

```tsx
export default function ChannelsPage() {
  return (
    <RequiresBusinessType types={["online", "hybrid"]}>
      <ChannelsPageInner />
    </RequiresBusinessType>
  );
}
```

- [ ] **Step 4: Wrap ecommerce-orders/page.tsx**

```tsx
export default function EcommerceOrdersPage() {
  return (
    <RequiresBusinessType types={["online", "hybrid"]}>
      <EcommerceOrdersPageInner />
    </RequiresBusinessType>
  );
}
```

- [ ] **Step 5: Wrap ecommerce/page.tsx**

```tsx
export default function EcommercePage() {
  return (
    <RequiresBusinessType types={["online", "hybrid"]}>
      <EcommercePageInner />
    </RequiresBusinessType>
  );
}
```

- [ ] **Step 6: Type check**

```bash
cd apps/admin-web && npx tsc --noEmit 2>&1 | head -20 && cd -
```

Expected: no errors. If a page's existing default function name conflicts with what you renamed it to, adjust accordingly — keep the inner name unique to the file.

- [ ] **Step 7: Commit**

```bash
git add apps/admin-web/src/app/\(main\)/shifts/page.tsx \
        apps/admin-web/src/app/\(main\)/inventory-pools/page.tsx \
        apps/admin-web/src/app/\(main\)/channels/page.tsx \
        apps/admin-web/src/app/\(main\)/ecommerce-orders/page.tsx \
        apps/admin-web/src/app/\(main\)/ecommerce/page.tsx
git commit -m "feat(admin-web): wrap business-type-restricted pages in RequiresBusinessType guard"
```

---

## Task 7: End-to-end smoke test + push

- [ ] **Step 1: Full rebuild**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
sleep 5
docker compose logs admin-web --tail=10
```

Expected: `✓ Compiled successfully`, no runtime errors.

- [ ] **Step 2: Manual matrix test**

Open `http://localhost:3100` in a browser. Use the Settings page to switch business type and verify each scenario:

**As `online`:**
- Sidebar groups visible: Sell (4 items), Catalog (3), Stock (2 — no Reconciliation), Insights (3), People (1 — no Shifts), Setup (5 incl E-commerce)
- Direct nav to `/shifts` → renders the "Not part of your current setup" guard with link to settings
- Direct nav to `/reconciliation` → renders the guard

**As `retail`:**
- Sidebar groups: Sell (3 — no E-comm Orders, no Channels), Catalog (3), Stock (2 — no Inventory Pools), Insights (3), People (2), Setup (4 — no E-commerce)
- Direct nav to `/channels` → guard renders
- Direct nav to `/ecommerce-orders` → guard renders
- Direct nav to `/inventory-pools` → guard renders
- Direct nav to `/ecommerce` → guard renders

**As `hybrid`:**
- All groups show their full item set: Sell (5), Catalog (3), Stock (3), Insights (3), People (2), Setup (5)
- All previously-guarded pages render normally

- [ ] **Step 3: Push**

```bash
git push origin main
```

---

## Self-review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `BusinessTypeProvider` + `useBusinessType` hook | Task 1 |
| `localStorage` cache + invalidation | Task 1 |
| `typeAllows` helper | Task 1 |
| Soft route guard component | Task 2 |
| Collapsible group rendering | Task 3 |
| 7-group nav structure | Task 4 |
| Item filtering: permission AND type | Task 4 (`filterItem`) |
| "Sell" expanded by default | Task 4 (`isExpanded`) |
| Group containing active page auto-expanded | Task 4 (`activeGroupLabel`) |
| Per-session expand state in localStorage | Task 4 (`EXPANDED_GROUPS_KEY`) |
| Skeleton during initial load | Task 4 (`btLoading && !flags`) |
| Settings URL bug fix (GET + POST) | Task 5 |
| Cache invalidation after switch | Task 5 |
| Type-aware switch messages | Task 5 |
| Wrap shifts, inventory-pools, channels, ecommerce-orders, ecommerce | Task 6 |
| End-to-end matrix verification | Task 7 |

**Placeholder scan:** None present.

**Type consistency:**
- `BusinessType` ("online" | "retail" | "hybrid") used identically across context, route guard, AppShell, and pages
- `BusinessTypeFlags` matches the backend response shape exactly
- `NavItem` interface is shared between `NavGroup.tsx` and `AppShell.tsx` (imported)
- `typeAllows(flags, allowed)` signature consistent in both context and AppShell consumers
- `invalidate()` exported from context, used by settings page

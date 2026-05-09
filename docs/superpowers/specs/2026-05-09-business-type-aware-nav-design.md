# Business-Type-Aware Navigation Design Spec

**Date:** 2026-05-09
**Status:** Approved
**Phase:** 1 of 6 (UI declutter roadmap)

---

## Problem

The admin-web sidebar shows a flat list of 22 nav items to every operator regardless of their business type. Items are gated only by RBAC permissions, never by what the merchant actually does. An online-only store sees `Shifts` and `Reconciliation`; a retail-only store sees `Channels` and `E-comm Orders`. Non-technical users get overwhelmed at first glance, and demo prospects see clutter that doesn't match their use case.

The backend already has a complete `business_type` framework (`online | retail | hybrid`) with a flag-matrix endpoint at `GET /v1/admin/tenant-settings/business-type`. The frontend never picked it up — and the existing settings UI to switch types calls a wrong URL (`/v1/admin/business-type`), so the switch is silently broken.

---

## Goals

1. Hide nav items not relevant to the merchant's business type.
2. Group the remaining items into 7 collapsible sections that map to merchant mental models, so even hybrid (the densest case) feels structured.
3. Fix the broken business-type switcher URL in settings.
4. Add soft route guards so direct-URL access to hidden pages shows a friendly message instead of broken state.

---

## Non-goals

- Per-page UX audit & click-reduction (Phase 2)
- Onboarding picker for new tenants (Phase 4)
- Dashboard redesign (Phase 3)
- Guided walkthroughs (Phase 5)
- Cross-page command palette (Phase 6)

---

## Backend (already production-ready, no changes needed)

```
GET  /v1/admin/tenant-settings/business-type
     → { business_type, show_shops_management, show_pos_features,
         show_ecommerce_features, can_add_physical_store, can_add_online_channel }

POST /v1/admin/tenant-settings/business-type
     { business_type: "online" | "retail" | "hybrid" }
     → BusinessTypeOut

POST /v1/admin/setup/enable-physical-store
     → BusinessTypeOut  (online → hybrid upgrade)
```

Default value of `tenants.business_type` is `"retail"`, NOT NULL. Every existing and new tenant has a definite type, so the frontend never has to handle null.

---

## Frontend changes

### Data flow

A new `BusinessTypeContext` is provided by `AppShell`. On mount:

1. Read cached value from `localStorage` keyed `business-type:{tenant_id}` — render immediately if present
2. Fetch `GET /v1/admin/tenant-settings/business-type` in the background
3. Update context + cache when fetch resolves

If no cache exists (first login), show a sidebar skeleton during the ~150ms initial fetch — no flash of full sidebar followed by collapse.

The settings page invalidates this cache after a successful switch and triggers an immediate refetch so the sidebar updates without a page reload.

### Nav structure

Seven collapsible groups. "Home" pinned at the top with no group header.

| Group | Items | Visibility |
|---|---|---|
| **Home** (pinned, no header) | Dashboard | all |
| **Sell** | Orders (POS) | retail, hybrid |
| | E-comm Orders | online, hybrid |
| | Channels | online, hybrid |
| | Discounts | all |
| | Tax | all |
| **Catalog** | Products | all |
| | Purchase Orders | all |
| | Suppliers | all |
| **Stock** | Inventory | all |
| | Inventory Pools | online, hybrid |
| | Reconciliation | retail, hybrid |
| **Insights** | Analytics | all |
| | Reports | all |
| | Audit Log | all |
| **People** | Team | all |
| | Shifts | retail, hybrid |
| **Setup** | E-commerce | online, hybrid |
| | Integrations | all |
| | Billing | all |
| | Get Apps | all |
| | Settings | all |

**Per-type totals:**

| Type | Total visible | Per-group counts |
|---|---|---|
| online | 16 | Sell 4, Catalog 3, Stock 2, Insights 3, People 1, Setup 5 |
| retail | 16 | Sell 3, Catalog 3, Stock 2, Insights 3, People 2, Setup 4 |
| hybrid | 19 | Sell 5, Catalog 3, Stock 3, Insights 3, People 2, Setup 5 |

### Group expand/collapse rules

- The group containing the currently active page is auto-expanded
- One group's expanded state persists per session in `localStorage` (key: `nav-expanded-groups`)
- "Sell" is expanded by default for new sessions (most-visited)

### Filtering rule

A nav item renders only when **both** gates pass:

```
visible = hasPermission(item.permission) AND typeAllows(item, businessType)
```

The two gates are independent. A retail tenant with `staff:read` sees Team; the same tenant without `staff:read` doesn't, regardless of type.

### Soft route guards

Direct URL access to a page that the user's business type doesn't allow (bookmark, pasted URL) renders a friendly state via a new `<RequiresBusinessType>` wrapper:

> *"This feature isn't part of your current setup. [Switch your business type →]"*

The link points to settings. Backend RLS and permission checks still enforce real boundaries — no data is exposed to clients who shouldn't see it. The wrapper is purely UX.

### Settings page fixes

- **Bug fix:** change URL from `/v1/admin/business-type` to `/v1/admin/tenant-settings/business-type` (both GET and POST)
- After a successful POST, invalidate `BusinessTypeContext` cache and refetch — sidebar updates immediately
- Show a toast on switch:
  - **online → hybrid** or **retail → hybrid**: *"Hybrid mode active — you'll see both POS and ecommerce features in the sidebar."*
  - **hybrid → online** or **hybrid → retail**: *"Switched. Your existing data is preserved; hidden sections can be restored anytime by switching back."*

---

## Files

| File | Change |
|---|---|
| `apps/admin-web/src/lib/business-type-context.tsx` | New — `BusinessTypeProvider`, `useBusinessType()` hook, localStorage cache, invalidate function |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | Wrap children in provider; replace flat `NAV` array with grouped structure; render collapsible sections; filter by type+permission |
| `apps/admin-web/src/components/dashboard/RequiresBusinessType.tsx` | New — soft route guard component |
| `apps/admin-web/src/app/(main)/settings/page.tsx` | Fix URL; invalidate context after switch; add toasts |
| `apps/admin-web/src/app/(main)/shifts/page.tsx` | Wrap export in `RequiresBusinessType types={["retail","hybrid"]}` |
| `apps/admin-web/src/app/(main)/inventory-pools/page.tsx` | Wrap export in `RequiresBusinessType types={["online","hybrid"]}` |
| `apps/admin-web/src/app/(main)/channels/page.tsx` | Wrap export in `RequiresBusinessType types={["online","hybrid"]}` |
| `apps/admin-web/src/app/(main)/ecommerce-orders/page.tsx` | Wrap export in `RequiresBusinessType types={["online","hybrid"]}` |
| `apps/admin-web/src/app/(main)/ecommerce/page.tsx` | Wrap export in `RequiresBusinessType types={["online","hybrid"]}` |

---

## What does NOT change

- Backend `business_type` API or model
- RBAC permission checks
- Existing pages' internal layouts
- Tenant default value (`"retail"`)
- Backend RLS enforcement

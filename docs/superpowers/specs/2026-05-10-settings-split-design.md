# Settings Split Design Spec

**Date:** 2026-05-10
**Status:** Approved
**Phase:** UI declutter / L1

---

## Problem

The Settings page is 805 lines and contains 7 completely unrelated concerns on a single vertical scroll. Non-technical users frequently can't find settings without scrolling past everything else. It's the last obviously cluttered page a demo prospect encounters.

---

## Goals

1. Settings Index is a clean card grid — one card per concern, one click to the focused form.
2. Each sub-page is small, focused, and has a breadcrumb back to the index.
3. The dashboard setup checklist "Configure email" item deep-links to `/settings/email` (not the generic settings page).
4. No logic changes — form state, API calls, and validation move unchanged into the new files.

---

## Non-goals

- Changing any form logic, API calls, or validation within the settings sections
- Adding settings that don't exist today
- Mobile-specific layout changes

---

## Index page

`apps/admin-web/src/app/(main)/settings/page.tsx` — **rewritten** as a grid index.

**Seven setting cards:**

| Card label | Icon | Description | Route |
|---|---|---|---|
| Email | `mail` | Configure SMTP or SendGrid for notifications | `/settings/email` |
| Currency | `payments` | Set your default currency and symbol | `/settings/currency` |
| Localisation | `language` | Timezone and financial year start | `/settings/localisation` |
| Devices | `devices` | POS device security and session timeouts | `/settings/devices` |
| Reconciliation | `account_balance` | Auto-resolve thresholds for shifts | `/settings/reconciliation` |
| Customer Groups | `groups` | Manage customer segment labels | `/settings/customer-groups` |
| Business Type | `storefront` | Switch between online, retail, or hybrid | `/settings/business-type` |

**Danger zone** — rendered below the grid on the index page itself (not a sub-page). Red-bordered section with the existing destructive actions.

---

## Sub-pages

Seven new `page.tsx` files. Each is the section extracted from the monolith with a `<Breadcrumbs>` header added. All form logic, state, and API calls move unchanged.

```
apps/admin-web/src/app/(main)/settings/
  page.tsx                    ← rewritten: index grid + danger zone
  email/page.tsx              ← extracted: email provider form
  currency/page.tsx           ← extracted: currency display section
  localisation/page.tsx       ← extracted: timezone + FY month form
  devices/page.tsx            ← extracted: device security form
  reconciliation/page.tsx     ← extracted: reconciliation thresholds form
  customer-groups/page.tsx    ← extracted: customer groups CRUD
  business-type/page.tsx      ← extracted: business type switcher
```

Each sub-page starts with:
```tsx
<Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "<Section Name>" }]} />
<PageHeader kicker="Settings" title="<Section Name>" subtitle="<one-liner>" />
```

---

## Navigation updates

### AppShell sidebar
No change — `/settings` already in `ROOT_ROUTES` and the nav item. Sub-routes resolve correctly within the existing tenant-prefix stripping.

### Dashboard setup checklist (`apps/admin-web/src/app/(main)/overview/page.tsx`)
The `email` item in `allSetupItems` currently has `href: "/settings"`. Update to `href: "/settings/email"`.

---

## Files

| File | Status |
|---|---|
| `apps/admin-web/src/app/(main)/settings/page.tsx` | REWRITE — index grid + danger zone |
| `apps/admin-web/src/app/(main)/settings/email/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/settings/currency/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/settings/localisation/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/settings/devices/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/settings/reconciliation/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/settings/customer-groups/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/settings/business-type/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/overview/page.tsx` | MODIFY — email href |

---

## Spec self-review

**Placeholder scan:** None.

**Consistency:** All 7 sub-routes match their card hrefs. Danger zone stays on index. Breadcrumb pattern is the same across all 7 sub-pages. ✅

**Scope:** 8 frontend files + 1 link update. No backend changes. Right-sized. ✅

**Ambiguity:**
- "Logic moves unchanged" — means copy the exact `useState`, `useEffect`, fetch calls, and JSX form body. Only the outer page wrapper and breadcrumb are new. ✅
- "Danger zone on index" — rendered after the card grid, separated by a `<hr>` or spacing. ✅

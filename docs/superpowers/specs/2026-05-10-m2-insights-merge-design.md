# M2 — Merge Analytics + Reports → Insights Design

**Date:** 2026-05-10
**Phase:** Audit M2 (~1-2 days)

## Problem
Analytics (charts dashboard) and Reports (CSV export hub) are two separate sidebar items but they're conceptually related ("data about your business"). Merchants wonder where to look — and the smaller list page would benefit from being co-located.

## Solution
- New page at `/insights` with two tabs: **Dashboard** (analytics charts) and **Reports** (CSV export grid).
- Remove `/analytics` and `/reports` from the sidebar nav. Add a single "Insights" item in their place.
- Old routes (`/analytics`, `/reports`) are deleted — anyone with a stale bookmark gets a 404; minor cost since these aren't deep-linked from setup checklist or anywhere else.

## Files
| File | Status |
|---|---|
| `apps/admin-web/src/app/(main)/insights/page.tsx` | NEW — two-tab page |
| `apps/admin-web/src/app/(main)/analytics/page.tsx` | DELETE — content moves into insights tab |
| `apps/admin-web/src/app/(main)/reports/page.tsx` | DELETE — content moves into insights tab |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | Replace Analytics+Reports nav items with a single "Insights" item; add `"insights"` to `ROOT_ROUTES` |
| `apps/admin-web/src/lib/search-context.tsx` | Add `"insights"` to `ROOT_ROUTES` (same set, separate file) |

## Layout
```
/insights
  ├── PageHeader (kicker: Insights, title: Insights, subtitle: ...)
  ├── Tabs: [ Dashboard | Reports ]
  ├── Tab content:
  │     - Dashboard: existing analytics charts
  │     - Reports: existing reports CSV grid
```

## Implementation
The cleanest approach is to copy the JSX bodies of the two existing pages into helper components (`<DashboardTab />` and `<ReportsTab />`) inside the new `insights/page.tsx` file. State and handlers move with the JSX. Since the two old files are deleted afterwards, there's no duplication concern.

## Out of scope
Cross-section linking (e.g. "Export this chart as CSV") — keep them as parallel views for now.

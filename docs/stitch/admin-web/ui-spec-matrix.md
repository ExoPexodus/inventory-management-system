# UI spec matrix (Stitch → React)

Derived from the seven Stitch exports (light desktop, primary `#2C3E50`, warm background `#fbf9f4`, Manrope/Public Sans family, rounded cards).

## Tokens (target)

| Token | Stitch / notes |
|-------|----------------|
| Background page | `#fbf9f4` |
| Surface / card | white with subtle border `#2C3E50` ~15% |
| Primary text | `#2C3E50` |
| Muted text | `#2C3E50` at ~60–80% opacity |
| Radius | `rounded-lg` / `rounded-xl` |
| Spacing | generous sections (`py-8`, `gap-6`), dense tables |
| Typography | strong page title, section labels (uppercase/small), tabular nums for money |
| App frame | left rail + thin top utility strip + large content canvas |

## Component mapping

| Stitch pattern | `apps/admin-web` component |
|----------------|----------------------------|
| Top app bar + utility strip | `components/dashboard/AppShell` |
| KPI stat tiles | `components/ui/primitives.tsx::StatTile` |
| Section cards | `components/ui/primitives.tsx::Panel` |
| Data tables | per-screen table blocks inside `Panel` |
| Status chips | `components/ui/primitives.tsx::Badge` |
| Filter row | `TextInput` + `SelectInput` primitives |
| Sidebar nav | `components/dashboard/AppShell` |
| Charts (analytics) | simple CSS bars + tabular grid in analytics route |

## Screen → data modules

| Screen | Primary API (MVP) |
|--------|-------------------|
| Executive overview | `GET /v1/admin/dashboard-summary` |
| Order audit | `GET /v1/admin/transactions` |
| Supplier hub | `GET/POST /v1/admin/suppliers` (+ `status`,`q` filters) |
| Analytics | `GET /v1/admin/analytics/sales-series` |
| New entry hub | `POST /v1/admin/products`, `POST /v1/admin/shops`, `GET/POST /v1/admin/product-groups` |
| Inventory ledger | `GET /v1/admin/inventory/movements` |
| Staff & permissions | `GET/PATCH /v1/admin/operators` (+ `role`,`q` filters) |

## Tenant scope policy

- All admin-web screens are tenant-implicit from operator JWT context.
- Tenant selectors are intentionally removed from UI.
- API rejects cross-tenant requests even when a different `tenant_id` is provided.

## Desktop parity QA checklist (latest pass)

| Route | Block order parity | Data parity | State parity | Notes |
|------|---------------------|------------|--------------|-------|
| `/overview` | near-match | complete | complete | KPI + activity hierarchy restored; deeper decorative styling still possible |
| `/orders` | near-match | complete | complete | filter row, status chips, cursor paging, tax context included |
| `/suppliers` | near-match | complete | complete | add/list + search/status filtering implemented |
| `/analytics` | partial-match | complete | complete | chart type is simplified bars (not full Stitch chart treatment) |
| `/entries` | near-match | complete | complete | creation flows for shop/product/group/variant active |
| `/inventory` | near-match | complete | complete | stock snapshot + movement journal + filters + cursor paging |
| `/staff` | near-match | complete | complete | role filter/search + active toggle feedback present |

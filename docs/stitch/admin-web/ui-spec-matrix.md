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

## Component mapping

| Stitch pattern | `apps/admin-web` component |
|----------------|----------------------------|
| Top app bar + search | `DashboardShell` + `TopBar` |
| KPI stat tiles | `components/dashboard/StatTile` |
| Section cards | `components/ui/Card` |
| Data tables | `components/ui/DataTable` |
| Status chips | `components/ui/Badge` |
| Filter row | `components/ui/FilterBar` |
| Sidebar nav | `DashboardNav` |
| Charts (analytics) | simple SVG/CSS bars or placeholder + API series |

## Screen → data modules

| Screen | Primary API (MVP) |
|--------|-------------------|
| Executive overview | `GET /v1/admin/dashboard-summary` |
| Order audit | `GET /v1/transactions` (existing) |
| Supplier hub | `GET/POST /v1/admin/suppliers` |
| Analytics | `GET /v1/admin/analytics/sales-series` |
| New entry hub | `POST /v1/admin/products`, `POST /v1/shops`, supplier create, etc. |
| Inventory ledger | `GET /v1/admin/inventory/movements` |
| Staff & permissions | `GET/PATCH /v1/admin/operators` |

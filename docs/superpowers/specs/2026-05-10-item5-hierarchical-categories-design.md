# Item 5 — Hierarchical Category Table Design

**Date:** 2026-05-10
**Phase:** Stickerize onboarding (~3-4 days)

## Problem
`Product.category` is a flat `String(128)` field. No hierarchy, no per-product multi-membership, no metadata. Stickerize and other catalogs with nested categories ("Anime → Shounen → …") need real category modelling.

## Locked decisions (from brainstorm)
- **Many-to-many** product↔category via join table
- **Drop legacy `Product.category` column** after migrating values into the new system
- **Storefront parent category page** lists products from category AND all descendants
- **Metadata:** name, slug, parent_id, description, sort_order. **No image field.**

## Schema

### `categories` (new)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK → tenants(id) CASCADE | indexed |
| parent_id | UUID FK → categories(id) SET NULL | nullable; indexed |
| slug | String(128) | unique within tenant |
| name | String(255) | |
| description | Text | nullable |
| sort_order | Integer default 0 | within siblings |
| created_at, updated_at | timestamptz | |

Composite unique: `(tenant_id, slug)`.

### `product_categories` (new join)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK | for RLS |
| product_id | UUID FK → products(id) CASCADE | |
| category_id | UUID FK → categories(id) CASCADE | |
| created_at | timestamptz | |

Composite unique: `(product_id, category_id)`. Indexes on both FKs.

### Migration `20260527000001_categories.py`
1. Create both tables.
2. For each tenant: group existing non-null `Product.category` strings; create one `Category` row per unique value (slug = slugified name; fallback `name-{shortuuid}` on collision); insert `product_categories` rows mapping each product to its category.
3. Drop `Product.category` column.

## Backend

### New router `services/api/app/routers/admin_categories.py`

```
GET    /v1/admin/categories                  → flat list (frontend builds tree)
POST   /v1/admin/categories                  → create { name, slug?, parent_id?, description?, sort_order? }
PATCH  /v1/admin/categories/{id}             → update name | description | parent_id | sort_order | slug
DELETE /v1/admin/categories/{id}             → delete; children get parent_id = NULL (orphaned to root)
POST   /v1/admin/categories/reorder          → batch [{ id, sort_order }]
PUT    /v1/admin/products/{id}/categories    → replace { category_ids: [...] }
GET    /v1/admin/products/{id}/categories    → list current category_ids
```

Validation:
- Slug auto-generated from name if not provided; ASCII-only `[a-z0-9-]+`.
- Cannot set `parent_id` to self or any descendant (cycle prevention).
- All operations scoped by tenant.

### Storefront — `services/api/app/routers/storefront/catalog.py`

**New endpoint:**
```
GET /v1/storefront/categories
  → list[{ id, slug, name, parent_id, description, sort_order }]
```
Channel-scoped via `X-Channel-Id`. Returns ALL categories for the tenant (frontend builds tree).

**Extend `/v1/storefront/products`:**
- New optional param `category_slug: str | None`
- When set: load all categories for tenant, find the one with matching slug, collect IDs of itself + all descendants (recursive in Python), filter products via `product_categories.product_id IN ...`
- Works alongside existing tags[] / price / sort filters

### Admin product create/edit — `services/api/app/routers/admin_web.py`

`POST /v1/admin/products` and `PATCH /v1/admin/products/{id}` gain optional `category_ids: list[UUID]`. When provided, replace the product's category set. The legacy `category` body field is removed (after migration drops the column).

Admin product list `ProductListItem` response gains `category_slugs: list[str]` (computed from joins). The legacy `category: str` field is removed.

## Frontend

### New admin page — `apps/admin-web/src/app/(main)/categories/page.tsx`

Tree view of categories with:
- Expand/collapse for parents
- Inline rename
- "Add child" button per category
- Reorder via up/down arrows (sort_order tiebreaker)
- Delete (with confirm — children become orphans/roots)
- Edit description (modal)

### AppShell sidebar
Add "Categories" item under Catalog group. All business types. Permission `catalog:read`.

### Product list — `apps/admin-web/src/app/(main)/products/page.tsx`
- Replace any UI references to `product.category` (string) with `product.category_slugs` (list — render as badge chips)
- Add a "Categories" link/button per row that opens a `CategoriesModal` (next item below)

### New modal — `CategoriesModal` (inline in products/page.tsx)
Manages a product's category memberships. Multi-select tree picker (checkbox per category). Save calls `PUT /v1/admin/products/{id}/categories`.

### Storefront SDK
- `packages/storefront-sdk/src/types.ts` — add `StorefrontCategory` type
- `packages/storefront-sdk/src/client.ts` — add `listCategories()` method; extend `listProducts` params to accept `categorySlug?: string`

## Files
| File | Status |
|---|---|
| `services/api/app/models/tables.py` | Add `Category`, `ProductCategory` models; remove `Product.category` field |
| `services/api/app/models/__init__.py` | Export new models |
| `services/api/alembic/versions/20260527000001_categories.py` | NEW migration |
| `services/api/app/routers/admin_categories.py` | NEW router |
| `services/api/app/main.py` | Register new router |
| `services/api/app/routers/storefront/catalog.py` | Add `/categories` endpoint; extend product list with `category_slug` param |
| `services/api/app/routers/admin_web.py` | Update product create/edit/list to use category_ids |
| `apps/admin-web/src/app/(main)/categories/page.tsx` | NEW tree view |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | Add Categories nav item |
| `apps/admin-web/src/app/(main)/products/page.tsx` | Replace category string usage; add CategoriesModal |
| `packages/storefront-sdk/src/types.ts` | Add `StorefrontCategory` |
| `packages/storefront-sdk/src/client.ts` | Add `listCategories()`, extend `listProducts` |

## Out of scope
- Drag-and-drop reordering (use up/down arrows for v1)
- Category-level SEO meta tags (description suffices)
- Multi-tenant moves (categories tied to tenant_id, not movable)

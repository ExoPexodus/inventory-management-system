# Item 6 — Admin Product List Pagination Design

**Date:** 2026-05-10
**Phase:** Stickerize onboarding (~½ day)

## Problem
`GET /v1/admin/products` returns ALL products in one response (no pagination). At 800 products that's a ~600 KB JSON payload on every admin `/products` page load — inefficient and won't scale past a few thousand.

## Solution
1. **Backend:** wrap the response in `{ items, total, page, per_page }` (matching storefront pattern). Add `page`, `per_page`, `tags[]` query params. Existing `q`/`status`/`category` continue to work unchanged.
2. **Frontend:** add pagination controls; adapt the existing fetch + state to the new wrapped response.

## Backend changes — `services/api/app/routers/admin_web.py`

```python
class ProductListResponse(BaseModel):
    items: list[ProductListItem]
    total: int
    page: int
    per_page: int

@router.get("/products", response_model=ProductListResponse, ...)
def admin_list_products(
    ctx, db,
    q: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None,
    tags: list[str] | None = Query(default=None, alias="tags[]"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
):
    # build base_where, count total separately, paginate the rows
```

Tag filter mirrors the storefront pattern from earlier today: OR-match using PostgreSQL JSONB `?` operator per tag.

## Frontend changes — `apps/admin-web/src/app/(main)/products/page.tsx`

- New state: `page` (number), `total` (number), `perPage` (constant = 50)
- Update `fetchProducts` to:
  - Send `page` + `per_page` query params
  - Parse `{ items, total }` from response
  - Set both `rows` and `total`
- Add pagination controls below the table — "Page N of M · X products" + Prev/Next buttons
- Reset `page = 1` when filters change

## Files
| File | Status |
|---|---|
| `services/api/app/routers/admin_web.py` | Wrap response, add 3 query params |
| `apps/admin-web/src/app/(main)/products/page.tsx` | Adapt fetch + add pagination UI |

## Out of scope
- Cursor-based pagination (offset is fine at this scale)
- Server-side sorting (current sort is alphabetical by name; sufficient for now)

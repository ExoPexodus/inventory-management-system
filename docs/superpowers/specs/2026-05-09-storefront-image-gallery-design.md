# Storefront Image Gallery Design Spec

**Date:** 2026-05-09
**Status:** Approved

---

## Problem

`StorefrontProductOut.image_url` was returning `null` because it read from `products.image_url` — a legacy column never written by any real user action. Merchants upload images through the R2 gallery flow, which writes to `product_images`, not `products.image_url`. The quick fix (fallback to `product.images[0]`) works but leaves a two-source-of-truth problem. More importantly, the storefront has no way to return the full image gallery for a product detail page.

---

## Goals

1. Product list returns a single thumbnail URL efficiently (no N+1, no over-fetching).
2. Product detail returns the full ordered gallery array for carousels and multi-photo views.
3. `products.image_url` is silently treated as a legacy fallback — never shown to merchants, never requires migration.

---

## Design

### Response shape

`StorefrontProductOut` gains one new field:

```
image_url: str | None           — primary image URL, always present (list + detail)
images:    list[Image] | None   — full gallery, null in list, populated in detail
```

`Image` shape:
```json
{ "url": "https://...", "alt_text": "...", "sort_order": 0 }
```

`image_url` resolution priority: `products.image_url` → first gallery image → `null`. This ensures the legacy field acts as an explicit override if ever set, while the gallery drives real content.

---

### List endpoint — `GET /v1/storefront/products`

Uses a **correlated scalar subquery** to fetch the first gallery image URL alongside each product in a single SQL round-trip. No `selectinload`, no extra queries per product.

```sql
SELECT products.*,
       (SELECT url FROM product_images
        WHERE product_id = products.id
        ORDER BY sort_order ASC, created_at ASC
        LIMIT 1) AS first_image_url
FROM products
WHERE tenant_id = :tid AND status = 'active'
ORDER BY name
LIMIT :lim OFFSET :off
```

`_to_out` receives `(product, first_image_url: str | None)`. Returns `images = null`.

---

### Detail endpoint — `GET /v1/storefront/products/{slug_or_id}`

Single product fetch — `selectinload(Product.images)` is correct here (one product, all its images in one extra query). Returns the full `images` array sorted by `sort_order ASC`. `image_url` is still populated as `images[0].url` for backward compat.

---

### `products.image_url` (legacy column)

- **Not removed** — no migration needed.
- **Not exposed** in any merchant admin UI or edit form.
- **Used only as a silent fallback** in the priority chain: if set, it overrides the gallery. In practice this only affects demo-seed products.

---

## Files changed

| File | Change |
|------|--------|
| `services/api/app/routers/storefront/catalog.py` | Add `StorefrontImageOut` model; add `images` field to `StorefrontProductOut`; replace list selectinload with correlated subquery; update `_to_out` signature; update detail to populate gallery |
| `services/api/tests/routers/test_storefront_catalog.py` | Tests covering list returns `images=null`, detail returns full gallery, `image_url` fallback chain |

---

## What does NOT change

- `products.image_url` DB column — stays, no migration
- `product_images` table — unchanged
- Admin catalog API — unchanged
- Storefront SDK `StorefrontProduct` type — gains optional `images` field (additive, backward compatible)

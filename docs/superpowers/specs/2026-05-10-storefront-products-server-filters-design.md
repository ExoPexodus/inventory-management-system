# Storefront Products — Server-Side Filtering Design

**Date:** 2026-05-10
**Source:** Brief from Stickerize storefront team forwarded by user

## Problem
`GET /v1/storefront/products` has no tag, price, or sort filtering. Storefronts with 800+ products have to fetch the full catalog (≈800 KB) and filter client-side. Pagination is impossible because the filter happens after the fact. The SDK already forwards the new params; the storefront feature flag flips on the moment the API supports them.

## Endpoint changes — all optional, all backward compatible

`GET /v1/storefront/products` gains:

| Param | Type | Effect |
|---|---|---|
| `tags[]` | repeated string | OR match — product passes if `product.tags` contains ANY of the provided values. Case-sensitive. |
| `min_price_cents` | int | `unit_price_cents >= min_price_cents` |
| `max_price_cents` | int | `unit_price_cents <= max_price_cents` |
| `sort_by` | enum | `created_at` (default), `unit_price_cents`, `name`, `discount_price_cents` |
| `sort_order` | enum | `asc` or `desc`. Default: `desc` for `created_at`, `asc` for everything else |

**Special case:** when `sort_by=discount_price_cents`, add `WHERE discount_price_cents IS NOT NULL` — only show products with an active discount.

## `total` must reflect filtered count
Counted with the same filters as the row query.

## Implementation
Single file: `services/api/app/routers/storefront/catalog.py` — extend `list_products`.

For the JSONB tags filter: build OR clauses with PostgreSQL JSONB `?` operator (per-tag): `Product.tags.op('?')(tag_value)`.

For sorting: validate `sort_by` against an allowlist; pick the column dynamically; apply order direction. For `discount_price_cents` add the NULL-exclusion to the where clause.

## Verification
The brief includes 3 curl tests — must pass:
1. Tag filter returns only matching products + correct total
2. Tag + price range returns the intersection
3. `sort_by=discount_price_cents` excludes NULL discount products

## Out of scope
- Changing the search `q` parameter behaviour
- Adding `tags[]` to the admin product list endpoint (different endpoint)

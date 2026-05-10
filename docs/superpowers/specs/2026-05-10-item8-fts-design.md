# Item 8 — Full-Text Product Search

**Date:** 2026-05-10
**Phase:** Stickerize onboarding (~1-2 days)

## Problem
Current product search uses `ILIKE '%foo%'` against name/sku in admin and storefront catalog endpoints. At 800+ products, ILIKE without indexes is acceptable but won't scale; more importantly, ILIKE does not match across description / tags / category names, and ranks poorly. Stickerize merchants want a customer searching "anime sticker" to surface products whose names + descriptions + categories + tags collectively match — ranked by relevance.

## Locked decisions (from brainstorm)
- Use **PostgreSQL `tsvector` + GIN index**.
- Trigger-populated column (no application-side maintenance).
- Both admin and storefront search upgrade.
- Search corpus: name + sku + description + tags + category names.

## Schema

### `products` (extend)
Add column:
| Column | Type | Notes |
|---|---|---|
| search_vector | TSVECTOR | nullable; populated by trigger |

Add GIN index `ix_products_search_vector` on `search_vector`.

### Trigger
A trigger function rebuilds `search_vector` on every INSERT or UPDATE to products. It also fires on UPDATE of `product_categories` rows (when a product's categories change, its vector should re-build).

The corpus weighting (PostgreSQL `setweight`):
- Weight A: `name` (most important)
- Weight B: `sku`
- Weight C: `tags` (joined to space-separated string), aggregated category names from joined `categories.name`
- Weight D: `description`, `short_description`

Use `to_tsvector('simple', ...)` (the `simple` config keeps every token, no stemming or stopwords — best for SKUs, brand names, and short product titles where stemming would hurt). If we later want English stemming, swap to `'english'` in the trigger and re-run a full update.

### Implementation strategy

A single PL/pgSQL function `products_refresh_search_vector(prod_id UUID)`:
1. Builds the vector from the product row + joined categories
2. UPDATEs `products.search_vector` for that product

Two triggers call into it:
- `tg_products_search_vector` — AFTER INSERT OR UPDATE OF (name, sku, description, short_description, tags) ON products
- `tg_product_categories_search_vector` — AFTER INSERT OR DELETE OR UPDATE ON product_categories (calls refresh for OLD/NEW.product_id)

Initial backfill in the migration: `UPDATE products SET search_vector = ...` for all existing rows using the same expression.

### Migration `20260529000001_product_search_vector.py`
1. `op.add_column("products", sa.Column("search_vector", postgresql.TSVECTOR, nullable=True))`
2. `op.execute(...)` to create the trigger function and triggers.
3. Backfill existing rows.
4. Create the GIN index `ix_products_search_vector`.

Downgrade: drop triggers + function, drop index, drop column.

## Backend changes

### Helper — `services/api/app/services/product_search.py` (new)
```python
def make_tsquery(raw: str) -> str:
    """Sanitize a free-text query into a tsquery expression.
    Splits on whitespace, drops empty, ANDs all tokens with prefix matching:
    'red sticker' → 'red:* & sticker:*'."""
```

Returns a string suitable for `to_tsquery('simple', ...)`. Strips characters that would break tsquery (`& | ! ( ) :`); keeps unicode letters/digits/dashes.

### Storefront `list_products` — `services/api/app/routers/storefront/catalog.py`
When `q` is set, replace the existing ILIKE clause with:
```python
ts = make_tsquery(q)
if ts:
    base_where.append(Product.search_vector.op("@@")(func.to_tsquery("simple", ts)))
```

When `sort_by` is unspecified AND `q` is provided, default sort to `ts_rank(search_vector, query) DESC` (existing default sort to `name asc` only when no `q`). To avoid breaking the existing sort logic, branch: if q-based search, ORDER BY `ts_rank` DESC; otherwise existing logic.

### Admin `admin_list_products` — `services/api/app/routers/admin_web.py`
Same upgrade. Falls back to ILIKE if FTS produces no matches? No — keep it simple: FTS is the only path when `q` is set. ILIKE removed.

### Admin transactions search at `admin_web.py:97-102`
This is product search inside transactions. Out of scope for this PR. Tracked separately if needed.

## Frontend
No frontend changes — search input behaviour is unchanged from the user's perspective. The query just routes to a better backend.

## Edge cases / risks
- **Empty `q` after sanitization:** if all tokens are stripped (e.g., user types `&&&`), `make_tsquery` returns "" — treat as "no search filter applied".
- **Rate of trigger fires:** category changes are infrequent in normal admin use; trigger overhead is negligible.
- **Bulk imports:** the trigger fires per row. For 800-row imports this adds ~milliseconds; acceptable. If needed later, the migration's backfill expression can be re-run after a bulk import that bypasses the trigger.
- **Multi-language:** `simple` config handles Unicode; sufficient for English + most European/Indian scripts. Stemming opt-in is a future enhancement.

## Files
| File | Status |
|---|---|
| `services/api/app/models/tables.py` | Add `search_vector` column to Product |
| `services/api/alembic/versions/20260529000001_product_search_vector.py` | NEW migration |
| `services/api/app/services/product_search.py` | NEW helper |
| `services/api/app/routers/storefront/catalog.py` | Replace ILIKE with FTS |
| `services/api/app/routers/admin_web.py` | Replace ILIKE with FTS |

## Out of scope
- Stemming / language config switching
- Synonym dictionaries
- Search analytics (logging queries)
- Replacing ILIKE in transaction search and other secondary search surfaces

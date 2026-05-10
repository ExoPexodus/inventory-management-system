# Item 7 — Quantity / Category-Based Discount Conditions

**Date:** 2026-05-10
**Phase:** Stickerize onboarding (~2-3 days)

## Problem
Current discounts only support: percentage / fixed amount / free shipping with optional `min_subtotal_cents`. There is no way to express:
- "Buy 5+ stickers, get 10% off" (cart-total quantity gate)
- "3+ of the same SKU, get 15% off that line" (per-line quantity gate)
- "10% off Anime category" (category-targeted scoping)
- "Spend more, save more" (tiered: 5+ → 10%, 10+ → 20%)

## Locked decisions (from brainstorm)
- **Quantity scope:** both per-line and cart-total supported — merchant picks one per discount
- **Tiered:** multi-tier supported
- **Category targeting:** both `category_id` (FK) and `tag` string — merchant picks per discount

## Schema

### `discounts` (extend)
Add columns:
| Column | Type | Default | Notes |
|---|---|---|---|
| condition_quantity_scope | String(16) | `"none"` | one of `none|per_line|cart_total` |
| condition_min_quantity | Integer | NULL | required when scope ≠ `none` |
| condition_category_id | UUID FK → categories(id) SET NULL | NULL | optional |
| condition_tag | String(64) | NULL | optional, lowercase |

A discount may have BOTH category_id AND tag conditions; both must match (AND).

### `discount_tiers` (new)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK | for RLS |
| discount_id | UUID FK → discounts(id) CASCADE | |
| threshold_quantity | Integer NOT NULL | minimum qualifying qty for this tier |
| value_bps | Integer | for percentage discounts |
| value_cents | Integer | for fixed-amount discounts |
| sort_order | Integer default 0 | tiebreaker for display |

Composite unique: `(discount_id, threshold_quantity)`. Index on `discount_id`.

When `discount_tiers` rows exist for a discount, the discount's own `value_bps` / `value_cents` are ignored — the qualifying tier (highest threshold ≤ qualifying_quantity) wins. If no tier matches, the discount does not apply.

### Migration `20260528000001_discount_conditions.py`
Chain from `20260527000001`. Adds the 4 columns to `discounts` (all nullable / defaulted), creates `discount_tiers` table. No data migration needed — existing discounts default to `condition_quantity_scope = "none"` and no tiers.

## Service changes — `app/services/discount_service.py`

`apply_discount(...)` gains a new parameter:
```python
@dataclass
class CartLine:
    product_id: UUID
    quantity: int
    unit_price_cents: int

def apply_discount(
    db, *,
    tenant_id, channel_id,
    cart_subtotal_cents,
    cart_lines: list[CartLine] | None = None,   # NEW
    code=None, customer_id=None,
) -> dict[str, Any]:
    ...
```

### Algorithm
1. Find discount as before.
2. Run window / min_subtotal / global limit / customer limit checks (unchanged).
3. **Filter cart_lines to qualifying lines** (skip if no condition set):
   - If `condition_category_id`: fetch product_ids that belong to the category (SELECT product_id FROM product_categories WHERE category_id = X). Filter cart_lines.
   - If `condition_tag`: fetch product_ids whose `Product.tags` JSONB contains the tag (`tags @> [tag]`). Filter cart_lines.
   - With both: AND (intersect product_ids).
4. **Compute qualifying quantity** based on `condition_quantity_scope`:
   - `none` → use total qty across qualifying lines (just for tier resolution; if no tiers and no min_quantity, no quantity gate)
   - `per_line` → max(line.quantity for line in qualifying)
   - `cart_total` → sum(line.quantity for line in qualifying)
5. **Quantity gate:** if `condition_min_quantity` set and qualifying_quantity < min → `DiscountNotEligibleError`.
6. **Compute qualifying subtotal:** sum(line.unit_price * line.quantity for line in qualifying). If no condition is set, qualifying_subtotal = cart_subtotal_cents.
7. **Resolve tier (if any):** highest tier with threshold_quantity ≤ qualifying_quantity. Use that tier's `value_bps` / `value_cents`. If tiers exist but none match → `DiscountNotEligibleError`.
8. **Compute amount:**
   - `percentage`: `round_half_up_cents(qualifying_subtotal * value_bps / 10000)`, capped at qualifying_subtotal
   - `fixed_amount`: `min(value_cents, qualifying_subtotal)`
   - `free_shipping`: 0 (no quantity/category interaction)
9. Cap final amount at `cart_subtotal_cents` (defensive).

### Error cases
- Tiers configured but `condition_quantity_scope == "none"` → 422 at admin save time.
- `condition_min_quantity` set but scope == "none" → 422 at admin save time.
- `free_shipping` + tiers → allow but warn (tiers are ignored for free shipping).

## Admin API — `app/routers/admin_discounts.py`

`POST /v1/admin/discounts` and `PATCH /v1/admin/discounts/{id}` accept the 4 new condition fields plus an optional `tiers: list[{threshold_quantity, value_bps?, value_cents?, sort_order?}]` array.

When `tiers` is provided: replace the entire set (delete existing + insert new) — no partial updates.

`GET /v1/admin/discounts/{id}` returns tiers in response.

Validation:
- `condition_category_id` must belong to tenant.
- `condition_tag` lowercased server-side.
- `condition_quantity_scope` ∈ `{"none","per_line","cart_total"}`.
- If tiers, all tiers within one discount must use the same field shape (all `value_bps` OR all `value_cents`, matching `discount.discount_type`).

## Storefront API
The cart cost calculation that calls `apply_discount` (`/v1/storefront/cart/{token}/discount` and checkout total recompute) must pass `cart_lines`. Find call sites and update.

## Admin UI — `apps/admin-web/src/app/(main)/discounts/page.tsx`

Discount form (in the create/edit dialog) gains:
- **Quantity scope** select: None / Per Line / Cart Total
- **Min quantity** number input (visible when scope ≠ None)
- **Category** select (lazy-loaded from `/api/ims/v1/admin/categories`)
- **Tag** text input
- **Tiers** repeating row: threshold qty + (percent OR fixed amount) + remove button + "Add tier" button

When discount_type changes, tiers' value field switches between bps/cents. The form posts the full tier array on save.

Discount list table: add a "Conditions" column that shows a compact summary like:
- "5+ in cart"
- "Anime category, 10+ per line"
- "3 tiers: 5/10/20+"

## Files
| File | Status |
|---|---|
| `services/api/app/models/tables.py` | Extend Discount, add DiscountTier |
| `services/api/app/models/__init__.py` | Export DiscountTier |
| `services/api/alembic/versions/20260528000001_discount_conditions.py` | NEW migration |
| `services/api/app/services/discount_service.py` | Algorithm rewrite per above |
| `services/api/app/routers/admin_discounts.py` | Accept new fields + tiers |
| `services/api/app/routers/storefront/*.py` | Pass cart_lines into apply_discount |
| `apps/admin-web/src/app/(main)/discounts/page.tsx` | Form + list updates |

## Out of scope
- Per-customer-group conditions (separate feature)
- BXGY (buy-X-get-Y) — different shape, will need its own design
- Stacking multiple conditioned discounts in one cart — current eval picks one matching discount, future enhancement

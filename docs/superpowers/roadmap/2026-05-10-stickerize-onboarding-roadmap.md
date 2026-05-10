# Stickerize Onboarding Roadmap

**Date:** 2026-05-10
**Mode:** Autonomous (decisions made at my discretion; stop only for blockers)
**Workflow:** Full brainstorm → spec → plan → implement per feature (matching prior autonomous run)

---

## Locked design decisions

### Item 6 — Admin product list pagination
- Default page size 50, max 200 (mirrors storefront)
- Tag filter included alongside existing q / status / category

### Item 5 — Hierarchical Category table
- **Categories per product:** many-to-many via `product_categories` join
- **Legacy `Product.category` string column:** migrate values into new categories, then **drop the column**
- **Parent category storefront behaviour:** show all products from descendants (Anime page lists Anime + Anime/Shounen + …)
- **Category metadata:** name, slug, parent_id, **description**, **sort_order** within siblings. **No image/banner field.**

### Item 7 — Quantity / category-based discount conditions
- **Quantity scope:** both per-line ("3+ of THIS SKU") and cart-total ("5+ items in cart") — merchant picks per discount
- **Tiered:** multi-tier supported ("5+ → 10%, 10+ → 20%")
- **Category targeting:** both category-id AND tag — merchant picks per discount

### Item 8 — Full-text product search
- **Include now** as future-proofing (originally deferred; now in scope)
- PostgreSQL `tsvector` + GIN index, populated via trigger
- Both admin and storefront search upgrade

---

## Execution order
1. **Item 6** — Admin pagination (quick warm-up, ~½ day)
2. **Item 5** — Category hierarchy (biggest, ~3-4 days)
3. **Item 7** — Discount conditions (depends on Item 5 for category targeting; ~2-3 days)
4. **Item 8** — Full-text search (~1-2 days)

---

## Per-feature workflow
1. Brief spec (autonomous decisions documented)
2. Plan
3. Implement via subagent-driven development
4. Backend tests + frontend rebuild + push
5. Continue to next feature

## Stop conditions
- Genuine blocker
- Otherwise continuous

## Progress
| # | Feature | Status |
|---|---|---|
| 6 | Admin product list pagination | ✅ shipped |
| 5 | Hierarchical Category table | ✅ shipped |
| 7 | Discount conditions (quantity + category/tag) | ✅ shipped |
| 8 | Full-text product search | ✅ shipped |
